from __future__ import annotations

from typing import Any

from app.additions.repository import AdditionRepository
from app.additions.service import AdditionService
from app.additions.state import GROUP_STATES


KNOWN_SOURCES = {"plugintheme", "ultrapackv2"}


def _sources(value: Any) -> set[str] | None:
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
    self: AdditionRepository,
    query: str = "",
    group: str = "",
    stage: str = "",
    page: int = 1,
    page_size: int = 5,
    sources: Any = None,
) -> dict[str, Any]:
    filters: list[str] = []
    values: list[Any] = []
    if query:
        filters.append("(product_name LIKE ? OR source_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ?)")
        values += [f"%{query}%"] * 3
    if group:
        if group not in GROUP_STATES:
            raise ValueError("Grupo operacional inválido")
        filters.append("public_state=?")
        values.append(GROUP_STATES[group])
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
    with self.connection() as db:
        total = int(db.execute("SELECT COUNT(*) FROM addition_jobs" + where, values).fetchone()[0])
        rows = db.execute(
            "SELECT * FROM addition_jobs" + where + " ORDER BY created_at LIMIT ? OFFSET ?",
            values + [page_size, (page - 1) * page_size],
        ).fetchall()
        counts = {"total": int(db.execute("SELECT COUNT(*) FROM addition_jobs").fetchone()[0])}
        for group_name, state in GROUP_STATES.items():
            counts[group_name] = int(db.execute("SELECT COUNT(*) FROM addition_jobs WHERE public_state=?", (state,)).fetchone()[0])
    return {
        "items": [self.decode(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "counts": counts,
        "sources": sorted(selected) if selected is not None else None,
    }


def _service_list(self: AdditionService, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    return {
        "ok": True,
        **self.repository.list(
            str(payload.get("query") or ""),
            str(payload.get("group") or ""),
            str(payload.get("stage") or ""),
            int(payload.get("page") or 1),
            int(payload.get("page_size") or 5),
            sources=payload.get("sources"),
        ),
        "batch": self.batch.state(),
        "database": str(self.repository.path),
    }


def install_addition_source_filters() -> None:
    if getattr(AdditionRepository, "_crapscraper_source_filters_installed", False):
        return
    AdditionRepository.list = _repository_list
    AdditionRepository._crapscraper_source_filters_installed = True
    AdditionService.list = _service_list


__all__ = ["install_addition_source_filters"]
