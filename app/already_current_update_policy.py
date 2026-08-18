from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping
from uuid import uuid4
from urllib.parse import urlparse

import app.operations.execution_plan as execution_plan_module
from app.integrations.woocommerce import pt_versao
from app.operations.models import JobState, OperationalJob, record_execution_outcome
from app.operations.preparation import UpdatePreparationService
from app.operations.real_executor import ControlledUpdateExecutor

_INSTALLED = False
_BASE_EXECUTE: Callable[..., Any] | None = None
_BASE_PREPARE: Callable[..., Any] | None = None
_BASE_BUILD_PLAN: Callable[..., Any] | None = None
_ALREADY_CURRENT_SKIP_KEYS = frozenset({"already_updated", "downloaded", "new_zip"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(value: Any) -> str:
    return str(value or "").strip().lstrip("vV")


def _validation_key(item: Any) -> str:
    return str(getattr(item, "key", "") or "")


def _already_current_marker(preview: Any) -> Any | None:
    return next(
        (item for item in getattr(preview, "validations", []) if _validation_key(item) == "already_updated"),
        None,
    )


def _already_current_preview(preview: Mapping[str, Any]) -> bool:
    validations = preview.get("validations") or []
    for item in validations:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("key") or "") == "already_updated" and item.get("ok") is True:
            return True
    return False


def _patched_prepare(self: UpdatePreparationService, job: OperationalJob) -> Any:
    """Converte o caso 'já atualizado' em preparação terminal bem-sucedida.

    O fluxo base detecta corretamente quando a versão atual do PluginTema já é
    igual ou superior à versão efetiva da fonte, mas historicamente marcava as
    validações de download como falha para impedir uma escrita desnecessária.
    Aqui mantemos essa proteção de não escrever e mudamos apenas a semântica:
    quando não há nenhuma outra falha real, o preview fica pronto para uma
    conclusão idempotente sem download, staging, backup ou alteração em produção.
    """
    if _BASE_PREPARE is None:
        raise RuntimeError("prepare base indisponível")

    preview = _BASE_PREPARE(self, job)
    marker = _already_current_marker(preview)
    if marker is None:
        return preview

    blocking = [
        item for item in getattr(preview, "validations", [])
        if not bool(getattr(item, "ok", False)) and _validation_key(item) not in _ALREADY_CURRENT_SKIP_KEYS
    ]
    if blocking:
        return preview

    message = str(getattr(marker, "detail", "") or "Produto já está atualizado; nenhuma ação necessária.")
    for item in getattr(preview, "validations", []):
        key = _validation_key(item)
        if key not in _ALREADY_CURRENT_SKIP_KEYS:
            continue
        item.ok = True
        item.level = "info"
        if key == "already_updated":
            item.label = "Produto já atualizado"
            item.detail = message
        else:
            item.label = "Download dispensado" if key == "downloaded" else "Novo ZIP dispensado"
            item.detail = "Produto já está na versão efetiva; nenhuma escrita ou novo download é necessário."

    job.execution_error = ""
    job.prepared_at = _now()
    job.current_sha256 = str((getattr(preview, "current_zip", {}) or {}).get("sha256") or "")
    job.new_sha256 = ""
    job.local_staging_path = ""
    job.set_state(JobState.PREPARED, "Produto já atualizado; conclusão sem escrita preparada")
    preview.state = job.state.value
    notices = getattr(preview, "notices", None)
    if isinstance(notices, list) and message not in notices:
        notices.append(message)
    self.logger("✅ Produto já atualizado; download e escrita dispensados")
    return preview


def _terminal_already_current_plan(
    job: OperationalJob,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = logger or (lambda _message: None)
    versions = dict(preview.get("versions") or {})
    site_version = _norm(versions.get("site_version") or job.plugintema_version)
    approved = _norm(versions.get("approved_source_version") or job.approved_source_version)
    effective = _norm(versions.get("effective_source_version") or job.effective_source_version)
    if not site_version or not effective:
        raise ValueError("Conclusão sem escrita exige versões atual e efetiva válidas")
    if approved and approved != _norm(job.approved_source_version):
        raise ValueError("Snapshot aprovado do job diverge do preview preparado")
    if job.relationship not in execution_plan_module.SAFE_RELATIONSHIPS:
        raise ValueError("Vínculo do job não é seguro")

    marker = next(
        (
            item for item in preview.get("validations", []) or []
            if isinstance(item, Mapping) and str(item.get("key") or "") == "already_updated"
        ),
        {},
    )
    message = str(marker.get("detail") or f"Destino já está na versão {site_version}; nenhuma alteração foi necessária.")
    current = dict(preview.get("current_zip") or {})
    remote_path = str(preview.get("physical_path") or current.get("path") or "")
    remote_name = PurePosixPath(remote_path).name if remote_path else ""
    downloads = [dict(item) for item in (preview.get("downloads") or [])]
    variations = [int(item) for item in (preview.get("variations") or [])]
    source_type = "PluginTheme" if "plugintheme.net" in (urlparse(job.ultrapack_url).hostname or "") else "UltraPackV2"

    log("🧭 Produto já está atualizado; concluindo sem plano de escrita")
    plan = {
        "plan_id": str(uuid4()),
        "schema_version": 1,
        "state": "completed",
        "ready": True,
        "terminal": True,
        "already_current": True,
        "execution_enabled": False,
        "job_id": job.job_id,
        "comparison_item_id": job.comparison_item_id,
        "woo_product_id": job.woo_product_id,
        "product": dict(preview.get("product") or {"name": job.name}),
        "relationship": job.relationship,
        "site_version": site_version,
        "approved_source_version": approved,
        "effective_source_version": effective,
        "origin": {"type": source_type, "version": effective, "local_staging_path": ""},
        "destination": {"type": "PluginTema", "woo_product_id": job.woo_product_id, "remote_path": remote_path},
        "current_zip": {
            "remote_path": remote_path,
            "name": remote_name,
            "size": current.get("size"),
            "sha256": str(current.get("sha256") or ""),
            "owner": current.get("owner", ""),
            "group": current.get("group", ""),
            "mode": current.get("mode", ""),
        },
        "new_zip": {"skipped": True, "reason": "already_current", "sha256": "", "entries": 0},
        "woocommerce": {
            "variation_ids": variations,
            "download_ids": [str(item.get("id") or "") for item in downloads],
            "download_names": [str(item.get("name") or "") for item in downloads],
            "current_file": remote_path,
            "future_file": remote_path,
            "original_downloads": downloads,
        },
        "wordpress": {"pt_versao_current": site_version, "pt_versao_future": site_version},
        "backup": {"skipped": True, "reason": "already_current"},
        "remote_staging": {"skipped": True, "reason": "already_current"},
        "preconditions": [],
        "planned_steps": ["Nenhuma escrita necessária: o destino já está na versão efetiva da fonte."],
        "rollback": {
            "skipped": True,
            "reason": "Nenhuma alteração em produção foi executada.",
            "steps": [],
            "checklist": [],
        },
        "status_label": "Concluído — produto já atualizado",
        "execution_label": "Nenhuma execução necessária",
        "message": message,
    }

    job.execution_error = ""
    job.completed_at = _now()
    job.last_completed_step = "already_current"
    job.queue_position = 0
    job.effective_source_version = effective
    job.set_state(JobState.COMPLETED, message)
    record_execution_outcome(job, plan, "already_current")
    log(f"✅ {message}")
    log("✅ Ciclo concluído com sucesso; ZIP e pt_versao permaneceram inalterados")
    return plan


def _patched_build_execution_plan(
    job: OperationalJob,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if _BASE_BUILD_PLAN is None:
        raise RuntimeError("build_execution_plan base indisponível")
    if preview.get("ready") is True and _already_current_preview(preview):
        return _terminal_already_current_plan(job, preview, logger=logger)
    return _BASE_BUILD_PLAN(job, preview, logger=logger)


def _patched_execute(
    self: ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    # Mantém as mesmas regras de autorização do executor real antes de qualquer leitura/decisão.
    self.authorize(job, plan, confirmation)

    expected = _norm(plan.get("effective_source_version") or job.effective_source_version)
    product_reader = getattr(self.woo, "get_product_fresh", self.woo.get_product)
    product = product_reader(job.woo_product_id)
    current = _norm(pt_versao(product))

    if expected and current and current == expected:
        message = f"Destino já está na versão {expected}; nenhuma alteração foi necessária."
        job.execution_error = ""
        job.completed_at = _now()
        job.last_completed_step = "already_current"
        job.queue_position = 0
        job.set_state(JobState.COMPLETED, message)
        record_execution_outcome(job, dict(plan), "already_current")
        self.log(f"ℹ {message}")
        self.log("ℹ ZIP e pt_versao não foram alterados porque o produto já estava atualizado.")
        return {
            "ok": True,
            "state": job.state.value,
            "already_current": True,
            "completed_at": job.completed_at,
            "message": message,
        }

    if _BASE_EXECUTE is None:
        raise RuntimeError("execute base indisponível")
    return _BASE_EXECUTE(self, job, plan, confirmation)


def install_already_current_update_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE, _BASE_PREPARE, _BASE_BUILD_PLAN
    if _INSTALLED:
        return

    _BASE_PREPARE = UpdatePreparationService._prepare
    UpdatePreparationService._prepare = _patched_prepare

    _BASE_BUILD_PLAN = execution_plan_module.build_execution_plan
    execution_plan_module.build_execution_plan = _patched_build_execution_plan

    _BASE_EXECUTE = ControlledUpdateExecutor.execute
    ControlledUpdateExecutor.execute = _patched_execute
    _INSTALLED = True
