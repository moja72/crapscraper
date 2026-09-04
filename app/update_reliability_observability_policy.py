from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path
from typing import Any, Callable

from app import settings
import app.operational_simple_flow_recovery_policy as simple_recovery
import app.operations.runtime as runtime
import app.update_recoverability_policy as recoverability
import app.web as web
from app.operations.models import JobState, OperationalJob


_INSTALLED = False
_BASE_JOB_PUBLIC: Callable[[OperationalJob], dict[str, Any]] | None = None
_BASE_PERSIST_JOB: Callable[[OperationalJob], None] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_BASE_RESET_RETRY: Callable[..., OperationalJob] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_reliability_observability.js"
_LEDGER_PATH = Path(settings.DATA_DIR) / "update_success_counts.json"
_LEDGER_LOCK = threading.RLock()
_LEDGER: dict[str, Any] | None = None

_SOURCE_ARTIFACT_MARKERS = (
    "resposta da origem incompatível com um arquivo zip",
    "resposta da origem incompativel com um arquivo zip",
    "artefato inválido",
    "artefato invalido",
    "arquivo zip inválido",
    "arquivo zip invalido",
    "file is not a zip file",
    "badzipfile",
    "invalid zip",
)
_COMPLETED_RESULTS = frozenset({"completed", "complete", "success", "successful", "concluido", "concluído"})


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _load_ledger() -> dict[str, Any]:
    global _LEDGER
    with _LEDGER_LOCK:
        if isinstance(_LEDGER, dict):
            return _LEDGER
        try:
            raw = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw.setdefault("schema_version", 1)
        raw.setdefault("products", {})
        if not isinstance(raw["products"], dict):
            raw["products"] = {}
        _LEDGER = raw
        return _LEDGER


def _write_ledger() -> None:
    with _LEDGER_LOCK:
        ledger = _load_ledger()
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = _LEDGER_PATH.with_suffix(_LEDGER_PATH.suffix + ".tmp")
        temporary.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(_LEDGER_PATH)


def _event_key(job: OperationalJob, item: dict[str, Any] | None = None) -> str:
    record = dict(item or {})
    raw = "|".join(
        _clean(value)
        for value in (
            record.get("plan_id"),
            record.get("executing_at"),
            record.get("completed_at"),
            record.get("effective_source_version"),
            record.get("job_id") or job.job_id,
            job.woo_product_id,
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _successful_events(job: OperationalJob) -> list[str]:
    events: list[str] = []
    for item in list(getattr(job, "execution_history", []) or []):
        if not isinstance(item, dict):
            continue
        if _clean(item.get("result")).lower() not in _COMPLETED_RESULTS:
            continue
        events.append(_event_key(job, item))

    if job.state == JobState.COMPLETED:
        current_key = _event_key(
            job,
            {
                "job_id": job.job_id,
                "executing_at": getattr(job, "executing_at", ""),
                "completed_at": getattr(job, "completed_at", ""),
                "effective_source_version": getattr(job, "effective_source_version", ""),
            },
        )
        # record_execution_outcome normalmente já representa a execução atual.
        # O fallback só entra quando não existe nenhum histórico equivalente.
        if current_key not in events:
            has_current = any(
                isinstance(item, dict)
                and _clean(item.get("job_id")) == _clean(job.job_id)
                and _clean(item.get("completed_at")) == _clean(getattr(job, "completed_at", ""))
                and _clean(item.get("result")).lower() in _COMPLETED_RESULTS
                for item in list(getattr(job, "execution_history", []) or [])
            )
            if not has_current:
                events.append(current_key)
    return events


def _sync_successes(job: OperationalJob) -> int:
    product_id = str(int(getattr(job, "woo_product_id", 0) or 0))
    if product_id == "0":
        return 0
    events = _successful_events(job)
    changed = False
    with _LEDGER_LOCK:
        ledger = _load_ledger()
        products = ledger["products"]
        entry = products.setdefault(product_id, {"count": 0, "events": []})
        known = set(str(value) for value in (entry.get("events") or []))
        for event in events:
            if event in known:
                continue
            known.add(event)
            changed = True
        count = len(known)
        if int(entry.get("count") or 0) != count:
            changed = True
        entry["count"] = count
        entry["events"] = sorted(known)
        entry["product_name"] = _clean(getattr(job, "name", ""))
        products[product_id] = entry
        if changed:
            _write_ledger()
        return count


def _count_for(job: OperationalJob) -> int:
    product_id = str(int(getattr(job, "woo_product_id", 0) or 0))
    if product_id == "0":
        return 0
    _sync_successes(job)
    with _LEDGER_LOCK:
        entry = dict(_load_ledger().get("products", {}).get(product_id) or {})
    return max(0, int(entry.get("count") or 0))


def _failure_summary(error: Any) -> str:
    raw = _clean(error)
    if not raw:
        return ""
    lowered = raw.lower()

    if "wrong owner for" in lowered:
        return "O ZIP atual está com proprietário incorreto no servidor; o backup seguro foi bloqueado antes de qualquer alteração."
    if "wrong group for" in lowered:
        return "O ZIP atual está com grupo incorreto no servidor; o backup seguro foi bloqueado antes de qualquer alteração."
    if "wrong mode for" in lowered:
        return "O ZIP atual está com permissões incorretas no servidor; o backup seguro foi bloqueado antes de qualquer alteração."
    if "zip atual do produto não foi encontrado" in lowered or "zip atual do produto nao foi encontrado" in lowered:
        return "O arquivo ZIP atual configurado no WooCommerce não existe no repositório de downloads."
    if "mas o arquivo não existe" in lowered or "mas o arquivo nao existe" in lowered:
        return "O arquivo ZIP atual apontado pelo WooCommerce não existe no repositório de downloads."
    if any(marker in lowered for marker in _SOURCE_ARTIFACT_MARKERS):
        return "A origem não entregou um arquivo ZIP válido; a resposta recebida foi rejeitada antes de qualquer alteração."
    if "backup existente diverge" in lowered:
        return "O backup existente não corresponde ao ZIP original esperado; a nova tentativa foi bloqueada por segurança."
    if "sha-256" in lowered and "diverg" in lowered:
        return "A integridade do arquivo divergiu do SHA-256 esperado; a atualização foi interrompida antes da confirmação final."

    # Remove JSON técnico comum da frase principal; o detalhe completo continua
    # disponível em Detalhes/logs.
    sentence = re.split(r"(?<=[.!?])\s+", raw, maxsplit=1)[0]
    sentence = re.sub(r"\s*\{.*$", "", sentence).strip()
    return (sentence[:217] + "...") if len(sentence) > 220 else sentence


def _patched_job_public(job: OperationalJob) -> dict[str, Any]:
    if _BASE_JOB_PUBLIC is None:
        raise RuntimeError("job_public base indisponível")
    data = dict(_BASE_JOB_PUBLIC(job))
    data["updates_count"] = _count_for(job)
    data["failure_summary"] = _failure_summary(data.get("execution_error"))
    return data


def _patched_persist_job(job: OperationalJob) -> None:
    if _BASE_PERSIST_JOB is None:
        raise RuntimeError("persist_job base indisponível")
    _BASE_PERSIST_JOB(job)
    if job.state == JobState.COMPLETED:
        _sync_successes(job)


def _source_artifact_failure(error: Any) -> bool:
    lowered = _clean(error).lower()
    return bool(lowered and any(marker in lowered for marker in _SOURCE_ARTIFACT_MARKERS))


def _patched_reset_for_retry(job_id: str, manager: Any) -> OperationalJob:
    if _BASE_RESET_RETRY is None:
        raise RuntimeError("reset de retry base indisponível")
    try:
        previous_error = _clean(runtime.get_job(job_id).execution_error)
    except Exception:
        previous_error = ""

    job = _BASE_RESET_RETRY(job_id, manager)
    if not _source_artifact_failure(previous_error):
        return job

    # Resposta que não é ZIP costuma ser sessão expirada, página HTML intermediária
    # ou download incompleto. O retry deve partir de uma sessão nova e jamais
    # reaproveitar o artefato rejeitado.
    job.local_staging_path = ""
    job.new_sha256 = ""
    try:
        primary = web._get_primary_app(manager)
        logger = web._UPDATE_LOGS.for_job(job.job_id)
        simple_recovery._invalidate_source_session(primary, job, logger)
        job.diagnostics.append(
            "Retry da fonte: sessão descartada porque a tentativa anterior não entregou um ZIP válido."
        )
    except Exception as error:
        job.diagnostics.append(
            f"Retry da fonte: não foi possível renovar a sessão antecipadamente ({_clean(error)}); a preparação fará nova validação."
        )
    runtime.persist_job(job)
    return job


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-update-reliability-observability>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_update_reliability_observability_policy() -> None:
    global _INSTALLED, _BASE_JOB_PUBLIC, _BASE_PERSIST_JOB, _BASE_RENDER, _BASE_RESET_RETRY
    if _INSTALLED:
        return

    _BASE_JOB_PUBLIC = runtime.job_public
    runtime.job_public = _patched_job_public

    _BASE_PERSIST_JOB = runtime.persist_job
    runtime.persist_job = _patched_persist_job

    _BASE_RESET_RETRY = recoverability._reset_for_retry
    recoverability._reset_for_retry = _patched_reset_for_retry

    # Backfill best-effort do histórico ainda presente no runtime. O ledger é
    # independente do histórico visual, então futuras limpezas não zeram a métrica.
    try:
        with runtime._LOCK:
            jobs = list(runtime._JOBS.values())
        for job in jobs:
            _sync_successes(job)
    except Exception:
        pass

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True


__all__ = [
    "install_update_reliability_observability_policy",
    "_failure_summary",
]
