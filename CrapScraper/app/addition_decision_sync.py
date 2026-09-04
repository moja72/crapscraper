from __future__ import annotations

from typing import Any

_INSTALLED = False


def _approval_fields(item: dict[str, Any]) -> dict[str, Any]:
    from app.updates.repository import source_kind

    kind = source_kind(item)
    provider = str(item.get("source_provider_name") or ("PluginTheme" if kind == "plugintheme" else "UltraPackV2"))
    url = str(item.get("source_product_url") or item.get("source_official_url") or "")
    name = str(item.get("product_name") or item.get("source_product_name") or item.get("source_name") or item.get("comparison_item_id") or "")
    explicit_kind = str(item.get("kind") or item.get("product_type") or item.get("item_type") or "").strip().lower()
    product_kind = "theme" if explicit_kind in {"theme", "tema"} or any(marker in (url + " " + name).lower() for marker in ("/theme", "tema", " theme")) else "plugin"
    return {
        "source_kind": kind,
        "source_name": provider,
        "source_url": url,
        "source_product_id": str(item.get("source_product_id") or ""),
        "source_version": str(item.get("source_version") or ""),
        "product_name": name,
        "kind": product_kind,
        "official_url": str(item.get("source_official_url") or ""),
    }


def _patch_repository_materialize() -> None:
    from app.additions.models import utc_now
    from app.additions.repository import AdditionRepository

    if getattr(AdditionRepository, "_crapscraper_decision_reconcile", False):
        return
    original_materialize = AdditionRepository.materialize

    def materialize(self: Any, approvals: Any) -> dict[str, int]:
        rows = [dict(item) for item in list(approvals or []) if isinstance(item, dict)]
        base = dict(original_materialize(self, rows))
        approved = {str(item.get("comparison_item_id") or "").strip(): item for item in rows if str(item.get("comparison_item_id") or "").strip()}
        updated = 0
        removed = 0
        now = utc_now()

        with self.connection() as db:
            stale = db.execute(
                "SELECT job_id,comparison_item_id FROM addition_jobs WHERE public_state='ready' AND attempts=0 AND woo_product_id=0"
            ).fetchall()
            for row in stale:
                if str(row["comparison_item_id"]) in approved:
                    continue
                db.execute("DELETE FROM addition_jobs WHERE job_id=?", (row["job_id"],))
                removed += 1

            for key, approval in approved.items():
                current = db.execute("SELECT * FROM addition_jobs WHERE comparison_item_id=?", (key,)).fetchone()
                if not current or str(current["public_state"]) in {"running", "success"}:
                    continue
                desired = _approval_fields(approval)
                changed = any(str(current[field] or "") != str(value or "") for field, value in desired.items())
                if not changed:
                    continue
                db.execute(
                    "UPDATE addition_jobs SET source_kind=?,source_name=?,source_url=?,source_product_id=?,source_version=?,"
                    "product_name=?,kind=?,official_url=?,public_state='ready',stage='prepared',current_error=NULL,finished_at='',updated_at=? "
                    "WHERE comparison_item_id=?",
                    (
                        desired["source_kind"], desired["source_name"], desired["source_url"], desired["source_product_id"],
                        desired["source_version"], desired["product_name"], desired["kind"], desired["official_url"], now, key,
                    ),
                )
                updated += 1

        return {**base, "updated": updated, "removed": removed, "total": self.count()}

    AdditionRepository.materialize = materialize
    AdditionRepository._crapscraper_decision_reconcile = True


def _patch_decision_sync() -> None:
    from app.comparison.service import ComparisonService
    import app.addition_runtime_recovery as runtime

    if getattr(ComparisonService, "_crapscraper_all_decisions_sync_additions", False):
        return
    original_save = ComparisonService.save_decision
    original_bulk = ComparisonService.save_decisions_bulk

    def sync() -> None:
        try:
            runtime._sync_after_new_product_approval()
        except Exception:
            pass

    def save_decision(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_save(self, payload)
        sync()
        return result

    def save_bulk(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_bulk(self, payload)
        sync()
        return result

    ComparisonService.save_decision = save_decision
    ComparisonService.save_decisions_bulk = save_bulk
    ComparisonService._crapscraper_all_decisions_sync_additions = True


def install_addition_decision_sync() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_repository_materialize()
    _patch_decision_sync()
    _INSTALLED = True


__all__ = ["install_addition_decision_sync"]
