from __future__ import annotations

import re
import csv
import html
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from app.plugintema_catalog import categories_match_catalog_kind, product_matches_catalog_kind


PRICE_FIELDS = ("annual_regular", "annual_sale", "lifetime_regular", "lifetime_sale")


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def is_pack_product(product: Mapping[str, Any]) -> bool:
    categories = [_fold(item.get("name", "")) for item in product.get("categories", []) or []
                  if isinstance(item, Mapping)]
    return str(product.get("type", "")).strip().lower() == "bundle" or any(
        value in {"pack", "packs", "pacote", "pacotes"} for value in categories
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


def list_store_pack_products(woo: Any) -> list[dict[str, Any]]:
    """Lista bundles e produtos da categoria Pack sem duplicar registros."""
    found: dict[int, Mapping[str, Any]] = {}
    fields = "id,name,type,status,categories,regular_price,sale_price,price"
    for product in _paged_products(woo, status="publish", type="bundle", _fields=fields):
        found[int(product.get("id") or 0)] = product
    category_ids: list[int] = []
    page = 1
    while True:
        batch = list(woo.list_product_categories(page=page, per_page=100) or [])
        category_ids.extend(
            int(item.get("id") or 0) for item in batch if isinstance(item, Mapping)
            and _fold(item.get("name", "")) in {"pack", "packs", "pacote", "pacotes"}
        )
        if len(batch) < 100:
            break
        page += 1
    for category_id in category_ids:
        for product in _paged_products(
            woo, status="publish", category=category_id, _fields=fields,
        ):
            if is_pack_product(product):
                found[int(product.get("id") or 0)] = product
    return [
        {
            "product_id": product_id,
            "product_name": str(product.get("name", "") or ""),
            "product_type": str(product.get("type", "") or ""),
            "regular_price": str(product.get("regular_price", "") or ""),
            "sale_price": str(product.get("sale_price", "") or ""),
            "last_price": str(product.get("price", "") or ""),
        }
        for product_id, product in sorted(found.items(), key=lambda item: str(item[1].get("name", "")).casefold())
        if product_id
    ]


def normalize_price_pair(regular: Any, sale: Any) -> tuple[str, str]:
    def parse(value: Any, *, required: bool) -> str:
        raw = str(value or "").strip().replace("R$", "").strip()
        if raw and "," in raw and "." in raw:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", ".")
        if not raw and not required:
            return ""
        if not raw:
            raise ValueError("Informe o preço original.")
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            raise ValueError("Use valores monetários válidos.") from None
        if amount < 0:
            raise ValueError("Os preços não podem ser negativos.")
        return format(amount.quantize(Decimal("0.01")), "f")
    normalized_regular, normalized_sale = parse(regular, required=True), parse(sale, required=False)
    if normalized_sale and Decimal(normalized_sale) >= Decimal(normalized_regular):
        raise ValueError("O preço promocional deve ser menor que o preço original.")
    return normalized_regular, normalized_sale


def update_store_pack_price(woo: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    product_id = int(payload.get("product_id") or 0)
    if product_id <= 0:
        raise ValueError("Produto pack inválido.")
    product = woo.get_product(product_id)
    if not is_pack_product(product):
        raise ValueError("O produto selecionado não é um pacote/pack.")
    regular, sale = normalize_price_pair(payload.get("regular_price"), payload.get("sale_price"))
    updated = woo.update_product_prices(product_id, regular, sale, authorized=True)
    return {
        "ok": True, "message": f"Preços de {product.get('name') or ('#' + str(product_id))} atualizados.",
        "product": {
            "product_id": product_id, "product_name": str(updated.get("name") or product.get("name") or ""),
            "product_type": str(updated.get("type") or product.get("type") or ""),
            "regular_price": str(updated.get("regular_price", regular) or regular),
            "sale_price": str(updated.get("sale_price", sale) or sale),
            "last_price": str(updated.get("price") or sale or regular),
        },
    }


def products_without_short_description(
    woo: Any, query: str = "", *,
    progress: Callable[[int, int, int, str], None] | None = None,
) -> list[dict[str, Any]]:
    folded_query = _fold(query)
    missing = []
    page, examined = 1, 0
    while True:
        batch = list(woo.list_products(
            page=page, per_page=100, status="publish",
            _fields="id,name,type,categories,short_description,permalink",
        ) or [])
        for product in batch:
            if not isinstance(product, Mapping):
                continue
            examined += 1
            short = html.unescape(re.sub(r"<[^>]+>", " ", str(product.get("short_description", "") or "")))
            if _fold(short):
                continue
            searchable = _fold(" ".join((str(product.get("id", "")), str(product.get("name", "")))))
            if folded_query and folded_query not in searchable:
                continue
            missing.append({
                "product_id": int(product.get("id") or 0),
                "product_name": str(product.get("name", "") or ""),
                "product_type": str(product.get("type", "") or ""),
                "categories": [str(item.get("name", "") or "") for item in product.get("categories", []) or [] if isinstance(item, Mapping)],
                "permalink": str(product.get("permalink", "") or ""),
            })
        if progress:
            progress(page, examined, len(missing), str(batch[-1].get("name", "")) if batch else "")
        if len(batch) < 100:
            break
        page += 1
    return missing


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


def read_store_price_reference_products(
    imports_dir: Path, kinds: Iterable[str] = ("plugin", "theme"), *, limit_per_kind: int | None = 3,
) -> list[dict[str, Any]]:
    """Lê poucos IDs representativos dos catálogos locais, sem consultar todo o WooCommerce."""
    requested = tuple(dict.fromkeys(str(kind).strip().lower() for kind in kinds))
    selected = {kind: [] for kind in requested if kind in {"plugin", "theme"}}
    seen_ids: set[int] = set()
    paths = sorted(Path(imports_dir).glob("plugintema-*.csv"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                categories = [item.strip() for item in str(row.get("Categorias", "")).split(",") if item.strip()]
                try:
                    product_id = int(str(row.get("ID", "")).strip())
                except ValueError:
                    continue
                if product_id in seen_ids:
                    continue
                kind = next((item for item in selected if categories_match_catalog_kind(categories, item)), "")
                limit = max(1, limit_per_kind) if limit_per_kind is not None else None
                if not kind or (limit is not None and len(selected[kind]) >= limit):
                    continue
                selected[kind].append({
                    "id": product_id,
                    "name": str(row.get("Nome", "") or ""),
                    "categories": [{"name": category} for category in categories],
                })
                seen_ids.add(product_id)
                if limit is not None and selected and all(len(items) >= limit for items in selected.values()):
                    return [product for items in selected.values() for product in items]
    return [product for items in selected.values() for product in items]


def build_store_pricing_snapshot(
    woo: Any, kinds: Iterable[str] = ("plugin", "theme"), *,
    products: Iterable[Mapping[str, Any]] | None = None,
    progress: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    requested_kinds = tuple(dict.fromkeys(str(kind).strip().lower() for kind in kinds))
    selected_products = list(products) if products is not None else _selected_products(woo, requested_kinds)
    if progress:
        progress("reading", 0, len(selected_products), "")
    variations: list[dict[str, Any]] = []
    unmatched = 0
    distribution: dict[str, Counter[tuple[str, str]]] = {
        "annual": Counter(), "lifetime": Counter()
    }
    by_kind: dict[str, dict[str, Any]] = {
        kind: {
            "product_ids": set(),
            "variation_count": 0,
            "unmatched_variation_count": 0,
            "distribution": {"annual": Counter(), "lifetime": Counter()},
        }
        for kind in requested_kinds
        if kind in {"plugin", "theme"}
    }
    def load_variations(product: Mapping[str, Any]) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
        return product, list(woo.list_variations(
            int(product["id"]),
            per_page=100,
            _fields="id,name,sku,attributes,regular_price,sale_price",
        ))

    # A API do WooCommerce exige uma rota por produto. Execute essas leituras em
    # paralelo para que a prévia não cresça linearmente com o catálogo.
    workers = min(12, max(1, len(selected_products)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="store-prices") as executor:
        loaded = []
        futures = [executor.submit(load_variations, product) for product in selected_products]
        for completed, future in enumerate(as_completed(futures), start=1):
            loaded.append(future.result())
            if progress:
                product = loaded[-1][0]
                progress("reading", completed, len(selected_products), str(product.get("name", "")))

    for product, product_variations in loaded:
        product_kind = next(
            (kind for kind in requested_kinds if product_matches_catalog_kind(product, kind)),
            "",
        )
        kind_summary = by_kind.get(product_kind)
        if kind_summary is not None:
            kind_summary["product_ids"].add(int(product["id"]))
        for variation in product_variations:
            period = variation_period(variation)
            if not period:
                unmatched += 1
                if kind_summary is not None:
                    kind_summary["unmatched_variation_count"] += 1
                continue
            regular = str(variation.get("regular_price", "") or "")
            sale = str(variation.get("sale_price", "") or "")
            distribution[period][(regular, sale)] += 1
            if kind_summary is not None:
                kind_summary["variation_count"] += 1
                kind_summary["distribution"][period][(regular, sale)] += 1
            variations.append({
                "product_id": int(product["id"]), "product_name": str(product.get("name", "")),
                "variation_id": int(variation["id"]), "period": period,
                "regular_price": regular, "sale_price": sale,
                "kind": product_kind,
            })
    serialized_by_kind = {
        kind: {
            "product_count": len(summary["product_ids"]),
            "variation_count": summary["variation_count"],
            "unmatched_variation_count": summary["unmatched_variation_count"],
            "distribution": {
                period: [
                    {"regular_price": pair[0], "sale_price": pair[1], "count": count}
                    for pair, count in values.most_common(8)
                ]
                for period, values in summary["distribution"].items()
            },
        }
        for kind, summary in by_kind.items()
    }
    return {
        "ok": True,
        "product_count": len(selected_products),
        "variation_count": len(variations),
        "unmatched_variation_count": unmatched,
        "distribution": {
            period: [
                {"regular_price": pair[0], "sale_price": pair[1], "count": count}
                for pair, count in values.most_common(8)
            ] for period, values in distribution.items()
        },
        "by_kind": serialized_by_kind,
        "variations": variations,
    }


def apply_store_prices(
    woo: Any, payload: Mapping[str, Any], *,
    progress: Callable[[str, int, int, str], None] | None = None,
    products: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    if str(payload.get("confirmation", "") or "").strip() != "ALTERAR PRECOS":
        raise ValueError('Digite "ALTERAR PRECOS" para confirmar.')
    kinds = payload.get("kinds", [])
    if not isinstance(kinds, list):
        raise ValueError("Seleção de produtos inválida.")
    prices = normalize_prices(payload)
    snapshot = build_store_pricing_snapshot(woo, kinds, progress=progress, products=products)
    if not snapshot["product_count"]:
        raise ValueError("Nenhum produto foi encontrado no catálogo local. Atualize o catálogo de Plugins e Temas e tente novamente.")
    if not snapshot["variations"]:
        raise ValueError("Nenhuma variação anual ou vitalícia foi encontrada nos produtos selecionados.")
    grouped: dict[int, list[dict[str, Any]]] = {}
    product_names: dict[int, str] = {}
    for variation in snapshot["variations"]:
        period = variation["period"]
        product_names[variation["product_id"]] = variation["product_name"]
        grouped.setdefault(variation["product_id"], []).append({
            "id": variation["variation_id"],
            "regular_price": prices[f"{period}_regular"],
            "sale_price": prices[f"{period}_sale"],
        })
    updated = 0
    errors: list[dict[str, Any]] = []
    def update_product(item: tuple[int, list[dict[str, Any]]]) -> tuple[int, int, str]:
        product_id, updates = item
        try:
            rows = woo.update_variations_prices(product_id, updates, authorized=True)
            return product_id, len(rows), ""
        except Exception as error:
            return product_id, 0, str(error)

    if progress:
        progress("updating", 0, len(grouped), "")
    # Quatro escritas simultâneas reduzem bastante o tempo total sem disparar
    # dezenas de requisições concorrentes contra o WooCommerce. O processamento
    # é dividido em blocos para a interface sempre identificar o lote atual.
    items = list(grouped.items())
    completed = 0
    write_workers = min(4, max(1, len(items)))
    with ThreadPoolExecutor(max_workers=write_workers, thread_name_prefix="store-price-writes") as executor:
        for offset in range(0, len(items), write_workers):
            batch = items[offset:offset + write_workers]
            batch_names = [product_names.get(item[0]) or f"Produto #{item[0]}" for item in batch]
            current_label = ", ".join(batch_names[:3])
            if len(batch_names) > 3:
                current_label += f" e mais {len(batch_names) - 3}"
            if progress:
                progress("updating", completed, len(items), current_label)
            future_names = {
                executor.submit(update_product, item): product_names.get(item[0]) or f"Produto #{item[0]}"
                for item in batch
            }
            for future in as_completed(future_names):
                product_name = future_names[future]
                product_id, count, message = future.result()
                completed += 1
                updated += count
                if message:
                    errors.append({"product_id": product_id, "product_name": product_name, "message": message})
                if progress:
                    progress("updating", completed, len(items), product_name)
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
