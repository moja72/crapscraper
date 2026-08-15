from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from typing import Any


CATALOG_COLUMNS = (
    "ID",
    "Tipo",
    "Nome",
    "Slug",
    "URL",
    "Status",
    "Metadado: pt_versao",
    "Metadado: site_oficial",
    "Categorias",
)


@dataclass(frozen=True)
class CatalogFilters:
    kinds: tuple[str, ...] = ("plugin",)
    categories: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("publish",)
    query: str = ""
    product_ids: tuple[int, ...] = ()
    version: str = "all"


def _metadata_value(product: Mapping[str, Any], key: str) -> str:
    values = [
        item.get("value")
        for item in product.get("meta_data", []) or []
        if isinstance(item, Mapping) and str(item.get("key", "")) == key
    ]
    return "" if not values or values[0] is None else str(values[0])


def _category_names(product: Mapping[str, Any]) -> list[str]:
    return [
        str(item.get("name", "")).strip()
        for item in product.get("categories", []) or []
        if isinstance(item, Mapping) and str(item.get("name", "")).strip()
    ]


def categories_match_catalog_kind(categories: Iterable[str], kind: str) -> bool:
    """Reconhece categorias de tipo inteiras, sem confundir nomes de marcas."""
    expected = str(kind or "").strip().lower()
    aliases = {
        "plugin": {"plugin", "plugins", "plugin wordpress", "plugins wordpress"},
        "theme": {"tema", "temas", "theme", "themes", "tema wordpress", "temas wordpress"},
        "template": {"template", "templates", "modelo", "modelos"},
    }
    if expected not in aliases:
        return False
    normalized = {
        " ".join(re.findall(r"[a-z0-9]+", str(category or "").lower()))
        for category in categories
    }
    return bool(normalized & aliases[expected])


def product_matches_catalog_kind(product: Mapping[str, Any], kind: str) -> bool:
    """Classifica pelo catálogo/taxonomia existente, sem inventar um novo tipo."""
    return categories_match_catalog_kind(_category_names(product), kind)


def build_catalog_rows(
    products: Iterable[Mapping[str, Any]],
    *,
    kind: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for product in products:
        if not isinstance(product, Mapping) or not product_matches_catalog_kind(product, kind):
            continue
        rows.append(
            {
                "ID": str(product.get("id", "") or ""),
                "Tipo": str(product.get("type", "simple") or "simple"),
                "Nome": str(product.get("name", "") or "").strip(),
                "Slug": str(product.get("slug", "") or "").strip(),
                "URL": str(product.get("permalink", "") or "").strip(),
                "Status": str(product.get("status", "") or "").strip(),
                "Metadado: pt_versao": _metadata_value(product, "pt_versao"),
                "Metadado: site_oficial": _metadata_value(product, "site_oficial"),
                "Categorias": ", ".join(_category_names(product)),
            }
        )
    return rows


def build_filtered_catalog_rows(
    products: Iterable[Mapping[str, Any]], filters: CatalogFilters,
) -> list[dict[str, str]]:
    category_filter = {value.casefold() for value in filters.categories if value}
    id_filter = set(filters.product_ids)
    query = filters.query.strip().casefold()
    statuses = {value for value in filters.statuses if value}
    selected: list[Mapping[str, Any]] = []
    for product in products:
        if not isinstance(product, Mapping):
            continue
        product_id = int(product.get("id", 0) or 0)
        version = _metadata_value(product, "pt_versao").strip()
        categories = {name.casefold() for name in _category_names(product)}
        if id_filter and product_id not in id_filter:
            continue
        product_status = str(product.get("status", "") or "")
        if statuses and product_status and product_status not in statuses:
            continue
        if category_filter and not categories.intersection(category_filter):
            continue
        if query and query not in f'{product.get("name", "")} {product.get("slug", "")}'.casefold():
            continue
        if filters.version == "with" and not version:
            continue
        if filters.version == "without" and version:
            continue
        if not any(product_matches_catalog_kind(product, kind) for kind in filters.kinds):
            continue
        selected.append(product)

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for kind in filters.kinds:
        for row in build_catalog_rows(selected, kind=kind):
            if row["ID"] not in seen:
                seen.add(row["ID"])
                rows.append(row)
    return rows


def encode_catalog_csv(rows: Iterable[Mapping[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CATALOG_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def read_all_products(
    woo: Any, *, per_page: int = 100, statuses: Iterable[str] = ("publish",),
) -> list[Mapping[str, Any]]:
    products: list[Mapping[str, Any]] = []
    for status in tuple(statuses) or ("publish",):
        page = 1
        while True:
            batch = list(woo.list_products(page=page, per_page=per_page, status=status) or [])
            products.extend(item for item in batch if isinstance(item, Mapping))
            if len(batch) < per_page:
                break
            page += 1
    return products
