from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from app.comparison.fast_view import build_comparison_payload
from app.comparison.service import ComparisonService


_ORIGINAL_SAVE_DECISION = ComparisonService.save_decision
_ORIGINAL_SAVE_BULK = ComparisonService.save_decisions_bulk
_ORIGINAL_RESET_DECISION = ComparisonService.reset_decision


def _optional(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key, "")
    return int(value) if str(value) != "" else None


def _run(self: ComparisonService, payload: dict[str, Any]) -> dict[str, Any]:
    with self.lock:
        self.source_id = str(payload.get("source_id") or self.source_id)
        self.site_id = str(payload.get("site_id") or self.site_id)
        source = self.repository.resolve(self.source_id)
        site = self.repository.resolve(self.site_id)
        signature = ((source.stat().st_mtime_ns, source.stat().st_size), (site.stat().st_mtime_ns, site.stat().st_size))

        requested_force = bool(payload.get("force"))
        skip_force = bool(getattr(self, "_crapscraper_skip_next_forced_rebuild", False))
        effective_force = requested_force and not skip_force
        if requested_force:
            self._crapscraper_skip_next_forced_rebuild = False

        cached = not effective_force and signature == self._signature
        started = time.perf_counter()
        result = build_comparison_payload(
            source_path=source,
            site_path=site,
            status=str(payload.get("status", "")),
            query=str(payload.get("query", "")),
            decision=str(payload.get("decision", "")),
            candidate_filter=str(payload.get("confidence", "")),
            candidate_count_min=_optional(payload, "candidate_count_min"),
            candidate_count_max=_optional(payload, "candidate_count_max"),
            score_min=_optional(payload, "score_min"),
            score_max=_optional(payload, "score_max"),
            page=int(payload.get("page", 1)),
            page_size=int(payload.get("page_size", 5)),
            force=effective_force,
        )
        elapsed = round(time.perf_counter() - started, 3)
        self._signature = signature
        self.last_run = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_seconds": elapsed,
            "cached": cached,
            "source_id": self.source_id,
            "site_id": self.site_id,
            "processed": result.get("summary", {}).get("total_rows", 0),
            "filtered": result.get("pagination", {}).get("total_rows", 0),
            "log": [
                f"Fonte: {self.source_id}",
                f"Site: {self.site_id}",
                f"Processados: {result.get('summary', {}).get('total_rows', 0)}",
                f"Filtrados: {result.get('pagination', {}).get('total_rows', 0)}",
                f"Duração: {elapsed:.3f}s",
                f"Cache: {'reutilizado' if cached else 'recalculado'}",
            ],
        }
        result.update(source_id=self.source_id, site_id=self.site_id, revision=self.revision, operation=self.last_run)
        return result


def _save_decision(self: ComparisonService, payload: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SAVE_DECISION(self, payload)
    self._crapscraper_skip_next_forced_rebuild = True
    return result


def _save_bulk(self: ComparisonService, payload: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_SAVE_BULK(self, payload)
    self._crapscraper_skip_next_forced_rebuild = True
    return result


def _reset_decision(self: ComparisonService, payload: dict[str, Any]) -> dict[str, Any]:
    result = _ORIGINAL_RESET_DECISION(self, payload)
    self._crapscraper_skip_next_forced_rebuild = True
    return result


def install_comparison_performance_runtime() -> None:
    if getattr(ComparisonService, "_crapscraper_fast_view_installed", False):
        return
    ComparisonService.run = _run
    ComparisonService.save_decision = _save_decision
    ComparisonService.save_decisions_bulk = _save_bulk
    ComparisonService.reset_decision = _reset_decision
    ComparisonService._crapscraper_fast_view_installed = True


install_comparison_performance_runtime()

__all__ = ["install_comparison_performance_runtime"]
