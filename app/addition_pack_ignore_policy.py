from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import app.addition_operational_ui_policy as operational
import app.comparison_decisions as decisions
import app.operations.queue as operation_queue
import app.web as web


_INSTALLED = False
_BASE_LIST_APPROVED: Callable[[], list[dict[str, Any]]] | None = None
_BASE_SAVE_DECISION: Callable[..., dict[str, Any]] | None = None

_TARGET_NAME = "500codecanyonplugins"
_IGNORE_NOTE = "Ignorado automaticamente: pack agregado 500 CodeCanyon Plugins."


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def is_ignored_pack(row: Mapping[str, Any]) -> bool:
    """Regra permanente e intencionalmente específica para este pack.

    O registro antigo nem sempre carrega ``source_product_url`` na decisão/job.
    Exigir o domínio PluginTheme fazia o mesmo pack escapar do filtro e voltar a
    aparecer em Preparação. O nome exato normalizado é suficiente porque esta é
    uma exclusão de negócio explícita, não uma heurística para bundles em geral.
    """
    return any(
        _key(value) == _TARGET_NAME
        for value in (
            row.get("source_name"),
            row.get("site_name"),
            row.get("title"),
            row.get("name"),
        )
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


def _scrub_existing_jobs() -> int:
    """Oculta/desativa jobs já materializados antes da regra existir."""
    changed = 0
    try:
        operational._ensure_schema()
        now = operational._utc_now()
        with operational.additions._db() as connection:
            rows = connection.execute(
                "SELECT job_id, source_name, title, queue_state FROM addition_jobs"
            ).fetchall()
            for raw in rows:
                row = dict(raw)
                if not is_ignored_pack(row):
                    continue
                state = _clean(row.get("queue_state"))
                values: dict[str, Any] = {
                    "approval_active": 0,
                    "enqueue_after_prepare": 0,
                    "hidden_from_queue": 1,
                    "status_message": "Ignorado permanentemente pelo CrapScraper: pack 500 CodeCanyon Plugins.",
                    "operation_error": "",
                    "updated_at": now,
                }
                if state not in {"executing", "completed"}:
                    values.update(
                        queue_state="canceled",
                        current_step="ignored_pack",
                        queue_position=0,
                    )
                columns = ", ".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE addition_jobs SET {columns} WHERE job_id=?",
                    tuple(values.values()) + (str(row["job_id"]),),
                )
                changed += 1
    except Exception:
        return changed
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
    _scrub_existing_jobs()

    # Reprojeta as aprovações depois da limpeza para ele desaparecer da UI já no
    # primeiro boot com esta versão.
    try:
        operational._sync_approved_operational()
    except Exception:
        pass

    _INSTALLED = True
