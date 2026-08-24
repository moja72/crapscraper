from __future__ import annotations

import re
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

import app.addition_operational_ui_policy as operational
import app.comparison_decisions as decisions
import app.operations.queue as operation_queue
import app.web as web


_INSTALLED = False
_BASE_LIST_APPROVED: Callable[[], list[dict[str, Any]]] | None = None
_BASE_SAVE_DECISION: Callable[..., dict[str, Any]] | None = None

_TARGET_NAME = "500codecanyonplugins"
_IGNORE_NOTE = "Ignorado automaticamente: pack agregado 500 CodeCanyon Plugins do PluginTheme.net."


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _is_plugintheme_url(value: Any) -> bool:
    raw = _clean(value)
    if not raw:
        return False
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    try:
        host = (urlparse(raw).hostname or "").lower().lstrip("www.")
    except Exception:
        return False
    return host == "plugintheme.net" or host.endswith(".plugintheme.net")


def is_ignored_pack(row: Mapping[str, Any]) -> bool:
    names = (
        row.get("source_name"),
        row.get("site_name"),
        row.get("title"),
    )
    if not any(_key(value) == _TARGET_NAME for value in names):
        return False
    return _is_plugintheme_url(
        row.get("source_product_url")
        or row.get("source_official_url")
        or row.get("site_product_url")
    )


def _filtered_list_approved_additions() -> list[dict[str, Any]]:
    base = _BASE_LIST_APPROVED or decisions.list_approved_additions
    return [dict(row) for row in base() if not is_ignored_pack(row)]


def _guarded_save_decision(
    comparison_item_id: Any,
    decision: Any,
    *,
    note: Any = "",
    operator: Any = "",
    site_id: Any = "",
    site_name: Any = "",
    source_name: Any = "",
    status: Any = "",
    recommended_action: Any = "",
    **snapshot: Any,
) -> dict[str, Any]:
    base = _BASE_SAVE_DECISION or decisions.save_decision
    candidate = {
        "site_name": site_name,
        "source_name": source_name,
        **snapshot,
    }
    normalized = str(decision or "").strip().lower()
    if normalized == "approve_new_product" and is_ignored_pack(candidate):
        decision = "ignore"
        note = _IGNORE_NOTE
        operator = _clean(operator) or "automatic-pack-ignore"
    return base(
        comparison_item_id,
        decision,
        note=note,
        operator=operator,
        site_id=site_id,
        site_name=site_name,
        source_name=source_name,
        status=status,
        recommended_action=recommended_action,
        **snapshot,
    )


def _retroactive_ignore() -> int:
    if _BASE_LIST_APPROVED is None or _BASE_SAVE_DECISION is None:
        return 0
    changed = 0
    for row in list(_BASE_LIST_APPROVED()):
        if not is_ignored_pack(row):
            continue
        snapshot = {column: row.get(column, "") for column in decisions.SNAPSHOT_COLUMNS}
        _BASE_SAVE_DECISION(
            row.get("comparison_item_id"),
            "ignore",
            note=_IGNORE_NOTE,
            operator="automatic-pack-ignore",
            site_id=row.get("site_id", ""),
            site_name=row.get("site_name", ""),
            source_name=row.get("source_name", ""),
            status=row.get("status", ""),
            recommended_action=row.get("recommended_action", ""),
            **snapshot,
        )
        changed += 1
    return changed


def install_addition_pack_ignore_policy() -> None:
    global _INSTALLED, _BASE_LIST_APPROVED, _BASE_SAVE_DECISION
    if _INSTALLED:
        return

    _BASE_LIST_APPROVED = decisions.list_approved_additions
    _BASE_SAVE_DECISION = decisions.save_decision

    # Protege decisões futuras, inclusive as rotas que importaram save_decision
    # por nome antes desta policy ser instalada.
    decisions.save_decision = _guarded_save_decision
    web.save_decision = _guarded_save_decision

    # Toda materialização/sincronização operacional passa a excluir o pack.
    decisions.list_approved_additions = _filtered_list_approved_additions
    operation_queue.list_approved_additions = _filtered_list_approved_additions
    operational.list_approved_additions = _filtered_list_approved_additions

    _retroactive_ignore()

    # Desativa imediatamente um job antigo que já esteja visível em Preparação.
    try:
        operational._sync_approved_operational()
    except Exception:
        pass

    _INSTALLED = True
