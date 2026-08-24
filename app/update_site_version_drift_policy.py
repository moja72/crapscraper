from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app import settings
from app.operations.models import JobState
from app.operations.preparation import UpdatePreparationService, UpdatePreview


_INSTALLED = False
_BASE_PREPARE: Callable[..., UpdatePreview] | None = None


def _version(value: Any) -> tuple[int, ...] | None:
    text = str(value or "").strip()
    parts = text.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _compare(left: Any, right: Any) -> int | None:
    a, b = _version(left), _version(right)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    aa = a + (0,) * (width - len(a))
    bb = b + (0,) * (width - len(b))
    return (aa > bb) - (aa < bb)


def _is_safe_forward_drift(current: Any, snapshot: Any, source: Any) -> bool:
    """Aceita só o caso em que o site avançou, mas ainda precisa do update.

    Exemplo real: comparação 2.32.1, WooCommerce 2.35.4 e fonte 2.36.0.
    O snapshot da comparação ficou velho, mas o estado atual de produção é
    consistente e pode virar a nova base do plano. Regressões nunca são aceitas.
    """
    site_vs_snapshot = _compare(current, snapshot)
    site_vs_source = _compare(current, source)
    return site_vs_snapshot == 1 and site_vs_source == -1


def _repair_safe_forward_drift(
    service: UpdatePreparationService,
    job: Any,
    preview: UpdatePreview,
) -> bool:
    version_validation = next(
        (item for item in preview.validations if item.key == "version"),
        None,
    )
    if version_validation is None or version_validation.ok:
        return False

    # Esta correção só pode transformar o preview em pronto quando a ÚNICA
    # divergência é o snapshot antigo de pt_versao. Qualquer outro bloqueio
    # continua valendo exatamente como antes.
    other_failures = [
        item for item in preview.validations
        if not item.ok and item.key != "version"
    ]
    if other_failures:
        return False

    current_version = str((preview.versions or {}).get("site_version") or "").strip()
    source_version = str((preview.versions or {}).get("effective_source_version") or "").strip()
    snapshot_version = str(getattr(job, "plugintema_version", "") or "").strip()

    if not _is_safe_forward_drift(current_version, snapshot_version, source_version):
        return False

    version_validation.ok = True
    version_validation.level = "info"
    version_validation.detail = (
        f"Comparação desatualizada: registrava {snapshot_version}; WooCommerce já está em "
        f"{current_version}. O plano usará {current_version} como base para atualizar até "
        f"{source_version}."
    )

    # O plano e o rollback precisam partir do estado REAL observado agora no
    # WooCommerce, não do snapshot antigo da comparação.
    job.plugintema_version = current_version
    job.current_sha256 = str((preview.current_zip or {}).get("sha256") or "")
    job.new_sha256 = str((preview.new_zip or {}).get("sha256") or "")
    job.local_staging_path = str((preview.new_zip or {}).get("path") or "")
    job.prepared_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job.execution_error = ""
    job.set_state(JobState.PREPARED, "Preview preparado com pt_versao atual revalidado")
    preview.state = job.state.value

    notice = (
        f"A comparação registrava pt_versao {snapshot_version}, mas o WooCommerce já está em "
        f"{current_version}. A base do plano foi atualizada automaticamente; alvo {source_version}."
    )
    if notice not in preview.notices:
        preview.notices.append(notice)

    execution_available = bool(
        settings.UPDATE_EXECUTION_ENABLED
        and preview.execution_enabled
    )
    if execution_available:
        preview.execution_label = "Execução controlada disponível"

    service.logger(
        f"ℹ pt_versao da comparação estava desatualizado: {snapshot_version} → "
        f"{current_version}; preparação liberada para alvo {source_version}."
    )
    return True


def _patched_prepare(self: UpdatePreparationService, job: Any) -> UpdatePreview:
    if _BASE_PREPARE is None:
        raise RuntimeError("Preparação base indisponível")
    preview = _BASE_PREPARE(self, job)
    _repair_safe_forward_drift(self, job, preview)
    return preview


def install_update_site_version_drift_policy() -> None:
    global _INSTALLED, _BASE_PREPARE
    if _INSTALLED:
        return
    _BASE_PREPARE = UpdatePreparationService._prepare
    UpdatePreparationService._prepare = _patched_prepare
    _INSTALLED = True
