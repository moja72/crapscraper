from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any, Callable

import app.store_pricing as store_pricing

_INSTALLED = False
_BASE_LIST: Callable[..., list[dict[str, Any]]] | None = None
_BASE_UPDATE: Callable[..., dict[str, Any]] | None = None

_PLAN_CATEGORY_KEYS = frozenset({
    "plano", "planos", "assinatura", "assinaturas", "subscription", "subscriptions",
    "membership", "memberships",
})


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def is_plan_product(product: Mapping[str, Any]) -> bool:
    """Reconhece produtos comerciais de plano sem depender de IDs fixos."""
    if store_pricing.is_pack_product(product):
        return False
    categories = {
        _fold(item.get("name", ""))
        for item in product.get("categories", []) or []
        if isinstance(item, Mapping)
    }
    product_type = _fold(product.get("type", ""))
    name = _fold(product.get("name", ""))
    return bool(
        categories.intersection(_PLAN_CATEGORY_KEYS)
        or "subscription" in product_type
        or name == "plano"
        or name.startswith("plano ")
    )


def _paged_products(woo: Any, **filters: Any) -> list[Mapping[str, Any]]:
    products: list[Mapping[str, Any]] = []
    page = 1
    while True:
        batch = list(woo.list_products(page=page, per_page=100, **filters) or [])
        products.extend(item for item in batch if isinstance(item, Mapping))
        if len(batch) < 100:
            break
        page += 1
    return products


def _list_store_plan_products(woo: Any) -> list[dict[str, Any]]:
    """Lista planos publicados usando campos leves da API WooCommerce."""
    fields = "id,name,type,status,categories,regular_price,sale_price,price"
    found: dict[int, Mapping[str, Any]] = {}
    for product in _paged_products(woo, status="publish", _fields=fields):
        if not is_plan_product(product):
            continue
        product_id = int(product.get("id") or 0)
        if product_id > 0:
            found[product_id] = product
    return [
        {
            "product_id": product_id,
            "product_name": str(product.get("name", "") or ""),
            "product_type": str(product.get("type", "") or ""),
            "regular_price": str(product.get("regular_price", "") or ""),
            "sale_price": str(product.get("sale_price", "") or ""),
            "last_price": str(product.get("price", "") or ""),
            "pricing_group": "plan",
        }
        for product_id, product in sorted(
            found.items(), key=lambda item: str(item[1].get("name", "")).casefold()
        )
    ]


def _variation_label(variation: Mapping[str, Any], period: str) -> str:
    if period == "annual":
        return "Anual"
    if period == "lifetime":
        return "Vitalício"
    options = [
        str(item.get("option") or "").strip()
        for item in variation.get("attributes", []) or []
        if isinstance(item, Mapping) and str(item.get("option") or "").strip()
    ]
    if options:
        return " / ".join(dict.fromkeys(options))
    return str(variation.get("name") or variation.get("sku") or "Variação").strip()


def _expand_product_rows(woo: Any, parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    product_id = int(parent.get("product_id") or 0)
    if product_id <= 0:
        return []
    pricing_group = str(parent.get("pricing_group") or "pack")
    try:
        variations = list(woo.list_variations(
            product_id,
            per_page=100,
            _fields="id,name,sku,attributes,regular_price,sale_price,price",
        ) or [])
    except Exception:
        variations = []

    rows: list[dict[str, Any]] = []
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        period = store_pricing.variation_period(variation)
        if pricing_group == "pack" and period not in {"annual", "lifetime"}:
            continue
        variation_id = int(variation.get("id") or 0)
        if variation_id <= 0:
            continue
        rows.append({
            **dict(parent),
            "variation_id": variation_id,
            "variation": _variation_label(variation, period),
            "period": period,
            "regular_price": str(variation.get("regular_price", "") or ""),
            "sale_price": str(variation.get("sale_price", "") or ""),
            "last_price": str(
                variation.get("price")
                or variation.get("sale_price")
                or variation.get("regular_price")
                or ""
            ),
        })

    if rows:
        rows.sort(key=lambda item: (
            0 if item.get("period") == "annual" else 1 if item.get("period") == "lifetime" else 2,
            str(item.get("variation") or "").casefold(),
        ))
        return rows
    return [{**dict(parent), "variation_id": 0, "variation": "Produto", "period": ""}]


def _patched_list_store_pack_products(woo: Any) -> list[dict[str, Any]]:
    base = _BASE_LIST or store_pricing.list_store_pack_products
    pack_parents = [{**item, "pricing_group": "pack"} for item in base(woo)]
    plan_parents = _list_store_plan_products(woo)
    rows: list[dict[str, Any]] = []
    for parent in [*pack_parents, *plan_parents]:
        rows.extend(_expand_product_rows(woo, parent))
    return rows


def _patched_update_store_pack_price(woo: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    product_id = int(payload.get("product_id") or 0)
    variation_id = int(payload.get("variation_id") or 0)
    if product_id <= 0:
        raise ValueError("Produto inválido.")

    product = woo.get_product(product_id)
    is_pack = store_pricing.is_pack_product(product)
    is_plan = is_plan_product(product)
    if not (is_pack or is_plan):
        raise ValueError("O produto selecionado não é um pacote nem um plano reconhecido.")

    regular, sale = store_pricing.normalize_price_pair(
        payload.get("regular_price"), payload.get("sale_price")
    )
    pricing_group = "pack" if is_pack else "plan"

    if variation_id <= 0:
        updated = woo.update_product_prices(product_id, regular, sale, authorized=True)
        return {
            "ok": True,
            "message": f"Preços de {product.get('name') or ('#' + str(product_id))} atualizados.",
            "product": {
                "product_id": product_id,
                "product_name": str(updated.get("name") or product.get("name") or ""),
                "product_type": str(updated.get("type") or product.get("type") or ""),
                "variation_id": 0,
                "variation": "Produto",
                "period": "",
                "pricing_group": pricing_group,
                "regular_price": str(updated.get("regular_price", regular) or regular),
                "sale_price": str(updated.get("sale_price", sale) or sale),
                "last_price": str(updated.get("price") or sale or regular),
            },
        }

    variation = woo.get_variation(product_id, variation_id)
    period = store_pricing.variation_period(variation)
    if is_pack and period not in {"annual", "lifetime"}:
        raise ValueError("A variação selecionada do pacote não é Anual nem Vitalícia.")

    updated_rows = woo.update_variations_prices(
        product_id,
        [{"id": variation_id, "regular_price": regular, "sale_price": sale}],
        authorized=True,
    )
    updated = next(
        (item for item in updated_rows if int(item.get("id") or 0) == variation_id),
        variation,
    )
    label = _variation_label(variation, period)
    return {
        "ok": True,
        "message": f"{product.get('name') or ('#' + str(product_id))} · {label} atualizado.",
        "product": {
            "product_id": product_id,
            "product_name": str(product.get("name") or ""),
            "product_type": str(product.get("type") or ""),
            "variation_id": variation_id,
            "variation": label,
            "period": period,
            "pricing_group": pricing_group,
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
