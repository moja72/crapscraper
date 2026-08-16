from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from typing import Any

from app.plugintema_catalog import product_matches_catalog_kind


PRICE_FIELDS = ("annual_regular", "annual_sale", "lifetime_regular", "lifetime_sale")


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def variation_period(variation: Mapping[str, Any]) -> str:
    parts = [variation.get("name", ""), variation.get("sku", "")]
    parts.extend(
        item.get("option", "")
        for item in variation.get("attributes", []) or []
        if isinstance(item, Mapping)
    )
    value = _fold(" ".join(map(str, parts)))
    if any(token in value for token in ("vitalici", "lifetime", "perpetu")):
        return "lifetime"
    if any(token in value for token in ("anual", "annual", "1 ano", "12 mes")):
        return "annual"
    return ""


def normalize_prices(payload: Mapping[str, Any]) -> dict[str, str]:
    prices: dict[str, str] = {}
    for field in PRICE_FIELDS:
        raw = str(payload.get(field, "") or "").strip().replace("R$", "").strip()
        if raw and "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", ".")
        if not raw:
            if field.endswith("_sale"):
                prices[field] = ""
                continue
            raise ValueError("Informe os dois preços originais.")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            raise ValueError("Use valores monetários válidos.") from None
        if value < 0:
            raise ValueError("Os preços não podem ser negativos.")
        prices[field] = format(value.quantize(Decimal("0.01")), "f")
    for period in ("annual", "lifetime"):
        sale = prices[f"{period}_sale"]
        regular = prices[f"{period}_regular"]
        if sale and Decimal(sale) >= Decimal(regular):
            raise ValueError("O preço promocional deve ser menor que o preço original.")
    return prices


def _selected_products(woo: Any, kinds: Iterable[str]) -> list[Mapping[str, Any]]:
    selected_kinds = {str(kind).strip().lower() for kind in kinds} & {"plugin", "theme"}
    if not selected_kinds:
        raise ValueError("Selecione Plugins e/ou Temas.")
    products: list[Mapping[str, Any]] = []
    page = 1
    while True:
        # Preços, downloads e metadados tornam a listagem completa muito pesada.
        # Para classificar Plugin/Tema bastam estes campos leves.
        batch = list(woo.list_products(
            page=page,
            per_page=100,
            status="publish",
            _fields="id,name,type,categories,tags,attributes",
        ) or [])
        products.extend(
            product for product in batch
            if isinstance(product, Mapping)
            and any(product_matches_catalog_kind(product, kind) for kind in selected_kinds)
        )
        if len(batch) < 100:
            break
        page += 1
    return products


def build_store_pricing_snapshot(woo: Any, kinds: Iterable[str] = ("plugin", "theme")) -> dict[str, Any]:
    products = _selected_products(woo, kinds)
    variations: list[dict[str, Any]] = []
    unmatched = 0
    distribution: dict[str, Counter[tuple[str, str]]] = {
        "annual": Counter(), "lifetime": Counter()
    }
    def load_variations(product: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
        return product, list(woo.list_variations(
            int(product["id"]),
            per_page=100,
            _fields="id,name,sku,attributes,regular_price,sale_price",
        ))

    # A API do WooCommerce exige uma rota por produto. Execute essas leituras em
    # paralelo para que a prévia não cresça linearmente com o catálogo.
    workers = min(12, max(1, len(products)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="store-prices") as executor:
        loaded = [
            future.result()
            for future in as_completed(executor.submit(load_variations, product) for product in products)
        ]

    for product, product_variations in loaded:
        for variation in product_variations:
            period = variation_period(variation)
            if not period:
                unmatched += 1
                continue
            regular = str(variation.get("regular_price", "") or "")
            sale = str(variation.get("sale_price", "") or "")
            distribution[period][(regular, sale)] += 1
            variations.append({
                "product_id": int(product["id"]), "product_name": str(product.get("name", "")),
                "variation_id": int(variation["id"]), "period": period,
                "regular_price": regular, "sale_price": sale,
            })
    return {
        "ok": True,
        "product_count": len(products),
        "variation_count": len(variations),
        "unmatched_variation_count": unmatched,
        "distribution": {
            period: [
                {"regular_price": pair[0], "sale_price": pair[1], "count": count}
                for pair, count in values.most_common(8)
            ] for period, values in distribution.items()
        },
        "variations": variations,
    }


def apply_store_prices(woo: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    if str(payload.get("confirmation", "") or "").strip() != "ALTERAR PRECOS":
        raise ValueError('Digite "ALTERAR PRECOS" para confirmar.')
    kinds = payload.get("kinds", [])
    if not isinstance(kinds, list):
        raise ValueError("Seleção de produtos inválida.")
    prices = normalize_prices(payload)
    snapshot = build_store_pricing_snapshot(woo, kinds)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for variation in snapshot["variations"]:
        period = variation["period"]
        grouped.setdefault(variation["product_id"], []).append({
            "id": variation["variation_id"],
            "regular_price": prices[f"{period}_regular"],
            "sale_price": prices[f"{period}_sale"],
        })
    updated = 0
    errors: list[dict[str, Any]] = []
    for product_id, updates in grouped.items():
        try:
            updated += len(woo.update_variations_prices(product_id, updates, authorized=True))
        except Exception as error:
            errors.append({"product_id": product_id, "message": str(error)})
    return {
        "ok": not errors,
        "message": (
            f"{updated} variações atualizadas em {len(grouped) - len(errors)} produtos."
            if not errors else
            f"{updated} variações atualizadas; {len(errors)} produtos apresentaram erro."
        ),
        "updated_variation_count": updated,
        "updated_product_count": len(grouped) - len(errors),
        "unmatched_variation_count": snapshot["unmatched_variation_count"],
        "errors": errors,
    }
