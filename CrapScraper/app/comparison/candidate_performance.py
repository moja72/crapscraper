from __future__ import annotations

from typing import Any, Mapping

from app.comparison import matching

_ORIGINAL_BUILD_MATCH_CANDIDATES = matching.build_match_candidates
_MAX_EXPENSIVE_CANDIDATES = 240


def _cheap_rank(site: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[float, ...]:
    site_tokens = set(site.get("name_tokens") or set())
    source_tokens = set(source.get("name_tokens") or set())
    shared = site_tokens & source_tokens
    union = site_tokens | source_tokens
    token_ratio = len(shared) / len(union) if union else 0.0
    site_domain = str(site.get("url_domain") or "")
    source_domain = str(source.get("url_domain") or "")
    site_slug = str(site.get("url_slug") or "")
    source_slug = str(source.get("url_slug") or "")
    site_name = str(site.get("name_key") or "")
    source_name = str(source.get("name_key") or "")
    return (
        1.0 if site_slug and site_slug == source_slug else 0.0,
        1.0 if site_domain and site_domain == source_domain else 0.0,
        1.0 if len(site_name) >= 4 and site_name[:4] == source_name[:4] else 0.0,
        float(len(shared)),
        token_ratio,
        -float(abs(len(site_name) - len(source_name))),
    )


def _build_match_candidates(
    site: Mapping[str, Any],
    source_rows: list[dict[str, Any]],
    *,
    excluded_source_indexes: set[int] | None = None,
    candidate_source_indexes: set[int] | None = None,
    limit: int = 3,
    minimum_score: int = 45,
) -> list[dict[str, Any]]:
    indexes = candidate_source_indexes
    if indexes is not None and len(indexes) > _MAX_EXPENSIVE_CANDIDATES:
        valid = [index for index in indexes if 0 <= index < len(source_rows)]
        valid.sort(key=lambda index: _cheap_rank(site, source_rows[index]), reverse=True)
        indexes = set(valid[:_MAX_EXPENSIVE_CANDIDATES])
    return _ORIGINAL_BUILD_MATCH_CANDIDATES(
        site,
        source_rows,
        excluded_source_indexes=excluded_source_indexes,
        candidate_source_indexes=indexes,
        limit=limit,
        minimum_score=minimum_score,
    )


def install_candidate_performance() -> None:
    if getattr(matching, "_crapscraper_candidate_performance_installed", False):
        return
    matching.build_match_candidates = _build_match_candidates
    matching._crapscraper_candidate_performance_installed = True


install_candidate_performance()

__all__ = ["install_candidate_performance", "_MAX_EXPENSIVE_CANDIDATES"]
