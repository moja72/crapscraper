from __future__ import annotations

from typing import Any, Callable, Mapping

import app.operations.real_executor as real_executor
import app.update_recoverability_policy as recoverability
from app.integrations.wordpress import IntegrationError
from app.operations.models import OperationalJob


_INSTALLED = False
_BASE_EXECUTE: Callable[..., dict[str, Any]] | None = None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _restore_preserved_zip(
    executor: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
) -> None:
    """Restore the original ZIP if metadata repair failed after rename but before install.

    The controlled metadata-repair strategy may move production to the job backup
    before the new .new file is installed. If a staging/helper step then fails,
    the base recovery function can raise before its ``changed_zip`` flag becomes
    true. This final safety net restores the validated backup whenever production
    is absent, without touching successful installs or unrelated strategies.
    """
    if _clean(plan.get("filesystem_strategy")) != "controlled_metadata_repair":
        return

    current = dict(plan.get("current_zip") or {})
    remote_path = _clean(current.get("remote_path"))
    expected_sha = _clean(current.get("sha256")).lower()
    if not remote_path or not expected_sha:
        return

    writer = recoverability.RecoveryWriteSSHStorage.from_env(
        job_id=job.job_id,
        target_path=remote_path,
        write_authorized=True,
    )
    try:
        # If production still exists, the original executor either never renamed
        # it or already completed/rolled back the filesystem transaction.
        if writer.exists(writer.target_path):
            return
        if not writer.exists(writer.backup_path):
            return
        if writer.sha256(writer.backup_path).lower() != expected_sha:
            raise IntegrationError(
                "Backup preservado após falha diverge do SHA original; restauração automática bloqueada"
            )
        writer._rename_recovery(writer.backup_path, writer.target_path)
        if writer.sha256(writer.target_path).lower() != expected_sha:
            raise IntegrationError("Restauração de segurança não confirmou o SHA original")
        executor.log(
            "✅ Falha ocorreu depois de preservar o ZIP e antes da nova instalação; "
            "o ZIP original foi restaurado automaticamente."
        )
    finally:
        writer.close()


def _patched_execute(
    self: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    if _BASE_EXECUTE is None:
        raise RuntimeError("Executor base indisponível")
    try:
        return _BASE_EXECUTE(self, job, plan, confirmation)
    except Exception:
        try:
            _restore_preserved_zip(self, job, plan)
        except Exception as restore_error:
            # Do not hide the original failure. Escalate the persisted state and
            # append the restoration problem to the technical log for intervention.
            job.execution_error = (
                f"{_clean(getattr(job, 'execution_error', ''))} | "
                f"Falha na restauração de segurança: {_clean(restore_error)}"
            ).strip(" |")
            try:
                from app.operations.models import JobState
                job.set_state(JobState.ROLLBACK_REQUIRED, "Restauração de segurança do ZIP falhou")
            except Exception:
                pass
            self.log(f"❌ Falha na restauração de segurança: {_clean(restore_error)}")
        raise


def install_update_recovery_finalizer_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE
    if _INSTALLED:
        return
    _BASE_EXECUTE = real_executor.ControlledUpdateExecutor.execute
    real_executor.ControlledUpdateExecutor.execute = _patched_execute
    _INSTALLED = True


__all__ = ["install_update_recovery_finalizer_policy", "_restore_preserved_zip"]
