from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

import app.operations.real_executor as real_executor
import app.update_recoverability_policy as recoverability
from app.integrations.ssh_helper import SSHHelperRequest
from app.operations.models import OperationalJob


_INSTALLED = False
_BASE_EXECUTE: Callable[..., dict[str, Any]] | None = None
_METADATA_MARKERS = ("wrong owner for", "wrong group for", "wrong mode for")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _metadata_failure(error: Any) -> bool:
    lowered = _clean(error).lower()
    return any(marker in lowered for marker in _METADATA_MARKERS)


def _patched_execute(
    self: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    strategy = _clean(plan.get("filesystem_strategy"))
    if strategy in {"recreate_missing", "controlled_metadata_repair"}:
        if _BASE_EXECUTE is None:
            raise RuntimeError("Executor base indisponível")
        return _BASE_EXECUTE(self, job, plan, confirmation)

    # O preview costuma descobrir owner/group/mode por SFTP+stat. Em hosts onde
    # esse detalhe não chegou ao preview, faça uma inspeção read-only pelo MESMO
    # helper que executaria o backup. Se ele acusar somente metadados legados,
    # converta a tentativa para a estratégia transacional que preserva o ZIP antigo
    # por rename e instala o .new preparado com owner/group/mode corretos.
    current = dict(plan.get("current_zip") or {})
    remote_path = _clean(current.get("remote_path"))
    file_name = PurePosixPath(remote_path).name if remote_path else ""
    if file_name:
        try:
            self.helper.invoke(SSHHelperRequest("inspect", file_name))
        except Exception as error:
            if _metadata_failure(error):
                repaired = dict(plan)
                repaired["current_zip"] = dict(current)
                repaired["filesystem_strategy"] = "controlled_metadata_repair"
                repaired["current_zip"]["metadata_repair"] = True
                repaired["status_label"] = "Plano recuperado — metadados antigos serão corrigidos"
                self.log(
                    "♻ Metadados antigos do ZIP detectados pelo helper. "
                    "A troca continuará pelo caminho controlado, preservando o arquivo anterior para rollback."
                )
                return recoverability._execute_repair_strategy(self, job, repaired, confirmation)
            # Qualquer outro erro continua no fluxo base, que possui as mensagens e
            # proteções próprias. A inspeção extra nunca transforma outra falha em
            # permissão de escrita.

    if _BASE_EXECUTE is None:
        raise RuntimeError("Executor base indisponível")
    return _BASE_EXECUTE(self, job, plan, confirmation)


def install_update_metadata_preflight_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE
    if _INSTALLED:
        return
    _BASE_EXECUTE = real_executor.ControlledUpdateExecutor.execute
    real_executor.ControlledUpdateExecutor.execute = _patched_execute
    _INSTALLED = True


__all__ = ["install_update_metadata_preflight_policy", "_metadata_failure"]
