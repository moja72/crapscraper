from __future__ import annotations

from typing import Any, Callable, Mapping

import app.operations.runtime as runtime
import app.web as web

_INSTALLED = False
_BASE_SAVE_PLAN: Callable[[str, Mapping[str, Any]], dict[str, Any]] | None = None


def _save_plan(job_id: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    """Persiste o plano sem enfileirar o job automaticamente.

    Preparação e fila são etapas distintas do fluxo operacional. Um job que
    chega a ``PLAN_READY`` permanece em Preparação até o usuário escolher
    explicitamente ``Adicionar à fila``. A execução também continua dependendo
    do comando separado ``Executar fila``.
    """
    if _BASE_SAVE_PLAN is None:
        raise RuntimeError("save_plan base indisponível")
    return _BASE_SAVE_PLAN(job_id, plan)


def install_update_queue_lifecycle_policy() -> None:
    global _INSTALLED, _BASE_SAVE_PLAN
    if _INSTALLED:
        return

    _BASE_SAVE_PLAN = runtime.save_plan
    runtime.save_plan = _save_plan
    # app.web importou save_plan diretamente; a rota /atualizacoes/plano usa este binding.
    web.save_plan = _save_plan
    _INSTALLED = True
