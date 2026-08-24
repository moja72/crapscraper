from __future__ import annotations

import csv
import json
import os
import threading
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app import settings
from app.plugintema_catalog import (
    CatalogFilters,
    build_filtered_catalog_rows,
    categories_match_catalog_kind,
    encode_catalog_csv,
)

_CACHE_SCHEMA = 2
_META_SCHEMA = 1
_FULL_REFRESH_AFTER = timedelta(hours=6)
_MAX_INCREMENTAL_RUNS = 20
_INCREMENTAL_OVERLAP = timedelta(minutes=5)
_CACHE_REQUIRED_STATUSES = ("publish", "draft", "private")
_CACHE_OPTIONAL_STATUSES = ("pending", "trash")
_CACHE_STATUSES = _CACHE_REQUIRED_STATUSES + _CACHE_OPTIONAL_STATUSES
_ROOT_CATEGORY_NAMES = {
    "plugin", "plugins", "plugin wordpress", "plugins wordpress",
    "tema", "temas", "theme", "themes", "tema wordpress", "temas wordpress",
    "template", "templates", "modelo", "modelos",
}
_CACHE_LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _atomic_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".refresh.tmp")
    try:
        temporary.write_bytes(encode_catalog_csv(rows))
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def default_cache_path() -> Path:
    return Path(settings.DATA_DIR) / "cache" / "plugintema-products-v2.json"


def catalog_meta_path(catalog_path: str | Path) -> Path:
    path = Path(catalog_path)
    return path.with_suffix(path.suffix + ".meta.json")


def _catalog_stamp(path: Path) -> str:
    parts = path.stem.rsplit("-", 3)
    if len(parts) >= 4:
        tail = "-".join(parts[-3:])
        if len(tail) >= 20 and tail[:8].isdigit():
            return tail
    return ""


def _filters_payload(mode: str, filters: CatalogFilters, *, inferred: bool = False) -> dict[str, Any]:
    return {
        "schema": _META_SCHEMA,
        "mode": str(mode or "custom"),
        "filters": asdict(filters),
        "inferred": bool(inferred),
        "saved_at": _iso(_now()),
    }


def save_catalog_definition(
    catalog_path: str | Path,
    mode: str,
    filters: CatalogFilters,
    *,
    inferred: bool = False,
) -> Path:
    path = catalog_meta_path(catalog_path)
    _atomic_json(path, _filters_payload(mode, filters, inferred=inferred))
    return path


def _read_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except (OSError, csv.Error, UnicodeError):
        return []


def _row_categories(row: Mapping[str, Any]) -> list[str]:
    return [part.strip() for part in str(row.get("Categorias") or "").split(",") if part.strip()]


def _infer_kinds(rows: list[Mapping[str, Any]], stem: str) -> tuple[str, ...]:
    lower = stem.lower()
    if lower.startswith("plugintema-plugin-") or lower == "plugintema-plugin":
        return ("plugin",)
    if lower.startswith("plugintema-theme-") or lower == "plugintema-theme":
        return ("theme",)
    if lower.startswith("plugintema-template-") or lower == "plugintema-template":
        return ("template",)
    found: list[str] = []
    for kind in ("plugin", "theme", "template"):
        if any(categories_match_catalog_kind(_row_categories(row), kind) for row in rows):
            found.append(kind)
    return tuple(found) or ("plugin", "theme")


def _infer_common_categories(rows: list[Mapping[str, Any]]) -> tuple[str, ...]:
    if not rows:
        return ()
    common: set[str] | None = None
    labels: dict[str, str] = {}
    for row in rows:
        current: set[str] = set()
        for category in _row_categories(row):
            key = " ".join(category.lower().split())
            if key in _ROOT_CATEGORY_NAMES:
                continue
            current.add(key)
            labels.setdefault(key, category)
        common = current if common is None else common.intersection(current)
        if not common:
            return ()
    return tuple(labels[key] for key in sorted(common or ()))


def infer_catalog_definition(catalog_path: str | Path) -> tuple[str, CatalogFilters]:
    path = Path(catalog_path)
    rows = _read_rows(path)
    stem = path.stem.lower()
    if stem.startswith("plugintema-plugin-"):
        mode = "plugin"
    elif stem.startswith("plugintema-theme-"):
        mode = "theme"
    elif stem.startswith("plugintema-template-"):
        mode = "template"
    elif stem.startswith("plugintema-selection-"):
        mode = "selection"
    else:
        mode = "custom"

    kinds = _infer_kinds(rows, path.stem)
    statuses = tuple(sorted({str(row.get("Status") or "").strip() for row in rows if str(row.get("Status") or "").strip()}))
    if not statuses:
        statuses = ("publish",)

    categories = _infer_common_categories(rows) if mode == "custom" else ()
    versions = [str(row.get("Metadado: pt_versao") or "").strip() for row in rows]
    version_filter = "with" if mode == "custom" and versions and all(versions) else "all"
    return mode, CatalogFilters(
        kinds=kinds,
        categories=categories,
        statuses=statuses,
        query="",
        product_ids=(),
        version=version_filter,
    )


def load_catalog_definition(catalog_path: str | Path) -> tuple[str, CatalogFilters, bool]:
    path = Path(catalog_path)
    candidates = [catalog_meta_path(path)]
    stamp = _catalog_stamp(path)
    if stamp:
        candidates.extend(sorted(path.parent.glob(f"plugintema-*-{stamp}.csv.meta.json")))
    for meta_path in candidates:
        if not meta_path.exists():
            continue
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            raw = dict(payload.get("filters") or {})
            filters = CatalogFilters(
                kinds=tuple(str(item) for item in raw.get("kinds", ()) if str(item)),
                categories=tuple(str(item) for item in raw.get("categories", ()) if str(item)),
                statuses=tuple(str(item) for item in raw.get("statuses", ()) if str(item)),
                query=str(raw.get("query") or ""),
                product_ids=tuple(int(item) for item in raw.get("product_ids", ()) if str(item).isdigit()),
                version=str(raw.get("version") or "all"),
            )
            if filters.kinds:
                return str(payload.get("mode") or "custom"), filters, bool(payload.get("inferred"))
        except (OSError, ValueError, TypeError):
            continue
    mode, filters = infer_catalog_definition(path)
    save_catalog_definition(path, mode, filters, inferred=True)
    return mode, filters, True


def _load_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if int(payload.get("schema") or 0) != _CACHE_SCHEMA:
        return {}
    products = payload.get("products")
    if not isinstance(products, dict):
        return {}
    return payload


def _list_pages(
    woo: Any,
    *,
    status: str,
    modified_after: str = "",
    progress: Callable[[str, int, int, str], None] | None = None,
) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    page = 1
    while True:
        filters: dict[str, Any] = {"status": status}
        if modified_after:
            filters.update({"modified_after": modified_after, "orderby": "modified", "order": "asc"})
        batch = list(woo.list_products(page=page, per_page=100, **filters) or [])
        result.extend(item for item in batch if isinstance(item, Mapping))
        if progress:
            progress("sync", page, len(result), f"{status}: página {page}")
        if len(batch) < 100:
            break
        page += 1
    return result


def _list_status_safely(
    woo: Any,
    *,
    status: str,
    modified_after: str = "",
    progress: Callable[[str, int, int, str], None] | None = None,
) -> list[Mapping[str, Any]]:
    try:
        return _list_pages(woo, status=status, modified_after=modified_after, progress=progress)
    except Exception:
        if status not in _CACHE_OPTIONAL_STATUSES:
            raise
        if progress:
            progress("sync", 0, 0, f"{status}: status opcional não disponível neste WooCommerce")
        return []


def sync_product_cache(
    woo: Any,
    *,
    cache_path: str | Path | None = None,
    force_full: bool = False,
    now: datetime | None = None,
    progress: Callable[[str, int, int, str], None] | None = None,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    path = Path(cache_path or default_cache_path())
    current_time = (now or _now()).astimezone(timezone.utc)

    with _CACHE_LOCK:
        cached = _load_cache(path)
        products_by_id = dict(cached.get("products") or {})
        full_at = _parse_time(cached.get("full_synced_at"))
        incremental_runs = int(cached.get("incremental_runs") or 0)
        need_full = bool(
            force_full
            or not products_by_id
            or full_at is None
            or current_time - full_at >= _FULL_REFRESH_AFTER
            or incremental_runs >= _MAX_INCREMENTAL_RUNS
        )

        mode = "full" if need_full else "incremental"
        changed = 0
        touched = 0
        try:
            if need_full:
                fresh: dict[str, Mapping[str, Any]] = {}
                for status in _CACHE_STATUSES:
                    for product in _list_status_safely(woo, status=status, progress=progress):
                        product_id = int(product.get("id") or 0)
                        if product_id <= 0:
                            continue
                        touched += 1
                        if status != "trash" and str(product.get("status") or status) != "trash":
                            fresh[str(product_id)] = product
                changed = sum(
                    1 for key in set(fresh).union(products_by_id)
                    if fresh.get(key) != products_by_id.get(key)
                )
                products_by_id = fresh
                full_at = current_time
                incremental_runs = 0
            else:
                synced_at = _parse_time(cached.get("synced_at")) or full_at or current_time
                modified_after = _iso(synced_at - _INCREMENTAL_OVERLAP)
                for status in _CACHE_STATUSES:
                    for product in _list_status_safely(
                        woo, status=status, modified_after=modified_after, progress=progress
                    ):
                        product_id = int(product.get("id") or 0)
                        if product_id <= 0:
                            continue
                        touched += 1
                        key = str(product_id)
                        if status == "trash" or str(product.get("status") or "") == "trash":
                            if key in products_by_id:
                                products_by_id.pop(key, None)
                                changed += 1
                            continue
                        if products_by_id.get(key) != product:
                            products_by_id[key] = product
                            changed += 1
                incremental_runs += 1
        except Exception:
            if mode != "incremental":
                raise
            mode = "full-fallback"
            fresh = {}
            touched = 0
            for status in _CACHE_STATUSES:
                for product in _list_status_safely(woo, status=status, progress=progress):
                    product_id = int(product.get("id") or 0)
                    if product_id <= 0:
                        continue
                    touched += 1
                    if status != "trash" and str(product.get("status") or status) != "trash":
                        fresh[str(product_id)] = product
            changed = sum(
                1 for key in set(fresh).union(products_by_id)
                if fresh.get(key) != products_by_id.get(key)
            )
            products_by_id = fresh
            full_at = current_time
            incremental_runs = 0

        payload = {
            "schema": _CACHE_SCHEMA,
            "synced_at": _iso(current_time),
            "full_synced_at": _iso(full_at or current_time),
            "incremental_runs": incremental_runs,
            "products": products_by_id,
        }
        _atomic_json(path, payload)
        products = [value for value in products_by_id.values() if isinstance(value, Mapping)]
        return products, {
            "mode": mode,
            "cache_path": str(path),
            "cached_products": len(products),
            "touched_products": touched,
            "changed_products": changed,
            "synced_at": payload["synced_at"],
        }


def _rows_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row.get("ID") or ""): row for row in rows if str(row.get("ID") or "")}


def refresh_catalog(
    catalog_path: str | Path,
    woo: Any,
    *,
    force_full: bool = False,
    cache_path: str | Path | None = None,
    progress: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    path = Path(catalog_path)
    if not path.exists() or not path.is_file():
        raise ValueError("Catálogo PluginTema não encontrado.")

    mode, filters, inferred = load_catalog_definition(path)
    old_rows = _read_rows(path)
    old_by_id = _rows_by_id(old_rows)
    if progress:
        progress("cache", 0, len(old_rows), "Sincronizando cache WooCommerce")
    products, cache = sync_product_cache(
        woo, cache_path=cache_path, force_full=force_full, progress=progress
    )
    if progress:
        progress("build", 0, len(products), "Aplicando categorias e filtros do catálogo")
    new_rows = build_filtered_catalog_rows(products, filters)
    new_by_id = _rows_by_id(new_rows)

    added = sorted(set(new_by_id) - set(old_by_id))
    removed = sorted(set(old_by_id) - set(new_by_id))
    version_changed = [
        product_id for product_id in set(old_by_id).intersection(new_by_id)
        if str(old_by_id[product_id].get("Metadado: pt_versao") or "")
        != str(new_by_id[product_id].get("Metadado: pt_versao") or "")
    ]
    category_changed = [
        product_id for product_id in set(old_by_id).intersection(new_by_id)
        if str(old_by_id[product_id].get("Categorias") or "")
        != str(new_by_id[product_id].get("Categorias") or "")
    ]

    _atomic_csv(path, new_rows)
    save_catalog_definition(path, mode, filters, inferred=inferred)
    if progress:
        progress("done", len(new_rows), len(new_rows), "Catálogo atualizado")

    return {
        "ok": True,
        "catalog": path.name,
        "mode": mode,
        "definition_inferred": inferred,
        "before": len(old_rows),
        "after": len(new_rows),
        "added": len(added),
        "removed": len(removed),
        "versions_updated": len(version_changed),
        "categories_updated": len(category_changed),
        "cache": cache,
        "filters": {
            "kinds": list(filters.kinds),
            "categories": list(filters.categories),
            "statuses": list(filters.statuses),
            "query": filters.query,
            "product_ids": list(filters.product_ids),
            "version": filters.version,
        },
    }
