from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import json
import csv
import unicodedata
from datetime import datetime, timezone
from collections import deque
from threading import RLock
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse
from pathlib import Path
from urllib.request import Request, urlopen

from app.comparison_decisions import list_decisions
from app.operations.models import JobState, OperationalJob, utc_now_iso
from app.operations.runtime import (
    get_active_manual_job, get_job, persist_job, register_manual_job, save_plan, save_preview,
)
from app.plugintema_catalog import product_matches_catalog_kind

ALLOWED_KINDS = ("plugin", "theme", "template")
TERMINAL_STATES = frozenset({"completed", "failed", "error", "blocked", "rolled_back", "rollback_required"})
SAFE_RELATIONSHIPS = frozenset({"safe_auto", "manual_confirmed"})
_MONITOR_LOCK = RLock()
_MONITOR_LOGS: deque[str] = deque(maxlen=160)
_MONITOR: dict[str, Any] = {
    "enabled": False, "monitor_status": "disabled", "state": "Monitor desativado",
    "last_check": "", "next_check": "", "interval_seconds": 5,
    "request_id": "", "product": "", "product_id": 0, "source": "",
    "current_version": "", "new_version": "", "error": "",
}


def manual_monitor_update(**values: Any) -> None:
    with _MONITOR_LOCK:
        _MONITOR.update(values)


def manual_monitor_log(message: Any) -> None:
    from app.operations.update_logging import UpdateLogger
    safe = UpdateLogger.sanitize(message)
    with _MONITOR_LOCK:
        _MONITOR_LOGS.append(f"[{datetime.now().strftime('%H:%M:%S')}] {safe}")


def manual_monitor_snapshot() -> dict[str, Any]:
    with _MONITOR_LOCK:
        return {"ok": True, **_MONITOR, "logs": list(_MONITOR_LOGS)}


def _version(value: Any) -> tuple[int, ...] | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


def is_newer(candidate: Any, current: Any) -> bool:
    left, right = _version(candidate), _version(current)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def source_name(url: Any) -> str:
    host = urlparse(str(url or "")).netloc.lower()
    return "PluginTheme" if "plugintheme" in host else ("UltraPackV2" if "ultrapack" in host else "")


def _match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _official_key(value: Any) -> str:
    parsed = urlparse(str(value or "").strip())
    return (parsed.netloc.lower().removeprefix("www.") + parsed.path.rstrip("/").lower()) if parsed.netloc else ""


def discover_catalog_candidates(product: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Localiza vínculos seguros nos catálogos atuais, sem depender de decisão antiga."""
    from app import settings
    product_id = int(product.get("id") or 0)
    name_key = _match_text(product.get("name"))
    official = ""
    for meta in product.get("meta_data", []) or []:
        if str(meta.get("key") or "") in {"pt_site_oficial", "site_oficial", "official_url"}:
            official = str(meta.get("value") or "")
            break
    official_key = _official_key(official)
    found: dict[str, dict[str, Any]] = {}
    for path in Path(settings.DATA_DIR).glob("slots/**/catalog.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    url = str(row.get("link_produto") or "").strip()
                    if not source_name(url):
                        continue
                    row_name = str(row.get("nome_produto") or "")
                    row_official = str(row.get("pagina_oficial") or "")
                    exact_official = bool(official_key and _official_key(row_official) == official_key)
                    exact_name = bool(name_key and _match_text(row_name) == name_key)
                    if not exact_official and not exact_name:
                        continue
                    version = str(row.get("versao_produto") or "").strip().removeprefix('="').removesuffix('"')
                    found[url] = {
                        "comparison_item_id": f"catalog:{product_id}:{hashlib.sha256(url.encode()).hexdigest()[:16]}",
                        "woo_product_id": product_id, "site_id": product_id,
                        "site_name": str(product.get("name") or ""), "source_name": row_name,
                        "source_version": version, "source_product_url": url,
                        "source_official_url": row_official,
                        "relationship_state": "safe_auto" if exact_official else "relationship_required",
                        "queue_type": "update", "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                        "catalog_path": str(path),
                    }
        except (OSError, csv.Error, UnicodeError):
            continue
    return list(found.values())


def _product_id(row: Mapping[str, Any]) -> int:
    try:
        return int(float(row.get("woo_product_id") or row.get("site_id") or 0))
    except (TypeError, ValueError):
        return 0


def evaluate_manual_candidates(product_id: int, current_version: str,
                               decisions: list[Mapping[str, Any]] | None = None,
                               *, inspector: Callable[[Mapping[str, Any]], Any] | None = None,
                               log: Callable[[Any], None] | None = None) -> dict[str, Any]:
    """Classifica a descoberta sem confundir ausência de dados com produto atualizado."""
    rows = [dict(row) for row in (decisions if decisions is not None else list_decisions())
            if _product_id(row) == int(product_id)]
    emit = log or (lambda _message: None)
    emit(f"Woo ID: {product_id}; pt_versao atual: {current_version or '(ausente)'}")
    if not rows:
        emit("Nenhuma decisão/correspondência foi localizada para este Woo ID.")
        return {"status": "no_match", "current_version": current_version, "candidates": [],
                "message": "Não foi possível localizar correspondência válida nos catálogos."}

    valid, missing, unsafe, stale, inspection_failed = [], [], [], [], []
    max_age_hours = max(1, int(os.getenv("SCRAPER_WORDPRESS_COMPARISON_MAX_AGE_HOURS", "24") or 24))
    for original in rows:
        row = dict(original)
        origin = source_name(row.get("source_product_url"))
        relationship = str(row.get("relationship_state") or "")
        version = str(row.get("source_version") or "").strip()
        item_id = str(row.get("comparison_item_id") or "")
        reason = "aceito"
        if not origin:
            reason = "origem não reconhecida"
            unsafe.append(row)
        elif relationship not in SAFE_RELATIONSHIPS:
            reason = f"vínculo inseguro ({relationship or 'ausente'})"
            unsafe.append(row)
        else:
            if inspector is not None:
                try:
                    inspected = inspector(row)
                    if isinstance(inspected, (tuple, list)):
                        inspected = inspected[-1] if inspected else ""
                    if str(inspected or "").strip():
                        version = str(inspected).strip()
                        row["source_version"] = version
                        row["manual_live_validated"] = True
                    else:
                        row["manual_inspection_error"] = "source_version_missing"
                        reason = "revalidação não retornou versão"
                        inspection_failed.append(row)
                except Exception as error:
                    row["manual_inspection_error"] = type(error).__name__
                    reason = f"falha ao revalidar fonte ({type(error).__name__})"
                    inspection_failed.append(row)
            if _version(version) is None:
                reason = "versão da fonte ausente ou inválida"
                missing.append(row)
            else:
                valid.append(row)
                updated = str(row.get("updated_at") or "")
                if not row.get("manual_live_validated") and updated:
                    try:
                        age = datetime.now(timezone.utc) - datetime.fromisoformat(updated.replace("Z", "+00:00"))
                        if age.total_seconds() > max_age_hours * 3600:
                            stale.append(row)
                    except ValueError:
                        stale.append(row)
        emit("Candidato " + (item_id or "(sem id)") + f": origem={origin or '(desconhecida)'}, "
             f"versão={version or '(ausente)'}, vínculo={relationship or '(ausente)'}, resultado={reason}.")

    newer = [row for row in valid if row not in inspection_failed and is_newer(row.get("source_version"), current_version)]
    if newer:
        newer.sort(key=lambda row: (_version(row.get("source_version")) or (),
                                    1 if source_name(row.get("source_product_url")) == "PluginTheme" else 0),
                   reverse=True)
        selected = dict(newer[0])
        selected["manual_source_name"] = source_name(selected.get("source_product_url"))
        emit(f"Origem selecionada: {selected['manual_source_name']}; versão escolhida: "
             f"{selected.get('source_version')}; is_newer=true.")
        return {"status": "update_available", "current_version": current_version,
                "new_version": selected.get("source_version", ""), "source": selected["manual_source_name"],
                "candidate": selected, "candidates": rows, "message": "Atualização encontrada."}
    if unsafe:
        status, message = "relationship_required", "Existe candidato, mas o vínculo precisa ser confirmado com segurança."
    elif missing:
        status, message = "source_version_missing", "Produto localizado, mas a versão da fonte não pôde ser determinada."
    elif stale or inspection_failed:
        status, message = "comparison_stale", "A comparação disponível está desatualizada e precisa ser revalidada."
    elif valid:
        status, message = "up_to_date", "Produto já está atualizado nas fontes correspondentes verificadas."
    else:
        status, message = "no_match", "Não foi possível localizar correspondência válida nos catálogos."
    emit(f"Resultado da comparação: {status}; nenhum candidato realmente novo foi selecionado.")
    return {"status": status, "current_version": current_version, "candidates": rows, "message": message}


def select_manual_candidate(product_id: int, current_version: str,
                            decisions: list[Mapping[str, Any]] | None = None) -> dict[str, Any] | None:
    return evaluate_manual_candidates(product_id, current_version, decisions).get("candidate")


def create_manual_job(woo: Any, product_id: int, *, initiated_by: str,
                      inspector: Callable[[Mapping[str, Any]], Any] | None = None,
                      log: Callable[[Any], None] | None = None) -> tuple[OperationalJob | None, dict[str, Any]]:
    active = get_active_manual_job(product_id)
    if active is not None:
        return active, {"ok": True, "status": "accepted", "job_id": active.job_id,
                        "source": active.source_name, "previous_version": active.plugintema_version,
                        "new_version": active.effective_source_version or active.approved_source_version,
                        "reused": True, "message": "A atualização deste produto já está em andamento."}
    product = woo.get_product(int(product_id))
    kinds = [kind for kind in ALLOWED_KINDS if product_matches_catalog_kind(product, kind)]
    if not kinds:
        raise ValueError("O produto não pertence aos tipos Plugin, Tema ou Template.")
    from app.integrations.woocommerce import pt_versao
    current = pt_versao(product)
    if log:
        log(f"Produto WooCommerce: {product.get('name') or product_id}")
    persisted = [dict(row) for row in list_decisions() if _product_id(row) == int(product_id)]
    catalog = discover_catalog_candidates(product)
    merged = {str(row.get("source_product_url") or row.get("comparison_item_id")): row for row in persisted}
    for row in catalog:
        key = str(row.get("source_product_url") or row.get("comparison_item_id"))
        if key in merged and str(merged[key].get("relationship_state") or "") in SAFE_RELATIONSHIPS:
            row["relationship_state"] = merged[key]["relationship_state"]
            row["comparison_item_id"] = merged[key].get("comparison_item_id") or row["comparison_item_id"]
        merged[key] = row
    if log:
        log(f"Correspondências: {len(persisted)} decisões persistidas; {len(catalog)} candidatos nos catálogos atuais.")
    discovery = evaluate_manual_candidates(product_id, current, list(merged.values()), inspector=inspector, log=log)
    discovery["product_name"] = str(product.get("name") or "")
    candidate = discovery.get("candidate")
    if candidate is None:
        return None, {"ok": True, **discovery}
    origin = str(candidate["manual_source_name"])
    job = OperationalJob(
        comparison_item_id=str(candidate.get("comparison_item_id") or f"manual:{product_id}:{time.time_ns()}"),
        woo_product_id=int(product_id), name=str(product.get("name") or candidate.get("site_name") or ""),
        plugintema_version=current, ultrapack_version=str(candidate.get("source_version") or ""),
        ultrapack_url=str(candidate.get("source_product_url") or ""),
        official_url=str(candidate.get("source_official_url") or ""), decision="approve_update",
        relationship=str(candidate.get("relationship_state") or ""), queue_type="update",
        approved_source_version=str(candidate.get("source_version") or ""), source_name=origin,
        initiated_by=str(initiated_by or "wordpress-super-admin")[:160], manual_requested_at=utc_now_iso(),
    )
    register_manual_job(job)
    return job, {"ok": True, "status": "accepted", "job_id": job.job_id,
                 "source": origin, "previous_version": current, "new_version": job.approved_source_version,
                 "message": f"Atualização {origin} adicionada à lista Manual."}


def run_manual_job(job: OperationalJob, *, preparation_factory: Callable[[], Any],
                   plan_builder: Callable[..., dict[str, Any]], executor_factory: Callable[[Any], Any],
                   logger: Any, state_callback: Callable[[str, str], None] | None = None) -> None:
    state = state_callback or (lambda _status, _message: None)
    try:
        state("preparing", "Preparando e validando o arquivo da atualização.")
        preview = preparation_factory().prepare(job).to_dict()
        preview["update_logs"] = logger.to_list()
        save_preview(job.job_id, preview)
        if preview.get("ready") is not True:
            raise ValueError("A preparação segura bloqueou esta atualização.")
        state("preparing", "Gerando plano seguro de atualização.")
        plan = plan_builder(job, preview, logger=logger.log)
        plan["update_logs"] = logger.to_list()
        save_plan(job.job_id, plan)
        persist_job(job)
        state("executing", "Executando substituição segura, atualização de pt_versao e validação final.")
        executor_factory(job).execute(job, plan, f"EXECUTAR {job.woo_product_id}")
        state("validating", "Validando o resultado final da atualização.")
    except Exception as error:
        if job.state not in {JobState.BLOCKED, JobState.ROLLED_BACK, JobState.ROLLBACK_REQUIRED}:
            job.set_state(JobState.ERROR, "Falha na atualização manual")
        job.execution_error = logger.sanitize(error)
        logger.log(f"Falha na atualização manual: {job.execution_error}")
    finally:
        job.execution_logs = logger.to_list()
        persist_job(job)


def manual_job_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    return {"ok": True, "job_id": job.job_id, "status": job.state.value,
            "terminal": job.state.value in TERMINAL_STATES, "product": job.name,
            "source": job.source_name, "previous_version": job.plugintema_version,
            "new_version": job.effective_source_version or job.approved_source_version,
            "requested_at": job.manual_requested_at, "completed_at": job.completed_at,
            "result": job.execution_error or (job.diagnostics[-1] if job.diagnostics else ""),
            "logs": list(job.execution_logs[-20:]), "queue_name": job.queue_name}


class WordPressManualQueueClient:
    """Cliente outbound: o PC busca pedidos no WordPress, sem expor porta local."""
    def __init__(self, base_url: str, secret: str, *, timeout: float = 20.0) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.secret = str(secret)
        self.timeout = float(timeout)
        if not self.base_url.startswith("https://"):
            raise ValueError("A fila manual exige SCRAPER_WP_BASE_URL com HTTPS.")
        if len(self.secret) < 24:
            raise ValueError("SCRAPER_WORDPRESS_MANUAL_SECRET deve ter ao menos 24 caracteres.")

    def _request(self, method: str, route: str, subject: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        timestamp, nonce = str(int(time.time())), os.urandom(16).hex()
        message = "\n".join((timestamp, nonce, method.upper(), route, subject))
        signature = hmac.new(self.secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        body = json.dumps(dict(payload or {})).encode("utf-8") if payload is not None else None
        request = Request(self.base_url + "/wp-json" + route, data=body, method=method.upper(), headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "X-CrapScraper-Timestamp": timestamp, "X-CrapScraper-Nonce": nonce,
            "X-CrapScraper-Signature": signature,
        })
        with urlopen(request, timeout=self.timeout) as response:
            decoded = json.loads(response.read().decode("utf-8") or "{}")
        if not isinstance(decoded, dict) or decoded.get("ok") is False:
            raise RuntimeError(str(decoded.get("message") if isinstance(decoded, dict) else "Resposta WordPress inválida"))
        return decoded

    def pending(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/crapscraper/v1/manual-updates/pending", "poll")
        return [dict(item) for item in result.get("requests", []) if isinstance(item, Mapping)]

    def report(self, request_id: str, **payload: Any) -> dict[str, Any]:
        route = f"/crapscraper/v1/manual-updates/{request_id}/status"
        return self._request("POST", route, request_id, payload)
