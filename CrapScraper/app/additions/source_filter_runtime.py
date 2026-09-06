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


# Compatibility names retain the canonical repository/service implementations.
_repository_list = AdditionRepository.list
_service_list = AdditionService.list


def install_addition_source_filters() -> None:
    if getattr(AdditionRepository, "_crapscraper_source_filters_installed", False):
        return
    AdditionRepository.list = _repository_list
    AdditionRepository._crapscraper_source_filters_installed = True
    AdditionService.list = _service_list


__all__ = ["install_addition_source_filters"]
