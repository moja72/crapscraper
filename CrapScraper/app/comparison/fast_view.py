from __future__ import annotations

from typing import Any

from app.collection.legacy_core import settings
from app.comparison import decisions, matching


def _text(value: Any) -> str:
    return matching._strip_accents(matching._normalize_spaces(value).lower())


def _integer(value: Any, *, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    number = int(value)
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _overlay_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = [str(row.get("comparison_item_id") or "") for row in rows if row.get("comparison_item_id")]
    saved = decisions.get_decisions_map(ids)
    output: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        item = saved.get(str(row.get("comparison_item_id") or ""), {})
        row.update(
            decision=str(item.get("decision") or "pending"),
            decision_label=str(item.get("decision_label") or "Pendente"),
            decision_note=str(item.get("note") or ""),
            decision_operator=str(item.get("operator") or ""),
            decision_queue_type=str(item.get("queue_type") or ""),
            decision_updated_at=str(item.get("updated_at") or ""),
            has_saved_decision=bool(item),
        )
        if item.get("status") == "updated":
            from app.update_completion_and_retry_runtime import _completed_overlay_is_current
            row["original_decision"] = item.get("decision")
            if _completed_overlay_is_current(row, item):
                row.update(status="updated", status_label="Atualizado",
                           decision_label="Atualizado", decision_queue_type="",
                           recommended_action="no_action")
                row["site_version"] = item.get("site_version") or row.get("site_version")
            else:
                # History remains approve_update in SQLite, but the next source
                # version needs a fresh approval in the operational view.
                row.update(decision="pending", decision_label="Pendente", decision_queue_type="")
        output.append(row)
    return output


def _candidate_filter(rows: list[dict[str, Any]], value: str) -> list[dict[str, Any]]:
    if not value or value == "all":
        return rows
    if value == "with_candidates":
        return [row for row in rows if int(row.get("match_candidate_count") or 0) > 0]
    if value == "without_candidates":
        return [
            row for row in rows
            if str(row.get("status") or "").lower() == "site_only"
            and int(row.get("match_candidate_count") or 0) == 0
        ]
    if value in {"exact", "probable", "ambiguous"}:
        return [
            row for row in rows
            if str(row.get("match_level") or "").lower() == value
            and int(row.get("match_candidate_count") or 0) > 0
        ]
    if value == "disputed":
        return [row for row in rows if bool(row.get("has_disputed_candidate"))]
    if value == "safe_url":
        return [row for row in rows if str(row.get("match_method") or "").lower() == "official_url"]
    if value == "safe_name":
        return [row for row in rows if str(row.get("match_method") or "").lower() == "normalized_name"]
    return rows


def _decision_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: 0 for key in decisions.DECISION_LABELS}
    for row in rows:
        key = str(row.get("decision") or "pending").lower()
        if key not in counts:
            key = "pending"
        counts[key] += 1
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "approved_total": counts.get("approve_update", 0) + counts.get("approve_new_product", 0) + counts.get("same_product", 0),
        "pending_total": counts.get("pending", 0),
        "ignored_total": counts.get("ignore", 0),
        "review_total": counts.get("review_later", 0),
    }


def build_comparison_payload(
    *,
    source_path: Any,
    site_path: Any,
    status: str = "",
    query: str = "",
    decision: str = "",
    candidate_filter: str = "",
    candidate_count_min: int | None = None,
    candidate_count_max: int | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    page: int = 1,
    page_size: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Renderiza filtros/decisões sobre o matching estrutural em cache.

    Decisões são deliberadamente relidas do SQLite a cada request. Assim uma
    aprovação nunca obriga a recalcular milhares de relações de catálogo.
    """
    full = matching._get_cached_comparison(source_path, site_path, force=force)
    all_rows = _overlay_decisions([dict(row) for row in full.get("rows", [])])
    rows = list(all_rows)

    normalized_status = matching._normalize_spaces(status).lower()
    normalized_decision = matching._normalize_spaces(decision).lower()
    normalized_candidate = matching._normalize_spaces(candidate_filter).lower()
    normalized_query = _text(query)

    if normalized_status and normalized_status != "all":
        rows = [row for row in rows if str(row.get("status") or "").lower() == normalized_status]

    if normalized_decision and normalized_decision != "all":
        if normalized_decision == "approved":
            approved = {"approve_update", "approve_new_product", "same_product"}
            rows = [row for row in rows if str(row.get("decision") or "pending").lower() in approved]
        else:
            rows = [row for row in rows if str(row.get("decision") or "pending").lower() == normalized_decision]

    rows = _candidate_filter(rows, normalized_candidate)

    if normalized_query:
        rows = [
            row for row in rows
            if normalized_query in _text(" ".join(
                str(row.get(key) or "")
                for key in (
                    "site_id", "site_name", "source_name", "site_version", "source_version",
                    "source_category", "site_official_url", "source_official_url", "source_product_url",
                )
            ))
        ]

    count_min = _integer(candidate_count_min, minimum=0)
    count_max = _integer(candidate_count_max, minimum=0)
    if count_min is not None and count_max is not None and count_min > count_max:
        count_min, count_max = count_max, count_min
    if count_min is not None:
        rows = [row for row in rows if int(row.get("match_candidate_count") or 0) >= count_min]
    if count_max is not None:
        rows = [row for row in rows if int(row.get("match_candidate_count") or 0) <= count_max]

    resolved_score_min = _integer(score_min, minimum=0, maximum=100)
    resolved_score_max = _integer(score_max, minimum=0, maximum=100)
    if resolved_score_min is not None and resolved_score_max is not None and resolved_score_min > resolved_score_max:
        resolved_score_min, resolved_score_max = resolved_score_max, resolved_score_min
    if resolved_score_min is not None:
        rows = [row for row in rows if int(row.get("match_score") or 0) >= resolved_score_min]
    if resolved_score_max is not None:
        rows = [row for row in rows if int(row.get("match_score") or 0) <= resolved_score_max]

    default_size = int(getattr(settings, "COMPARISON_DEFAULT_PAGE_SIZE", 30) or 30)
    max_size = int(getattr(settings, "COMPARISON_MAX_PAGE_SIZE", 100) or 100)
    resolved_page_size = max(1, min(int(page_size or default_size), max_size))
    total_filtered = len(rows)
    total_pages = max(1, (total_filtered + resolved_page_size - 1) // resolved_page_size)
    resolved_page = max(1, min(int(page or 1), total_pages))
    start = (resolved_page - 1) * resolved_page_size

    return {
        "ok": True,
        "summary": {
            **{key: value for key, value in full.items() if key != "rows"},
            "decision_summary": _decision_summary(all_rows),
            "saved_decision_summary": decisions.get_decision_summary(),
        },
        "filters": {
            "status": normalized_status or "all",
            "query": query,
            "decision": normalized_decision or "all",
            "candidate_filter": normalized_candidate or "all",
            "candidate_count_min": count_min,
            "candidate_count_max": count_max,
            "score_min": resolved_score_min,
            "score_max": resolved_score_max,
        },
        "pagination": {
            "page": resolved_page,
            "page_size": resolved_page_size,
            "total_rows": total_filtered,
            "total_pages": total_pages,
        },
        "rows": rows[start:start + resolved_page_size],
    }


__all__ = ["build_comparison_payload"]
