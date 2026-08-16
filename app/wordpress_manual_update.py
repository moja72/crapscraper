from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

from app.comparison_decisions import list_decisions
from app.operations.models import JobState, OperationalJob, utc_now_iso
from app.operations.runtime import (
    get_active_manual_job, get_job, persist_job, register_manual_job, save_plan, save_preview,
)
from app.plugintema_catalog import product_matches_catalog_kind

ALLOWED_KINDS = ("plugin", "theme", "template")
TERMINAL_STATES = frozenset({"completed", "failed", "error", "blocked", "rolled_back", "rollback_required"})
_NONCES: dict[str, int] = {}
_NONCE_LOCK = threading.RLock()


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


def select_manual_candidate(product_id: int, current_version: str,
                            decisions: list[Mapping[str, Any]] | None = None) -> dict[str, Any] | None:
    candidates = []
    for row in decisions if decisions is not None else list_decisions(queue_type="update"):
        if int(float(row.get("woo_product_id") or row.get("site_id") or 0)) != int(product_id):
            continue
        origin = source_name(row.get("source_product_url"))
        if not origin or row.get("relationship_state") not in {"safe_auto", "manual_confirmed"}:
            continue
        if not is_newer(row.get("source_version"), current_version):
            continue
        candidates.append((0 if origin == "PluginTheme" else 1, dict(row), origin))
    if not candidates:
        return None
    _priority, selected, origin = min(candidates, key=lambda item: item[0])
    selected["manual_source_name"] = origin
    return selected


def verify_signed_request(headers: Mapping[str, Any], method: str, path: str, subject: str,
                          *, now: int | None = None, secret: str | None = None) -> None:
    shared = str(secret if secret is not None else os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET", ""))
    if len(shared) < 24:
        raise PermissionError("Integração manual não configurada com segredo forte.")
    timestamp = str(headers.get("X-CrapScraper-Timestamp", "") or "")
    nonce = str(headers.get("X-CrapScraper-Nonce", "") or "")
    signature = str(headers.get("X-CrapScraper-Signature", "") or "")
    current = int(time.time() if now is None else now)
    try:
        numeric_timestamp = int(timestamp)
    except ValueError:
        raise PermissionError("Assinatura sem data válida.") from None
    if abs(current - numeric_timestamp) > 300 or not nonce or len(nonce) > 128:
        raise PermissionError("Assinatura expirada ou nonce inválido.")
    message = "\n".join((timestamp, nonce, method.upper(), path, str(subject)))
    expected = hmac.new(shared.encode(), message.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("Assinatura da requisição inválida.")
    with _NONCE_LOCK:
        for key, seen in list(_NONCES.items()):
            if current - seen > 300:
                _NONCES.pop(key, None)
        if nonce in _NONCES:
            raise PermissionError("Requisição já utilizada.")
        _NONCES[nonce] = current


def create_manual_job(woo: Any, product_id: int, *, initiated_by: str) -> tuple[OperationalJob | None, dict[str, Any]]:
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
    candidate = select_manual_candidate(product_id, current)
    if candidate is None:
        return None, {"ok": True, "status": "up_to_date", "current_version": current,
                      "message": "Produto atualizado ou nenhuma versão mais recente foi encontrada."}
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
                   logger: Any) -> None:
    try:
        preview = preparation_factory().prepare(job).to_dict()
        preview["update_logs"] = logger.to_list()
        save_preview(job.job_id, preview)
        if preview.get("ready") is not True:
            raise ValueError("A preparação segura bloqueou esta atualização.")
        plan = plan_builder(job, preview, logger=logger.log)
        plan["update_logs"] = logger.to_list()
        save_plan(job.job_id, plan)
        persist_job(job)
        executor_factory(job).execute(job, plan, f"EXECUTAR {job.woo_product_id}")
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
