from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from app import settings

_SCHEMA = 1
_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def cache_path() -> Path:
    return Path(settings.DATA_DIR) / "cache" / "store-pricing-v1.json"


def _empty() -> dict[str, Any]:
    return {"schema": _SCHEMA, "plans": {}, "packs": {}}


def _load() -> dict[str, Any]:
    path = cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _empty()
    if int(payload.get("schema") or 0) != _SCHEMA:
        return _empty()
    if not isinstance(payload.get("plans"), dict):
        payload["plans"] = {}
    if not isinstance(payload.get("packs"), dict):
        payload["packs"] = {}
    return payload


def _save(payload: Mapping[str, Any]) -> None:
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def normalize_kinds(kinds: Iterable[str]) -> tuple[str, ...]:
    values = tuple(
        dict.fromkeys(
            str(item).strip().lower()
            for item in kinds
            if str(item).strip().lower() in {"plugin", "theme"}
        )
    )
    return values or ("plugin", "theme")


def plan_key(kinds: Iterable[str]) -> str:
    return "+".join(sorted(normalize_kinds(kinds)))


def get_plan_snapshot(kinds: Iterable[str]) -> dict[str, Any] | None:
    key = plan_key(kinds)
    with _LOCK:
        item = _load().get("plans", {}).get(key)
        if not isinstance(item, dict) or not isinstance(item.get("snapshot"), dict):
            return None
        snapshot = dict(item["snapshot"])
        snapshot["cache"] = {
            "saved": True,
            "cached_at": str(item.get("cached_at") or ""),
            "source": str(item.get("source") or "woocommerce"),
            "key": key,
        }
        return snapshot


def set_plan_snapshot(
    kinds: Iterable[str], snapshot: Mapping[str, Any], *, source: str = "woocommerce"
) -> dict[str, Any]:
    key = plan_key(kinds)
    clean = dict(snapshot)
    clean.pop("variations", None)
    clean.pop("cache", None)
    clean["read_only"] = True
    with _LOCK:
        payload = _load()
        payload["plans"][key] = {
            "cached_at": _now_iso(),
            "source": source,
            "snapshot": clean,
        }
        _save(payload)
    return get_plan_snapshot(kinds) or clean


def get_pack_snapshot() -> dict[str, Any] | None:
    with _LOCK:
        item = _load().get("packs") or {}
        if not isinstance(item, dict) or not isinstance(item.get("products"), list):
            return None
        rows = [dict(row) for row in item.get("products", []) if isinstance(row, Mapping)]
        return {
            "ok": True,
            "products": rows,
            "total": len(rows),
            "cache": {
                "saved": True,
                "cached_at": str(item.get("cached_at") or ""),
                "source": str(item.get("source") or "woocommerce"),
            },
        }


def set_pack_snapshot(
    products: Iterable[Mapping[str, Any]], *, source: str = "woocommerce"
) -> dict[str, Any]:
    rows = [dict(row) for row in products if isinstance(row, Mapping)]
    with _LOCK:
        payload = _load()
        payload["packs"] = {
            "cached_at": _now_iso(),
            "source": source,
            "products": rows,
        }
        _save(payload)
    return get_pack_snapshot() or {"ok": True, "products": rows, "total": len(rows)}


def patch_pack_product(product: Mapping[str, Any]) -> dict[str, Any]:
    product_id = int(product.get("product_id") or 0)
    with _LOCK:
        payload = _load()
        packs = payload.get("packs") or {}
        rows = [dict(row) for row in packs.get("products", []) if isinstance(row, Mapping)]
        replaced = False
        for index, row in enumerate(rows):
            if int(row.get("product_id") or 0) == product_id and product_id > 0:
                rows[index] = dict(product)
                replaced = True
                break
        if product_id > 0 and not replaced:
            rows.append(dict(product))
            rows.sort(key=lambda item: str(item.get("product_name") or "").casefold())
        payload["packs"] = {
            "cached_at": _now_iso(),
            "source": "write-through",
            "products": rows,
        }
        _save(payload)
    return get_pack_snapshot() or {"ok": True, "products": rows, "total": len(rows)}


def _distribution_count(summary: Mapping[str, Any], period: str) -> int:
    values = (summary.get("distribution") or {}).get(period) or []
    return max(
        1,
        sum(int(item.get("count") or 0) for item in values if isinstance(item, Mapping)),
    )


def patch_plan_prices(kinds: Iterable[str], prices: Mapping[str, Any]) -> dict[str, Any]:
    selected = normalize_kinds(kinds)
    existing = get_plan_snapshot(selected) or {
        "ok": True,
        "product_count": 0,
        "variation_count": 0,
        "unmatched_variation_count": 0,
        "distribution": {"annual": [], "lifetime": []},
        "by_kind": {},
        "read_only": True,
    }
    by_kind = dict(existing.get("by_kind") or {})
    total_count = 0
    annual_total = 0
    lifetime_total = 0
    for kind in selected:
        previous = dict(by_kind.get(kind) or {})
        annual_count = _distribution_count(previous, "annual")
        lifetime_count = _distribution_count(previous, "lifetime")
        variation_count = max(
            int(previous.get("variation_count") or 0), annual_count + lifetime_count
        )
        by_kind[kind] = {
            **previous,
            "variation_count": variation_count,
            "distribution": {
                "annual": [{
                    "regular_price": str(prices.get("annual_regular") or ""),
                    "sale_price": str(prices.get("annual_sale") or ""),
                    "count": annual_count,
                }],
                "lifetime": [{
                    "regular_price": str(prices.get("lifetime_regular") or ""),
                    "sale_price": str(prices.get("lifetime_sale") or ""),
                    "count": lifetime_count,
                }],
            },
        }
        total_count += variation_count
        annual_total += annual_count
        lifetime_total += lifetime_count
    snapshot = {
        **existing,
        "ok": True,
        "variation_count": max(int(existing.get("variation_count") or 0), total_count),
        "distribution": {
            "annual": [{
                "regular_price": str(prices.get("annual_regular") or ""),
                "sale_price": str(prices.get("annual_sale") or ""),
                "count": max(1, annual_total),
            }],
            "lifetime": [{
                "regular_price": str(prices.get("lifetime_regular") or ""),
                "sale_price": str(prices.get("lifetime_sale") or ""),
                "count": max(1, lifetime_total),
            }],
        },
        "by_kind": by_kind,
        "read_only": True,
    }
    return set_plan_snapshot(selected, snapshot, source="write-through")
