from __future__ import annotations

import math
from typing import Any

from app.additions.service import AdditionService


_INSTALLED = False
_ORIGINAL_LIST = None


def _sort_key(item: dict[str, Any], sort_by: str):
    if sort_by == "name":
        return str(item.get("product_name") or "").casefold()
    return str(item.get("created_at") or "")


def _collect(
    service: AdditionService,
    *,
    query: str,
    group: str,
    stage: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    first = service.repository.list(query, group, stage, 1, 100)
    items = list(first["items"])
    for page in range(2, int(first.get("pages") or 1) + 1):
        items.extend(service.repository.list(query, group, stage, page, 100)["items"])
    return items, dict(first.get("counts") or {})


def _list(self: AdditionService, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    p = payload or {}
    query = str(p.get("query") or "")
    group = str(p.get("group") or "")
    stage = str(p.get("stage") or "")
    sort_by = str(p.get("sort_by") or "date").strip().lower()
    sort_order = str(p.get("sort_order") or "desc").strip().lower()
    page = max(1, int(p.get("page") or 1))
    page_size = max(1, min(100, int(p.get("page_size") or 5)))

    if sort_by not in {"date", "name"}:
        raise ValueError("Campo de ordenação inválido")
    if sort_order not in {"asc", "desc"}:
        raise ValueError("Direção de ordenação inválida")

    items, counts = _collect(self, query=query, group=group, stage=stage)
    items.sort(key=lambda item: _sort_key(item, sort_by), reverse=sort_order == "desc")

    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    page = min(page, pages)
    start = (page - 1) * page_size

    return {
        "ok": True,
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "counts": counts,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "batch": self.batch.state(),
        "database": str(self.repository.path),
    }


def install_addition_sort_runtime() -> None:
    global _INSTALLED, _ORIGINAL_LIST
    if _INSTALLED:
        return
    _ORIGINAL_LIST = AdditionService.list
    AdditionService.list = _list
    _INSTALLED = True


__all__ = ["install_addition_sort_runtime"]
