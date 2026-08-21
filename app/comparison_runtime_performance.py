from __future__ import annotations

import heapq
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import app.comparison as comparison

_INSTALLED = False
_BASE_BUILD_MATCH_CANDIDATES: Callable[..., list[dict[str, Any]]] | None = None
_BUILD_LOCK = threading.Lock()


def _candidate_limit() -> int:
    try:
        value = int(os.getenv("SCRAPER_COMPARISON_MAX_APPROX_CANDIDATES", "80") or 80)
    except (TypeError, ValueError):
        value = 80
    return max(20, min(value, 300))


def _candidate_priority(site: Mapping[str, Any], source: Mapping[str, Any]) -> tuple[Any, ...]:
    site_tokens = set(site.get("name_tokens") or set())
    source_tokens = set(source.get("name_tokens") or set())
    shared = site_tokens & source_tokens
    union = site_tokens | source_tokens

    site_slug = str(site.get("url_slug") or "").strip()
    source_slug = str(source.get("url_slug") or "").strip()
    same_slug = bool(site_slug and source_slug and site_slug == source_slug)

    site_domain = str(site.get("url_domain") or "").strip()
    source_domain = str(source.get("url_domain") or "").strip()
    same_domain = bool(site_domain and source_domain and site_domain == source_domain)

    site_name = str(site.get("name_key") or "").strip()
    source_name = str(source.get("name_key") or "").strip()
    same_prefix = bool(len(site_name) >= 4 and len(source_name) >= 4 and site_name[:4] == source_name[:4])
    first_token_match = bool(
        site_name and source_name
        and site_name.split(" ", 1)[0] == source_name.split(" ", 1)[0]
    )
    overlap = (len(shared) / len(union)) if union else 0.0
    length_delta = abs(len(site_name) - len(source_name))

    # URL/slug continuam com prioridade máxima. Depois usamos sinais baratos de
    # nome para escolher quais poucos candidatos merecem o SequenceMatcher caro.
    return (
        int(same_slug),
        int(same_domain),
        min(len(shared), 4),
        round(overlap, 4),
        int(same_prefix),
        int(first_token_match),
        -length_delta,
    )


def _bounded_build_match_candidates(
    site: Mapping[str, Any],
    source_rows: list[dict[str, Any]],
    *,
    excluded_source_indexes: set[int] | None = None,
    candidate_source_indexes: set[int] | None = None,
    limit: int = 3,
    minimum_score: int = 45,
) -> list[dict[str, Any]]:
    base = _BASE_BUILD_MATCH_CANDIDATES or comparison.build_match_candidates
    if candidate_source_indexes is None:
        return base(
            site,
            source_rows,
            excluded_source_indexes=excluded_source_indexes,
            candidate_source_indexes=None,
            limit=limit,
            minimum_score=minimum_score,
        )

    excluded = excluded_source_indexes or set()
    valid_indexes = [
        int(index)
        for index in candidate_source_indexes
        if int(index) not in excluded and 0 <= int(index) < len(source_rows)
    ]
    maximum = _candidate_limit()
    if len(valid_indexes) <= maximum:
        selected = set(valid_indexes)
    else:
        selected = set(
            heapq.nlargest(
                maximum,
                valid_indexes,
                key=lambda index: _candidate_priority(site, source_rows[index]),
            )
        )

    return base(
        site,
        source_rows,
        excluded_source_indexes=excluded_source_indexes,
        candidate_source_indexes=selected,
        limit=limit,
        minimum_score=minimum_score,
    )


def _unlocked_cached_comparison(
    source_path: Path,
    site_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Evita manter o cache lock global durante todo o cálculo pesado."""
    cache_key = (comparison._file_signature(source_path), comparison._file_signature(site_path))

    with comparison._CACHE_LOCK:
        if (
            not force
            and comparison._CACHE_KEY == cache_key
            and isinstance(comparison._CACHE_PAYLOAD, dict)
        ):
            return comparison._CACHE_PAYLOAD

    # Só um recálculo pesado por processo. O lock pequeno do cache fica livre
    # para leituras enquanto o trabalho é executado.
    with _BUILD_LOCK:
        with comparison._CACHE_LOCK:
            if (
                not force
                and comparison._CACHE_KEY == cache_key
                and isinstance(comparison._CACHE_PAYLOAD, dict)
            ):
                return comparison._CACHE_PAYLOAD

        payload = comparison._build_full_comparison(source_path, site_path)
        with comparison._CACHE_LOCK:
            comparison._CACHE_KEY = cache_key
            comparison._CACHE_PAYLOAD = payload
        return payload


def install_comparison_runtime_performance() -> None:
    global _INSTALLED, _BASE_BUILD_MATCH_CANDIDATES
    if _INSTALLED:
        return

    _BASE_BUILD_MATCH_CANDIDATES = comparison.build_match_candidates
    comparison.build_match_candidates = _bounded_build_match_candidates
    comparison._get_cached_comparison = _unlocked_cached_comparison
    _INSTALLED = True
