from __future__ import annotations

import json
import csv
import io
import os
import re
import threading
import webbrowser
from uuid import uuid4
from collections.abc import Mapping
from contextlib import suppress
from datetime import datetime, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from app import settings
from app.configuration import missing_for, prerequisite_status
from app.app import ScraperApp, ScraperRunManager
from app.comparison import (
    build_comparison_payload,
    comparison_catalog_has_product,
    search_comparison_catalog_products,
)
from app.comparison_decisions import (
    get_decision,
    get_decision_history,
    reset_decision,
    save_decision,
    save_decisions_bulk,
    save_relationship,
)
from app.models import build_context
from app.plugintema_catalog import (
    CatalogFilters, build_catalog_rows, build_filtered_catalog_rows,
    encode_catalog_csv, read_all_products, categories_match_catalog_kind,
)
from app.operations.runtime import (
    get_job, get_preview, materialize as materialize_update_jobs, persist_job,
    save_plan, save_preview, get_plan, is_execution_eligible, enqueue_jobs,
    queue_snapshot, set_queue_status, next_queued_job, cancel_pending_queue,
    create_update_queue, select_update_queue, rename_update_queue, delete_update_queue,
    clear_update_queue,
    history_jobs, clear_update_history,
    update_queue_details,
)
from app.operations.update_logging import UpdateLogRegistry
from app.operations.models import JobState

_UPDATE_LOGS = UpdateLogRegistry()
_UPDATE_WORKERS: dict[str, threading.Thread] = {}
_UPDATE_JOB_LOCKS: dict[str, threading.Lock] = {}
_UPDATE_WORKERS_LOCK = threading.RLock()
_UPDATE_QUEUE_WORKER: threading.Thread | None = None
_WORDPRESS_MANUAL_WORKER: threading.Thread | None = None
_STORE_PRICE_LOCK = threading.RLock()
_STORE_PRICE_JOB: dict[str, Any] = {
    "job_id": "", "status": "idle", "phase": "", "completed": 0, "total": 0, "message": "",
}
_STORE_DESCRIPTION_LOCK = threading.RLock()
_STORE_DESCRIPTION_JOB: dict[str, Any] = {
    "job_id": "", "status": "idle", "page": 0, "examined": 0, "found": 0,
    "current_product": "", "message": "",
}


def _store_price_job_snapshot() -> dict[str, Any]:
    with _STORE_PRICE_LOCK:
        return dict(_STORE_PRICE_JOB)


def _start_store_price_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    from app.store_pricing import apply_store_prices, normalize_prices, read_store_price_reference_products

    if str(payload.get("confirmation", "") or "").strip() != "ALTERAR PRECOS":
        raise ValueError('Digite "ALTERAR PRECOS" para confirmar.')
    kinds = payload.get("kinds", [])
    if not isinstance(kinds, list) or not ({str(item) for item in kinds} & {"plugin", "theme"}):
        raise ValueError("Selecione Plugins e/ou Temas.")
    normalize_prices(payload)
    selected_kinds = tuple(dict.fromkeys(str(item) for item in kinds if str(item) in {"plugin", "theme"}))
    reference_products = read_store_price_reference_products(
        Path(settings.COMPARISON_IMPORTS_DIR), selected_kinds, limit_per_kind=None,
    )
    if not reference_products:
        raise ValueError("Nenhum produto foi encontrado no catálogo local. Atualize o catálogo de Plugins e Temas e tente novamente.")
    job_id = uuid4().hex
    with _STORE_PRICE_LOCK:
        if _STORE_PRICE_JOB.get("status") == "running":
            raise ValueError("Já existe uma alteração de preços em andamento.")
        _STORE_PRICE_JOB.update({
            "job_id": job_id, "status": "running", "phase": "reading", "completed": 0,
            "total": len(reference_products), "message": f"Lendo variações: 0 de {len(reference_products)}.",
            "errors": [],
        })

    def progress(phase: str, completed: int, total: int, current_product: str = "") -> None:
        label = "Lendo variações" if phase == "reading" else "Atualizando produtos"
        if phase == "updating" and current_product:
            message = f"Atualizando agora: {current_product}"
        elif phase == "reading" and current_product:
            message = f"Variações lidas: {current_product}"
        else:
            message = f"{label}: {completed} de {total}."
        with _STORE_PRICE_LOCK:
            _STORE_PRICE_JOB.update({
                "phase": phase, "completed": completed, "total": total,
                "current_product": current_product, "message": message,
            })

    def run() -> None:
        try:
            result = apply_store_prices(
                _build_store_woocommerce_client(), payload, progress=progress,
                products=reference_products,
            )
            with _STORE_PRICE_LOCK:
                _STORE_PRICE_JOB.update(result)
                _STORE_PRICE_JOB["status"] = "completed" if result.get("ok") else "error"
        except Exception as error:
            with _STORE_PRICE_LOCK:
                _STORE_PRICE_JOB.update({
                    "status": "error", "message": str(error), "error": str(error),
                })

    threading.Thread(target=run, name="store-price-update", daemon=True).start()
    return _store_price_job_snapshot()


def _store_description_job_snapshot() -> dict[str, Any]:
    with _STORE_DESCRIPTION_LOCK:
        return dict(_STORE_DESCRIPTION_JOB)


def _start_store_description_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    from app.store_pricing import products_without_short_description
    query = str(payload.get("query", "") or "").strip()
    job_id = uuid4().hex
    with _STORE_DESCRIPTION_LOCK:
        if _STORE_DESCRIPTION_JOB.get("status") == "running":
            raise ValueError("Já existe uma verificação de descrições em andamento.")
        _STORE_DESCRIPTION_JOB.update({
            "job_id": job_id, "status": "running", "page": 0, "examined": 0,
            "found": 0, "current_product": "", "query": query, "products": [],
            "message": "Iniciando varredura completa dos produtos publicados…",
        })

    def progress(page: int, examined: int, found: int, current_product: str) -> None:
        with _STORE_DESCRIPTION_LOCK:
            _STORE_DESCRIPTION_JOB.update({
                "page": page, "examined": examined, "found": found,
                "current_product": current_product,
                "message": f"Página {page}: {examined} produtos verificados; {found} sem breve descrição.",
            })

    def run() -> None:
        try:
            products = products_without_short_description(
                _build_store_woocommerce_client(), query, progress=progress,
            )
            with _STORE_DESCRIPTION_LOCK:
                _STORE_DESCRIPTION_JOB.update({
                    "status": "completed", "products": products, "found": len(products),
                    "message": f"Varredura concluída: {_STORE_DESCRIPTION_JOB.get('examined', 0)} produtos verificados.",
                })
        except Exception as error:
            with _STORE_DESCRIPTION_LOCK:
                _STORE_DESCRIPTION_JOB.update({
                    "status": "error", "message": str(error), "error": str(error),
                })

    threading.Thread(target=run, name="store-description-scan", daemon=True).start()
    return _store_description_job_snapshot()


def _run_update_queue() -> None:
    """Executa um job por vez; o estado persistido decide pausa e retomada."""
    while True:
        job = next_queued_job()
        if job is None:
            snapshot = queue_snapshot()
            if snapshot["status"] == "running" and not snapshot["queued"]:
                set_queue_status("stopped")
            return
        logger = _UPDATE_LOGS.for_job(job.job_id)
        try:
            preview, plan = get_preview(job.job_id), get_plan(job.job_id)
            if not is_execution_eligible(job, preview, plan):
                job.set_state(JobState.BLOCKED, "Pré-condições de execução da fila não atendidas")
                job.queue_position = 0
                job.execution_error = "Execução bloqueada: o job deixou de atender às pré-condições da fila."
                persist_job(job)
                continue
            job.attempts += 1
            logger.clear()
            executor = _build_controlled_update_executor(job, logger.log)
            executor.execute(job, plan, f"EXECUTAR {job.woo_product_id}")
        except Exception as error:
            if job.state == JobState.EXECUTING:
                job.set_state(JobState.ERROR, "Falha técnica durante execução sequencial")
            job.execution_error = logger.sanitize(error)
            logger.log(f"Falha na execução: {job.execution_error}")
        finally:
            job.queue_position = 0
            job.execution_logs = logger.to_list()
            persist_job(job)


def _start_update_queue_worker() -> bool:
    global _UPDATE_QUEUE_WORKER
    with _UPDATE_WORKERS_LOCK:
        if _UPDATE_QUEUE_WORKER and _UPDATE_QUEUE_WORKER.is_alive():
            return False
        set_queue_status("running")
        _UPDATE_QUEUE_WORKER = threading.Thread(
            target=_run_update_queue, name="update-queue", daemon=True
        )
        _UPDATE_QUEUE_WORKER.start()
        return True


def _start_wordpress_manual_worker_legacy(manager: Any) -> bool:
    """Busca no WordPress pedidos criados pelo botão Super Admin."""
    global _WORDPRESS_MANUAL_WORKER
    if os.getenv("SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    secret = os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET", "").strip()
    base_url = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    if not secret or not base_url:
        return False
    with _UPDATE_WORKERS_LOCK:
        if _WORDPRESS_MANUAL_WORKER and _WORDPRESS_MANUAL_WORKER.is_alive():
            return False

        def loop() -> None:
            from app.operations.execution_plan import build_execution_plan
            from app.wordpress_manual_update import (
                WordPressManualQueueClient, create_manual_job, manual_job_status, run_manual_job,
            )
            client = WordPressManualQueueClient(base_url, secret)
            while True:
                try:
                    requests = client.pending()
                    for request in requests:
                        request_id = str(request.get("request_id") or "")
                        product_id = int(request.get("product_id") or 0)
                        if not request_id or product_id <= 0:
                            continue
                        try:
                            client.report(request_id, status="processing", message="CrapScraper iniciou a verificação segura.")
                            job, response = create_manual_job(
                                _build_readonly_woocommerce_client(), product_id,
                                initiated_by=f"wordpress-super-admin #{request.get('requested_by', '')}",
                            )
                            if job is None:
                                client.report(request_id, status="up_to_date",
                                              previous_version=response.get("current_version", ""),
                                              message=response.get("message", "Nenhuma atualização encontrada."))
                                continue
                            logger = _UPDATE_LOGS.for_job(job.job_id)
                            logger.clear()
                            primary = _get_primary_app(manager)
                            if not response.get("reused"):
                                run_manual_job(
                                    job, preparation_factory=lambda: _build_update_preparation_service(primary, logger.log),
                                    plan_builder=build_execution_plan,
                                    executor_factory=lambda current: _build_controlled_update_executor(current, logger.log),
                                    logger=logger,
                                )
                            status = manual_job_status(job.job_id)
                            final_state = status["status"] if status["terminal"] else "processing"
                            if final_state not in {"processing", "completed", "error", "blocked", "rolled_back", "rollback_required"}:
                                final_state = "error"
                            client.report(request_id, status=final_state, job_id=job.job_id,
                                          source=status["source"], previous_version=status["previous_version"],
                                          new_version=status["new_version"],
                                          message=status["result"] or ("Atualização concluída." if final_state == "completed" else "Processando."))
                        except Exception as error:
                            with suppress(Exception):
                                client.report(request_id, status="error", message=str(error))
                except Exception as error:
                    from app.wordpress_manual_update import manual_monitor_log
                    manual_monitor_log(f"Falha no worker legado: {error}")
                threading.Event().wait(5)

        _WORDPRESS_MANUAL_WORKER = threading.Thread(
            target=loop, name="wordpress-manual-poller", daemon=True,
        )
        _WORDPRESS_MANUAL_WORKER.start()
        return True


def _start_wordpress_manual_worker(manager: Any) -> bool:
    """Worker observável que consome a fila REST e reutiliza o fluxo seguro local."""
    global _WORDPRESS_MANUAL_WORKER
    from app.wordpress_manual_update import manual_monitor_log, manual_monitor_update
    enabled = os.getenv("SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    secret = os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET", "").strip()
    base_url = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    if not enabled:
        manual_monitor_update(enabled=False, monitor_status="disabled", state="Monitor desativado")
        return False
    if not secret or not base_url:
        manual_monitor_update(enabled=False, monitor_status="error", state="Configuração incompleta",
                              error="URL ou segredo da fila WordPress não configurado.")
        return False
    with _UPDATE_WORKERS_LOCK:
        if _WORDPRESS_MANUAL_WORKER and _WORDPRESS_MANUAL_WORKER.is_alive():
            return False

        def loop() -> None:
            from app.operations.execution_plan import build_execution_plan
            from app.operations.update_logging import UpdateLogger
            from app.wordpress_manual_update import WordPressManualQueueClient, create_manual_job, manual_job_status, run_manual_job
            client = WordPressManualQueueClient(base_url, secret)
            manual_monitor_update(enabled=True, monitor_status="monitoring", state="Monitorando WordPress", error="")
            manual_monitor_log("Monitor WordPress iniciado; consulta a cada 5s.")
            while True:
                try:
                    now = datetime.now().astimezone()
                    manual_monitor_update(last_check=now.isoformat(), next_check=(now + timedelta(seconds=5)).isoformat(),
                                          monitor_status="monitoring", state="Consultando WordPress", error="")
                    requests = client.pending()
                    if not requests:
                        manual_monitor_update(state="Monitorando WordPress")
                    for request in requests:
                        request_id = str(request.get("request_id") or "")
                        product_id = int(request.get("product_id") or 0)
                        if not request_id or product_id <= 0:
                            manual_monitor_log("Pedido inválido ignorado: identificador ou Woo ID ausente.")
                            continue
                        try:
                            manual_monitor_update(monitor_status="processing", state="Pedido recebido", request_id=request_id,
                                                  product_id=product_id, product="", source="", current_version="", new_version="")
                            manual_monitor_log(f"Pedido recebido do WordPress; Woo ID: {product_id}")
                            client.report(request_id, status="locating", message="Pedido recebido pelo PC. Localizando correspondências.")
                            primary = _get_primary_app(manager)

                            def inspect(row: Mapping[str, Any]) -> Any:
                                from app.integrations.plugintheme_download import PluginThemeDownloader, SourceDownloader
                                from app.integrations.ultrapack_download import UltrapackDownloader
                                from app.integrations.ultrapack_session import get_authenticated_plugintheme_session, get_authenticated_ultrapack_session
                                url = str(row.get("source_product_url") or "")
                                downloader = SourceDownloader(UltrapackDownloader(getattr(primary, "ultrapack_http_session", None)),
                                                              PluginThemeDownloader(getattr(primary, "plugintheme_http_session", None)))
                                session = (get_authenticated_plugintheme_session(primary, url) if SourceDownloader.is_plugintheme(url)
                                           else get_authenticated_ultrapack_session(primary, url))
                                downloader.session = session.session
                                return downloader.inspect_product(url)

                            client.report(request_id, status="comparing", message="Comparando versões em PluginTheme e UltraPackV2.")
                            manual_monitor_update(state="Comparando versões")
                            job, response = create_manual_job(
                                _build_readonly_woocommerce_client(), product_id,
                                initiated_by=f"wordpress-super-admin #{request.get('requested_by', '')}",
                                inspector=inspect, log=manual_monitor_log,
                            )
                            if job is None:
                                result_state = str(response.get("status") or "no_match")
                                manual_monitor_update(monitor_status="monitoring", state=response.get("message", result_state),
                                                      product=response.get("product_name", ""),
                                                      current_version=response.get("current_version", ""))
                                client.report(request_id, status=result_state,
                                              previous_version=response.get("current_version", ""),
                                              message=response.get("message", "Nenhuma atualização encontrada."))
                                continue
                            logger = _UPDATE_LOGS.for_job(job.job_id)
                            logger.clear()
                            manual_monitor_update(state="Preparando atualização", product=job.name, source=job.source_name,
                                                  current_version=job.plugintema_version, new_version=job.approved_source_version)
                            client.report(request_id, status="preparing", job_id=job.job_id, source=job.source_name,
                                          previous_version=job.plugintema_version, new_version=job.approved_source_version,
                                          message="Atualização encontrada. Preparando o fluxo seguro.")
                            if not response.get("reused"):
                                def report_phase(phase: str, message: str) -> None:
                                    manual_monitor_update(state=message)
                                    manual_monitor_log(message)
                                    client.report(request_id, status=phase, job_id=job.job_id, source=job.source_name,
                                                  previous_version=job.plugintema_version,
                                                  new_version=job.approved_source_version, message=message)
                                run_manual_job(job, preparation_factory=lambda: _build_update_preparation_service(primary, logger.log),
                                               plan_builder=build_execution_plan,
                                               executor_factory=lambda current: _build_controlled_update_executor(current, logger.log),
                                               logger=logger, state_callback=report_phase)
                            status = manual_job_status(job.job_id)
                            final_state = status["status"] if status["terminal"] else "processing"
                            if final_state not in {"processing", "completed", "error", "blocked", "rolled_back", "rollback_required"}:
                                final_state = "error"
                            client.report(request_id, status=final_state, job_id=job.job_id, source=status["source"],
                                          previous_version=status["previous_version"], new_version=status["new_version"],
                                          message=status["result"] or ("Atualização concluída." if final_state == "completed" else "Processando."))
                            for entry in status.get("logs", []):
                                manual_monitor_log(entry)
                            manual_monitor_update(monitor_status="monitoring", state="Concluído" if final_state == "completed" else final_state,
                                                  source=status["source"], current_version=status["previous_version"], new_version=status["new_version"])
                        except Exception as error:
                            safe = UpdateLogger.sanitize(error)
                            manual_monitor_log(f"Erro no pedido {request_id}: {safe}")
                            manual_monitor_update(monitor_status="error", state="Erro", error=safe)
                            with suppress(Exception):
                                client.report(request_id, status="error", message=safe)
                except Exception as error:
                    safe = UpdateLogger.sanitize(error)
                    manual_monitor_log(f"Falha REST WordPress: {safe}")
                    manual_monitor_update(monitor_status="error", state="Erro de conexão/autenticação", error=safe)
                threading.Event().wait(5)

        _WORDPRESS_MANUAL_WORKER = threading.Thread(target=loop, name="wordpress-manual-poller", daemon=True)
        _WORDPRESS_MANUAL_WORKER.start()
        return True


def _build_controlled_update_executor(job: Any, logger: Any) -> Any:
    from app.integrations.ssh_storage import ReadOnlySSHStorage, ControlledStagingSSHStorage
    from app.integrations.ssh_helper import RestrictedSSHHelperClient
    from app.integrations.woocommerce import WooCommerceClient
    from app.integrations.woocommerce_version import WooCommerceVersionWriter, controlled_product_patch
    from app.operations.real_executor import ControlledUpdateExecutor
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    key = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    secret = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    woo = WooCommerceClient(base, key, secret)
    storage = ReadOnlySSHStorage.from_env().connect()
    file_name = PurePosixPath(get_plan(job.job_id)["current_zip"]["remote_path"]).name
    staging = ControlledStagingSSHStorage.from_env(
        file_name=file_name, job_id=job.job_id, write_authorized=True
    ).connect()
    helper = RestrictedSSHHelperClient(storage._client, execution_enabled=True)
    writer = WooCommerceVersionWriter(
        woo, write_enabled=True, patch=lambda product_id, payload:
        controlled_product_patch(woo, product_id, payload)
    )
    return ControlledUpdateExecutor(woo, storage, staging, helper, writer,
                                    enabled=settings.UPDATE_EXECUTION_ENABLED, logger=logger)


def _build_update_preparation_service(app: Any, logger: Any = None) -> Any:
    """Monta integrações somente-leitura e escolhe a fonte pelo domínio do job."""
    from app.integrations.ssh_storage import ReadOnlySSHStorage
    from app.integrations.ultrapack_download import UltrapackDownloader
    from app.integrations.plugintheme_download import PluginThemeDownloader, SourceDownloader
    from app.integrations.woocommerce import WooCommerceClient
    from app.operations.preparation import UpdatePreparationService
    from app.integrations.ultrapack_session import (
        get_authenticated_plugintheme_session, get_authenticated_ultrapack_session,
    )
    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    username = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    password = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    if not all((base, username, password)):
        raise RuntimeError(
            "Configure SCRAPER_WP_BASE_URL/SCRAPER_WC_CONSUMER_KEY/"
            "SCRAPER_WC_CONSUMER_SECRET para preparar o job."
        )
    def session_provider(job):
        if SourceDownloader.is_plugintheme(job.ultrapack_url):
            return get_authenticated_plugintheme_session(app, job.ultrapack_url).session
        return get_authenticated_ultrapack_session(app, job.ultrapack_url).session
    storage = ReadOnlySSHStorage.from_env().connect()
    staging = settings.DATA_DIR / "staging" / "updates"

    def helper_probe() -> bool:
        client = getattr(storage, "_client", None)
        if client is None:
            return False
        _stdin, stdout, _stderr = client.exec_command(
            "test -x /usr/local/sbin/crapscraper-zip-helper", timeout=15
        )
        return stdout.channel.recv_exit_status() == 0

    return UpdatePreparationService(
        WooCommerceClient(base, username, password), storage,
        SourceDownloader(
            UltrapackDownloader(getattr(app, "ultrapack_http_session", None)),
            PluginThemeDownloader(getattr(app, "plugintheme_http_session", None)),
        ), staging_root=staging,
        helper_probe=helper_probe, session_provider=session_provider, logger=logger,
    )


def _build_readonly_woocommerce_client() -> Any:
    from app.integrations.woocommerce import WooCommerceClient

    base = os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    key = os.getenv("SCRAPER_WC_CONSUMER_KEY", "").strip()
    secret = os.getenv("SCRAPER_WC_CONSUMER_SECRET", "").strip()
    if not all((base, key, secret)):
        raise RuntimeError("Configuração WooCommerce incompleta para exportar o catálogo.")
    return WooCommerceClient(base, key, secret)


def _build_store_woocommerce_client() -> Any:
    """Cliente de Loja com falha rápida para nunca prender a interface."""
    client = _build_readonly_woocommerce_client()
    return type(client)(
        client.base_url,
        client.username,
        client.password,
        timeout=12.0,
        retries=0,
    )


def _update_prerequisites(*, check_ssh_connection: bool = False, app: Any = None) -> dict[str, Any]:
    """Diagnostico sem segredos; rede SSH somente quando explicitamente solicitada."""
    result = prerequisite_status()
    if app is not None:
        from app.integrations.plugintheme_manual_session import plugintheme_cookie_diagnostic
        result["plugintheme_cookies"] = plugintheme_cookie_diagnostic(app)
    if check_ssh_connection and result["ssh_read"]["ok"]:
        from app.integrations.ssh_storage import ReadOnlySSHStorage
        storage = ReadOnlySSHStorage.from_env()
        try:
            storage.connect()
            directory = storage.identify_directory()
            result["ssh_connection"] = {"ok": True, "status": "OK"}
            result["ssh_directory"] = {
                "ok": bool(directory.get("directory")), "status": "OK" if directory.get("directory") else "INACESSIVEL"
            }
        except Exception:
            result["ssh_connection"] = {"ok": False, "status": "FALHA"}
            result["ssh_directory"] = {"ok": False, "status": "INACESSIVEL"}
        finally:
            storage.close()
    return result


def _prepare_ultrapack_session_only(app: Any, job: Any) -> dict[str, Any]:
    """Homologacao: autentica e valida somente a pagina fonte."""
    from app.integrations.ultrapack_session import get_authenticated_ultrapack_session

    source_url = str(getattr(job, "ultrapack_url", "") or "").strip()
    status = get_authenticated_ultrapack_session(app, source_url)
    return {
        "job_id": str(getattr(job, "job_id", "") or ""),
        "state": "authenticated",
        "authenticated": status.authenticated,
        "ultrapack_session": "OK" if status.authenticated else "FALHA",
        "session_reused": status.reused,
        "source_product_url": source_url,
        "current_url": status.current_url,
        "download_called": False,
        "message": "Sessao Ultrapack pronta; download bloqueado nesta homologacao.",
    }
from app.storage import (
    build_context_paths,
    build_slots_public_list,
    get_active_slot_name,
    get_slot_dir,
    list_slots,
    load_catalog_items,
    load_status_text,
    path_exists,
    read_text,
)


try:
    from app.core.exceptions import build_error_payload
except Exception:  # pragma: no cover
    def build_error_payload(
        error: Exception,
        *,
        fallback_message: str = "Erro interno.",
        fallback_code: str = "internal_error",
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "error": fallback_code,
            "message": str(error) or fallback_message,
            "details": {},
        }


INLINE_FALLBACK_CSS = r"""
:root{
  --bg:#050505;
  --panel:#0d0d0d;
  --panel-2:#141414;
  --line:#202020;
  --text:#f5f5f5;
  --muted:#a3a3a3;
  --accent:#7c3aed;
  --accent-2:#e11d48;
  --success:#10b981;
  --warning:#f59e0b;
  --danger:#ef4444;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);font-family:Arial,Helvetica,sans-serif}
body{padding:20px}
.wrap{max-width:1400px;margin:0 auto}
.page-head{display:flex;flex-direction:column;gap:10px;margin-bottom:18px}
h1{margin:0;font-size:30px;line-height:1.15}
.subtitle{color:var(--muted);font-size:14px;line-height:1.5}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:16px}
.section-title{margin:0 0 14px 0;font-size:18px;font-weight:700}
.row{display:flex;gap:10px;flex-wrap:wrap}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:14px}
.context-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px}
.context-box{background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:12px}
.context-label{font-size:12px;color:var(--muted);margin-bottom:6px}
.context-value{font-size:14px;font-weight:700;word-break:break-word}
.field{display:flex;flex-direction:column;gap:8px}
.field label{font-size:13px;font-weight:700}
input,select,textarea,button{font:inherit}
input,select,textarea{width:100%;background:#080808;border:1px solid var(--line);color:var(--text);border-radius:12px;padding:12px}
textarea{min-height:110px;resize:vertical}
button{border:0;border-radius:12px;padding:12px 16px;cursor:pointer;font-weight:700}
button:disabled{opacity:.55;cursor:not-allowed}
.btn-primary{background:var(--accent);color:#fff}
.btn-secondary{background:#27272a;color:#fff}
.btn-success{background:var(--success);color:#001b12}
.btn-danger{background:var(--danger);color:#fff}
.btn-warning{background:var(--warning);color:#221400}
.quick-grid{display:grid;grid-template-columns:repeat(4,minmax(220px,1fr));gap:10px}
.quick-grid button{width:100%;text-align:left}
.checkbox-list{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px;max-height:360px;overflow:auto;padding-right:4px}
.checkbox-item{display:flex;align-items:flex-start;gap:10px;padding:10px;border:1px solid var(--line);border-radius:12px;background:#080808}
.checkbox-item input{width:auto;margin-top:2px}
.checkbox-text{display:flex;flex-direction:column;gap:2px;min-width:0}
.checkbox-meta{font-size:12px;color:var(--muted);word-break:break-word}
.badge{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:#080808;border:1px solid var(--line);font-size:12px;color:#ddd}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:12px}
.kpi{background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:12px}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:22px;font-weight:700;margin-top:6px}
.small{font-size:13px;color:var(--muted);line-height:1.5}
pre{white-space:pre-wrap;word-break:break-word;background:#000;color:#f8fafc;padding:14px;border-radius:12px;height:520px;overflow:auto;border:1px solid var(--line);margin:0;font-family:Consolas,Monaco,monospace;font-size:14px}
.notice{padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:var(--panel-2);color:#d4d4d8;font-size:13px;line-height:1.5}
.hidden{display:none!important}
@media (max-width:1100px){
  .form-grid,.quick-grid,.context-grid,.kpi-grid,.checkbox-list{grid-template-columns:1fr 1fr}
}
@media (max-width:700px){
  body{padding:14px}
  .form-grid,.quick-grid,.context-grid,.kpi-grid,.checkbox-list{grid-template-columns:1fr}
}
"""

INLINE_FALLBACK_JS = r"""
(function(){
  const byId = (id) => document.getElementById(id);
  const bootNode = byId('monitor-boot-data');
  let BOOT = {};
  try { BOOT = JSON.parse(bootNode?.textContent || '{}'); } catch (_e) {}
  const ENDPOINTS = Object.assign({
    boot: '/boot',
    state: '/state',
    logsFull: '/logs_full',
    context: '/context',
    config: '/config',
    start: '/start',
    continue: '/continue',
    pause: '/pause',
    resume: '/resume',
    stop: '/stop',
    slotCreate: '/slot/create',
    slotSwitch: '/slot/switch',
    slotDefault: '/slot/default',
    slotDelete: '/slot/delete',
    runPrefix: '/run/',
  }, BOOT.endpoints || {});
  const POLL_INTERVAL_MS = Number(BOOT.poll_interval_ms || 1200);

  function esc(text){
    return String(text ?? '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#039;');
  }

  function setText(id, value, fallback='-'){
    const node = byId(id);
    if(node) node.textContent = String(value ?? fallback);
  }

  function readConfig(){
    return {
      verify_mode: String(byId('verify_mode')?.value || 'complete'),
      scope_mode: String(byId('scope_mode')?.value || 'all'),
      scope_start: String(byId('scope_start')?.value || '1'),
      scope_end: String(byId('scope_end')?.value || '0'),
      scope_match_text: String(byId('scope_match_text')?.value || ''),
      save_every_items: String(byId('save_every_items')?.value || '10'),
      save_every_minutes: String(byId('save_every_minutes')?.value || '10'),
      selected_categories: Array.from(document.querySelectorAll('.scope-category-checkbox:checked')).map(node => String(node.value || '')),
    };
  }

  function writeConfig(data){
    if(byId('verify_mode')) byId('verify_mode').value = String(data?.verify_mode ?? 'complete');
    if(byId('scope_mode')) byId('scope_mode').value = String(data?.scope_mode ?? 'all');
    if(byId('scope_start')) byId('scope_start').value = String(data?.scope_start ?? '1');
    if(byId('scope_end')) byId('scope_end').value = String(data?.scope_end ?? '0');
    if(byId('scope_match_text')) byId('scope_match_text').value = String(data?.scope_match_text ?? '');
    if(byId('save_every_items')) byId('save_every_items').value = String(data?.save_every_items ?? '10');
    if(byId('save_every_minutes')) byId('save_every_minutes').value = String(data?.save_every_minutes ?? '10');
    toggleScopeFields();
  }

  function toggleScopeFields(){
    const mode = String(byId('scope_mode')?.value || 'all');
    if(byId('field_range_start')) byId('field_range_start').style.display = mode === 'range' ? 'flex' : 'none';
    if(byId('field_range_end')) byId('field_range_end').style.display = mode === 'range' ? 'flex' : 'none';
    if(byId('field_match')) byId('field_match').style.display = mode === 'match' ? 'flex' : 'none';
    if(byId('field_selected_categories')) byId('field_selected_categories').style.display = mode === 'selected' ? 'flex' : 'none';
  }
  window.toggleScopeFields = toggleScopeFields;

  async function getJson(url){
    const res = await fetch(url, {cache:'no-store'});
    return await res.json();
  }

  async function postJson(url, payload){
    const res = await fetch(url, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload || {})
    });
    return await res.json();
  }

  function renderSlots(data){
    const slots = Array.isArray(data?.slots) ? data.slots : [];
    const select = byId('slot_select');
    if(select){
      const currentValue = String(data?.current_slot || data?.slot_name || '');
      select.innerHTML = slots.map(slot => {
        const marker = slot.is_default ? ' ⭐' : '';
        return `<option value="${esc(slot.name)}">${esc(String(slot.name || '') + marker)}</option>`;
      }).join('');
      if(currentValue) select.value = currentValue;
      select.disabled = !!data?.running;
    }
    if(byId('new_slot_name')) byId('new_slot_name').disabled = !!data?.running;
    if(byId('slot_delete_btn')) byId('slot_delete_btn').disabled = !!data?.running || String(data?.current_slot || '') === String(data?.default_slot || '');
    if(byId('slot_default_btn')){
      const isDefault = String(data?.current_slot || '') === String(data?.default_slot || '');
      byId('slot_default_btn').disabled = !!data?.running || isDefault;
      byId('slot_default_btn').textContent = isDefault ? '⭐ Default atual' : '⭐ Default';
    }
    setText('slot_current_label', data?.current_slot || data?.slot_name || '-');
    setText('slot_default_label', data?.default_slot || '-');
  }

  function renderCategories(data){
    const categories = Array.isArray(data?.available_categories) ? data.available_categories : [];
    const selected = new Set(Array.isArray(data?.selected_categories) ? data.selected_categories.map(String) : []);
    setText('available_categories_count', String(categories.length), '0');
    setText('selected_categories_count', String(selected.size) + ' selecionadas', '0 selecionadas');
    const wrap = byId('selected_categories_list');
    if(!wrap) return;
    if(!categories.length){
      wrap.innerHTML = '<div class="badge">Nenhuma categoria disponível ainda.</div>';
      return;
    }
    wrap.innerHTML = categories.map((cat, index) => {
      const url = String(cat.url || cat.categoria_url || '');
      const nome = String(cat.nome || cat.categoria_nome || url || '-');
      const total = cat.total ?? cat.total_esperado ?? 0;
      const checked = selected.has(url) ? 'checked' : '';
      return `
        <label class="checkbox-item">
          <input type="checkbox" class="scope-category-checkbox" value="${esc(url)}" ${checked}>
          <span class="checkbox-text">
            <span>${esc(String(index + 1) + '. ' + nome)}</span>
            <span class="checkbox-meta">${esc(String(total))} itens • ${esc(url)}</span>
          </span>
        </label>
      `;
    }).join('');
  }

  function renderKpis(data){
    setText('status_text', data?.status || 'Pronto');
    setText('summary_text', data?.summary || '-');
    setText('current_phase_text', data?.current_phase || '-');
    setText('current_category_text', data?.current_category || '-');
    setText('current_item_text', data?.current_item || '-');
    setText('timer_text', data?.timer_text || '0:00:00');
    setText('saved_count_text', data?.saved_count ?? 0, '0');
    setText('pending_count_text', data?.pending_count ?? 0, '0');
    setText('queue_detected_count_text', data?.queue_detected_count ?? 0, '0');
    setText('new_items_added_text', data?.new_items_added ?? 0, '0');
    setText('items_updated_text', data?.items_updated ?? 0, '0');
    setText('items_unchanged_text', data?.items_unchanged ?? 0, '0');
    setText('new_links_detected_text', data?.new_links_detected ?? 0, '0');
    setText('existing_links_detected_text', data?.existing_links_detected ?? 0, '0');
    setText('reused_categories_text', data?.reused_categories ?? 0, '0');
    setText('refetched_categories_text', data?.refetched_categories ?? 0, '0');
    setText('resume_queue_text', `${data?.resume_queue_index ?? 0}/${data?.resume_queue_total ?? 0}`);
    setText('updated_at_text', data?.updated_at || '-');
    setText('run_started_at_text', data?.run_started_at || '-');
    setText('run_finished_at_text', data?.run_finished_at || '-');
    setText('ctx_site', data?.site_key || '-');
    setText('ctx_item_type', data?.item_type_key || '-');
    setText('ctx_account', data?.account_key || '-');
    setText('ctx_slot', data?.current_slot || data?.slot_name || '-');

    const running = !!data?.running;
    const paused = !!data?.paused;
    if(byId('run_primary_btn')) byId('run_primary_btn').disabled = running;
    if(byId('run_categories_btn')) byId('run_categories_btn').disabled = running;
    if(byId('run_links_btn')) byId('run_links_btn').disabled = running;
    if(byId('run_review_btn')) byId('run_review_btn').disabled = running;
    if(byId('run_selected_btn')) byId('run_selected_btn').disabled = running;
    if(byId('continue_btn')) byId('continue_btn').disabled = running || !data?.can_continue;
    if(byId('pause_btn')) byId('pause_btn').disabled = !running || paused;
    if(byId('resume_btn')) byId('resume_btn').disabled = !running || !paused;
    if(byId('stop_btn')) byId('stop_btn').disabled = !running;
  }

  function renderLogs(logs){
    const el = byId('logs');
    if(!el) return;
    const text = Array.isArray(logs) ? logs.join('\n') : String(logs || '');
    const shouldStickBottom = (el.scrollTop + el.clientHeight >= el.scrollHeight - 50);
    el.textContent = text;
    if(shouldStickBottom) el.scrollTop = el.scrollHeight;
  }

  async function loadState(){
    try{
      const payload = await getJson(ENDPOINTS.state);
      const data = payload?.data || {};
      renderKpis(data);
      renderSlots(data);
      renderCategories(data);
      renderLogs(payload?.logs || []);
    }catch(_e){}
  }
  window.loadState = loadState;

  async function saveConfig(){
    const result = await postJson(ENDPOINTS.config, readConfig());
    alert(result.message || (result.ok ? 'Configuração salva.' : 'Falha ao salvar.'));
    await loadState();
    byId('config_modal')?.classList.add('hidden');
  }
  window.saveConfig = saveConfig;

  async function runPrimary(){ const r = await postJson(ENDPOINTS.start, {}); alert(r.message || 'OK'); await loadState(); }
  window.runPrimary = runPrimary;



  async function runMode(mode){ const r = await postJson(ENDPOINTS.runPrefix + mode, {}); alert(r.message || 'OK'); await loadState(); }
  window.runMode = runMode;

  async function continueRun(){ const r = await postJson(ENDPOINTS.continue, {}); alert(r.message || 'OK'); await loadState(); }
  window.continueRun = continueRun;

  async function postAction(key){
    const map = {pause:ENDPOINTS.pause,resume:ENDPOINTS.resume,stop:ENDPOINTS.stop};
    const url = map[key];
    if(!url) return;
    const r = await postJson(url, {});
    alert(r.message || 'OK');
    await loadState();
  }
  window.postAction = postAction;

  async function createSlot(){
    const slotName = String(byId('new_slot_name')?.value || '').trim();
    if(!slotName){ alert('Digite um nome para o slot.'); return; }
    const r = await postJson(ENDPOINTS.slotCreate, {slot_name: slotName});
    alert(r.message || 'OK');
    if(byId('new_slot_name')) byId('new_slot_name').value = '';
    await loadState();
  }
  window.createSlot = createSlot;

  async function switchSlot(){
    const slotName = String(byId('slot_select')?.value || '');
    if(!slotName) return;
    const r = await postJson(ENDPOINTS.slotSwitch, {slot_name: slotName});
    alert(r.message || 'OK');
    await loadState();
  }
  window.switchSlot = switchSlot;

  async function setDefaultSlotToggle(){
    const slotName = String(byId('slot_select')?.value || '');
    if(!slotName) return;
    const r = await postJson(ENDPOINTS.slotDefault, {slot_name: slotName});
    alert(r.message || 'OK');
    await loadState();
  }
  window.setDefaultSlotToggle = setDefaultSlotToggle;

  async function deleteCurrentSlot(){
    const slotName = String(byId('slot_select')?.value || '');
    if(!slotName) return;
    if(!confirm(`Deseja apagar o slot "${slotName}"?`)) return;
    const r = await postJson(ENDPOINTS.slotDelete, {slot_name: slotName});
    alert(r.message || 'OK');
    await loadState();
  }
  window.deleteCurrentSlot = deleteCurrentSlot;

  async function copyFullLog(){
    try{
      const payload = await getJson(ENDPOINTS.logsFull);
      const text = String(payload?.text || '');
      if(!text.trim()){ alert('O log está vazio.'); return; }
      await navigator.clipboard.writeText(text);
      alert('Log completo copiado.');
    }catch(_e){
      alert('Não foi possível copiar o log.');
    }
  }
  window.copyFullLog = copyFullLog;

  document.addEventListener('DOMContentLoaded', () => {
    writeConfig(BOOT.run_options || BOOT.initial_state?.data || {});
    toggleScopeFields();
    loadState();
    setInterval(loadState, POLL_INTERVAL_MS);
  });
})();
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  __STYLES_BLOCK__
</head>
<body>
  <div class="wrap">
       <div class="page-head">
      <div class="page-brand">
        <img
          class="page-brand-mascot"
          src="/mascote.webp"
          alt="Mascote CrapScraper"
        >
        <div class="page-brand-content">
          <div class="page-brand-title-row"><h1>__HEADER_TITLE__</h1><img class="page-brand-title-image" src="/emoji.webp" alt="" onerror="this.hidden=true"></div>
          <div class="subtitle">Coletar • Comparar • Atualizar • Adicionar • Loja</div>
        </div>
      </div>
    </div>

    <div class="tabs-nav main-tabs-nav" role="tablist" aria-label="Seções principais">
      <button type="button" class="tab-btn is-active" role="tab" aria-selected="true" aria-controls="tab_panel_principal" data-tab-target="principal" id="tab_btn_principal">Coletar</button>
      <button type="button"
        class="tab-btn"
        role="tab"
        aria-selected="false"
        aria-controls="tab_panel_comparacao"
        data-tab-target="comparacao"
        id="tab_btn_comparacao">
  Comparar
</button>

<button type="button"
        class="tab-btn"
        role="tab"
        aria-selected="false"
        aria-controls="tab_panel_atualizacoes"
        data-tab-target="atualizacoes"
        id="tab_btn_atualizacoes">
  Atualizar
</button>

<button type="button"
        class="tab-btn"
        role="tab"
        aria-selected="false"
        aria-controls="tab_panel_adicoes"
        data-tab-target="adicoes"
        id="tab_btn_adicoes">
  Adicionar
</button>
<span class="main-tabs-spacer" aria-hidden="true"></span>
<button type="button"
        class="tab-btn tab-btn-store"
        role="tab"
        aria-selected="false"
        aria-controls="tab_panel_loja"
        data-tab-target="loja"
        id="tab_btn_loja">
  Loja
</button>
    </div>

    <div class="page-head-sticky">
      <div class="page-head-badges">
        <div class="row page-head-main">
          <span class="badge head-status-badge is-idle" id="head_status_badge">
            <span class="head-status-icon" aria-hidden="true">⚪</span>
            <span class="head-status-label">Parado</span>
          </span>

          <span class="badge" id="head_slot_badge">Catálogo: __SLOT_NAME__</span>
          <span class="badge" id="head_site_badge">Site: __SITE_LABEL__</span>
          <span class="badge" id="head_item_type_badge">Tipo: __ITEM_TYPE_LABEL__</span>
          <span class="badge" id="head_account_badge">Conta: __ACCOUNT_LABEL__</span>
        </div>

        <div class="page-head-runs hidden" id="head_runs_switcher_wrap">
          <div class="small" id="head_runs_switcher_label">Outras execuções disponíveis</div>
          <div class="row page-head-runs-list" id="head_runs_switcher_list"></div>
        </div>
      </div>
    </div>

<section class="tab-panel" id="tab_panel_principal">
      <div class="collection-operations-group" id="collection_operations_group">
        <div id="runs_section_wrap"></div>
      </div>

      <div class="card" id="catalog_management_card">
        <div class="row catalog-management-head">
          <div><div class="section-title">Catálogos</div><div class="small">Gerenciamento diário dos catálogos coletados.</div></div>
          <button class="btn-secondary catalog-management-button" type="button" id="open_catalogos_modal_btn">Gerenciar Cat&aacute;logos</button>
        </div>
        <div class="form-grid">
          <div class="field">
            <label for="slot_select">Carregar catálogo existente</label>
            <div class="row">
              <select id="slot_select"></select>
              <button class="btn-success" onclick="switchSlot()">📂 Carregar</button>
              <button class="btn-secondary" id="slot_default_btn" onclick="setDefaultSlotToggle()">⭐ Default</button>
              <button class="btn-warning" id="slot_clear_btn" onclick="clearCurrentSlot()">🧹 Limpar</button>
              <button class="btn-danger" id="slot_delete_btn" onclick="deleteCurrentSlot()">🗑️ Apagar</button>
            </div>
          </div>
          <div class="field">
            <label for="new_slot_name">Criar novo catálogo</label>
            <div class="row">
              <input id="new_slot_name" type="text" placeholder="Ex.: yith, importacao-abril, testes">
              <button class="btn-success" onclick="createSlot()">Criar</button>
            </div>
          </div>
          <div class="field">
            <label>Resumo do catálogo</label>
            <div class="small">
              <span>Catálogo atual: <strong id="slot_current_label">-</strong></span>
              <span class="catalog-summary-separator">Catálogo default: <strong id="slot_default_label">-</strong></span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">Contexto</div>
        <div class="form-grid">
          <div class="field">
            <label for="site_key">Site</label>
            <select id="site_key"></select>
          </div>
          <div class="field">
            <label for="item_type_key">Tipo de item</label>
            <select id="item_type_key"></select>
          </div>
          <div class="field">
            <label for="account_key">Conta</label>
            <select id="account_key"></select>
          </div>
          <div class="field">
            <label>Ações de contexto</label>
            <div class="row">
              <button class="btn-success" id="apply_context_btn" onclick="applyContext()">Aplicar contexto</button>
              <button class="btn-secondary" id="refresh_context_btn" onclick="loadState()">Recarregar contexto</button>
            </div>
          </div>
        </div>
      </div>

      <div class="collect-config-launch"><button class="btn-secondary catalog-management-button" type="button" id="open_config_modal_btn">⚙️ Configuração</button></div>

      <div class="collection-modal hidden" id="config_modal" role="dialog" aria-modal="true" aria-labelledby="config_modal_title">
        <div class="collection-modal-backdrop" data-config-modal-close></div>
        <div class="card collection-modal-card configuration-modal-card">
        <button class="comparison-link-modal-close collection-modal-close" type="button" data-config-modal-close aria-label="Fechar configuração">&times;</button>
        <div class="section-title" id="config_modal_title">Configuração</div>
        <div class="small configuration-validation-help">
          A validação normal confere os dados essenciais e é mais rápida; a completa revisita todas as categorias e itens para uma conferência mais profunda.
        </div>
        <div class="form-grid">
          <div class="field">
            <label for="verify_mode">Validação</label>
            <select id="verify_mode">
              <option value="normal">Normal</option>
              <option value="complete" selected>Completa</option>
            </select>
          </div>
          <div class="field">
            <label for="scope_mode">Escopo</label>
            <select id="scope_mode" onchange="toggleScopeFields()">
              <option value="all">Todas as categorias</option>
              <option value="range">Intervalo por posição</option>
              <option value="match">Texto / filtro</option>
              <option value="selected">Somente selecionadas</option>
            </select>
          </div>
          <div class="field" id="field_range_start" style="display:none;">
            <label for="scope_start">Início do intervalo</label>
            <input id="scope_start" type="number" min="1" step="1" value="1">
          </div>
          <div class="field" id="field_range_end" style="display:none;">
            <label for="scope_end">Fim do intervalo</label>
            <input id="scope_end" type="number" min="0" step="1" value="0">
          </div>
          <div class="field" id="field_match" style="display:none;">
            <label for="scope_match_text">Texto para filtro</label>
            <textarea id="scope_match_text" placeholder="Ex.: elementor, yith, codecanyon"></textarea>
          </div>
          <div class="field">
            <label for="save_every_items">Salvar a cada itens</label>
            <input id="save_every_items" type="number" min="1" step="1" value="10">
          </div>
          <div class="field">
            <label for="save_every_minutes">Salvar a cada minutos</label>
            <input id="save_every_minutes" type="number" min="1" step="1" value="10">
          </div>
          <div class="field" id="field_selected_categories" style="display:none;grid-column:1/-1;">
            <label>Categorias selecionadas</label>
            <div class="small">
              Disponíveis: <strong id="available_categories_count">0</strong> •
              Selecionadas: <strong id="selected_categories_count">0 selecionadas</strong>
            </div>
            <div class="row" style="margin:10px 0 12px;">
              <button class="btn-secondary" id="select_all_categories_btn" onclick="selectAllCategories()">Selecionar todas</button>
              <button class="btn-secondary" id="invert_selected_categories_btn" onclick="invertSelectedCategories()">Inverter seleção</button>
              <button class="btn-secondary" id="clear_selected_categories_btn" onclick="clearSelectedCategories()">Limpar seleção</button>
            </div>
            <div class="checkbox-list" id="selected_categories_list">
              <div class="badge">Nenhuma categoria disponível ainda.</div>
            </div>
          </div>
        </div>

        <div class="row" style="justify-content:flex-end; margin-top:16px;">
          <button class="btn-success" id="save_config_btn" onclick="saveConfig()">💾 Salvar configuração</button>
        </div>
        </div>
      </div>

      <div class="card quick-actions-card">
        <div class="section-title">Ações rápidas</div>
   <div class="quick-grid">
  <button class="btn-primary" id="run_primary_btn" onclick="runPrimary()">▶️ Iniciar</button>
  <div class="quick-action-with-help"><button class="btn-secondary" id="run_categories_btn" onclick="runMode('categories_only')">📁 Atualizar categorias</button><button type="button" class="comparison-help quick-action-help" aria-label="Ajuda sobre Atualizar categorias" data-tooltip="Busca novamente as categorias disponíveis no site selecionado e atualiza o catálogo de categorias salvo.">?</button></div>
  <div class="quick-action-with-help"><button class="btn-secondary" id="run_links_btn" onclick="runMode('links_only')">🔗 Detectar links</button><button type="button" class="comparison-help quick-action-help" aria-label="Ajuda sobre Detectar links" data-tooltip="Verifica os produtos das categorias e identifica os links das páginas individuais sem executar uma revisão completa dos produtos.">?</button></div>
  <div class="quick-action-with-help"><button class="btn-secondary" id="run_review_btn" onclick="runMode('existing_review')">🔎 Revisar existentes</button><button type="button" class="comparison-help quick-action-help" aria-label="Ajuda sobre Revisar existentes" data-tooltip="Reabre os produtos já salvos para conferir dados que podem ter mudado, como nome, versão, página oficial e outras informações.">?</button></div>
  <button class="btn-warning" id="continue_btn" onclick="continueRun()" style="display:none;">⏯ Continuar</button>
  <div class="quick-action-with-help"><button class="btn-secondary" id="pause_resume_btn" onclick="togglePauseResume()">⏸ Pausar</button><button type="button" class="comparison-help quick-action-help pause-help" aria-label="Ajuda sobre Pausar ou Retomar" data-pause-tooltip="Pausa temporariamente a execução atual, preservando o progresso para retomada posterior." data-resume-tooltip="Continua uma execução interrompida a partir do progresso salvo anteriormente." data-tooltip="Pausa temporariamente a execução atual, preservando o progresso para retomada posterior.">?</button></div>
  <div class="quick-action-with-help"><button class="btn-danger" id="stop_btn" onclick="postAction('stop')">🛑 Parar</button><button type="button" class="comparison-help quick-action-help" aria-label="Ajuda sobre Parar" data-tooltip="Interrompe a execução atual e salva o progresso disponível para permitir continuação posteriormente, quando aplicável.">?</button></div>
</div>
      </div>

      <div class="card">
        <div class="section-title">Estado</div>
        <div class="kpi-grid">
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Status</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Status" data-tooltip="Situação atual da execução selecionada, como rodando, pausada, concluída ou interrompida.">?</button></div><div class="kpi-value" id="status_text">-</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Tempo</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Tempo" data-tooltip="Tempo total registrado para a execução atual.">?</button></div><div class="kpi-value" id="timer_text">0:00:00</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Itens salvos</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Itens salvos" data-tooltip="Quantidade total de produtos já persistidos no catálogo atual.">?</button></div><div class="kpi-value" id="saved_count_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Itens pendentes</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Itens pendentes" data-tooltip="Quantidade de produtos que ainda aguardam processamento na execução atual.">?</button></div><div class="kpi-value" id="pending_count_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Fila detectada</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Fila detectada" data-tooltip="Quantidade de itens identificados para processamento na fila da execução.">?</button></div><div class="kpi-value" id="queue_detected_count_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Novos itens</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Novos itens" data-tooltip="Produtos encontrados durante a execução que ainda não existiam no catálogo salvo.">?</button></div><div class="kpi-value" id="new_items_added_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Atualizados</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Atualizados" data-tooltip="Produtos existentes que tiveram alguma informação alterada durante a revisão.">?</button></div><div class="kpi-value" id="items_updated_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Sem mudança</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Sem mudança" data-tooltip="Produtos revisados cuja informação permaneceu igual à já salva.">?</button></div><div class="kpi-value" id="items_unchanged_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Novos links</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Novos links" data-tooltip="Links de produtos identificados pela primeira vez durante a detecção.">?</button></div><div class="kpi-value" id="new_links_detected_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Links existentes</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Links existentes" data-tooltip="Links detectados que já estavam registrados no catálogo.">?</button></div><div class="kpi-value" id="existing_links_detected_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Categorias reutilizadas</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Categorias reutilizadas" data-tooltip="Categorias cujo conteúdo salvo pôde ser reutilizado sem uma nova coleta completa.">?</button></div><div class="kpi-value" id="reused_categories_text">0</div></div>
          <div class="kpi principal-state-kpi"><div class="kpi-label comparison-kpi-label"><span>Categorias refeitas</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Categorias refeitas" data-tooltip="Categorias que precisaram ser coletadas novamente durante a execução.">?</button></div><div class="kpi-value" id="refetched_categories_text">0</div></div>
        </div>

        <div class="form-grid principal-state-details" style="margin-top:14px;">
          <div class="field">
            <label class="comparison-kpi-label"><span>Resumo</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Resumo" data-tooltip="Resumo do progresso e da situação atual da execução selecionada.">?</button></label>
            <div class="notice" id="summary_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Fila de continuação</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Fila de continuação" data-tooltip="Mostra o progresso da fila salva que ainda pode ser processada ou retomada.">?</button></label>
            <div class="notice" id="resume_queue_text">0/0</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Fase atual</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Fase atual" data-tooltip="Etapa do fluxo que está sendo executada neste momento.">?</button></label>
            <div class="notice" id="current_phase_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Categoria atual</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Categoria atual" data-tooltip="Categoria que está sendo processada no momento.">?</button></label>
            <div class="notice" id="current_category_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Item atual</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Item atual" data-tooltip="Produto ou item atualmente em processamento.">?</button></label>
            <div class="notice" id="current_item_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Última atualização</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Última atualização" data-tooltip="Horário da atualização mais recente recebida pelo painel.">?</button></label>
            <div class="notice" id="updated_at_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Início da execução</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Início da execução" data-tooltip="Data e horário em que esta execução foi iniciada.">?</button></label>
            <div class="notice" id="run_started_at_text">-</div>
          </div>
          <div class="field">
            <label class="comparison-kpi-label"><span>Fim da execução</span><button type="button" class="comparison-help" aria-label="Ajuda sobre Fim da execução" data-tooltip="Data e horário em que esta execução foi concluída ou interrompida.">?</button></label>
            <div class="notice" id="run_finished_at_text">-</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="section-title">Logs</div>
        <pre id="logs"></pre>
        <div class="log-copy-row">
          <button class="btn-success" id="copy_logs_btn" onclick="copyFullLog()">📋 Copiar log completo</button>
        </div>
      </div>
    </section>

    <section class="tab-panel hidden" id="tab_panel_catalogos">
      <div class="card">
        <div class="section-title">Catálogos</div>

        <div class="catalogos-loading" id="catalogos_loading" role="status" aria-live="polite">
          <span class="inline-loading-spinner" aria-hidden="true"></span>
          <span><strong>Carregando catálogos...</strong><br>Aguarde enquanto preparamos os cards e as informações de contexto.</span>
        </div>

        <div class="catalogos-content hidden" id="catalogos_content">

        <div class="form-grid catalogos-actions-grid">
          <div class="field">
            <label for="catalogos_filter_slot">Catálogo</label>
            <select id="catalogos_filter_slot"><option value="">Todos</option></select>
          </div>
          <div class="field catalogos-refresh-field">
            <label>Ações</label>
            <div class="row">
              <button class="btn-secondary" onclick="refreshCatalogos({showLoading:true})">Atualizar catálogos</button>
            </div>
          </div>
        </div>

        <div class="row" id="catalogos_cards_wrap" style="margin-top:14px;"></div>

        <div class="catalogos-table-toolbar">
          <div><div class="section-title catalogos-context-title">Contextos dos catálogos</div><span class="badge" id="catalogos_context_count">0 contextos</span></div>
          <button class="btn-danger" id="catalogos_remove_zero_btn" type="button" disabled>Remover contextos zerados</button>
        </div>

        <div class="catalogos-context-search cs-search-system" style="margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--bg-elev-1);">
          <div class="field">
            <label for="catalogos_search">Buscar nos contextos</label>
            <input id="catalogos_search" type="search" placeholder="Catálogo, site, tipo ou conta">
          </div>
        </div>

        <div class="table-wrap" style="margin-top:14px;">
          <table class="catalogos-table">
            <thead>
              <tr>
                <th>Catálogo</th>
                <th>Site</th>
                <th>Tipo</th>
                <th>Conta</th>
                <th>Itens</th>
                <th>Status</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody id="catalogos_table_body">
              <tr><td colspan="7">Carregando...</td></tr>
            </tbody>
          </table>
        </div>

        <div class="listing-meta-row catalogos-listing-meta">
          <div class="small" id="catalogos_result_meta">Mostrando 0 de 0 itens</div>
          <div class="listing-page-size"><label for="catalogos_page_size" class="small">Itens por página</label><input id="catalogos_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric"></div>
        </div>

        <div class="listing-pagination catalogos-pagination">
          <button class="btn-secondary" id="catalogos_prev_page" type="button">← Anterior</button>
          <span class="badge cs-page-jump" id="catalogos_page_label">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span>
          <button class="btn-secondary" id="catalogos_next_page" type="button">Próxima →</button>
        </div>

        <div class="card" style="margin-top:14px;">
          <div class="row" style="justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div class="section-title" id="catalogos_preview_title" style="margin:0;">Prévia</div>
            <div class="row"><button class="btn-secondary" id="catalogos_preview_download_btn" type="button" disabled>Baixar</button></div>
          </div>

          <div class="field" style="margin-bottom:12px;">
            <label for="catalogos_preview_search">Buscar na prévia</label>
            <input id="catalogos_preview_search" type="text" placeholder="Digite para filtrar o conteúdo atual">
          </div>

          <div id="catalogos_status_preview">
            <div class="notice">Selecione uma prévia na tabela.</div>
          </div>
          <div class="log-copy-row"><button class="btn-success hidden" id="catalogos_preview_copy_log_btn" type="button">📋 Copiar log completo</button></div>
        </div>
        </div>
      </div>
    </section>

    <div class="collection-modal catalog-rename-modal hidden" id="catalog_rename_modal" role="dialog" aria-modal="true" aria-labelledby="catalog_rename_title">
      <div class="collection-modal-backdrop" data-catalog-rename-close></div>
      <div class="card catalog-rename-modal-card">
        <button class="comparison-link-modal-close" type="button" aria-label="Fechar" data-catalog-rename-close>&times;</button>
        <div class="section-title" id="catalog_rename_title">Renomear catálogo</div>
        <div class="small" id="catalog_rename_help">Informe o novo nome do catálogo.</div>
        <div class="field catalog-rename-field">
          <label for="catalog_rename_name">Novo nome</label>
          <input id="catalog_rename_name" type="text" maxlength="80" autocomplete="off">
        </div>
        <div class="comparison-link-modal-actions">
          <button class="btn-secondary" type="button" data-catalog-rename-close>Cancelar</button>
          <button class="btn-success" id="catalog_rename_confirm" type="button">Salvar novo nome</button>
        </div>
      </div>
    </div>

    <section class="tab-panel hidden" id="tab_panel_fila">
      <div class="card">
        <div class="small" style="margin-bottom:12px;">
          Defina qual catálogo/contexto deve iniciar automaticamente quando outro terminar.
        </div>

        <div class="row" style="justify-content:space-between; align-items:center; margin-bottom:12px;">
          <span class="badge" id="fila_rules_count_badge">0 regras</span>

          <div class="row">
            <button class="btn-secondary" type="button" onclick="refreshFila()">Atualizar fila</button>
            <button class="btn-secondary" type="button" onclick="addFilaRule()">Adicionar regra</button>
            <button class="btn-success" type="button" onclick="saveFila()">Salvar fila</button>
          </div>
        </div>

             <div id="fila_rules_wrap" aria-live="polite">
          <div class="notice">Abra a aba Fila para carregar as regras.</div>
        </div>
      </div>
    </section>

    <section class="tab-panel hidden" id="tab_panel_comparacao">
      <div class="card">
        <div class="section-title">Comparação de catálogos</div>

        <div class="small comparison-intro" style="margin-bottom:14px;">
          Compare o catálogo selecionado do Ultrapack com o catálogo exportado do
          WooCommerce da PluginTema. Para evitar associações incorretas, o CrapScraper
          confirma automaticamente apenas correspondências únicas pela URL oficial ou
          pelo nome normalizado; os demais casos ficam disponíveis para revisão.
        </div>

        <div class="comparison-toolbar">

  <div class="comparison-source-grid">
    <div class="field">
      <label for="comparison_source_catalog">
        Catálogo de origem
      </label>

      <select id="comparison_source_catalog">
        <option value="">Carregando catálogos...</option>
      </select>
    </div>

    <div class="field">
      <div class="comparison-target-actions"><button class="btn-secondary comparison-manage-catalog-button" type="button" id="comparison_manage_plugintema_btn">Gerenciar cat&aacute;logos PluginTema</button><button class="btn-secondary comparison-update-catalog-button" type="button" id="comparison_update_plugintema_btn">Atualizar cat&aacute;logo PluginTema</button></div>
      <label for="comparison_target_catalog">
        Catálogo da PluginTema
      </label>

      <select id="comparison_target_catalog">
        <option value="">Carregando catálogos...</option>
      </select>
    </div>
  </div>


  <div class="comparison-filter-grid">

    <div class="field">
      <label for="comparison_status_filter">Situação</label>
      <select id="comparison_status_filter">
        <option value="all">Todas</option>
        <option value="update_available">Atualização disponível</option>
        <option value="updated">Atualizado</option>
        <option value="version_review">Revisar versão</option>
        <option value="site_version_missing">Versão ausente no site</option>
        <option value="source_version_missing">Versão ausente no Ultrapack</option>
        <option value="site_ahead">Site aparentemente mais novo</option>
        <option value="site_only">Somente no PluginTema</option>
        <option value="new_source">Novo no Ultrapack</option>
      </select>
    </div>

    <div class="field">
      <label for="comparison_decision_filter">Decisão</label>
      <select id="comparison_decision_filter">
        <option value="all">Todas</option>
        <option value="pending">Pendentes</option>
        <option value="approved">Aprovados</option>
        <option value="approve_update">Atualização aprovada</option>
        <option value="ignore">Ignorados</option>
        <option value="review_later">Revisar depois</option>
        <option value="same_product">Mesmo produto confirmado</option>
        <option value="different_products">Produtos diferentes</option>
        <option value="approve_new_product">Cadastro novo aprovado</option>
      </select>
    </div>

    <div class="field comparison-search-field">
      <label for="comparison_query">Buscar</label>
      <input
        id="comparison_query"
        type="search"
        placeholder="Nome, ID, versão ou categoria"
      >
    </div>

    <div class="field">
      <label for="comparison_candidate_filter">Buscar candidatos</label>
      <select id="comparison_candidate_filter">
        <option value="all">Todos</option>
        <option value="with_candidates">Produtos com candidatos</option>
        <option value="without_candidates">Produtos sem candidatos</option>
        <option value="exact">Sugestões exatas</option>
        <option value="probable">Sugestões prováveis</option>
        <option value="ambiguous">Sugestões ambíguas</option>
        <option value="disputed">Candidatos disputados</option>
        <option value="safe_url">Correspondência segura por URL</option>
        <option value="safe_name">Correspondência segura por nome</option>
      </select>
    </div>

  </div>


  <div class="comparison-actions-grid">

    <div class="field">
      <label for="comparison_score_min">Pontuação mínima</label>
      <input
        id="comparison_score_min"
        type="number"
        min="0"
        max="100"
        step="1"
        placeholder="Ex.: 70"
      >
    </div>

    <div class="field">
      <label for="comparison_score_max">Pontuação máxima</label>
      <input
        id="comparison_score_max"
        type="number"
        min="0"
        max="100"
        step="1"
        placeholder="Ex.: 90"
      >
    </div>

    <button
      type="button"
      class="btn-primary comparison-run-button"
      id="comparison_run_btn"
    >
      Comparar agora
    </button>

    <button
      type="button"
      class="btn-secondary comparison-reload-button"
      id="comparison_reload_sources_btn"
    >
      Atualizar lista
    </button>

  </div>

</div>


        <div class="notice" id="comparison_file_notice">
          Abra esta aba para carregar os dois catálogos.
        </div>
      </div>

     <details class="card hidden comparison-summary-accordion" id="comparison_summary_card" open>
  <summary class="comparison-summary-header">
    <div class="section-title">Resumo da comparação</div>
    <span class="comparison-summary-toggle" aria-hidden="true"></span>
  </summary>

  <div class="comparison-summary-content">

  <div class="comparison-group">
    <div class="comparison-group-head">
      <div class="comparison-group-title">
        Visão geral
      </div>

      <div class="comparison-group-description">
        Totais dos dois catálogos e quantidade de produtos
        associados automaticamente com segurança.
      </div>
    </div>

    <div class="kpi-grid comparison-kpi-grid">
      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Ultrapack</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre o total do Ultrapack"
            data-tooltip="Quantidade total de produtos válidos encontrados no catálogo selecionado do Ultrapack."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_source_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Produtos do site</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre os produtos do site"
            data-tooltip="Quantidade de produtos principais válidos encontrados no arquivo importado da PluginTema. Linhas de variações do WooCommerce não entram neste total."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_site_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Correspondências seguras</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre correspondências seguras"
            data-tooltip="Produtos associados automaticamente por URL oficial única ou nome normalizado único. Somente esses produtos participam da comparação automática de versões."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_matched_total"
        >0</div>
      </div>
    </div>
  </div>

  <div class="comparison-group">
    <div class="comparison-group-head">
      <div class="comparison-group-title">
        Situação dos produtos correspondentes
      </div>

      <div class="comparison-group-description">
        Resultado da comparação de versões apenas entre produtos
        que possuem correspondência segura.
      </div>
    </div>

    <div class="kpi-grid comparison-kpi-grid">
      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Atualizações</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre atualizações"
            data-tooltip="Produtos correspondentes em que a versão do Ultrapack é mais recente que a versão cadastrada na PluginTema."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_update_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Atualizados</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos atualizados"
            data-tooltip="Produtos correspondentes em que as versões do Ultrapack e da PluginTema são iguais ou equivalentes após normalização."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_updated_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Revisar versão</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre revisão de versão"
            data-tooltip="Produtos correspondentes cuja versão parece ter sido convertida em data, está em formato não confiável ou não pode ser comparada automaticamente."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_review_total"
        >0</div>
      </div>
    </div>
  </div>

  <div class="comparison-group">
    <div class="comparison-group-head">
      <div class="comparison-group-title">
        Produtos sem correspondência
      </div>

      <div class="comparison-group-description">
        Produtos que ainda não possuem uma associação segura
        entre os dois catálogos.
      </div>
    </div>

    <div class="kpi-grid comparison-kpi-grid">
      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Sem correspondência na PluginTema</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos sem correspondência na PluginTema"
            data-tooltip="Produtos encontrados no Ultrapack para os quais nenhuma correspondência segura foi localizada na PluginTema. Eles ainda não devem ser considerados produtos realmente novos."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_new_source_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Somente na PluginTema</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos somente na PluginTema"
            data-tooltip="Produtos encontrados na PluginTema para os quais nenhuma correspondência segura foi localizada no catálogo selecionado do Ultrapack."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_site_only_total"
        >0</div>
      </div>
    </div>
  </div>

  <div class="comparison-group comparison-candidate-metrics">
    <div class="comparison-group-head">
      <div class="comparison-group-title">Candidatos aproximados</div>
      <div class="comparison-group-description">Diagnostico das sugestoes encontradas para produtos ainda sem correspondencia segura.</div>
    </div>

    <div class="kpi-grid comparison-kpi-grid">
      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Produtos com candidatos</span><button type="button" class="comparison-help" aria-label="Explicação sobre produtos com candidatos" data-tooltip="Produtos sem correspondência segura para os quais o sistema encontrou pelo menos um candidato aproximado na outra base. Esses candidatos ainda precisam de confirmação antes de qualquer associação operacional.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_rows_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Produtos sem candidatos</span><button type="button" class="comparison-help" aria-label="Explicação sobre produtos sem candidatos" data-tooltip="Produtos sem correspondência segura para os quais nenhum candidato aproximado atingiu os critérios mínimos de similaridade definidos pelo comparador.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_none_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Sugestoes exatas</span><button type="button" class="comparison-help" aria-label="Explicação sobre sugestões exatas" data-tooltip="Candidatos aproximados classificados no nível mais forte de correspondência pelos sinais analisados. Mesmo assim, candidatos encontrados fora da associação segura devem ser confirmados antes de uso operacional.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_exact_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Sugestoes provaveis</span><button type="button" class="comparison-help" aria-label="Explicação sobre sugestões prováveis" data-tooltip="Candidatos que apresentam vários sinais favoráveis de serem o mesmo produto, mas ainda não possuem segurança suficiente para associação automática.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_probable_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Sugestoes ambiguas</span><button type="button" class="comparison-help" aria-label="Explicação sobre sugestões ambíguas" data-tooltip="Candidatos com semelhanças relevantes, mas também com conflitos, concorrência entre candidatos ou evidências insuficientes. Devem ser analisados manualmente.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_ambiguous_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label"><span>Total de candidatos</span><button type="button" class="comparison-help" aria-label="Explicação sobre o total de candidatos" data-tooltip="Quantidade total de sugestões de correspondência aproximada encontradas. Um mesmo produto pode possuir mais de um candidato, portanto este número não representa necessariamente a quantidade de produtos analisados.">?</button></div>
        <div class="kpi-value" id="comparison_candidate_total">0</div>
      </div>
    </div>
  </div>

  <div class="comparison-diagnostics">
    <div class="section-title comparison-diagnostics-title">
      Diagnóstico detalhado
    </div>

    <div class="kpi-grid comparison-diagnostics-grid">
      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Versão ausente no site</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre versões ausentes no site"
            data-tooltip="Produtos correspondentes que existem na PluginTema, mas não possuem versão cadastrada."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_site_version_missing_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Versão ausente no Ultrapack</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre versões ausentes no Ultrapack"
            data-tooltip="Produtos correspondentes cuja versão não está informada no catálogo do Ultrapack."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_source_version_missing_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Site aparentemente mais novo</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos mais novos no site"
            data-tooltip="Produtos correspondentes em que a versão cadastrada na PluginTema parece ser superior à versão encontrada no Ultrapack."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_site_ahead_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Correspondência por URL</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre correspondências por URL"
            data-tooltip="Produtos associados porque possuem a mesma URL oficial única nos dois catálogos."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_match_url_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Correspondência por nome</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre correspondências por nome"
            data-tooltip="Produtos associados porque possuem o mesmo nome normalizado único nos dois catálogos."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_match_name_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Versões suspeitas no site</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre versões suspeitas no site"
            data-tooltip="Versões da PluginTema que aparentam ter sido transformadas em datas por Excel, Google Sheets ou outro editor de planilhas."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_suspicious_site_versions_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Versões suspeitas no Ultrapack</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre versões suspeitas no Ultrapack"
            data-tooltip="Versões do Ultrapack que aparentam ter sido transformadas em datas por uma planilha ou outro editor."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_suspicious_source_versions_total"
        >0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Versões vazias</span>

          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre versões vazias"
            data-tooltip="Quantidade total de produtos sem versão informada, somando PluginTema e Ultrapack."
          >?</button>
        </div>

        <div
          class="kpi-value"
          id="comparison_missing_versions_total"
        >0</div>

        <div class="comparison-kpi-detail">
          Site:
          <strong id="comparison_missing_site_versions_total">0</strong>
          · Ultrapack:
          <strong id="comparison_missing_source_versions_total">0</strong>
        </div>

         </div>
    </div>
  </div>

  <div class="comparison-reconciliation">
    <div class="section-title comparison-diagnostics-title">
      Conferência matemática
    </div>

    <div class="comparison-reconciliation-grid">
      <div class="comparison-reconciliation-item">
        <div class="kpi-label comparison-kpi-label">
          <span>Correspondências</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre a conferência das correspondências"
            data-tooltip="Confere se a soma de todos os estados dos produtos correspondidos é exatamente igual ao total de correspondências seguras. Se os números divergirem, existe inconsistência na classificação dos resultados."
          >?</button>
        </div>
        <strong id="comparison_reconciliation_matches">-</strong>
      </div>

      <div class="comparison-reconciliation-item">
        <div class="kpi-label comparison-kpi-label">
          <span>Catálogo Ultrapack</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre a conferência do catálogo Ultrapack"
            data-tooltip="Confere se todos os produtos válidos do catálogo Ultrapack foram contabilizados entre correspondências seguras e produtos sem correspondência na PluginTema."
          >?</button>
        </div>
        <strong id="comparison_reconciliation_source">-</strong>
      </div>

      <div class="comparison-reconciliation-item">
        <div class="kpi-label comparison-kpi-label">
          <span>Catálogo PluginTema</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre a conferência do catálogo PluginTema"
            data-tooltip="Confere se todos os produtos principais válidos da PluginTema foram contabilizados entre correspondências seguras e produtos encontrados somente no site."
          >?</button>
        </div>
        <strong id="comparison_reconciliation_site">-</strong>
      </div>

      <div class="comparison-reconciliation-item">
        <div class="kpi-label comparison-kpi-label">
          <span>Métodos de correspondência</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre a conferência dos métodos de correspondência"
            data-tooltip="Confere se todas as correspondências seguras possuem um método de associação registrado, como URL oficial única ou nome normalizado único."
          >?</button>
        </div>
        <strong id="comparison_reconciliation_methods">-</strong>

         </div>
    </div>
  </div>

<details class="comparison-decisions-accordion" id="comparison_decisions_card">

  <summary class="comparison-decisions-summary">
    <div class="comparison-decisions-summary-text">
      <div class="section-title">Decisões operacionais</div>

      <div class="small comparison-decisions-description">
        Estado atual das decisões aplicadas aos produtos desta comparação.
      </div>
    </div>

    <span class="comparison-decisions-chevron" aria-hidden="true"></span>
  </summary>

  <div class="comparison-decisions-content">
    <div class="kpi-grid comparison-decision-grid">

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Pendentes</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre decisões pendentes"
            data-tooltip="Produtos que ainda não possuem uma decisão operacional definitiva. Inclui produtos nunca salvos no banco e produtos cuja decisão atual foi restaurada para Pendente."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_pending_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Aprovados</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre decisões aprovadas"
            data-tooltip="Total agregado de decisões positivas: atualizações aprovadas, cadastros novos aprovados e correspondências confirmadas como o mesmo produto."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_approved_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Ignorados</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos ignorados"
            data-tooltip="Produtos que o operador decidiu não processar neste fluxo. A decisão fica registrada, mas o produto não segue para atualização ou cadastro."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_ignored_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Revisar depois</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre revisar depois"
            data-tooltip="Produtos separados para análise posterior porque ainda faltam informações, confirmação de correspondência, validação de versão ou outra conferência manual."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_review_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Mesmo produto</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre mesmo produto"
            data-tooltip="Correspondências que não foram confirmadas automaticamente, mas que o operador verificou manualmente e declarou representarem o mesmo produto."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_same_product_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Produtos diferentes</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre produtos diferentes"
            data-tooltip="Sugestões ou associações que o operador analisou e confirmou serem produtos distintos. Elas não devem ser utilizadas como correspondência."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_different_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Cadastros aprovados</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre cadastros aprovados"
            data-tooltip="Produtos do Ultrapack confirmados como realmente novos e autorizados pelo operador para seguir para a fila da aba Adições."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_new_product_total">0</div>
      </div>

      <div class="kpi comparison-kpi">
        <div class="kpi-label comparison-kpi-label">
          <span>Decisões registradas</span>
          <button
            type="button"
            class="comparison-help"
            aria-label="Explicação sobre decisões registradas"
            data-tooltip="Quantidade de produtos que possuem um estado explicitamente persistido no banco SQLite. Não corresponde ao total de produtos pendentes que nunca foram salvos."
          >?</button>
        </div>
        <div class="kpi-value" id="comparison_decision_saved_total">0</div>
      </div>

    </div>
  </div>
</details>

  </div>
</details>

<div class="card" id="comparison_results_card">

        <div class="comparison-results-head">
          <div class="section-title">Resultado</div>
        </div>

        <div class="comparison-bulk-toolbar" id="comparison_bulk_toolbar">
          <label class="comparison-bulk-select-page">
            <input type="checkbox" id="comparison_select_page">
            <span>Selecionar página</span>
          </label>

          <label class="comparison-bulk-select-page">
            <input type="checkbox" id="comparison_select_all_results">
            <span>Selecionar todo resultado</span>
          </label>
          <button type="button" class="btn-secondary" id="comparison_clear_selection">Limpar seleção</button>

          <span class="badge" id="comparison_selected_count">0 selecionados</span>

         <div class="comparison-bulk-actions-row">

  <select id="comparison_bulk_decision">
    <option value="">Escolha uma decisão</option>
    <option value="approve_update">Aprovar atualização</option>
    <option value="ignore">Ignorar</option>
    <option value="review_later">Revisar depois</option>
    <option value="same_product">Mesmo produto</option>
    <option value="different_products">Produtos diferentes</option>
    <option value="approve_new_product">Aprovar cadastro novo</option>
    <option value="pending">Restaurar para pendente</option>
  </select>

</div>

<button type="button" class="btn-primary" id="comparison_bulk_apply_btn" disabled>
  Aplicar aos selecionados
</button>
          
        </div>

        <div class="listing-meta-row comparison-listing-meta">
          <div class="small" id="comparison_result_meta">-</div>
          <div class="listing-page-size">
            <label for="comparison_page_size" class="small">Itens por página</label>
            <input id="comparison_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric">
          </div>
        </div>

        <div class="listing-pagination comparison-pagination">
          <button type="button" class="btn-secondary" id="comparison_prev_btn">← Anterior</button>
          <span class="badge cs-page-jump" id="comparison_page_label">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span>
          <button type="button" class="btn-secondary" id="comparison_next_btn">Próxima →</button>
        </div>

        <div class="comparison-table-wrap">
          <table class="comparison-table">

<thead>
  <tr>
    <th>Situação</th>
    <th>Produtos</th>
    <th>Versões</th>
    <th>Candidato principal</th>
    <th>Correspondência</th>
    <th>Decisão</th>
    <th>Recomendação</th>
  </tr>
</thead>

<tbody id="comparison_rows">
  <tr>
    <td colspan="7">
      Nenhuma comparação executada.
    </td>
  </tr>
</tbody>
            
          </table>
        </div>

      </div>

        <details class="card updates-card-section updates-technical-log comparison-technical-log">
          <summary><span class="updates-disclosure-chevron" aria-hidden="true">▸</span><span>Log da comparação</span></summary>
          <pre id="comparison_log" class="log-output" aria-live="polite">Nenhum evento nesta sessão.</pre>
          <div class="log-copy-row"><button class="btn-success" id="comparison_copy_log" type="button">📋 Copiar log completo</button></div>
        </details>
    </section>
<div class="comparison-link-modal hidden" id="plugintema_update_modal" role="dialog" aria-modal="true" aria-labelledby="plugintema_update_modal_title">
  <div class="comparison-link-modal-backdrop" data-plugintema-close></div>
  <div class="comparison-link-modal-card plugintema-update-modal-card">
    <button class="comparison-link-modal-close" id="plugintema_update_modal_close" type="button" aria-label="Fechar">&times;</button>
    <div class="section-title" id="plugintema_update_modal_title">Atualizar cat&aacute;logo PluginTema</div>
    <p class="small">Gere um cat&aacute;logo atualizado diretamente da PluginTema para utilizar na compara&ccedil;&atilde;o.</p>
    <div class="field plugintema-catalog-name"><label for="plugintema_custom_name">Nome do catálogo <span class="small">(opcional)</span></label><input id="plugintema_custom_name" type="text" maxlength="80" placeholder="Ex.: Catálogo premium de agosto"></div>
    <div class="plugintema-mode-grid" aria-label="Conteúdo do catálogo">
      <label class="plugintema-mode-card"><input type="checkbox" name="plugintema_preset_kind" value="plugin" checked><strong>Plugins</strong><span>Inclui produtos classificados como plugins.</span></label>
      <label class="plugintema-mode-card"><input type="checkbox" name="plugintema_preset_kind" value="theme"><strong>Temas</strong><span>Inclui produtos classificados como temas.</span></label>
      <label class="plugintema-mode-card"><input type="checkbox" name="plugintema_preset_kind" value="template"><strong>Templates</strong><span>Inclui produtos classificados como templates.</span></label>
      <label class="plugintema-mode-card plugintema-custom-mode"><input type="radio" name="plugintema_custom_mode" value="custom"><strong>Personalizado</strong><span>Usa filtros e produtos escolhidos manualmente.</span></label>
    </div>
    <div class="plugintema-custom-filters hidden" id="plugintema_custom_filters"><div class="form-grid">
      <div class="field"><label for="plugintema_custom_kind">Tipo</label><select id="plugintema_custom_kind"><option value="plugin">Plugins</option><option value="theme">Temas</option><option value="template">Templates</option><option value="both">Plugins e Temas</option><option value="all">Plugins, Temas e Templates</option></select></div>
      <div class="field"><label for="plugintema_custom_status">Status do produto</label><select id="plugintema_custom_status"><option value="publish">Publicado</option><option value="draft">Rascunho</option><option value="private">Privado</option><option value="all">Todos</option></select></div>
      <div class="field"><label for="plugintema_custom_categories">Categoria WooCommerce</label><select id="plugintema_custom_categories" multiple size="5"></select></div>
      <div class="field"><label for="plugintema_custom_query">Busca por nome/termo</label><input id="plugintema_custom_query" type="search"></div>
      <div class="field"><label for="plugintema_custom_ids">IDs espec&iacute;ficos</label><input id="plugintema_custom_ids" type="text" placeholder="Ex.: 94567, 90109"></div>
      <div class="field"><label for="plugintema_custom_version">Produtos com vers&atilde;o</label><select id="plugintema_custom_version"><option value="all">Todos</option><option value="with">Somente com pt_versao</option><option value="without">Somente sem pt_versao</option></select></div>
    </div></div>
    <div class="plugintema-product-picker hidden" id="plugintema_product_picker">
      <div class="field"><label for="plugintema_product_search">Pesquisar produtos para adicionar</label><div class="row"><input id="plugintema_product_search" type="search" placeholder="Nome, termo ou ID"><button class="btn-secondary" id="plugintema_product_search_btn" type="button">Pesquisar</button></div></div>
      <div class="plugintema-search-results" id="plugintema_search_results"><div class="small">Pesquise plugins ou temas no WooCommerce.</div></div>
      <div class="plugintema-selected-head"><strong>Itens adicionados &agrave; compara&ccedil;&atilde;o personalizada</strong><span class="badge" id="plugintema_selected_count">0 itens</span></div>
      <div class="plugintema-selected-products" id="plugintema_selected_products"><div class="small">Nenhum item adicionado.</div></div>
    </div>
    <div class="notice plugintema-update-status" id="plugintema_update_status" aria-live="polite" aria-busy="false">Pronto para atualizar.</div>
    <div class="comparison-link-modal-actions"><button class="btn-secondary" id="plugintema_update_cancel" type="button">Cancelar</button><button class="btn-success" id="plugintema_update_submit" type="button">Atualizar cat&aacute;logo</button></div>
  </div>
</div>

<div class="comparison-link-modal hidden" id="plugintema_manage_modal" role="dialog" aria-modal="true" aria-labelledby="plugintema_manage_title">
  <div class="comparison-link-modal-backdrop" data-plugintema-manage-close></div>
  <div class="comparison-link-modal-card plugintema-manage-modal-card">
    <button class="comparison-link-modal-close" id="plugintema_manage_close" type="button" aria-label="Fechar">&times;</button>
    <div class="section-title" id="plugintema_manage_title">Gerenciar cat&aacute;logos PluginTema</div>
    <div class="small">Selecione, renomeie ou apague um catálogo. As contagens usam as categorias dos produtos WooCommerce.</div>
    <div class="plugintema-catalog-cards" id="plugintema_manage_catalog_cards" aria-live="polite"></div>
    <div class="form-grid plugintema-manage-filters"><div class="field"><label for="plugintema_manage_catalog">Cat&aacute;logo</label><select id="plugintema_manage_catalog"></select></div><div class="field"><label for="plugintema_manage_search">Pesquisar no cat&aacute;logo</label><input id="plugintema_manage_search" type="search" placeholder="Nome, ID, categoria ou versão"></div><div class="field"><label for="plugintema_manage_type">Tipo</label><select id="plugintema_manage_type"><option value="">Todos</option><option value="plugin">Plugins</option><option value="theme">Temas</option><option value="template">Templates</option></select></div><div class="field"><label for="plugintema_manage_status">Status</label><select id="plugintema_manage_status"><option value="">Todos</option><option value="publish">Publicado</option><option value="draft">Rascunho</option><option value="private">Privado</option></select></div></div>
    <div class="listing-meta-row plugintema-manage-toolbar"><div class="small" id="plugintema_manage_range">Mostrando 0 produtos.</div><div class="listing-page-size"><label for="plugintema_manage_page_size" class="small">Itens por página</label><input id="plugintema_manage_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric"><button class="btn-secondary btn-sm" id="plugintema_manage_download" type="button">⬇️ Baixar catálogo</button><button class="btn-danger btn-sm" id="plugintema_manage_delete" type="button">🗑️ Apagar catálogo</button></div></div>
    <div class="listing-pagination plugintema-manage-pagination"><button class="btn-secondary btn-sm" id="plugintema_manage_prev" type="button">← Anterior</button><span class="badge cs-page-jump" id="plugintema_manage_page_status">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span><button class="btn-secondary btn-sm" id="plugintema_manage_next" type="button">Próxima →</button></div>
    <div class="table-wrap"><table class="catalogos-table plugintema-manage-table"><thead><tr><th>ID</th><th>Nome</th><th>Tipo</th><th>Vers&atilde;o</th><th>Categorias</th><th>Status</th></tr></thead><tbody id="plugintema_manage_rows"><tr><td colspan="6">Selecione um cat&aacute;logo.</td></tr></tbody></table></div>
  </div>
</div>

<section
  class="tab-panel hidden"
  id="tab_panel_atualizacoes"
>
  <div class="card updates-operations-center updates-overview-card">
    <header class="updates-hero">
      <div><div class="section-title">Atualizações</div><div class="small">Prepare com segurança, revise o plano e execute sequencialmente.</div></div>
      <button class="btn-secondary" type="button" id="updates_refresh_btn">Atualizar dados</button>
      <div class="updates-progress-copy"><strong id="updates_progress_percent">0%</strong><span id="updates_progress_label">0 de 0 processados</span></div>
      <div class="updates-progress-track" role="progressbar" aria-label="Progresso geral" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span id="updates_progress_bar"></span></div>
      <div id="updates_now" class="updates-now">Nenhuma atualização em execução</div>
    </header>
    <div class="updates-lock" id="updates_execution_lock" role="status">Execução real bloqueada para homologação</div>
    <div id="updates_summary" class="updates-summary" aria-label="Resumo da fila"></div>
  </div>

  <div class="card updates-card-section updates-environment-card standard-update-accordion-card is-collapsed" data-update-accordion-kind="environment" aria-labelledby="updates_environment_title">
      <button class="standard-update-accordion-toggle" type="button" aria-expanded="false" aria-controls="updates_environment_details"><span class="standard-update-accordion-toggle-copy"><span class="standard-update-accordion-chevron" aria-hidden="true">▸</span><span class="standard-update-accordion-title">Ambiente</span></span><span class="standard-update-accordion-meta">Verificando pré-requisitos...</span></button>
      <div class="updates-section-heading"><div><div class="section-title standard-update-original-title" id="updates_environment_title">Ambiente</div><div id="updates_environment_summary" class="small">Verificando pré-requisitos...</div></div><div class="row"><button class="btn-secondary" type="button" id="updates_prerequisites_btn">Verificar</button></div></div>
      <div id="updates_environment_details">
        <div id="updates_environment_chips" class="updates-environment-chips" aria-live="polite"></div>
        <div class="plugintheme-session-diagnostic">
          <div><strong>Sessão PluginTheme</strong><div id="plugintheme_cookie_status" class="small" role="status">Cookies necessários: verificando...</div><div id="plugintheme_session_message" class="small" role="status"></div></div>
          <button class="btn-secondary" type="button" id="plugintheme_session_renew">🔐 Renovar sessão PluginTheme</button>
        </div>
      </div>
  </div>

  <div class="card updates-card-section updates-working-card" aria-labelledby="updates_working_title">
    <div class="section-title" id="updates_working_title">Preparação</div>
    <div class="hidden updates-conditional-controls" id="updates_working_controls">
    <div class="updates-subtitle" id="updates_filters_title">Busca e filtros</div>
    <div class="updates-filters" aria-label="Filtros da fila">
      <label>Status<select id="updates_status_filter"><option value="">Todos</option><option value="approved">Aprovado</option><option value="pending">Pendente</option><option value="validating">Validando</option><option value="downloading">Baixando</option><option value="staging">Preparando staging</option><option value="prepared">Preparado</option><option value="planned">Planejado</option><option value="plan_ready">Plano pronto</option><option value="installing">Instalando</option><option value="filesystem_validated">Sistema de arquivos validado</option><option value="updating_wordpress">Atualizando WordPress</option><option value="validating_wordpress">Validando WordPress</option><option value="validated">Validado</option><option value="dry_run_ready">Simulação pronta</option><option value="executing">Executando</option><option value="completed">Concluído</option><option value="blocked">Bloqueado</option><option value="failed">Falhou</option><option value="error">Erro</option><option value="interrupted">Interrompido</option><option value="rollback_required">Rollback necessário</option><option value="rolling_back">Executando rollback</option><option value="rolled_back">Rollback concluído</option></select></label>
      <label>Busca<input id="updates_search_filter" type="search" placeholder="Nome ou WooCommerce ID"></label>
      <label>Versão<select id="updates_version_filter"><option value="">Todas</option><option value="update">Somente com atualização</option><option value="advanced">Fonte avançou</option><option value="equal">Igual à comparação</option></select></label>
      <label>Relacionamento<select id="updates_relationship_filter"><option value="">Todos</option><option value="safe_auto">Vinculação automática</option><option value="manual_confirmed">Vinculação manual confirmada</option><option value="candidate">Candidato</option><option value="manual_rejected">Vinculação manual rejeitada</option><option value="confirmed_not_in_source">Confirmado como ausente no Ultrapack</option><option value="pending_review">Revisão pendente</option><option value="other">Outros</option></select></label>
      <button class="btn-secondary" type="button" id="updates_clear_filters">Limpar filtros</button>
    </div><div class="listing-meta-row"><strong id="updates_found_count">0 itens encontrados</strong><div class="listing-page-size"><label for="updates_page_size">Itens por página</label><input id="updates_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric"></div></div>
    <div class="listing-pagination"><button class="btn-secondary" type="button" id="updates_prev_page">← Anterior</button><span class="badge cs-page-jump" id="updates_page_label">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span><button class="btn-secondary" type="button" id="updates_next_page">Próxima →</button></div>
    <div class="updates-subtitle" id="updates_bulk_title">Operações em lote</div><div class="updates-bulkbar">
      <strong id="updates_selected_count">0 selecionados</strong>
      <button class="btn-secondary" type="button" id="updates_select_page">Selecionar página</button>
      <button class="btn-secondary" type="button" id="updates_select_filtered">Selecionar todos filtrados</button>
      <button class="btn-secondary" type="button" id="updates_clear_selection">Limpar seleção</button>
      <button class="btn-success" type="button" id="updates_prepare_selected">Preparar e gerar planos</button>
      <button class="btn-success" type="button" id="updates_enqueue_selected">Adicionar selecionados à fila</button>
    </div>
    <div id="updates_batch_progress" class="updates-batch-progress" aria-live="polite"></div>
    </div>
    <div id="updates_jobs" aria-live="polite"><div class="notice">Abra a aba para materializar os jobs aprovados.</div></div>
  </div>

  <div class="card updates-card-section updates-queue-section">
      <div class="updates-section-heading catalog-management-head"><div><div class="section-title">Fila de atualização</div><div id="updates_queue_meta" class="small">0 produtos · Fila parada</div></div><button class="btn-secondary catalog-management-button" id="open_update_lists_modal" type="button">Gerenciar Listas de Atualização</button></div>
      <div class="updates-queue-selector"><label>Lista ativa<select id="updates_queue_select"><option value="default">Padrão</option></select></label><span class="small" id="updates_queue_checkpoint">Nenhum progresso registrado.</span></div>
      <div class="row updates-queue-actions"><button class="btn-success" id="updates_queue_start" type="button">Executar fila</button><button class="btn-secondary" id="updates_queue_pause" type="button">Pausar</button><button class="btn-danger" id="updates_queue_cancel" type="button">Cancelar pendentes</button></div>
      <div class="hidden updates-conditional-controls" id="updates_queue_list_controls">
        <div class="updates-list-controls">
          <label>Buscar na fila<input id="updates_queue_search" type="search" placeholder="Nome ou WooCommerce ID"></label>
          <label>Estado<select id="updates_queue_status_filter"><option value="">Todos</option><option value="executing">Executando</option><option value="queued">Aguardando execução</option></select></label>
          <label>Itens por página<input id="updates_queue_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric"></label>
          <strong id="updates_queue_found_count">0 itens</strong>
        </div>
        <div class="listing-pagination"><button class="btn-secondary" id="updates_queue_prev" type="button">← Anterior</button><span class="badge cs-page-jump" id="updates_queue_page">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span><button class="btn-secondary" id="updates_queue_next" type="button">Próxima →</button></div>
      </div>
      <div id="updates_queue_jobs"></div>
  </div>

    <div data-operational-history-host data-history-type="update"></div>
    <details class="card updates-card-section updates-technical-log"><summary><span class="updates-disclosure-chevron" aria-hidden="true">▸</span><span class="section-title">Log técnico da sessão</span></summary><pre id="updates_log" class="log-output" aria-live="polite">Nenhum evento nesta sessão.</pre><div class="log-copy-row"><button class="btn-success" id="updates_copy_log" type="button">📋 Copiar log completo</button></div></details>
</section>

<div class="collection-modal hidden" id="update_lists_modal" role="dialog" aria-modal="true" aria-labelledby="update_lists_modal_title">
  <div class="collection-modal-backdrop" data-update-lists-close></div>
  <div class="card collection-modal-card update-lists-modal-card">
    <button class="comparison-link-modal-close collection-modal-close" type="button" data-update-lists-close aria-label="Fechar Gerenciar Listas de Atualização">&times;</button>
    <div class="section-title" id="update_lists_modal_title">Gerenciar Listas de Atualização</div>
    <div class="small">Crie, renomeie, ative ou apague listas persistidas de atualização.</div>
    <div class="update-lists-create"><label>Nova lista<input id="update_lists_new_name" maxlength="80" placeholder="Ex.: Atualizações de agosto"></label><button class="btn-success" id="update_lists_create" type="button">Criar lista</button></div>
    <div id="update_lists_rows" class="update-lists-rows" aria-live="polite"></div>
  </div>
</div>

<div class="collection-modal hidden" id="update_list_rename_modal" role="dialog" aria-modal="true" aria-labelledby="update_list_rename_title">
  <div class="collection-modal-backdrop" data-update-list-rename-close></div>
  <div class="card collection-modal-card update-list-small-modal">
    <button class="comparison-link-modal-close collection-modal-close" type="button" data-update-list-rename-close aria-label="Fechar">&times;</button>
    <div class="section-title" id="update_list_rename_title">Renomear Lista de Atualização</div>
    <p class="small" id="update_list_rename_help">Informe o novo nome da lista.</p>
    <label class="update-list-modal-field" for="update_list_rename_name">Novo nome<input id="update_list_rename_name" maxlength="80" autocomplete="off"></label>
    <div class="row update-list-modal-actions"><button class="btn-secondary" type="button" data-update-list-rename-close>Cancelar</button><button class="btn-success" id="update_list_rename_confirm" type="button">Salvar novo nome</button></div>
  </div>
</div>

<div class="collection-modal hidden" id="update_list_preview_modal" role="dialog" aria-modal="true" aria-labelledby="update_list_preview_title">
  <div class="collection-modal-backdrop" data-update-list-preview-close></div>
  <div class="card collection-modal-card update-list-preview-modal-card">
    <button class="comparison-link-modal-close collection-modal-close" type="button" data-update-list-preview-close aria-label="Fechar">&times;</button>
    <div class="section-title" id="update_list_preview_title">Visualizar Lista de Atualização</div>
    <div class="update-list-preview-summary" id="update_list_preview_summary"></div>
    <div class="update-list-preview-toolbar"><label>Pesquisar na lista<input id="update_list_preview_search" type="search" placeholder="Produto, WooCommerce ID ou estado"></label><span class="small" id="update_list_preview_count">0 itens</span></div>
    <div class="table-wrap"><table class="catalogos-table update-list-preview-table"><thead><tr><th>Posição</th><th>Woo ID</th><th>Produto</th><th>Estado</th><th>Versões</th><th>Atualização</th><th>Última etapa</th></tr></thead><tbody id="update_list_preview_rows"><tr><td colspan="7">Carregando...</td></tr></tbody></table></div>
    <div class="listing-meta-row update-list-preview-listing-meta">
      <div class="small" id="update_list_preview_result_meta">Mostrando 0 de 0 itens</div>
      <div class="listing-page-size"><label for="update_list_preview_page_size" class="small">Itens por página</label><input id="update_list_preview_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="5" inputmode="numeric"></div>
    </div>
    <div class="listing-pagination"><button class="btn-secondary" id="update_list_preview_prev" type="button">← Anterior</button><span class="badge cs-page-jump" id="update_list_preview_page">Página <input data-cs-page-input type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span>1</span></span><button class="btn-secondary" id="update_list_preview_next" type="button">Próxima →</button></div>
  </div>
</div>

<div class="comparison-link-modal hidden" id="update_execute_modal" role="dialog" aria-modal="true" aria-labelledby="update_execute_title">
  <div class="comparison-link-modal-backdrop" data-update-modal-close></div>
  <div class="comparison-link-modal-card update-execute-modal-card" role="document">
    <div class="comparison-link-modal-header"><div><div class="section-title" id="update_execute_title">Confirmar atualização individual</div><div class="small">Esta ação alterará o ZIP de produção e pt_versao.</div></div><button class="comparison-link-modal-close" type="button" data-update-modal-close aria-label="Fechar">×</button></div>
    <div id="update_execute_summary"></div>
    <label class="update-confirm-label" for="update_execute_confirmation">Confirmação obrigatória</label>
    <div class="small" id="update_execute_instruction"></div>
    <input id="update_execute_confirmation" autocomplete="off" spellcheck="false">
    <div class="row"><button class="btn-danger" id="update_execute_confirm" type="button" disabled>Executar atualização</button><button class="btn-secondary" type="button" data-update-modal-close>Cancelar</button></div>
  </div>
</div>

<section class="tab-panel hidden store-panel" id="tab_panel_loja" aria-labelledby="store_title">
  <section class="card wp-manual-monitor" aria-labelledby="wp_manual_monitor_title">
    <div class="section-title" id="wp_manual_monitor_title">Atualizações solicitadas pelo WordPress</div>
    <div class="wp-manual-grid" id="wp_manual_monitor" aria-live="polite" aria-busy="true">
      <div><span>Status do monitor</span><strong id="wp_manual_status">Carregando…</strong></div>
      <div><span>Última consulta</span><strong id="wp_manual_last">—</strong></div>
      <div><span>Próxima consulta</span><strong id="wp_manual_next">a cada 5s</strong></div>
      <div><span>Pedido atual</span><strong id="wp_manual_product">—</strong></div>
      <div><span>WooCommerce ID</span><strong id="wp_manual_product_id">—</strong></div>
      <div><span>Origem</span><strong id="wp_manual_source">ainda não definida</strong></div>
      <div><span>Versão atual</span><strong id="wp_manual_current">—</strong></div>
      <div><span>Versão encontrada</span><strong id="wp_manual_new">—</strong></div>
      <div class="wp-manual-state"><span>Estado</span><strong id="wp_manual_state">—</strong></div>
    </div>
    <div class="wp-manual-log" id="wp_manual_log" role="log" aria-label="Log das atualizações manuais">Aguardando o monitor…</div>
  </section>
  <div class="card store-hero">
    <div>
      <div class="section-title" id="store_title">Preços da loja</div>
      <div class="small">Aplique os mesmos preços a todos os plugins e/ou temas publicados. Apenas as variações anual e vitalícia serão alteradas.</div>
    </div>
  </div>
  <form class="card store-pricing-form" id="store_pricing_form" novalidate>
    <fieldset class="store-scope">
      <legend>Produtos incluídos</legend>
      <label><input type="checkbox" name="store_kind" value="plugin" checked> Plugins</label>
      <label><input type="checkbox" name="store_kind" value="theme" checked> Temas</label>
    </fieldset>
    <div class="store-price-grid">
      <fieldset class="store-price-card">
        <legend>Versão anual</legend>
        <label for="store_annual_regular">Valor original (R$)</label>
        <input id="store_annual_regular" name="annual_regular" inputmode="decimal" autocomplete="off" placeholder="Ex.: 79,90" required>
        <label for="store_annual_sale">Valor promocional (R$)</label>
        <input id="store_annual_sale" name="annual_sale" inputmode="decimal" autocomplete="off" placeholder="Vazio remove a promoção">
      </fieldset>
      <fieldset class="store-price-card">
        <legend>Versão vitalícia</legend>
        <label for="store_lifetime_regular">Valor original (R$)</label>
        <input id="store_lifetime_regular" name="lifetime_regular" inputmode="decimal" autocomplete="off" placeholder="Ex.: 149,90" required>
        <label for="store_lifetime_sale">Valor promocional (R$)</label>
        <input id="store_lifetime_sale" name="lifetime_sale" inputmode="decimal" autocomplete="off" placeholder="Vazio remove a promoção">
      </fieldset>
    </div>
    <div class="store-preview" id="store_preview" aria-live="polite" aria-busy="true"><span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando valores atuais de Plugins e Temas…</span></span></div>
    <div class="store-confirmation">
      <label for="store_confirmation">Confirmação obrigatória</label>
      <div class="small">Digite <strong>ALTERAR PRECOS</strong> para liberar a atualização em lote.</div>
      <input id="store_confirmation" name="confirmation" autocomplete="off" spellcheck="false">
    </div>
    <div class="store-form-actions"><button class="btn-success" id="store_apply_btn" type="submit" disabled>Aplicar preços em lote</button></div>
    <div class="notice hidden" id="store_result" role="status" aria-live="polite"></div>
  </form>
  <section class="card store-pack-card" aria-labelledby="store_pack_title">
    <div class="store-section-head">
      <div><div class="section-title" id="store_pack_title">Preços de pacotes / packs</div><div class="small">Edite individualmente os preços dos produtos bundle e dos produtos cadastrados na categoria Pack.</div></div>
      <button class="btn-secondary btn-sm" id="store_pack_refresh" type="button">Atualizar lista</button>
    </div>
    <div class="store-table-wrap" id="store_pack_prices" aria-live="polite" aria-busy="true">
      <span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando pacotes…</span></span>
    </div>
  </section>
  <section class="card store-quality-card" aria-labelledby="store_quality_title">
    <div class="store-section-head">
      <div><div class="section-title" id="store_quality_title">Breve descrição dos produtos</div><div class="small">Localize qualquer produto publicado cujo campo “Breve descrição sobre o produto” esteja vazio.</div></div>
    </div>
    <form class="store-quality-filter" id="store_missing_description_form">
      <label for="store_missing_description_search">Filtrar por nome ou ID</label>
      <div class="store-filter-row"><input id="store_missing_description_search" type="search" autocomplete="off" placeholder="Ex.: Elementor ou 92038"><button class="btn-secondary" type="submit">Buscar sem breve descrição</button></div>
    </form>
    <div class="store-table-wrap" id="store_missing_descriptions" aria-live="polite">
      <div class="small">Use o filtro para consultar os produtos sem breve descrição.</div>
    </div>
  </section>
</section>

<section
  class="tab-panel hidden"
  id="tab_panel_adicoes"
>
  <div class="card">
    <div class="section-title">Adições</div>

    <div class="notice">
      Nesta aba serão exibidos os produtos novos aprovados para cadastro na PluginTema.
      Nenhum produto será cadastrado automaticamente nesta fase.
    </div>
  </div>
</section>

  </div>

  <div
    class="comparison-link-modal hidden"
    id="comparison_link_modal"
    role="dialog"
    aria-modal="true"
    aria-labelledby="comparison_link_modal_title"
    aria-describedby="comparison_link_modal_product"
    tabindex="-1"
  >
    <div class="comparison-link-modal-backdrop"></div>

    <div class="comparison-link-modal-card" role="document">
      <div class="comparison-link-modal-header">
        <div>
          <div
            class="section-title"
            id="comparison_link_modal_title"
          >
            Vincular produto
          </div>

          <div
            class="comparison-cell-meta"
            id="comparison_link_modal_product"
          ></div>
        </div>

        <button
          type="button"
          class="comparison-link-modal-close"
          id="comparison_link_modal_close"
          aria-label="Fechar"
        >
          ×
        </button>
      </div>

      <div class="comparison-link-modal-section">
        <div class="comparison-link-modal-section-title">
          Produtos sugeridos
        </div>

        <div
          class="comparison-link-modal-suggestions"
          id="comparison_link_modal_suggestions"
        >
          <div class="comparison-candidate-empty">
            Nenhum produto sugerido.
          </div>
        </div>
      </div>

      <div class="comparison-link-modal-divider">
        Ou procure outro produto na planilha
      </div>

      <div class="comparison-link-modal-search">
        <label class="sr-only" for="comparison_link_modal_query">Pesquisar no catálogo oposto</label>
        <input
          type="search"
          id="comparison_link_modal_query"
          placeholder="Digite o nome, ID, versão ou categoria"
          autocomplete="off"
        >

        <button
          type="button"
          class="btn-primary"
          id="comparison_link_modal_search"
        >
          Buscar
        </button>
      </div>

      <div
        class="comparison-link-modal-status"
        id="comparison_link_modal_status"
        role="status"
        aria-live="polite"
        hidden
      ></div>

      <div
        class="comparison-link-modal-results"
        id="comparison_link_modal_results"
      >
        <div class="comparison-candidate-empty">
          Digite um termo para localizar outro produto.
        </div>
      </div>
    </div>
  </div>

  <div
    class="comparison-link-modal comparison-diagnostic-modal hidden"
    id="comparison_diagnostic_modal"
    role="dialog"
    aria-modal="true"
    aria-labelledby="comparison_diagnostic_modal_title"
    tabindex="-1"
  >
    <div class="comparison-link-modal-backdrop"></div>
    <div class="comparison-link-modal-card comparison-diagnostic-modal-card" role="document">
      <div class="comparison-link-modal-header">
        <div>
          <div class="section-title" id="comparison_diagnostic_modal_title">Diagnóstico da comparação</div>
          <div class="comparison-cell-meta" id="comparison_diagnostic_modal_subtitle"></div>
        </div>
        <button type="button" class="comparison-link-modal-close" id="comparison_diagnostic_modal_close" aria-label="Fechar diagnóstico">×</button>
      </div>
      <div class="comparison-diagnostic-content" id="comparison_diagnostic_modal_content"></div>
    </div>
  </div>

  <script id="monitor-boot-data" type="application/json">__BOOT_JSON__</script>
  __SCRIPT_BLOCK__
</body>
</html>
"""


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "sim"}:
        return True
    if text in {"0", "false", "no", "n", "off", "nao", "não"}:
        return False
    return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _boot_log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}")


def _setting_value(*names: str, default: Any) -> Any:
    for name in names:
        if hasattr(settings, name):
            value = getattr(settings, name)
            if value not in (None, ""):
                return value
    return default


def get_panel_host() -> str:
    return str(_setting_value("PANEL_HOST", "WEB_HOST", default="127.0.0.1"))


def get_panel_port() -> int:
    return max(1, _to_int(_setting_value("PANEL_PORT", "WEB_PORT", default=8765), 8765))


def get_auto_open_browser() -> bool:
    return _to_bool(_setting_value("PANEL_AUTO_OPEN_BROWSER", "WEB_AUTO_OPEN_BROWSER", default=True), True)


def get_include_inline_assets() -> bool:
    return _to_bool(_setting_value("PANEL_INCLUDE_INLINE_ASSETS", "WEB_INCLUDE_INLINE_ASSETS", default=False), False)


def build_panel_url(host: str | None = None, port: int | None = None, *, path: str = "/") -> str:
    resolved_host = str(host or get_panel_host()).strip() or "127.0.0.1"
    resolved_port = get_panel_port() if port is None else max(1, int(port))
    normalized_path = "/" + str(path or "/").lstrip("/")
    return f"http://{resolved_host}:{resolved_port}{normalized_path}"


def _build_run_path(run_id: str | None = None, subpath: str = "/") -> str:
    normalized_run_id = _normalize_spaces(run_id)
    if not normalized_run_id:
        return "/"

    encoded_run_id = quote(normalized_run_id, safe="")
    normalized_subpath = "/" + str(subpath or "/").lstrip("/")
    if normalized_subpath == "/":
        return f"/run/{encoded_run_id}/"
    return f"/run/{encoded_run_id}{normalized_subpath}"


def build_run_panel_url(
    run_id: str | None,
    *,
    host: str | None = None,
    port: int | None = None,
) -> str:
    return build_panel_url(host=host, port=port, path=_build_run_path(run_id, "/"))


def _build_panel_title(context: Any = None) -> str:
    return "CrapScraper"


def _panel_asset_candidates(kind: str) -> list[Path]:
    kind = str(kind or "").strip().lower()
    candidates: list[Path] = []

    if kind == "css":
        candidates.extend(
            [
                settings.PANEL_CSS_PATH,
                settings.APP_DIR / "assets" / "panel.css",
                settings.APP_DIR / "ui" / "assets" / "styles.css",
            ]
        )
    elif kind == "js":
        candidates.extend(
            [
                settings.PANEL_JS_PATH,
                settings.APP_DIR / "assets" / "panel.js",
                settings.APP_DIR / "ui" / "assets" / "app.js",
            ]
        )

    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in candidates:
        resolved = Path(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def _read_first_existing_asset(kind: str) -> str | None:
    for path in _panel_asset_candidates(kind):
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            continue
    return None


def _has_external_panel_assets() -> bool:
    return _read_first_existing_asset("css") is not None and _read_first_existing_asset("js") is not None


def _panel_asset_version(kind: str) -> str:
    for path in _panel_asset_candidates(kind):
        try:
            if path.is_file():
                return str(path.stat().st_mtime_ns)
        except OSError:
            continue
    return "0"


def _get_primary_run_mode() -> str:
    return str(getattr(settings, "RUN_MODE_PRIMARY", "primary") or "primary").strip().lower()


def _get_known_run_option_keys() -> set[str]:
    return {
        "verify_mode",
        "scope_mode",
        "scope_start",
        "scope_end",
        "scope_match_text",
        "save_every_items",
        "save_every_minutes",
        "selected_categories",
    }


def _extract_run_options(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None

    if isinstance(payload.get("run_options"), Mapping):
        return dict(payload.get("run_options", {}))

    options = {
        key: payload[key]
        for key in _get_known_run_option_keys()
        if key in payload
    }
    return options or None


def _extract_run_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}

    if isinstance(payload.get("run_payload"), Mapping):
        return dict(payload.get("run_payload", {}))

    excluded = _get_known_run_option_keys() | {
        "run_options",
        "run_payload",
        "site_key",
        "item_type_key",
        "account_key",
        "slot_name",
        "load_summary",
    }

    return {
        str(key): value
        for key, value in payload.items()
        if key not in excluded
    }


def _is_run_manager(value: Any) -> bool:
    return all(
        hasattr(value, attr)
        for attr in (
            "get_or_create_primary_run",
            "get_run",
            "create_run",
            "list_runs_public",
        )
    )


def _register_existing_app(manager: ScraperRunManager, app: Any) -> Any:
    if app is None:
        return app

    run_id = _normalize_spaces(getattr(app, "run_id", "")) or f"run-{id(app):x}"

    existing = manager._runs.get(run_id)  # type: ignore[attr-defined]
    if existing is not None and existing is not app:
        raise RuntimeError(f"Já existe uma execução registrada com run_id={run_id!r}.")

    manager._runs[run_id] = app  # type: ignore[attr-defined]
    if not getattr(manager, "_primary_run_id", ""):
        manager._primary_run_id = run_id  # type: ignore[attr-defined]

    setter = getattr(app, "set_manager", None)
    if callable(setter):
        with suppress(Exception):
            setter(manager, run_id=run_id)
    else:
        with suppress(Exception):
            setattr(app, "manager", manager)
        with suppress(Exception):
            setattr(app, "run_id", run_id)

    return app


def _ensure_manager(target: Any = None) -> ScraperRunManager:
    if _is_run_manager(target):
        manager = target
        with suppress(Exception):
            manager.get_or_create_primary_run()
        return manager

    if target is not None:
        existing = getattr(target, "manager", None)
        if _is_run_manager(existing):
            return existing

        existing = getattr(target, "_web_run_manager", None)
        if _is_run_manager(existing):
            return existing

        manager = ScraperRunManager()
        _register_existing_app(manager, target)
        with suppress(Exception):
            setattr(target, "_web_run_manager", manager)
        return manager

    manager = ScraperRunManager()
    manager.get_or_create_primary_run()
    return manager


def _get_primary_app(target: Any = None) -> Any:
    manager = _ensure_manager(target)
    return manager.get_or_create_primary_run()


def _get_run_app(target: Any = None, run_id: str | None = None) -> Any:
    manager = _ensure_manager(target)
    if _normalize_spaces(run_id):
        return manager.get_run(run_id)
    return manager.get_or_create_primary_run()


def _get_primary_run_id(target: Any = None) -> str:
    app = _get_primary_app(target)
    return _normalize_spaces(getattr(app, "run_id", ""))


def _build_run_summary(app: Any) -> dict[str, Any]:
    if app is None:
        return {}

    context_payload = _get_context_payload(app)
    state_payload = _build_state_payload(app)
    state_data = dict(state_payload.get("data", state_payload) or {}) if isinstance(state_payload, Mapping) else {}

    return {
        "run_id": _normalize_spaces(getattr(app, "run_id", "")),
        "context": dict(context_payload.get("public", {}) or {}),
        "status": state_data.get("status", "Parado"),
        "summary": state_data.get("summary", ""),
        "running": bool(state_data.get("running", False)),
        "paused": bool(state_data.get("paused", False)),
        "updated_at": state_data.get("updated_at", ""),
        "panel_path": _build_run_path(getattr(app, "run_id", ""), "/"),
    }


def _list_runs_public(target: Any = None) -> list[dict[str, Any]]:
    manager = _ensure_manager(target)

    lister = getattr(manager, "list_runs_public", None)
    if callable(lister):
        with suppress(Exception):
            payload = lister()
            if isinstance(payload, list):
                return [dict(item) for item in payload if isinstance(item, Mapping)]

    runs: list[dict[str, Any]] = []
    with suppress(Exception):
        runs_map = dict(getattr(manager, "_runs", {}) or {})
        runs = [_build_run_summary(app) for app in runs_map.values()]
    return runs


def _build_run_endpoints(run_id: str | None) -> dict[str, str]:
    return {
        "boot": _build_run_path(run_id, "/boot"),
        "state": _build_run_path(run_id, "/state"),
        "logsFull": _build_run_path(run_id, "/logs_full"),
        "context": _build_run_path(run_id, "/context"),
        "health": _build_run_path(run_id, "/health"),
        "config": _build_run_path(run_id, "/config"),
        "start": _build_run_path(run_id, "/start"),
        "continue": _build_run_path(run_id, "/continue"),
        "pause": _build_run_path(run_id, "/pause"),
        "resume": _build_run_path(run_id, "/resume"),
        "stop": _build_run_path(run_id, "/stop"),
        "slotCreate": _build_run_path(run_id, "/slot/create"),
        "slotSwitch": _build_run_path(run_id, "/slot/switch"),
        "slotDefault": _build_run_path(run_id, "/slot/default"),
        "slotDelete": _build_run_path(run_id, "/slot/delete"),
        "slotClear": _build_run_path(run_id, "/slot/clear"),
        "slotRename": _build_run_path(run_id, "/slot/rename"),
        "slotRemoveContext": _build_run_path(run_id, "/slot/remove-context"),
        "slotRemoveZeroContexts": _build_run_path(run_id, "/slot/remove-zero-contexts"),
        "runPrefix": _build_run_path(run_id, "/run/"),
        "panelCss": "/panel.css",
        "panelJs": "/panel.js",
        "runs": "/runs",
        "runCreate": "/run/create",
        "runDelete": "/run/delete",
        "queueGet": "/fila",
        "queueSave": "/fila",
        "runPanelPrefix": "/run/",
        "currentRunPanel": _build_run_path(run_id, "/"),
        "catalogosData": "/catalogos/data",
        "catalogosDownloadCsv": "/catalogos/download/csv",
        "catalogosDownloadStatus": "/catalogos/download/status",
        "catalogosDownloadLog": "/catalogos/download/log",
        "plugintemaCatalogExport": "/plugintema/catalogo/exportar",
        
"comparisonData": "/comparacao/data",
"comparisonSources": "/comparacao/fontes",
"plugintemaCatalogGenerate": "/plugintema/catalogo/gerar",
"plugintemaCatalogOptions": "/plugintema/catalogo/opcoes",
"plugintemaProductSearch": "/plugintema/catalogo/pesquisar",
"plugintemaCatalogManage": "/plugintema/catalogo/gerenciar",
        "plugintemaCatalogDownload": "/plugintema/catalogo/baixar",
        "storePricing": "/loja/precos",
        "wordpressManualStatus": "/loja/wordpress-manual/status",
"comparisonProducts": "/comparacao/produtos",
"comparisonRelationshipSave": "/comparacao/vinculo/salvar",
}


def _extract_run_route(path: str) -> tuple[str, str] | None:
    normalized_path = "/" + str(path or "/").lstrip("/")
    if not normalized_path.startswith("/run/"):
        return None

    stripped = normalized_path[len("/run/"):]
    if not stripped:
        return None

    parts = stripped.split("/", 1)
    run_id = _normalize_spaces(parts[0])
    if not run_id:
        return None

    if len(parts) == 1 or not parts[1]:
        return run_id, "/"

    return run_id, "/" + parts[1].lstrip("/")


def _get_context_payload(app: Any) -> dict[str, Any]:
    payload = {
        "public": {},
        "runtime": {},
        "configured": False,
        "run_options": {},
        "continue_info": {},
    }

    getter = getattr(app, "get_current_context_public", None)
    if callable(getter):
        with suppress(Exception):
            value = getter()
            if isinstance(value, Mapping):
                payload["public"] = dict(value)

    getter = getattr(app, "get_runtime_context_dict", None)
    if callable(getter):
        with suppress(Exception):
            value = getter()
            if isinstance(value, Mapping):
                payload["runtime"] = dict(value)

    getter = getattr(app, "is_current_context_configured", None)
    if callable(getter):
        with suppress(Exception):
            payload["configured"] = bool(getter())

    getter = getattr(app, "get_run_options_public", None)
    if callable(getter):
        with suppress(Exception):
            value = getter()
            if isinstance(value, Mapping):
                payload["run_options"] = dict(value)

    getter = getattr(app, "get_continue_info", None)
    if callable(getter):
        with suppress(Exception):
            value = getter()
            if isinstance(value, Mapping):
                payload["continue_info"] = dict(value)

    return payload


def _build_state_payload(app: Any) -> dict[str, Any]:
    builder = getattr(app, "build_public_state_payload", None)
    if callable(builder):
        with suppress(Exception):
            payload = builder()
            if isinstance(payload, Mapping):
                return dict(payload)

    snapshot = getattr(app, "snapshot", None)
    if callable(snapshot):
        with suppress(Exception):
            payload = snapshot()
            if isinstance(payload, Mapping):
                return dict(payload)

    state = getattr(app, "state", None)
    if state is not None:
        snap = getattr(state, "snapshot", None)
        if callable(snap):
            with suppress(Exception):
                payload = snap()
                if isinstance(payload, Mapping):
                    return dict(payload)

    return {"data": {}, "logs": []}


def _get_full_logs_text(app: Any) -> str:
    state = getattr(app, "state", None)
    if state is None:
        return ""

    getter = getattr(state, "full_logs_text", None)
    if callable(getter):
        with suppress(Exception):
            return str(getter())

    logs = getattr(state, "logs", None)
    if isinstance(logs, list):
        return "\n".join(str(item) for item in logs)

    return ""


def _iter_catalog_contexts_for_slot(slot_name: str) -> list[dict[str, str]]:
    slot_dir = get_slot_dir(slot_name)
    if not slot_dir.exists() or not slot_dir.is_dir():
        return []

    contexts: list[dict[str, str]] = []

    for site_dir in sorted(slot_dir.iterdir(), key=lambda p: p.name.lower()):
        if not site_dir.is_dir():
            continue

        for item_type_dir in sorted(site_dir.iterdir(), key=lambda p: p.name.lower()):
            if not item_type_dir.is_dir():
                continue

            for account_dir in sorted(item_type_dir.iterdir(), key=lambda p: p.name.lower()):
                if not account_dir.is_dir():
                    continue

                contexts.append(
                    {
                        "slot_name": slot_name,
                        "site_key": site_dir.name,
                        "item_type_key": item_type_dir.name,
                        "account_key": account_dir.name,
                    }
                )

    if contexts:
        return contexts

    return [
        {
            "slot_name": slot_name,
            "site_key": "",
            "item_type_key": "",
            "account_key": "",
        }
    ]


def _build_catalog_entry(slot_name: str, site_key: str, item_type_key: str, account_key: str) -> dict[str, Any]:
    has_context = bool(site_key and item_type_key and account_key)
    slot_dir = get_slot_dir(slot_name)

    catalog_items: list[dict[str, Any]] = []
    status_text = ""
    csv_exists = False
    status_exists = False
    log_exists = False
    csv_path = ""
    status_path = ""
    log_path = ""
    updated_at = ""
    updated_at_timestamp = 0.0

    if has_context:
        paths = build_context_paths(
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        catalog_items = load_catalog_items(
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        status_text = load_status_text(
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        csv_exists = path_exists(paths.output_csv_path)
        status_exists = path_exists(paths.status_txt_path)
        log_exists = path_exists(paths.runtime_log_path)
        csv_path = str(paths.output_csv_path)
        status_path = str(paths.status_txt_path)
        log_path = str(paths.runtime_log_path)
    else:
        if slot_dir.exists():
            for child in slot_dir.rglob("catalog.csv"):
                csv_exists = True
                csv_path = str(child)
                break

            for child in slot_dir.rglob("status.txt"):
                status_exists = True
                status_path = str(child)
                with suppress(Exception):
                    status_text = read_text(child, "")
                break

            for child in slot_dir.rglob("runtime.log"):
                log_exists = True
                log_path = str(child)
                break

    status_preview = str(status_text or "").strip()
    if len(status_preview) > 280:
        status_preview = status_preview[:280].rstrip() + "..."

    dated_paths = [Path(value) for value in (csv_path, status_path, log_path) if value]
    modified = [path.stat().st_mtime for path in dated_paths if path.exists()]
    if modified:
        updated_at_timestamp = max(modified)
        updated_at = datetime.fromtimestamp(updated_at_timestamp).strftime("%d/%m/%Y %H:%M")

    return {
        "catalogo_nome": slot_name,
        "slot_name": slot_name,
        "site_key": site_key,
        "item_type_key": item_type_key,
        "account_key": account_key,
        "items_count": len(catalog_items),
        "csv_exists": csv_exists,
        "status_exists": status_exists,
        "log_exists": log_exists,
        "csv_path": csv_path,
        "status_path": status_path,
        "log_path": log_path,
        "status_preview": status_preview,
        "updated_at": updated_at,
        "updated_at_timestamp": updated_at_timestamp,
        "download_csv_url": (
            f"/catalogos/download/csv?slot_name={quote(slot_name)}&site_key={quote(site_key)}&item_type_key={quote(item_type_key)}&account_key={quote(account_key)}"
            if has_context
            else ""
        ),
        "download_status_url": (
            f"/catalogos/download/status?slot_name={quote(slot_name)}&site_key={quote(site_key)}&item_type_key={quote(item_type_key)}&account_key={quote(account_key)}"
            if has_context
            else ""
        ),
        "download_log_url": (
            f"/catalogos/download/log?slot_name={quote(slot_name)}&site_key={quote(site_key)}&item_type_key={quote(item_type_key)}&account_key={quote(account_key)}"
            if has_context
            else ""
        ),
    }


def _build_catalogs_payload() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    slot_names: list[str] = []

    for slot in build_slots_public_list():
        slot_name = str(slot.get("name", "") or "").strip()
        if not slot_name:
            continue

        slot_names.append(slot_name)

        for context_item in _iter_catalog_contexts_for_slot(slot_name):
            rows.append(
                _build_catalog_entry(
                    context_item.get("slot_name", ""),
                    context_item.get("site_key", ""),
                    context_item.get("item_type_key", ""),
                    context_item.get("account_key", ""),
                )
            )

    rows.sort(
        key=lambda item: (
            str(item.get("catalogo_nome", "")).lower(),
            str(item.get("site_key", "")).lower(),
            str(item.get("item_type_key", "")).lower(),
            str(item.get("account_key", "")).lower(),
        )
    )

    return {
        "ok": True,
        "catalogos": rows,
        "catalogo_nomes": sorted(set(slot_names)),
    }

def _build_comparison_sources_payload() -> dict[str, Any]:
    saved_catalogs: list[dict[str, Any]] = []

    catalogs_payload = _build_catalogs_payload()

    for row in catalogs_payload.get("catalogos", []):
        if not row.get("csv_exists"):
            continue

        csv_path_text = _normalize_spaces(row.get("csv_path"))
        if not csv_path_text:
            continue

        csv_path = Path(csv_path_text)
        if not csv_path.exists() or not csv_path.is_file():
            continue

        slot_name = _normalize_spaces(
            row.get("slot_name") or row.get("catalogo_nome")
        )
        site_key = _normalize_spaces(row.get("site_key"))
        item_type_key = _normalize_spaces(row.get("item_type_key"))
        account_key = _normalize_spaces(row.get("account_key"))

        if not all(
            [
                slot_name,
                site_key,
                item_type_key,
                account_key,
            ]
        ):
            continue

        catalog_id = "|".join(
            [
                "saved",
                slot_name,
                site_key,
                item_type_key,
                account_key,
            ]
        )

        items_count = max(
            0,
            _to_int(row.get("items_count"), 0),
        )

        saved_catalogs.append(
            {
                "id": catalog_id,
                "kind": "saved",
                "label": (
                    f"{'Padrão' if slot_name.lower() == 'default' else slot_name}  "
                    f"{site_key}  {item_type_key}  {account_key} | "
                    f"{_normalize_spaces(row.get('updated_at')) or 'Data não registrada'} | "
                    f"{items_count:,} itens".replace(",", ".")
                ),
                "slot_name": slot_name,
                "site_key": site_key,
                "item_type_key": item_type_key,
                "account_key": account_key,
                "items_count": items_count,
                "updated_at": _normalize_spaces(row.get("updated_at")),
            }
        )

    imports_dir = Path(settings.COMPARISON_IMPORTS_DIR)
    imports_dir.mkdir(parents=True, exist_ok=True)

    imported_catalogs: list[dict[str, Any]] = []

    for csv_path in sorted(
        imports_dir.glob("*.csv"),
        key=lambda item: item.name.lower(),
    ):
        friendly_label = f"[Importado] {csv_path.name}"
        if csv_path.name.startswith("plugintema-"):
            parts = csv_path.stem.split("-")
            mode_labels = {"plugin": "Plugins", "theme": "Temas", "template": "Templates", "selection": "Seleção", "custom": "Personalizado"}
            mode_label = mode_labels.get(parts[1] if len(parts) > 1 else "", "Catálogo")
            if len(parts) > 5:
                custom_name = " ".join(parts[2:-3]).replace("_", " ").strip()
                if custom_name:
                    mode_label = custom_name
            generated_at = datetime.fromtimestamp(csv_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            friendly_label = mode_label.upper()
        items_count = plugin_count = theme_count = template_count = 0
        if csv_path.name.startswith("plugintema-"):
            with suppress(Exception):
                with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                items_count = len(rows)
                for catalog_row in rows:
                    categories = [value.strip() for value in str(catalog_row.get("Categorias", "") or "").split(",") if value.strip()]
                    if categories_match_catalog_kind(categories, "template"):
                        template_count += 1
                    elif categories_match_catalog_kind(categories, "theme"):
                        theme_count += 1
                    elif categories_match_catalog_kind(categories, "plugin"):
                        plugin_count += 1
            friendly_label = (
                f"{friendly_label} | {generated_at} | "
                f"{items_count:,} itens".replace(",", ".")
            )
        imported_catalogs.append(
            {
                "id": f"imported|{csv_path.name}",
                "kind": "imported",
                "label": friendly_label,
                "filename": csv_path.name,
                "size": csv_path.stat().st_size,
                "updated_at": datetime.fromtimestamp(csv_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "items_count": items_count,
                "plugin_count": plugin_count,
                "theme_count": theme_count,
                "template_count": template_count,
            }
        )

    return {
        "ok": True,
        "saved_catalogs": saved_catalogs,
        "imported_catalogs": imported_catalogs,
    }


def _parse_plugintema_filters(payload: Mapping[str, Any]) -> tuple[str, CatalogFilters]:
    mode = str(payload.get("mode", "plugin") or "plugin").strip().lower()
    if mode not in {"plugin", "theme", "template", "selection", "custom"}:
        raise ValueError("Modo de catÃ¡logo invÃ¡lido.")
    if mode == "selection":
        kinds = tuple(dict.fromkeys(
            str(value).strip().lower() for value in (payload.get("kinds") or [])
            if str(value).strip()
        ))
        if not kinds:
            raise ValueError("Selecione pelo menos um tipo de produto.")
    else:
        kind = mode if mode in {"plugin", "theme", "template"} else str(payload.get("kind", "plugin") or "plugin")
        kinds = {"both": ("plugin", "theme"), "all": ("plugin", "theme", "template")}.get(kind, (kind,))
    if any(value not in {"plugin", "theme", "template"} for value in kinds):
        raise ValueError("Tipo de produto invÃ¡lido.")
    status = "publish" if mode != "custom" else str(payload.get("status", "publish") or "publish")
    statuses = ("publish", "draft", "private") if status == "all" else (status,)
    if any(value not in {"publish", "draft", "private"} for value in statuses):
        raise ValueError("Status de produto invÃ¡lido.")
    raw_ids = str(payload.get("product_ids", "") or "").strip()
    product_ids: tuple[int, ...] = ()
    if raw_ids:
        pieces = [piece.strip() for piece in raw_ids.split(",") if piece.strip()]
        if any(not piece.isdigit() or int(piece) <= 0 for piece in pieces):
            raise ValueError("Informe IDs positivos separados por vÃ­rgula.")
        product_ids = tuple(dict.fromkeys(int(piece) for piece in pieces))
    categories = tuple(
        str(value).strip() for value in (payload.get("categories") or [])
        if str(value).strip()
    )
    version = str(payload.get("version", "all") or "all")
    if version not in {"all", "with", "without"}:
        raise ValueError("Filtro de versÃ£o invÃ¡lido.")
    return mode, CatalogFilters(
        kinds=kinds, categories=categories, statuses=statuses,
        query=str(payload.get("query", "") or "").strip(),
        product_ids=product_ids, version=version,
    )


def _generate_plugintema_comparison_catalog(payload: Mapping[str, Any], woo: Any) -> dict[str, Any]:
    mode, filters = _parse_plugintema_filters(payload)
    products = read_all_products(woo, statuses=filters.statuses)
    rows = build_filtered_catalog_rows(products, filters)
    imports_dir = Path(settings.COMPARISON_IMPORTS_DIR)
    imports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    raw_name = str(payload.get("catalog_name", "") or "").strip()
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_name).strip("_-")[:60]
    name_part = f"-{safe_name}" if safe_name else ""
    filename = f"plugintema-{mode}{name_part}-{stamp}.csv"
    destination = imports_dir / filename
    temporary = imports_dir / f".{filename}.tmp"
    try:
        temporary.write_bytes(encode_catalog_csv(rows))
        os.replace(temporary, destination)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()
    return {
        "ok": True,
        "catalog_id": f"imported|{filename}",
        "filename": filename,
        "products_count": len(rows),
        "message": f"Catálogo PluginTema atualizado: {len(rows)} produtos encontrados.",
    }


def _resolve_comparison_catalog_path(
    catalog_id: str,
) -> Path | None:
    normalized_id = _normalize_spaces(catalog_id)
    if not normalized_id or "|" not in normalized_id:
        return None

    kind, value = normalized_id.split("|", 1)

    if kind == "saved":
        parts = value.split("|")

        if len(parts) != 4:
            return None

        slot_name, site_key, item_type_key, account_key = parts

        paths = build_context_paths(
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )

        resolved_path = paths.output_csv_path

    elif kind == "imported":
        filename = Path(value).name

        # Impede caminhos como ../../arquivo.csv.
        if filename != value:
            return None

        imports_dir = Path(
            settings.COMPARISON_IMPORTS_DIR
        ).resolve()

        resolved_path = (
            imports_dir / filename
        ).resolve()

        if resolved_path.parent != imports_dir:
            return None

    else:
        return None

    if not resolved_path.exists():
        return None

    if not resolved_path.is_file():
        return None

    return resolved_path  


def _resolve_catalog_file_path(
    *,
    file_kind: str,
    slot_name: str,
    site_key: str,
    item_type_key: str,
    account_key: str,
) -> Path | None:
    if not (slot_name and site_key and item_type_key and account_key):
        return None

    paths = build_context_paths(
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )

    if file_kind == "csv":
        return paths.output_csv_path
    if file_kind == "status":
        return paths.status_txt_path
    if file_kind == "log":
        return paths.runtime_log_path
    return None


def build_boot_payload(target: Any = None, *, run_id: str | None = None) -> dict[str, Any]:
    manager = _ensure_manager(target)
    app = _get_run_app(manager, run_id)

    data: dict[str, Any] = {}
    getter = getattr(app, "get_boot_payload", None)
    if callable(getter):
        with suppress(Exception):
            payload = getter()
            if isinstance(payload, Mapping):
                data = dict(payload)

    if not data:
        context_payload = _get_context_payload(app)
        data = {
            "ok": True,
            "settings": settings.build_structural_public_settings(),
            "context": context_payload.get("public", {}),
            "runtime_context": context_payload.get("runtime", {}),
            "configured": context_payload.get("configured", False),
            "run_options": context_payload.get("run_options", {}),
            "continue_info": context_payload.get("continue_info", {}),
        }

    state_payload = data.get("state")
    if not isinstance(state_payload, Mapping):
        state_payload = _build_state_payload(app)

    resolved_run_id = _normalize_spaces(getattr(app, "run_id", run_id or ""))
    data["ok"] = True
    data["run_id"] = resolved_run_id
    data["state"] = dict(state_payload)
    data["initial_state"] = dict(state_payload)
    data["poll_interval_ms"] = int(getattr(settings, "STATE_POLL_INTERVAL_MS", 1200))
    data["endpoints"] = _build_run_endpoints(resolved_run_id)
    data["title"] = _build_panel_title(getattr(app, "get_current_context", lambda: None)())
    data["runs"] = _list_runs_public(manager)
    data["primary_run_id"] = _get_primary_run_id(manager)
    data["current_run_url"] = _build_run_path(resolved_run_id, "/")
    data["manager_mode"] = True
    return data


def render_panel_page(
    app: Any = None,
    *,
    manager: Any | None = None,
    run_id: str | None = None,
    include_inline_assets: bool = False,
    styles_href: str = "/panel.css",
    script_src: str = "/panel.js",
) -> str:
    target = manager if manager is not None else app
    boot_payload = build_boot_payload(target, run_id=run_id or getattr(app, "run_id", None))
    runtime_context = dict(boot_payload.get("runtime_context", {}) or {})
    context_payload = dict(boot_payload.get("context", {}) or {})

    title = str(boot_payload.get("title") or _build_panel_title(context_payload))
    site_label = str(runtime_context.get("site_label") or context_payload.get("site", {}).get("label") or context_payload.get("site_key") or "-")
    item_type_label = str(
        runtime_context.get("item_type_label_plural")
        or context_payload.get("item_type", {}).get("label_plural")
        or context_payload.get("item_type_key")
        or "-"
    )
    account_label = str(runtime_context.get("account_label") or context_payload.get("account", {}).get("label") or context_payload.get("account_key") or "-")
    slot_name = str(runtime_context.get("slot_name") or context_payload.get("slot_name") or "-")
    slot_display_name = "Principal" if slot_name.casefold() == "default" else slot_name

    if include_inline_assets:
        styles_block = f"<style>{INLINE_FALLBACK_CSS}</style>"
        extras = []
        for extra_name in ("catalog_cards_refinement.js", "pagination_autojump.js"):
            try:
                extra_source = (settings.APP_DIR / "static" / extra_name).read_text(encoding="utf-8")
            except OSError:
                continue
            safe_source = extra_source.replace("</script>", "<\\/script>")
            extras.append(f"<script>{safe_source}</script>")
        script_block = f"<script>{INLINE_FALLBACK_JS}</script>" + "".join(extras)
    else:
        if styles_href == "/panel.css":
            styles_href = f"{styles_href}?v={_panel_asset_version('css')}"
        if script_src == "/panel.js":
            script_src = f"{script_src}?v={_panel_asset_version('js')}"
        styles_block = (
            f'<link rel="stylesheet" '
            f'href="{escape(styles_href, quote=True)}">'
        )
        script_block = (
            f'<script src="{escape(script_src, quote=True)}"></script>'
            '<script src="/catalog_cards_refinement.js"></script>'
            '<script src="/pagination_autojump.js"></script>'
        )

    boot_json = json.dumps(
        boot_payload,
        ensure_ascii=False,
    ).replace("</", "<\\/")

    return (
        HTML_TEMPLATE
        .replace("__TITLE__", escape(title))
        .replace("__HEADER_TITLE__", escape(title))
        .replace("__SITE_LABEL__", escape(site_label))
        .replace("__ITEM_TYPE_LABEL__", escape(item_type_label))
        .replace("__ACCOUNT_LABEL__", escape(account_label))
        .replace("__SLOT_NAME__", escape(slot_display_name))
        .replace("__STYLES_BLOCK__", styles_block)
        .replace("__BOOT_JSON__", boot_json)
        .replace("__SCRIPT_BLOCK__", script_block)
    )


class PTThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # No Windows, SO_REUSEADDR permite que duas instâncias escutem a mesma
    # porta e distribuam requisições entre versões diferentes do painel.
    # A porta exclusiva garante que uma segunda inicialização falhe claramente.
    allow_reuse_address = False


def _normalize_action_result(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        payload = dict(result)
        payload.setdefault("ok", True)
        return payload

    if isinstance(result, tuple):
        if len(result) >= 2:
            return {"ok": bool(result[0]), "message": str(result[1])}
        if len(result) == 1:
            return {"ok": bool(result[0]), "message": "OK" if result[0] else "Falha."}

    if isinstance(result, bool):
        return {"ok": result, "message": "OK" if result else "Falha."}

    if result is None:
        return {"ok": True, "message": "OK"}

    return {"ok": True, "message": str(result)}


def _build_create_run_result(manager: ScraperRunManager, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(payload or {})
    app = manager.create_run(
        site_key=source.get("site_key"),
        item_type_key=source.get("item_type_key"),
        account_key=source.get("account_key"),
        slot_name=source.get("slot_name"),
        auto_load_summary=_to_bool(source.get("load_summary"), True),
    )
    return {
        "ok": True,
        "message": "Execução criada.",
        "run_id": app.run_id,
        "url": _build_run_path(app.run_id, "/"),
        "boot": build_boot_payload(manager, run_id=app.run_id),
        "runs": _list_runs_public(manager),
        "state": _build_state_payload(app),
    }


def _resolve_run_action_target(manager: ScraperRunManager, run_id: str | None = None) -> tuple[Any, str]:
    app = _get_run_app(manager, run_id)
    return app, _normalize_spaces(getattr(app, "run_id", run_id or ""))


def make_handler(
    app: Any,
    *,
    include_inline_assets: bool = False,
):
    manager = _ensure_manager(app)

    class Handler(BaseHTTPRequestHandler):
        server_version = "PTScriptHTTP/3.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _request_path(self) -> str:
            return urlsplit(self.path).path or "/"

        def _send_bytes(
            self,
            payload: bytes,
            *,
            code: int = 200,
            content_type: str = "application/octet-stream",
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _send_empty(self, *, code: int = 204) -> None:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _send_json(self, data: Any, *, code: int = 200) -> None:
            self._send_bytes(
                json.dumps(data, ensure_ascii=False).encode("utf-8"),
                code=code,
                content_type="application/json; charset=utf-8",
            )

        def _send_text(
            self,
            text: str,
            *,
            code: int = 200,
            content_type: str = "text/plain; charset=utf-8",
        ) -> None:
            self._send_bytes(
                str(text).encode("utf-8"),
                code=code,
                content_type=content_type,
            )

        def _send_html(self, html: str, *, code: int = 200) -> None:
            self._send_text(html, code=code, content_type="text/html; charset=utf-8")

        def _read_json_body(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except Exception:
                length = 0

            if length <= 0:
                return {}

            raw = self.rfile.read(length)
            try:
                decoded = json.loads(raw.decode("utf-8"))
                return dict(decoded) if isinstance(decoded, Mapping) else {}
            except Exception:
                return {}

        def _run_action(self, fn: Any, *args: Any, **kwargs: Any) -> None:
            try:
                result = fn(*args, **kwargs)
                self._send_json(_normalize_action_result(result))
            except Exception as error:
                self._send_json(build_error_payload(error), code=500)

        def _call_safe_action(self, target: Any, fn: Any, *args: Any, **kwargs: Any) -> None:
            safe_action = getattr(target, "safe_action", None)
            if callable(safe_action):
                try:
                    result = safe_action(fn, *args, **kwargs)
                    self._send_json(result if isinstance(result, Mapping) else _normalize_action_result(result))
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return

            self._run_action(fn, *args, **kwargs)

        def _serve_panel_html(self, *, run_id: str | None = None) -> None:
            try:
                resolved_app = _get_run_app(manager, run_id)
                should_inline = include_inline_assets or not _has_external_panel_assets()
                html = render_panel_page(
                    app=resolved_app,
                    manager=manager,
                    run_id=getattr(resolved_app, "run_id", run_id),
                    include_inline_assets=should_inline,
                    styles_href="/panel.css",
                    script_src="/panel.js",
                )
                self._send_html(html)
            except Exception as error:
                self._send_json(build_error_payload(error), code=500)

        def _serve_asset(self, kind: str) -> None:
            text = _read_first_existing_asset(kind)
            if text is None:
                text = INLINE_FALLBACK_CSS if kind == "css" else INLINE_FALLBACK_JS

            content_type = "text/css; charset=utf-8" if kind == "css" else "application/javascript; charset=utf-8"
            self._send_text(text, content_type=content_type)

        def _get_run_route(self, path: str) -> tuple[Any, str, str] | None:
            extracted = _extract_run_route(path)
            if extracted is None:
                return None

            run_id, subpath = extracted
            has_run = getattr(manager, "has_run", None)
            if callable(has_run):
                with suppress(Exception):
                    if not has_run(run_id):
                        return None

            app_for_run = _get_run_app(manager, run_id)
            resolved_run_id = _normalize_spaces(getattr(app_for_run, "run_id", run_id))
            return app_for_run, resolved_run_id, subpath

        def _route_get(self, path: str) -> bool:
            if path == "/":
                self._serve_panel_html(run_id=_get_primary_run_id(manager))
                return True

            if path == "/runs":
                self._send_json(
                    {
                        "ok": True,
                        "runs": _list_runs_public(manager),
                        "primary_run_id": _get_primary_run_id(manager),
                    }
                )
                return True

            if path == "/boot":
                self._send_json(build_boot_payload(manager, run_id=_get_primary_run_id(manager)))
                return True

            if path == "/state":
                self._send_json(_build_state_payload(_get_primary_app(manager)))
                return True

            if path == "/logs_full":
                self._send_json({"ok": True, "text": _get_full_logs_text(_get_primary_app(manager))})
                return True

            if path == "/context":
                self._send_json({"ok": True, **_get_context_payload(_get_primary_app(manager))})
                return True

            if path == "/health":
                primary_app = _get_primary_app(manager)
                is_running = getattr(primary_app, "is_running", None)
                is_paused = getattr(primary_app, "is_paused", None)
                running = bool(is_running()) if callable(is_running) else False
                paused = bool(is_paused()) if callable(is_paused) else False
                self._send_json(
                    {
                        "ok": True,
                        "running": running,
                        "paused": paused,
                        "context": _get_context_payload(primary_app),
                    }
                )
                return True

            if path == "/atualizacoes/jobs":
                self._send_json({"ok": True, "jobs": materialize_update_jobs(),
                                 "queue": queue_snapshot()})
                return True
            if path == "/atualizacoes/fila":
                self._send_json({"ok": True, "queue": queue_snapshot()})
                return True
            if path == "/atualizacoes/filas/detalhes":
                query = parse_qs(urlsplit(self.path).query or "")
                name = str(query.get("name", [""])[0] or "")
                self._send_json({"ok": True, **update_queue_details(name)})
                return True
            if path == "/atualizacoes/logs":
                query = parse_qs(urlsplit(self.path).query or "")
                job_id = str(query.get("job_id", [""])[0] or "")
                logs = _UPDATE_LOGS.to_list(job_id) if job_id else []
                if job_id and not logs:
                    with suppress(KeyError):
                        logs = list(get_job(job_id).execution_logs)
                self._send_json({"ok": True, "job_id": job_id, "logs": logs})
                return True

            if path == "/atualizacoes/historico/baixar":
                output = io.StringIO(newline="")
                columns = ["woocommerce_id", "produto", "estado", "origem", "fila", "iniciado_por",
                           "solicitado_em", "versao_anterior", "versao_origem", "concluido_em",
                           "ultima_etapa", "erro"]
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
                for job in history_jobs():
                    writer.writerow({"woocommerce_id": job.get("woo_product_id"), "produto": job.get("name"),
                                     "estado": job.get("state"), "origem": job.get("source_name"),
                                     "fila": job.get("queue_name"), "iniciado_por": job.get("initiated_by"),
                                     "solicitado_em": job.get("manual_requested_at"),
                                     "versao_anterior": job.get("plugintema_version"),
                                     "versao_origem": job.get("effective_source_version") or job.get("approved_source_version") or job.get("ultrapack_version"),
                                     "concluido_em": job.get("completed_at"),
                                     "ultima_etapa": job.get("last_completed_step"), "erro": job.get("execution_error")})
                body = ("\ufeff" + output.getvalue()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="historico-atualizacoes-{datetime.now():%Y%m%d-%H%M%S}.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return True



            run_route = self._get_run_route(path)
            if run_route is not None:
                run_app, run_id, subpath = run_route

                if subpath == "/":
                    self._serve_panel_html(run_id=run_id)
                    return True

                if subpath == "/boot":
                    self._send_json(
                        build_boot_payload(
                            manager,
                            run_id=run_id,
                        )
                    )
                    return True

                if subpath == "/state":
                    self._send_json(
                        _build_state_payload(run_app)
                    )
                    return True

                if subpath == "/logs_full":
                    self._send_json(
                        {
                            "ok": True,
                            "text": _get_full_logs_text(run_app),
                        }
                    )
                    return True

                if subpath == "/context":
                    self._send_json(
                        {
                            "ok": True,
                            **_get_context_payload(run_app),
                        }
                    )
                    return True

                if subpath == "/health":
                    is_running = getattr(
                        run_app,
                        "is_running",
                        None,
                    )
                    is_paused = getattr(
                        run_app,
                        "is_paused",
                        None,
                    )

                    running = (
                        bool(is_running())
                        if callable(is_running)
                        else False
                    )
                    paused = (
                        bool(is_paused())
                        if callable(is_paused)
                        else False
                    )

                    self._send_json(
                        {
                            "ok": True,
                            "run_id": run_id,
                            "running": running,
                            "paused": paused,
                            "context": _get_context_payload(
                                run_app
                            ),
                        }
                    )
                    return True

            if path == "/fila":
                try:
                    self._send_json(
                        {
                            "ok": True,
                            "queue_rules": manager.get_queue_rules(),
                        }
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )
                return True

            if path == "/comparacao/fontes":
                try:
                    self._send_json(
                        _build_comparison_sources_payload()
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )
                return True

            if path == "/comparacao/produtos":
                try:
                    query_params = parse_qs(
                        urlsplit(self.path).query or ""
                    )

                    source_id = str(
                        (query_params.get("source_id") or [""])[0] or ""
                    ).strip()
                    target_id = str(
                        (query_params.get("target_id") or [""])[0] or ""
                    ).strip()
                    role = str(
                        (query_params.get("role") or [""])[0] or ""
                    ).strip().lower()
                    search_query = str(
                        (query_params.get("q") or [""])[0] or ""
                    ).strip()

                    if role == "source":
                        catalog_path = _resolve_comparison_catalog_path(
                            source_id
                        )
                    elif role == "site":
                        catalog_path = _resolve_comparison_catalog_path(
                            target_id
                        )
                    else:
                        raise ValueError("Tipo de catálogo inválido.")

                    if catalog_path is None:
                        raise ValueError("Catálogo não encontrado.")

                    products = search_comparison_catalog_products(
                        catalog_path,
                        role=role,
                        query=search_query,
                        limit=50,
                    )

                    self._send_json(
                        {
                            "ok": True,
                            "role": role,
                            "query": search_query,
                            "products": products,
                            "total": len(products),
                        }
                    )
                except ValueError as error:
                    self._send_json(
                        {
                            "ok": False,
                            "message": str(error),
                        },
                        code=400,
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True

            if path == "/comparacao/data":
                query = parse_qs(
                    urlsplit(self.path).query or ""
                )

                source_id = str(
                    (query.get("source_id") or [""])[0] or ""
                ).strip()

                target_id = str(
                    (query.get("target_id") or [""])[0] or ""
                ).strip()

                status = str(
                    (query.get("status") or [""])[0] or ""
                ).strip()

                decision = str(
                    (query.get("decision") or [""])[0] or ""
                ).strip()

                search_query = str(
                    (query.get("q") or [""])[0] or ""
                ).strip()

                candidate_filter = str(
                    (query.get("candidate_filter") or [""])[0] or ""
                ).strip()

                candidate_count_min_text = str(
                    (query.get("candidate_count_min") or [""])[0] or ""
                ).strip()

                candidate_count_max_text = str(
                    (query.get("candidate_count_max") or [""])[0] or ""
                ).strip()

                score_min_text = str(
                    (query.get("score_min") or [""])[0] or ""
                ).strip()

                score_max_text = str(
                    (query.get("score_max") or [""])[0] or ""
                ).strip()

                candidate_count_min = (
                    max(
                        0,
                        _to_int(candidate_count_min_text, 0),
                    )
                    if candidate_count_min_text
                    else None
                )

                candidate_count_max = (
                    max(
                        0,
                        _to_int(candidate_count_max_text, 0),
                    )
                    if candidate_count_max_text
                    else None
                )

                score_min = (
                    max(
                        0,
                        min(
                            100,
                            _to_int(score_min_text, 0),
                        ),
                    )
                    if score_min_text
                    else None
                )

                score_max = (
                    max(
                        0,
                        min(
                            100,
                            _to_int(score_max_text, 100),
                        ),
                    )
                    if score_max_text
                    else None
                )

                page = max(
                    1,
                    _to_int(
                        (query.get("page") or ["1"])[0],
                        1,
                    ),
                )

                page_size = max(
                    1,
                    _to_int(
                        (query.get("page_size") or ["100"])[0],
                        100,
                    ),
                )

                force = str(
                    (query.get("force") or ["0"])[0] or "0"
                ).strip().lower() in {
                    "1",
                    "true",
                    "sim",
                    "yes",
                }

                if not source_id or not target_id:
                    self._send_json(
                        {
                            "ok": False,
                            "message": (
                                "Selecione o catálogo salvo e "
                                "o catálogo importado."
                            ),
                        },
                        code=400,
                    )
                    return True

                source_path = _resolve_comparison_catalog_path(
                    source_id
                )
                target_path = _resolve_comparison_catalog_path(
                    target_id
                )

                if source_path is None:
                    self._send_json(
                        {
                            "ok": False,
                            "message": (
                                "O catálogo de origem selecionado "
                                "não foi encontrado."
                            ),
                        },
                        code=404,
                    )
                    return True

                if target_path is None:
                    self._send_json(
                        {
                            "ok": False,
                            "message": (
                                "O catálogo importado selecionado "
                                "não foi encontrado."
                            ),
                        },
                        code=404,
                    )
                    return True

                if source_path.resolve() == target_path.resolve():
                    self._send_json(
                        {
                            "ok": False,
                            "message": (
                                "Selecione dois catálogos diferentes."
                            ),
                        },
                        code=400,
                    )
                    return True

                try:
                    self._send_json(
                        build_comparison_payload(
                            source_path=source_path,
                            site_path=target_path,
                            status=status,
                            query=search_query,
                            decision=decision,
                            candidate_filter=candidate_filter,
                            candidate_count_min=candidate_count_min,
                            candidate_count_max=candidate_count_max,
                            score_min=score_min,
                            score_max=score_max,
                            page=page,
                            page_size=page_size,
                            force=force,
                        )
                    )

                except FileNotFoundError as error:
                    self._send_json(
                        {
                            "ok": False,
                            "message": str(error),
                        },
                        code=404,
                    )

                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True

            if path == "/plugintema/catalogo/exportar":
                query = parse_qs(urlsplit(self.path).query or "")
                kind = str((query.get("tipo") or [""])[0] or "").strip().lower()
                if kind not in {"plugin", "theme"}:
                    self._send_json(
                        {"ok": False, "message": "Escolha Plugins ou Temas."},
                        code=400,
                    )
                    return True
                try:
                    products = read_all_products(_build_readonly_woocommerce_client())
                    payload = encode_catalog_csv(build_catalog_rows(products, kind=kind))
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                    return True
                suffix = "plugins" if kind == "plugin" else "temas"
                filename = f"catalogo-plugintema-{suffix}-{datetime.now():%Y%m%d}.csv"
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return True

            if path == "/plugintema/catalogo/opcoes":
                try:
                    woo = _build_readonly_woocommerce_client()
                    categories: list[dict[str, Any]] = []
                    page = 1
                    while True:
                        batch = woo.list_product_categories(page=page, per_page=100)
                        categories.extend(dict(item) for item in batch if isinstance(item, Mapping))
                        if len(batch) < 100:
                            break
                        page += 1
                    self._send_json({"ok": True, "categories": categories})
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/plugintema/catalogo/pesquisar":
                query = parse_qs(urlsplit(self.path).query or "")
                term = str((query.get("q") or [""])[0] or "").strip()
                if not term:
                    self._send_json({"ok": True, "products": []})
                    return True
                try:
                    woo = _build_readonly_woocommerce_client()
                    if term.isdigit():
                        candidates = [woo.get_product(int(term))]
                    else:
                        candidates = woo.search_products(term, per_page=50)
                    products = []
                    for product in candidates:
                        if not isinstance(product, Mapping):
                            continue
                        kinds = [kind for kind in ("plugin", "theme", "template") if build_filtered_catalog_rows([product], CatalogFilters(kinds=(kind,), statuses=()))]
                        if not kinds:
                            continue
                        products.append({
                            "id": int(product.get("id", 0) or 0),
                            "name": str(product.get("name", "") or ""),
                            "status": str(product.get("status", "") or ""),
                            "kind": kinds[0],
                        })
                    self._send_json({"ok": True, "products": products})
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/loja/wordpress-manual/status":
                from app.wordpress_manual_update import manual_monitor_snapshot
                self._send_json(manual_monitor_snapshot())
                return True

            if path == "/loja/precos":
                query = parse_qs(urlsplit(self.path).query or "")
                kinds = [value for value in query.get("tipo", []) if value in {"plugin", "theme"}]
                try:
                    selected = kinds or ["plugin", "theme"]
                    from app.store_pricing import (
                        build_store_pricing_snapshot, read_store_price_reference_products,
                    )
                    reference_products = read_store_price_reference_products(
                        Path(settings.COMPARISON_IMPORTS_DIR), selected
                    )
                    snapshot = build_store_pricing_snapshot(
                        _build_store_woocommerce_client(), selected, products=reference_products
                    )
                    snapshot.pop("variations", None)
                    snapshot["read_only"] = True
                    self._send_json(snapshot)
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/loja/precos/status":
                self._send_json({"ok": True, **_store_price_job_snapshot()})
                return True

            if path == "/loja/pacotes/precos":
                try:
                    from app.store_pricing import list_store_pack_products
                    products = list_store_pack_products(_build_store_woocommerce_client())
                    self._send_json({"ok": True, "products": products, "total": len(products)})
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/loja/produtos/sem-breve-descricao":
                self._send_json({"ok": True, **_store_description_job_snapshot()})
                return True

            if path == "/plugintema/catalogo/baixar":
                query = parse_qs(urlsplit(self.path).query or "")
                catalog_id = str((query.get("catalog_id") or [""])[0] or "").strip()
                generated = [item for item in _build_comparison_sources_payload()["imported_catalogs"] if str(item.get("filename", "")).startswith("plugintema-")]
                allowed = {str(item["id"]): item for item in generated}
                if not catalog_id or catalog_id not in allowed:
                    self._send_json({"ok": False, "message": "Catálogo PluginTema inválido."}, code=400)
                    return True
                path_value = _resolve_comparison_catalog_path(catalog_id)
                if path_value is None or not path_value.is_file():
                    self._send_json({"ok": False, "message": "Catálogo não encontrado."}, code=404)
                    return True
                payload = path_value.read_bytes()
                filename = Path(path_value.name).name
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return True

            if path == "/plugintema/catalogo/gerenciar":
                query = parse_qs(urlsplit(self.path).query or "")
                catalog_id = str((query.get("catalog_id") or [""])[0] or "").strip()
                generated = [item for item in _build_comparison_sources_payload()["imported_catalogs"] if str(item.get("filename", "")).startswith("plugintema-")]
                if not catalog_id:
                    self._send_json({"ok": True, "catalogs": generated, "rows": []})
                    return True
                allowed = {str(item["id"]): item for item in generated}
                if catalog_id not in allowed:
                    self._send_json({"ok": False, "message": "Catálogo PluginTema inválido."}, code=400)
                    return True
                path_value = _resolve_comparison_catalog_path(catalog_id)
                if path_value is None:
                    self._send_json({"ok": False, "message": "Catálogo não encontrado."}, code=404)
                    return True
                with path_value.open("r", encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self._send_json({"ok": True, "catalogs": generated, "rows": rows})
                return True

            if path == "/catalogos/data":
                self._send_json(_build_catalogs_payload())
                return True

            if path.startswith("/catalogos/download/"):
                query = parse_qs(urlsplit(self.path).query or "")
                slot_name = str((query.get("slot_name") or [""])[0] or "").strip()
                site_key = str((query.get("site_key") or [""])[0] or "").strip()
                item_type_key = str((query.get("item_type_key") or [""])[0] or "").strip()
                account_key = str((query.get("account_key") or [""])[0] or "").strip()

                if path.endswith("/csv"):
                    file_kind = "csv"
                elif path.endswith("/status"):
                    file_kind = "status"
                else:
                    file_kind = "log"

                resolved_path = _resolve_catalog_file_path(
                    file_kind=file_kind,
                    slot_name=slot_name,
                    site_key=site_key,
                    item_type_key=item_type_key,
                    account_key=account_key,
                )

                if resolved_path is None or not resolved_path.exists():
                    self._send_json({"ok": False, "message": "Arquivo não encontrado."}, code=404)
                    return True

                content_type = "text/plain; charset=utf-8"
                if file_kind == "csv":
                    content_type = "text/csv; charset=utf-8"

                payload = resolved_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{resolved_path.name}"',
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
                return True

            if path in {"/panel.css", "/assets/styles.css"}:
                self._serve_asset("css")
                return True

            if path in {"/panel.js", "/assets/app.js"}:
                self._serve_asset("js")
                return True

            if path in {"/catalog_cards_refinement.js", "/pagination_autojump.js"}:
                asset_path = settings.APP_DIR / "static" / path.lstrip("/")
                if not asset_path.is_file():
                    self._send_empty(code=404)
                else:
                    self._send_text(asset_path.read_text(encoding="utf-8"), content_type="application/javascript; charset=utf-8")
                return True

            if path == "/mascote.webp":
                mascot_path = settings.DATA_DIR / "crapscrapper mascote.webp"

                if not mascot_path.exists():
                    self._send_json(
                        {
                            "ok": False,
                            "message": "Mascote não encontrado.",
                        },
                        code=404,
                    )
                    return True

                self._send_bytes(
                    mascot_path.read_bytes(),
                    content_type="image/webp",
                )
                return True

            if path == "/emoji.webp":
                emoji_path = settings.APP_DIR / "static" / "emoji.webp"
                if not emoji_path.exists() or not emoji_path.is_file():
                    self._send_empty(code=404)
                    return True
                self._send_bytes(emoji_path.read_bytes(), content_type="image/webp")
                return True

            if path == "/favicon.ico":

                self._send_empty(code=204)
                return True

            return False

        def _route_post(self, path: str, payload: dict[str, Any]) -> bool:
            if path == "/loja/produtos/sem-breve-descricao":
                try:
                    self._send_json({"ok": True, "started": True, **_start_store_description_job(payload)}, code=202)
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/loja/pacotes/precos":
                try:
                    from app.store_pricing import update_store_pack_price
                    self._send_json(update_store_pack_price(_build_store_woocommerce_client(), payload))
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/loja/precos":
                try:
                    result = _start_store_price_job(payload)
                    self._send_json({"ok": True, "started": True, **result}, code=202)
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/plugintema/catalogo/gerar":
                try:
                    self._send_json(
                        _generate_plugintema_comparison_catalog(
                            payload, _build_readonly_woocommerce_client()
                        )
                    )
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/plugintema/catalogo/gerenciar":
                catalog_id = str(payload.get("catalog_id", "") or "").strip()
                generated = {
                    str(item["id"]): item
                    for item in _build_comparison_sources_payload()["imported_catalogs"]
                    if str(item.get("filename", "")).startswith("plugintema-")
                }
                if catalog_id not in generated:
                    self._send_json({"ok": False, "message": "Catálogo PluginTema inválido."}, code=400)
                    return True
                path_value = _resolve_comparison_catalog_path(catalog_id)
                if path_value is None or path_value.parent.resolve() != Path(settings.COMPARISON_IMPORTS_DIR).resolve():
                    self._send_json({"ok": False, "message": "Catálogo fora da área permitida."}, code=400)
                    return True
                action = str(payload.get("action", "delete") or "delete").strip().lower()
                if action == "rename":
                    raw_name = str(payload.get("name", "") or "").strip()
                    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_name).strip("_-")[:60]
                    if not safe_name:
                        self._send_json({"ok": False, "message": "Informe um nome válido."}, code=400)
                        return True
                    stamp_match = re.search(r"(\d{8}-\d{6}-\d{6})$", path_value.stem)
                    stamp = stamp_match.group(1) if stamp_match else datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                    destination = path_value.with_name(f"plugintema-custom-{safe_name}-{stamp}.csv")
                    if destination.exists() and destination != path_value:
                        self._send_json({"ok": False, "message": "Já existe um catálogo com esse nome."}, code=409)
                        return True
                    os.replace(path_value, destination)
                    self._send_json({"ok": True, "catalog_id": f"imported|{destination.name}",
                                     "message": "Catálogo PluginTema renomeado."})
                    return True
                if action != "delete":
                    self._send_json({"ok": False, "message": "Ação inválida."}, code=400)
                    return True
                path_value.unlink()
                self._send_json({"ok": True, "message": "Catálogo PluginTema apagado."})
                return True

            if path == "/atualizacoes/materializar":
                self._send_json({
                    "ok": True,
                    "jobs": materialize_update_jobs(payload.get("comparison_rows", [])),
                    "queue": queue_snapshot(),
                })
                return True

            if path == "/atualizacoes/preparar":
                job = None
                operation_lock = None
                job_id = str(payload.get("job_id") or "")
                logger = _UPDATE_LOGS.for_job(job_id)
                try:
                    missing = missing_for("prepare")
                    if missing:
                        raise RuntimeError(
                            "Pre-requisitos ausentes para PREPARAR: " + ", ".join(missing)
                            + ". Nenhum download foi iniciado."
                        )
                    job = get_job(job_id)
                    with _UPDATE_WORKERS_LOCK:
                        operation_lock = _UPDATE_JOB_LOCKS.setdefault(job.job_id, threading.Lock())
                    if not operation_lock.acquire(blocking=False):
                        raise ValueError("Outro processo deste job está em andamento")
                    if job.state == JobState.EXECUTING:
                        raise ValueError("Job em execução não pode ser preparado")
                    if job.state == JobState.COMPLETED:
                        raise ValueError("Ciclo concluído não pode ser preparado novamente")
                    primary = _get_primary_app(manager)
                    logger.clear()
                    factory = getattr(primary, "update_preparation_service_factory", None)
                    service = factory() if callable(factory) else _build_update_preparation_service(primary, logger.log)
                    preview = service.prepare(job).to_dict()
                    preview["update_logs"] = logger.to_list()
                    save_preview(job.job_id, preview)
                    self._send_json({"ok": True, "preview": preview})
                except (KeyError, ValueError, RuntimeError) as error:
                    safe_error = logger.sanitize(error)
                    if not any("Falha na preparação:" in entry for entry in logger.to_list()):
                        logger.log(f" Falha na preparação: {safe_error}")
                    self._send_json({"ok": False, "message": safe_error,
                                     "state": getattr(getattr(job, "state", None), "value", ""),
                                     "update_logs": logger.to_list()}, code=400)
                except Exception as error:
                    response = build_error_payload(error)
                    safe_error = logger.sanitize(response.get("message", error))
                    if not any("Falha na preparação:" in entry for entry in logger.to_list()):
                        logger.log(f" Falha na preparação: {safe_error}")
                    response["message"] = safe_error
                    response["state"] = getattr(getattr(job, "state", None), "value", "")
                    response["update_logs"] = logger.to_list()
                    self._send_json(response, code=500)
                finally:
                    if operation_lock is not None and operation_lock.locked():
                        operation_lock.release()
                return True

            if path == "/atualizacoes/plano":
                operation_lock = None
                try:
                    from app.operations.execution_plan import build_execution_plan
                    job = get_job(str(payload.get("job_id") or ""))
                    with _UPDATE_WORKERS_LOCK:
                        operation_lock = _UPDATE_JOB_LOCKS.setdefault(job.job_id, threading.Lock())
                    if not operation_lock.acquire(blocking=False):
                        raise ValueError("Outro processo deste job está em andamento")
                    if job.state == JobState.EXECUTING:
                        raise ValueError("Job em execução não pode gerar plano")
                    if job.state == JobState.COMPLETED:
                        raise ValueError("Ciclo concluído não pode gerar outro plano")
                    preview = get_preview(job.job_id)
                    logger = _UPDATE_LOGS.for_job(job.job_id)
                    logger.clear()
                    plan = build_execution_plan(job, preview, logger=logger.log)
                    plan["update_logs"] = logger.to_list()
                    save_plan(job.job_id, plan)
                    persist_job(job)
                    self._send_json({"ok": True, "plan": plan})
                except (KeyError, ValueError) as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                finally:
                    if operation_lock is not None and operation_lock.locked():
                        operation_lock.release()
                return True

            if path == "/atualizacoes/prerequisitos":
                self._send_json({
                    "ok": True,
                    "prerequisites": _update_prerequisites(
                        check_ssh_connection=bool(payload.get("check_ssh_connection", False)),
                        app=_get_primary_app(manager),
                    ),
                })
                return True

            if path == "/atualizacoes/plugintheme/renovar-sessao":
                try:
                    from app.integrations.plugintheme_manual_session import open_manual_plugintheme_session
                    primary = _get_primary_app(manager)
                    result = open_manual_plugintheme_session(primary)
                    self._send_json({"ok": True, **result})
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                return True

            if path == "/atualizacoes/fila/adicionar":
                ids = payload.get("job_ids") or []
                if not isinstance(ids, list):
                    self._send_json({"ok": False, "message": "job_ids deve ser uma lista"}, code=400)
                    return True
                added = enqueue_jobs(str(value) for value in ids)
                self._send_json({"ok": True, "added": added, "queue": queue_snapshot()})
                return True

            if path == "/atualizacoes/filas/criar":
                self._send_json({"ok": True, "queue": create_update_queue(payload.get("name", ""))})
                return True

            if path == "/atualizacoes/filas/selecionar":
                selected_name = str(payload.get("name", "") or "")
                queue = select_update_queue(selected_name)
                self._send_json({"ok": True, "queue": queue,
                                 "details": update_queue_details(queue["active_queue"])})
                return True

            if path == "/atualizacoes/filas/renomear":
                self._send_json({"ok": True, "queue": rename_update_queue(payload.get("name", ""), payload.get("new_name", ""))})
                return True

            if path == "/atualizacoes/filas/apagar":
                self._send_json({"ok": True, "queue": delete_update_queue(payload.get("name", ""))})
                return True

            if path == "/atualizacoes/filas/limpar":
                self._send_json({"ok": True, "queue": clear_update_queue(payload.get("name", ""))})
                return True

            if path == "/atualizacoes/historico/apagar":
                result = clear_update_history()
                self._send_json({"ok": True, **result})
                return True

            if path == "/atualizacoes/fila/iniciar":
                if not settings.UPDATE_EXECUTION_ENABLED:
                    self._send_json({"ok": False, "message": "Escrita WooCommerce bloqueada por configuração; a fila foi preservada."}, code=403)
                    return True
                started = _start_update_queue_worker()
                self._send_json({"ok": True, "started": started, "queue": queue_snapshot()}, code=202)
                return True

            if path == "/atualizacoes/fila/pausar":
                self._send_json({"ok": True, "queue": set_queue_status("paused")})
                return True

            if path == "/atualizacoes/fila/continuar":
                if not settings.UPDATE_EXECUTION_ENABLED:
                    self._send_json({"ok": False, "message": "Execução bloqueada por configuração."}, code=403)
                    return True
                _start_update_queue_worker()
                self._send_json({"ok": True, "queue": queue_snapshot()}, code=202)
                return True

            if path == "/atualizacoes/fila/cancelar-pendentes":
                canceled = cancel_pending_queue()
                self._send_json({"ok": True, "canceled": canceled, "queue": queue_snapshot()})
                return True

            if path == "/atualizacoes/executar":
                operation_lock = None
                worker_started = False
                try:
                    if not settings.UPDATE_EXECUTION_ENABLED:
                        raise PermissionError("Execução real bloqueada para homologação")
                    job = get_job(str(payload.get("job_id") or ""))
                    if job.state == JobState.QUEUED:
                        raise ValueError("Job na fila deve ser executado pelo controlador sequencial")
                    plan = get_plan(job.job_id)
                    preview = get_preview(job.job_id)
                    confirmation = str(payload.get("confirmation") or "")
                    from app.operations.real_executor import authorize_update_execution
                    authorize_update_execution(
                        job, plan, confirmation, enabled=settings.UPDATE_EXECUTION_ENABLED,
                        allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
                    )
                    if (settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS
                            and job.woo_product_id not in settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS):
                        raise PermissionError(
                            f"Produto WooCommerce #{job.woo_product_id} não está autorizado para execução real."
                        )
                    if str(payload.get("plan_id") or "") != str(plan.get("plan_id") or ""):
                        raise ValueError("Plano inexistente ou identificador inválido")
                    if preview.get("ready") is not True or plan.get("ready") is not True:
                        raise ValueError("Preview preparado e plano válido são obrigatórios")
                    if not is_execution_eligible(
                        job, preview, plan, enabled=settings.UPDATE_EXECUTION_ENABLED,
                        allowed_product_ids=settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
                    ):
                        raise ValueError("Job não está pronto para execução ou retry seguro")
                    with _UPDATE_WORKERS_LOCK:
                        operation_lock = _UPDATE_JOB_LOCKS.setdefault(job.job_id, threading.Lock())
                        if not operation_lock.acquire(blocking=False):
                            raise ValueError("Outro processo deste job está em andamento")
                        active = _UPDATE_WORKERS.get(job.job_id)
                        if active and active.is_alive():
                            operation_lock.release(); operation_lock = None
                            raise ValueError("Este job já está em execução")
                    logger = _UPDATE_LOGS.for_job(job.job_id)

                    def execute_one() -> None:
                        executor = None
                        try:
                            logger.clear()
                            executor = _build_controlled_update_executor(job, logger.log)
                            executor.execute(job, plan, confirmation)
                        except Exception as error:
                            if job.state == JobState.EXECUTING:
                                job.set_state(JobState.ERROR, "Falha técnica ao iniciar execução")
                            if not job.execution_error:
                                job.execution_error = logger.sanitize(error)
                                logger.log(f" Falha na execução: {job.execution_error}")
                        finally:
                            job.execution_logs = logger.to_list()
                            persist_job(job)
                            if operation_lock is not None and operation_lock.locked():
                                operation_lock.release()

                    job.set_state(JobState.EXECUTING)
                    persist_job(job)
                    worker = threading.Thread(target=execute_one,
                                              name=f"update-{job.job_id}", daemon=True)
                    _UPDATE_WORKERS[job.job_id] = worker
                    worker.start()
                    worker_started = True
                    self._send_json({"ok": True, "accepted": True, "job_id": job.job_id,
                                     "state": "executing"}, code=202)
                except PermissionError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=403)
                except (KeyError, ValueError) as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(build_error_payload(error), code=500)
                finally:
                    if (not worker_started and operation_lock is not None
                            and operation_lock.locked()):
                        operation_lock.release()
                return True

            if path == "/comparacao/vinculo/salvar":
                try:
                    relationship_state = str(
                        payload.get(
                            "relationship_state",
                            "manual_confirmed",
                        )
                        or "manual_confirmed"
                    ).strip()

                    site_product_key = str(payload.get("site_product_key", "") or "").strip()
                    source_product_key = str(payload.get("source_product_key", "") or "").strip()
                    source_path = _resolve_comparison_catalog_path(str(payload.get("source_id", "") or "").strip())
                    target_path = _resolve_comparison_catalog_path(str(payload.get("target_id", "") or "").strip())
                    if source_path is None or target_path is None:
                        raise ValueError("Selecione catálogos válidos antes de salvar o vínculo.")
                    if not comparison_catalog_has_product(target_path, role="site", product_key=site_product_key):
                        raise ValueError("O produto PluginTema não existe no catálogo selecionado.")
                    if relationship_state not in {"confirmed_not_in_source", "pending_review"} and not comparison_catalog_has_product(source_path, role="source", product_key=source_product_key):
                        raise ValueError("O produto Ultrapack não existe no catálogo selecionado.")

                    saved = save_relationship(
                        site_product_key,
                        source_product_key,
                        relationship_state,
                        site_id=payload.get("site_id", ""),
                        site_name=payload.get("site_name", ""),
                        site_official_url=payload.get(
                            "site_official_url",
                            "",
                        ),
                        source_name=payload.get("source_name", ""),
                        source_product_url=payload.get(
                            "source_product_url",
                            "",
                        ),
                        source_official_url=payload.get(
                            "source_official_url",
                            "",
                        ),
                        note=payload.get(
                            "note",
                            "Relacionamento salvo manualmente pelo painel.",
                        ),
                        operator=payload.get("operator", "local"),
                    )

                    messages = {
                        "manual_confirmed": "Produtos vinculados com sucesso.",
                        "manual_rejected": "Candidato rejeitado com sucesso.",
                        "confirmed_not_in_source": "Ausência no Ultrapack confirmada.",
                        "pending_review": "Produto marcado para revisão.",
                    }

                    self._send_json(
                        {
                            "ok": True,
                            "message": messages.get(
                                relationship_state,
                                "Relacionamento salvo com sucesso.",
                            ),
                            "relationship": saved,
                        }
                    )
                except ValueError as error:
                    self._send_json(
                        {
                            "ok": False,
                            "message": str(error),
                        },
                        code=400,
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True

            if path == "/comparacao/decisao/lote":
                try:
                    result = save_decisions_bulk(
                        payload.get("items", []),
                        payload.get("decision"),
                        note=payload.get("note", ""),
                        operator=payload.get("operator", "local"),
                    )

                    self._send_json(
                        {
                            "ok": True,
                            "message": (
                                str(result["total_saved"])
                                + " decisões salvas com sucesso."
                            ),
                            "result": result,
                        }
                    )
                except ValueError as error:
                    self._send_json(
                        {
                            "ok": False,
                            "message": str(error),
                        },
                        code=400,
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True


            if path == "/comparacao/decisao/salvar":
                try:
                    saved = save_decision(
                        payload.get("comparison_item_id"),
                        payload.get("decision"),
                        note=payload.get("note", ""),
                        operator=payload.get("operator", "local"),
                        site_id=payload.get("site_id", ""),
                        site_name=payload.get("site_name", ""),
                        source_name=payload.get("source_name", ""),
                        status=payload.get("status", ""),
                        recommended_action=payload.get(
                            "recommended_action",
                            "",
                        ),
                        **{
                            key: payload.get(key, "")
                            for key in (
                                "woo_product_id", "site_version", "site_product_url",
                                "site_official_url", "source_version", "source_product_url",
                                "source_official_url", "relationship_state", "relationship_label",
                            )
                        },
                    )

                    self._send_json(
                        {
                            "ok": True,
                            "message": "Decisão salva com sucesso.",
                            "decision": saved,
                        }
                    )
                except ValueError as error:
                    self._send_json(
                        {
                            "ok": False,
                            "message": str(error),
                        },
                        code=400,
                    )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True

            if path == "/comparacao/decisao/restaurar":
                try:
                    restored = reset_decision(
                        payload.get("comparison_item_id"),
                        note=payload.get(
                            "note",
                            "Decisão restaurada para pendente.",
                        ),
                        operator=payload.get("operator", "local"),
                    )

                    if restored is None:
                        self._send_json(
                            {
                                "ok": False,
                                "message": "Decisão não encontrada.",
                            },
                            code=404,
                        )
                    else:
                        self._send_json(
                            {
                                "ok": True,
                                "message": (
                                    "Decisão restaurada para pendente."
                                ),
                                "decision": restored,
                            }
                        )
                except Exception as error:
                    self._send_json(
                        build_error_payload(error),
                        code=500,
                    )

                return True


            if path == "/run/create":
                self._call_safe_action(manager, _build_create_run_result, manager, payload)
                return True

            if path == "/run/delete":
                self._call_safe_action(manager, getattr(manager, "remove_run"), payload.get("run_id"))
                return True

            if path == "/fila":
                self._call_safe_action(manager, getattr(manager, "save_queue_rules"), payload.get("rules", []))
                return True

            run_route = self._get_run_route(path)
            if run_route is not None:
                run_app, run_id, subpath = run_route

                if subpath == "/config":
                    self._call_safe_action(run_app, getattr(run_app, "save_run_options"), payload)
                    return True

                if subpath == "/context":
                    self._call_safe_action(
                        run_app,
                        getattr(run_app, "set_context"),
                        site_key=payload.get("site_key"),
                        item_type_key=payload.get("item_type_key"),
                        account_key=payload.get("account_key"),
                        slot_name=payload.get("slot_name"),
                        load_summary=_to_bool(payload.get("load_summary"), True),
                    )
                    return True

                if subpath == "/start":
                    self._call_safe_action(
                        manager,
                        getattr(manager, "start_run"),
                        run_id,
                        run_mode=payload.get("run_mode") or _get_primary_run_mode(),
                        run_options=_extract_run_options(payload),
                        run_payload=_extract_run_payload(payload),
                        resume=_to_bool(payload.get("resume"), False),
                        clear_logs=_to_bool(payload.get("clear_logs"), True),
                    )
                    return True

                if subpath == "/continue":
                    self._call_safe_action(
                        manager,
                        getattr(manager, "continue_run"),
                        run_id,
                        run_mode=payload.get("run_mode"),
                        run_options=_extract_run_options(payload),
                        run_payload=_extract_run_payload(payload),
                        clear_logs=_to_bool(payload.get("clear_logs"), True),
                    )
                    return True

                if subpath == "/pause":
                    self._call_safe_action(run_app, getattr(run_app, "pause"))
                    return True

                if subpath == "/resume":
                    self._call_safe_action(run_app, getattr(run_app, "resume"))
                    return True

                if subpath == "/stop":
                    self._call_safe_action(run_app, getattr(run_app, "stop"))
                    return True

                if subpath == "/slot/create":
                    self._call_safe_action(run_app, getattr(run_app, "create_and_switch_slot"), payload.get("slot_name"))
                    return True

                if subpath == "/slot/switch":
                    self._call_safe_action(run_app, getattr(run_app, "switch_slot"), payload.get("slot_name"))
                    return True

                if subpath == "/slot/default":
                    self._call_safe_action(run_app, getattr(run_app, "define_default_slot"), payload.get("slot_name"))
                    return True

                if subpath == "/slot/delete":
                    self._call_safe_action(run_app, getattr(run_app, "remove_slot"), payload.get("slot_name"))
                    return True

                if subpath == "/slot/clear":
                    self._call_safe_action(run_app, getattr(run_app, "clear_slot"), payload.get("slot_name"))
                    return True

                if subpath == "/slot/rename":
                    self._call_safe_action(
                        run_app,
                        getattr(run_app, "rename_slot"),
                        payload.get("old_slot_name"),
                        payload.get("new_slot_name"),
                    )
                    return True

                if subpath == "/slot/remove-context":
                    self._call_safe_action(
                        run_app,
                        getattr(run_app, "remove_slot_context"),
                        payload.get("slot_name"),
                        payload.get("site_key"),
                        payload.get("item_type_key"),
                        payload.get("account_key"),
                    )
                    return True

                if subpath == "/slot/remove-zero-contexts":
                    self._call_safe_action(
                        run_app,
                        getattr(run_app, "remove_zero_item_contexts"),
                        payload.get("slot_name"),
                    )
                    return True

                if subpath == "/refresh_summary":
                    self._call_safe_action(run_app, getattr(run_app, "load_initial_summary"))
                    return True

                if subpath == "/refresh_categories":
                    self._call_safe_action(
                        manager,
                        getattr(manager, "start_run"),
                        run_id,
                        run_mode=getattr(settings, "RUN_MODE_CATEGORIES_ONLY", "categories_only"),
                        run_options=_extract_run_options(payload),
                        run_payload=_extract_run_payload(payload),
                        clear_logs=_to_bool(payload.get("clear_logs"), True),
                    )
                    return True

                if subpath.startswith("/run/"):
                    mode = subpath.split("/run/", 1)[1].strip().lower()
                    self._call_safe_action(
                        manager,
                        getattr(manager, "start_run"),
                        run_id,
                        run_mode=mode,
                        run_options=_extract_run_options(payload),
                        run_payload=_extract_run_payload(payload),
                        resume=_to_bool(payload.get("resume"), False),
                        clear_logs=_to_bool(payload.get("clear_logs"), True),
                    )
                    return True

                return False

            primary_app, primary_run_id = _resolve_run_action_target(manager)

            if path == "/config":
                self._call_safe_action(primary_app, getattr(primary_app, "save_run_options"), payload)
                return True

            if path == "/context":
                self._call_safe_action(
                    primary_app,
                    getattr(primary_app, "set_context"),
                    site_key=payload.get("site_key"),
                    item_type_key=payload.get("item_type_key"),
                    account_key=payload.get("account_key"),
                    slot_name=payload.get("slot_name"),
                    load_summary=_to_bool(payload.get("load_summary"), True),
                )
                return True

            if path == "/start":
                self._call_safe_action(
                    manager,
                    getattr(manager, "start_run"),
                    primary_run_id,
                    run_mode=payload.get("run_mode") or _get_primary_run_mode(),
                    run_options=_extract_run_options(payload),
                    run_payload=_extract_run_payload(payload),
                    resume=_to_bool(payload.get("resume"), False),
                    clear_logs=_to_bool(payload.get("clear_logs"), True),
                )
                return True

            if path == "/continue":
                self._call_safe_action(
                    manager,
                    getattr(manager, "continue_run"),
                    primary_run_id,
                    run_mode=payload.get("run_mode"),
                    run_options=_extract_run_options(payload),
                    run_payload=_extract_run_payload(payload),
                    clear_logs=_to_bool(payload.get("clear_logs"), True),
                )
                return True

            if path == "/pause":
                self._call_safe_action(primary_app, getattr(primary_app, "pause"))
                return True

            if path == "/resume":
                self._call_safe_action(primary_app, getattr(primary_app, "resume"))
                return True

            if path == "/stop":
                self._call_safe_action(primary_app, getattr(primary_app, "stop"))
                return True

            if path == "/slot/create":
                self._call_safe_action(primary_app, getattr(primary_app, "create_and_switch_slot"), payload.get("slot_name"))
                return True

            if path == "/slot/switch":
                self._call_safe_action(primary_app, getattr(primary_app, "switch_slot"), payload.get("slot_name"))
                return True

            if path == "/slot/default":
                self._call_safe_action(primary_app, getattr(primary_app, "define_default_slot"), payload.get("slot_name"))
                return True

            if path == "/slot/delete":
                self._call_safe_action(primary_app, getattr(primary_app, "remove_slot"), payload.get("slot_name"))
                return True

            if path == "/slot/clear":
                self._call_safe_action(primary_app, getattr(primary_app, "clear_slot"), payload.get("slot_name"))
                return True

            if path == "/slot/rename":
                self._call_safe_action(
                    primary_app,
                    getattr(primary_app, "rename_slot"),
                    payload.get("old_slot_name"),
                    payload.get("new_slot_name"),
                )
                return True

            if path == "/slot/remove-context":
                self._call_safe_action(
                    primary_app,
                    getattr(primary_app, "remove_slot_context"),
                    payload.get("slot_name"),
                    payload.get("site_key"),
                    payload.get("item_type_key"),
                    payload.get("account_key"),
                )
                return True

            if path == "/slot/remove-zero-contexts":
                self._call_safe_action(
                    primary_app,
                    getattr(primary_app, "remove_zero_item_contexts"),
                    payload.get("slot_name"),
                )
                return True

            if path == "/refresh_summary":
                self._call_safe_action(primary_app, getattr(primary_app, "load_initial_summary"))
                return True

            if path == "/refresh_categories":
                self._call_safe_action(
                    manager,
                    getattr(manager, "start_run"),
                    primary_run_id,
                    run_mode=getattr(settings, "RUN_MODE_CATEGORIES_ONLY", "categories_only"),
                    run_options=_extract_run_options(payload),
                    run_payload=_extract_run_payload(payload),
                    clear_logs=_to_bool(payload.get("clear_logs"), True),
                )
                return True

            if path.startswith("/run/"):
                mode = path.split("/run/", 1)[1].strip().lower()
                if mode and "/" not in mode:
                    self._call_safe_action(
                        manager,
                        getattr(manager, "start_run"),
                        primary_run_id,
                        run_mode=mode,
                        run_options=_extract_run_options(payload),
                        run_payload=_extract_run_payload(payload),
                        resume=_to_bool(payload.get("resume"), False),
                        clear_logs=_to_bool(payload.get("clear_logs"), True),
                    )
                    return True

            return False

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Allow", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            path = self._request_path()
            if self._route_get(path):
                return
            self._send_json({"ok": False, "message": "Rota não encontrada."}, code=404)

        def do_POST(self) -> None:
            path = self._request_path()
            payload = self._read_json_body()
            if self._route_post(path, payload):
                return
            self._send_json({"ok": False, "message": "Rota não encontrada."}, code=404)

    return Handler


def prepare_app(app: ScraperApp | Any | None = None) -> ScraperApp | Any:
    if app is not None:
        resolved_target = app
    else:
        resolved_target = _ensure_manager(None)

    manager = _ensure_manager(resolved_target)

    for run_item in _list_runs_public(manager):
        with suppress(Exception):
            run_app = manager.get_run(run_item.get("run_id"))
            for method_name in (
                "refresh_slots_state",
                "load_initial_summary",
            ):
                method = getattr(run_app, method_name, None)
                if callable(method):
                    with suppress(Exception):
                        method()

    return resolved_target


def create_server(
    app: ScraperApp | Any | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    include_inline_assets: bool | None = None,
) -> tuple[ScraperApp | Any, PTThreadingHTTPServer, str]:
    resolved_target = prepare_app(app)
    manager = _ensure_manager(resolved_target)
    resolved_host = str(host or get_panel_host()).strip() or "127.0.0.1"
    resolved_port = get_panel_port() if port is None else max(1, int(port))
    resolved_inline_assets = get_include_inline_assets() if include_inline_assets is None else bool(include_inline_assets)

    handler = make_handler(
        manager,
        include_inline_assets=resolved_inline_assets,
    )

    try:
        server = PTThreadingHTTPServer((resolved_host, resolved_port), handler)
    except OSError as exc:
        detail = str(exc).strip() or "Erro ao abrir a porta."
        raise RuntimeError(
            f"Não foi possível iniciar o painel em {resolved_host}:{resolved_port}. {detail}"
        ) from exc

    with suppress(Exception):
        setattr(manager, "server", server)

    primary_app = _get_primary_app(manager)
    with suppress(Exception):
        setattr(primary_app, "server", server)

    url = build_panel_url(resolved_host, resolved_port)
    return resolved_target, server, url


def open_panel_in_browser(url: str, *, enabled: bool | None = None) -> bool:
    should_open = get_auto_open_browser() if enabled is None else bool(enabled)
    if not should_open:
        return False

    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def stop_server(server: ThreadingHTTPServer | None) -> None:
    if server is None:
        return

    with suppress(Exception):
        server.shutdown()

    with suppress(Exception):
        server.server_close()


def serve(
    app: ScraperApp | Any | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool | None = None,
    include_inline_assets: bool | None = None,
) -> ScraperApp | Any:
    resolved_target, server, url = create_server(
        app,
        host=host,
        port=port,
        include_inline_assets=include_inline_assets,
    )

    _boot_log(f"Painel iniciado em {url}")
    _boot_log("Abra no navegador se não abrir sozinho.")

    _start_wordpress_manual_worker(_ensure_manager(resolved_target))
    open_panel_in_browser(url, enabled=open_browser)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        _boot_log("Encerrando painel...")
    finally:
        stop_server(server)
        manager = _ensure_manager(resolved_target)
        with suppress(Exception):
            setattr(manager, "server", None)
        with suppress(Exception):
            setattr(_get_primary_app(manager), "server", None)

    return resolved_target


def start_server_in_thread(
    app: ScraperApp | Any | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    open_browser: bool | None = None,
    include_inline_assets: bool | None = None,
    thread_name: str = "ptscript-web-server",
) -> tuple[ScraperApp | Any, PTThreadingHTTPServer, threading.Thread, str]:
    resolved_target, server, url = create_server(
        app,
        host=host,
        port=port,
        include_inline_assets=include_inline_assets,
    )

    _start_wordpress_manual_worker(_ensure_manager(resolved_target))

    def _runner() -> None:
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            with suppress(Exception):
                server.server_close()

    thread = threading.Thread(
        target=_runner,
        name=thread_name,
        daemon=True,
    )
    thread.start()

    manager = _ensure_manager(resolved_target)
    with suppress(Exception):
        setattr(manager, "server_thread", thread)

    primary_app = _get_primary_app(manager)
    with suppress(Exception):
        setattr(primary_app, "server_thread", thread)

    _boot_log(f"Painel iniciado em {url}")
    _boot_log("Rodando em thread separada.")

    open_panel_in_browser(url, enabled=open_browser)
    return resolved_target, server, thread, url


run_server = serve


def main() -> None:
    serve()


__all__ = [
    "PTThreadingHTTPServer",
    "INLINE_FALLBACK_CSS",
    "INLINE_FALLBACK_JS",
    "HTML_TEMPLATE",
    "build_boot_payload",
    "build_panel_url",
    "build_run_panel_url",
    "create_server",
    "get_panel_host",
    "get_panel_port",
    "get_auto_open_browser",
    "get_include_inline_assets",
    "make_handler",
    "open_panel_in_browser",
    "prepare_app",
    "render_panel_page",
    "run_server",
    "serve",
    "start_server_in_thread",
    "stop_server",
    "main",
]


if __name__ == "__main__":
    main()
