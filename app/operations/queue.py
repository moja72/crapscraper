from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from app.comparison_decisions import list_approved_additions, list_approved_updates
from app.operations.models import OperationalJob


DecisionLoader = Callable[[], list[dict[str, Any]]]


def _job_from_decision(
    row: Mapping[str, Any], enrichment: Mapping[str, Any] | None = None
) -> OperationalJob:
    # Persisted snapshots are authoritative.  UI rows only fill fields missing
    # from decisions created before snapshot columns existed.
    merged = dict(enrichment or {})
    merged.update({key: value for key, value in dict(row).items() if value not in (None, "")})
    return OperationalJob(
        comparison_item_id=str(merged.get("comparison_item_id", "")),
        woo_product_id=int(float(merged.get("woo_product_id") or merged.get("site_id") or 0)),
        name=str(merged.get("site_name") or merged.get("source_name") or ""),
        plugintema_version=str(merged.get("site_version") or ""),
        ultrapack_version=str(merged.get("source_version") or ""),
        ultrapack_url=str(merged.get("source_product_url") or ""),
        official_url=str(merged.get("source_official_url") or ""),
        decision=str(merged.get("decision") or ""),
        relationship=str(merged.get("relationship_state") or ""),
        queue_type=str(merged.get("queue_type") or ""),
        approved_source_version=str(merged.get("source_version") or ""),
        effective_source_version="",
    )


def materialize_queue(
    *,
    update_loader: DecisionLoader = list_approved_updates,
    addition_loader: DecisionLoader = list_approved_additions,
    comparison_rows: Iterable[Mapping[str, Any]] = (),
) -> dict[str, list[OperationalJob]]:
    enrichment = {
        str(row.get("comparison_item_id", "")): row for row in comparison_rows
    }
    updates = [
        _job_from_decision(row, enrichment.get(str(row.get("comparison_item_id", ""))))
        for row in update_loader()
        if row.get("decision") == "approve_update" and row.get("queue_type") == "update"
    ]
    additions = [
        _job_from_decision(row, enrichment.get(str(row.get("comparison_item_id", ""))))
        for row in addition_loader()
        if row.get("decision") == "approve_new_product"
        and row.get("queue_type") == "new_product"
    ]
    return {"update": updates, "new_product": additions}
