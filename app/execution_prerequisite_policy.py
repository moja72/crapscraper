from __future__ import annotations

from typing import Any, Callable

from app import settings
import app.web as web

_INSTALLED = False
_BASE_PREREQUISITE_STATUS: Callable[..., dict[str, Any]] | None = None


def _patched_prerequisite_status() -> dict[str, Any]:
    if _BASE_PREREQUISITE_STATUS is None:
        return {}
    result = dict(_BASE_PREREQUISITE_STATUS())
    enabled = bool(settings.UPDATE_EXECUTION_ENABLED)
    allowed = sorted(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS)

    # O executor real usa escrita controlada e estritamente limitada ao pt_versao,
    # com confirmação GET posterior. A UI antiga mostrava esta etapa como bloqueada
    # de forma fixa, mesmo quando a trava real de execução estava habilitada.
    result["woocommerce_write"] = {
        "ok": enabled,
        "status": "HABILITADA" if enabled else "BLOQUEADA",
        "mode": "pt_versao_controlada",
    }
    result["remote_execution"] = {
        "ok": enabled,
        "status": "HABILITADA" if enabled else "BLOQUEADA",
    }
    update_execution = dict(result.get("update_execution") or {})
    update_execution.update(
        enabled=enabled,
        status="HABILITADA" if enabled else "BLOQUEADA",
        allowed_product_ids=allowed,
        allow_all_products=not bool(allowed),
    )
    result["update_execution"] = update_execution
    return result


def install_execution_prerequisite_policy() -> None:
    global _INSTALLED, _BASE_PREREQUISITE_STATUS
    if _INSTALLED:
        return
    _BASE_PREREQUISITE_STATUS = web.prerequisite_status
    web.prerequisite_status = _patched_prerequisite_status
    _INSTALLED = True
