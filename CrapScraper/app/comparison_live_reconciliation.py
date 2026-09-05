from __future__ import annotations

from typing import Any

from app.comparison import decisions, matching
from app.store.woocommerce import StoreWooCommerceGateway

_INSTALLED = False
_LIVE_GATEWAY: Any | None = None


def _gateway() -> Any:
    global _LIVE_GATEWAY
    if _LIVE_GATEWAY is None:
        _LIVE_GATEWAY = StoreWooCommerceGateway()
    return _LIVE_GATEWAY


def set_live_gateway(gateway: Any | None) -> None:
    global _LIVE_GATEWAY
    _LIVE_GATEWAY = gateway


def _meta(product: dict[str, Any], key: str) -> str:
    return next(
        (str(item.get("value") or "") for item in product.get("meta_data", []) or [] if str(item.get("key") or "") == key),
        "",
    )


def _source_row(row: dict[str, Any]) -> dict[str, Any] | None:
    normalized = matching._normalize_source_rows([
        {
            "nome_produto": row.get("source_name", ""),
            "versao_produto": row.get("source_version", ""),
            "pagina_oficial": row.get("source_official_url", ""),
            "link_produto": row.get("source_product_url", ""),
            "categoria_nome": row.get("source_category", ""),
        }
    ])
    return normalized[0] if normalized else None


def _site_row(product: dict[str, Any]) -> dict[str, Any] | None:
    normalized = matching._normalize_site_rows([
        {
            "ID": str(product.get("id") or ""),
            "Nome": str(product.get("name") or ""),
            "Tipo": str(product.get("type") or ""),
            "Metadado: pt_versao": _meta(product, "pt_versao"),
            "Metadado: site_oficial": _meta(product, "site_oficial"),
            "URL": str(product.get("permalink") or ""),
            "Categorias": ", ".join(str(item.get("name") or "") for item in product.get("categories", []) or []),
        }
    ])
    return normalized[0] if normalized else None


def _find_live_product(row: dict[str, Any], gateway: Any) -> tuple[dict[str, Any] | None, str]:
    name = str(row.get("source_name") or "").strip()
    if not name:
        return None, ""
    products = list(gateway.products(
        search=name,
        status="any",
        _fields="id,name,slug,status,type,categories,meta_data,permalink",
    ))
    source_name_key = matching.normalize_name_key(name)
    source_url_key = matching.normalize_url_key(row.get("source_official_url"))

    url_matches = [
        product for product in products
        if source_url_key and matching.normalize_url_key(_meta(product, "site_oficial")) == source_url_key
    ]
    if len(url_matches) == 1:
        return url_matches[0], "official_url"

    name_matches = [
        product for product in products
        if source_name_key and matching.normalize_name_key(product.get("name")) == source_name_key
    ]
    if len(name_matches) == 1:
        return name_matches[0], "normalized_name"
    return None, ""


def _decision_overlay(row: dict[str, Any]) -> None:
    item_id = str(row.get("comparison_item_id") or "")
    saved = decisions.get_decisions_map([item_id]).get(item_id, {}) if item_id else {}
    row["decision"] = saved.get("decision", "pending")
    row["decision_label"] = saved.get("decision_label", "Pendente")
    row["decision_note"] = saved.get("note", "")
    row["decision_operator"] = saved.get("operator", "")
    row["decision_queue_type"] = saved.get("queue_type", "")
    row["decision_updated_at"] = saved.get("updated_at", "")
    row["has_saved_decision"] = bool(saved)


def reconcile_row(row: dict[str, Any], gateway: Any | None = None) -> dict[str, Any]:
    if str(row.get("status") or "") != "new_source":
        return row
    gateway = gateway or _gateway()
    product, method = _find_live_product(row, gateway)
    if not product:
        return row
    source = _source_row(row)
    site = _site_row(product)
    if not source or not site:
        return row

    old_item_id = str(row.get("comparison_item_id") or "")
    if str(row.get("decision") or "") == "approve_new_product" and old_item_id:
        decisions.reset_decision(old_item_id, operator="live-woocommerce-reconciliation")

    matched = matching._matched_row(site, source, method)
    matched["comparison_item_id"] = matching.build_comparison_item_id(matched, matched)
    _decision_overlay(matched)
    matched["live_reconciled"] = True
    matched["live_woo_product_id"] = int(product.get("id") or 0)
    matched["catalog_snapshot_stale"] = True
    matched["status_reason"] = (
        f"WooCommerce ao vivo confirmou o produto #{int(product.get('id') or 0)} na PluginTema. "
        "O catálogo PluginTema selecionado estava desatualizado para este item. "
        + str(matched.get("status_reason") or "")
    ).strip()
    return matched


def _adjust_summary(result: dict[str, Any], changes: list[tuple[dict[str, Any], dict[str, Any]]]) -> None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    for old, new in changes:
        old_status = str(old.get("status") or "")
        new_status = str(new.get("status") or "")
        if old_status == new_status:
            continue
        if old_status in counts:
            counts[old_status] = max(0, int(counts.get(old_status) or 0) - 1)
        counts[new_status] = int(counts.get(new_status) or 0) + 1
        if old_status == "new_source":
            summary["unmatched_source_total"] = max(0, int(summary.get("unmatched_source_total") or 0) - 1)
            summary["matched_total"] = int(summary.get("matched_total") or 0) + 1
    if changes:
        summary["live_reconciled_total"] = int(summary.get("live_reconciled_total") or 0) + len(changes)


def install_comparison_live_reconciliation() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from app.comparison.service import ComparisonService
    if getattr(ComparisonService, "_crapscraper_live_woo_reconciliation", False):
        _INSTALLED = True
        return
    original_run = ComparisonService.run

    def run(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_run(self, payload)
        rows = list(result.get("rows") or [])
        changes: list[tuple[dict[str, Any], dict[str, Any]]] = []
        reconciled_rows: list[dict[str, Any]] = []
        gateway = _gateway()
        for row in rows:
            try:
                resolved = reconcile_row(dict(row), gateway)
            except Exception as error:
                resolved = dict(row)
                resolved["live_lookup_error"] = str(error)
            if resolved.get("live_reconciled"):
                changes.append((row, resolved))
            reconciled_rows.append(resolved)

        active_status = str((result.get("filters") or {}).get("status") or "all")
        if active_status == "new_source" and changes:
            reconciled_rows = [row for row in reconciled_rows if str(row.get("status") or "") == "new_source"]
            pagination = result.get("pagination") or {}
            pagination["total_rows"] = max(0, int(pagination.get("total_rows") or 0) - len(changes))
        result["rows"] = reconciled_rows
        result["live_reconciliation"] = {"checked": len(rows), "reconciled": len(changes)}
        _adjust_summary(result, changes)
        return result

    ComparisonService.run = run
    ComparisonService._crapscraper_live_woo_reconciliation = True
    _INSTALLED = True


__all__ = ["install_comparison_live_reconciliation", "set_live_gateway", "reconcile_row"]
