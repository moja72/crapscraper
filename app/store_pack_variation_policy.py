from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import app.store_pricing as store_pricing

_INSTALLED = False
_BASE_LIST: Callable[..., list[dict[str, Any]]] | None = None
_BASE_UPDATE: Callable[..., dict[str, Any]] | None = None


def _variation_label(variation: Mapping[str, Any], period: str) -> str:
    if period == "annual":
        return "Anual"
    if period == "lifetime":
        return "Vitalício"
    for item in variation.get("attributes", []) or []:
        if isinstance(item, Mapping) and str(item.get("option") or "").strip():
            return str(item.get("option") or "").strip()
    return str(variation.get("name") or variation.get("sku") or "Variação").strip()


def _patched_list_store_pack_products(woo: Any) -> list[dict[str, Any]]:
    base = _BASE_LIST or store_pricing.list_store_pack_products
    parents = list(base(woo))
    rows: list[dict[str, Any]] = []
    for parent in parents:
        product_id = int(parent.get("product_id") or 0)
        if product_id <= 0:
            continue
        try:
            variations = list(woo.list_variations(
                product_id,
                per_page=100,
                _fields="id,name,sku,attributes,regular_price,sale_price,price",
            ) or [])
        except Exception:
            variations = []
        recognized = []
        for variation in variations:
            if not isinstance(variation, Mapping):
                continue
            period = store_pricing.variation_period(variation)
            if period not in {"annual", "lifetime"}:
                continue
            recognized.append({
                **parent,
                "variation_id": int(variation.get("id") or 0),
                "variation": _variation_label(variation, period),
                "period": period,
                "regular_price": str(variation.get("regular_price", "") or ""),
                "sale_price": str(variation.get("sale_price", "") or ""),
                "last_price": str(variation.get("price", "") or variation.get("sale_price") or variation.get("regular_price") or ""),
            })
        if recognized:
            recognized.sort(key=lambda item: 0 if item.get("period") == "annual" else 1)
            rows.extend(recognized)
        else:
            rows.append({**parent, "variation_id": 0, "variation": "Produto", "period": ""})
    return rows


def _patched_update_store_pack_price(woo: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    variation_id = int(payload.get("variation_id") or 0)
    if variation_id <= 0:
        base = _BASE_UPDATE or store_pricing.update_store_pack_price
        return base(woo, payload)

    product_id = int(payload.get("product_id") or 0)
    if product_id <= 0:
        raise ValueError("Produto pack inválido.")
    product = woo.get_product(product_id)
    if not store_pricing.is_pack_product(product):
        raise ValueError("O produto selecionado não é um pacote/pack.")
    variation = woo.get_variation(product_id, variation_id)
    period = store_pricing.variation_period(variation)
    if period not in {"annual", "lifetime"}:
        raise ValueError("A variação selecionada não é Anual nem Vitalícia.")
    regular, sale = store_pricing.normalize_price_pair(
        payload.get("regular_price"), payload.get("sale_price")
    )
    updated_rows = woo.update_variations_prices(
        product_id,
        [{"id": variation_id, "regular_price": regular, "sale_price": sale}],
        authorized=True,
    )
    updated = next((item for item in updated_rows if int(item.get("id") or 0) == variation_id), variation)
    return {
        "ok": True,
        "message": f"{product.get('name') or ('#' + str(product_id))} · {_variation_label(variation, period)} atualizado.",
        "product": {
            "product_id": product_id,
            "product_name": str(product.get("name") or ""),
            "product_type": str(product.get("type") or ""),
            "variation_id": variation_id,
            "variation": _variation_label(variation, period),
            "period": period,
            "regular_price": str(updated.get("regular_price", regular) or regular),
            "sale_price": str(updated.get("sale_price", sale) or sale),
            "last_price": str(updated.get("price") or sale or regular),
        },
    }


def install_store_pack_variation_policy() -> None:
    global _INSTALLED, _BASE_LIST, _BASE_UPDATE
    if _INSTALLED:
        return
    _BASE_LIST = store_pricing.list_store_pack_products
    _BASE_UPDATE = store_pricing.update_store_pack_price
    store_pricing.list_store_pack_products = _patched_list_store_pack_products
    store_pricing.update_store_pack_price = _patched_update_store_pack_price
    _INSTALLED = True
