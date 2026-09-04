from __future__ import annotations

from typing import Any

from app.updates.repository import UpdateRepository
from app.updates.service import UpdateService
from app.updates.state import GROUP_BY_STATE


KNOWN_SOURCES = {"plugintheme", "ultrapackv2"}


def _sources(value: Any) -> set[str] | None:
    """None = filtro ausente; set vazio = usuário desmarcou todas as fontes."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        raw = [str(item) for item in value]
    else:
        raw = str(value).split(",")
    tokens = {item.strip().lower() for item in raw if item is not None and str(item).strip()}
    if "__none__" in tokens:
        return set()
    return tokens & KNOWN_SOURCES


def _repository_list(
    self: UpdateRepository,
    *,
    query: str = "",
    group: str = "",
    stage: str = "",
    page: int = 1,
    page_size: int = 5,
    sort_by: str = "date",
    sort_order: str = "desc",
    sources: Any = None,
) -> dict[str, Any]:
    filters: list[str] = []
    values: list[Any] = []
    if query:
        filters.append("(product_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? OR source_name LIKE ?)")
        values += [f"%{query}%"] * 3
    if group:
        states = GROUP_BY_STATE.get(group)
        if not states:
            raise ValueError("Grupo operacional inválido")
        filters.append("public_state=?")
        values.append(states[0])
    if stage:
        filters.append("stage=?")
        values.append(stage)

    selected = _sources(sources)
    if selected is not None:
        if not selected:
            filters.append("1=0")
        else:
            ordered = sorted(selected)
            filters.append("source_kind IN (" + ",".join("?" for _ in ordered) + ")")
            values.extend(ordered)

    where = " WHERE " + " AND ".join(filters) if filters else ""
    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    sort_columns = {"date": "created_at", "name": "product_name"}
    if sort_by not in sort_columns:
        raise ValueError("Campo de ordenacao invalido")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("Direcao de ordenacao invalida")
    column = sort_columns[sort_by]
    direction = sort_order.upper()
    order = f"{column} COLLATE NOCASE {direction}, queue_position {direction}, job_id {direction}"

    with self.connection() as db:
        total = int(db.execute("SELECT COUNT(*) FROM update_jobs" + where, values).fetchone()[0])
        rows = db.execute(
            "SELECT * FROM update_jobs" + where + f" ORDER BY {order} LIMIT ? OFFSET ?",
            values + [page_size, (page - 1) * page_size],
        ).fetchall()
        counts = {"total": int(db.execute("SELECT COUNT(*) FROM update_jobs").fetchone()[0])}
        for key, state in (("prepared", "ready"), ("running", "running"), ("success", "success"), ("error", "error")):
            counts[key] = int(db.execute("SELECT COUNT(*) FROM update_jobs WHERE public_state=?", (state,)).fetchone()[0])

    return {
        "items": [self._decode(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "counts": counts,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "sources": sorted(selected) if selected is not None else None,
    }


def _service_list(self: UpdateService, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    self.materialize()
    result = self.repository.list(
        query=str(payload.get("query") or ""),
        group=str(payload.get("group") or ""),
        stage=str(payload.get("stage") or ""),
        page=int(payload.get("page") or 1),
        page_size=int(payload.get("page_size") or 5),
        sort_by=str(payload.get("sort_by") or "date"),
        sort_order=str(payload.get("sort_order") or "desc"),
        sources=payload.get("sources"),
    )
    result["items"] = [self._with_execution(item) for item in result["items"]]
    return {"ok": True, **result, "batch": self.batch.state(), "database": str(self.repository.path)}


def _selection(self: UpdateService, payload: dict[str, Any]) -> dict[str, Any]:
    base = {
        "query": str(payload.get("query") or ""),
        "group": str(payload.get("group") or ""),
        "stage": str(payload.get("stage") or ""),
        "sort_by": str(payload.get("sort_by") or "date"),
        "sort_order": str(payload.get("sort_order") or "desc"),
        "sources": payload.get("sources"),
    }
    first = self.repository.list(**base, page=1, page_size=100)
    items = list(first["items"])
    for page in range(2, int(first.get("pages") or 1) + 1):
        items.extend(self.repository.list(**base, page=page, page_size=100)["items"])
    return {"ok": True, "items": [self._with_execution(item) for item in items], "total": len(items)}


def install_update_source_filters() -> None:
    if getattr(UpdateRepository, "_crapscraper_source_filters_installed", False):
        return
    UpdateRepository.list = _repository_list
    UpdateRepository._crapscraper_source_filters_installed = True
    UpdateService.list = _service_list
    UpdateService.selection = _selection


__all__ = ["install_update_source_filters"]
