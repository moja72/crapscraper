from __future__ import annotations

import hashlib
import os
import re
import threading
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from app.comparison import matching

_CACHE_LOCK = threading.RLock()
_CATALOG_CACHE: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def _provider(url: Any) -> str:
    host = str(urlparse(str(url or "")).netloc or "").lower()
    if "plugintheme" in host:
        return "PluginTheme"
    if "ultrapack" in host:
        return "UltraPackV2"
    return ""


def _version_key(value: Any) -> tuple[int, ...]:
    parts = tuple(int(part) for part in re.findall(r"\d+", str(value or "")))
    while len(parts) > 1 and parts[-1] == 0:
        parts = parts[:-1]
    return parts or (0,)


def _product_official_url(product: Mapping[str, Any]) -> str:
    accepted = {"site_oficial", "pt_site_oficial", "pagina_oficial", "official_url"}
    for item in product.get("meta_data", []) or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("key") or "").strip().lower() in accepted:
            value = str(item.get("value") or "").strip()
            if value:
                return value
    return ""


def _catalog_rows(path: Path) -> list[dict[str, Any]]:
    signature = (str(path.resolve()), int(path.stat().st_mtime_ns), int(path.stat().st_size))
    with _CACHE_LOCK:
        cached = _CATALOG_CACHE.get(signature)
        if cached is not None:
            return list(cached)
    try:
        rows = matching._normalize_source_rows(matching._read_csv_rows(path))
    except (OSError, UnicodeError, ValueError):
        rows = []
    with _CACHE_LOCK:
        for key in [key for key in _CATALOG_CACHE if key[0] == signature[0] and key != signature]:
            _CATALOG_CACHE.pop(key, None)
        _CATALOG_CACHE[signature] = list(rows)
    return rows


def _source_catalogs(data_dir: Path) -> list[Path]:
    result: list[Path] = []
    for path in data_dir.rglob("*.csv"):
        try:
            relative = path.relative_to(data_dir).as_posix().lower()
        except ValueError:
            continue
        if relative.startswith("update_queues/"):
            continue
        if "plugintema" in relative and "plugintheme" not in relative:
            continue
        result.append(path)
    return result


def discover_safe_update(
    product: Mapping[str, Any],
    current_version: str,
    *,
    data_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Descobre atualização por vínculo determinístico, sem exigir aprovação prévia.

    Para execução vinda do MU-plugin aceitamos automaticamente apenas URL oficial
    idêntica. Nome idêntico continua sendo diagnóstico/candidato, nunca autorização.
    """
    product_id = int(product.get("id") or 0)
    if product_id <= 0:
        return {"ok": False, "state": "no_match", "message": "WooCommerce ID inválido."}

    configured_root = str(data_dir or os.getenv("SCRAPER_DATA_DIR", "")).strip()
    root = Path(configured_root).resolve() if configured_root else Path()
    if not configured_root or not root.is_dir():
        return {"ok": False, "state": "no_match", "message": "Diretório de catálogos indisponível."}

    site_name = str(product.get("name") or "").strip()
    site_name_key = matching.normalize_name_key(site_name)
    site_official_url = _product_official_url(product)
    site_url_key = matching.normalize_url_key(site_official_url)
    safe: list[dict[str, Any]] = []
    name_only: list[dict[str, Any]] = []

    for path in _source_catalogs(root):
        for source in _catalog_rows(path):
            source_url = str(source.get("source_product_url") or "").strip()
            provider = _provider(source_url)
            if not provider:
                continue
            exact_url = bool(site_url_key and site_url_key == str(source.get("url_key") or ""))
            exact_name = bool(site_name_key and site_name_key == str(source.get("name_key") or ""))
            if not (exact_url or exact_name):
                continue
            candidate = {**source, "provider": provider, "catalog_path": str(path), "exact_url": exact_url, "exact_name": exact_name}
            (safe if exact_url else name_only).append(candidate)

    if not safe:
        if name_only:
            return {
                "ok": True,
                "state": "relationship_required",
                "message": "Há candidato por nome, mas a URL oficial não confirma o vínculo automaticamente.",
                "unsafe_candidates": len(name_only),
            }
        return {"ok": True, "state": "no_match", "message": "Não foi possível localizar correspondência segura nos catálogos atuais."}

    safe.sort(
        key=lambda row: (
            _version_key(row.get("source_version")),
            1 if row.get("provider") == "PluginTheme" else 0,
        ),
        reverse=True,
    )
    selected = safe[0]
    target = str(selected.get("source_version") or "").strip()
    if not target:
        return {"ok": True, "state": "source_version_missing", "message": "Correspondência encontrada, mas a versão da fonte está ausente."}

    comparison_id = "manual:auto:" + hashlib.sha256(
        f"{product_id}|{selected.get('source_product_url') or selected.get('source_official_url')}".encode("utf-8")
    ).hexdigest()[:24]
    approval = {
        "comparison_item_id": comparison_id,
        "woo_product_id": product_id,
        "site_id": product_id,
        "site_name": site_name,
        "site_version": str(current_version or "").strip(),
        "site_official_url": site_official_url,
        "source_name": str(selected.get("source_name") or site_name),
        "source_provider_name": str(selected.get("provider") or ""),
        "source_version": target,
        "source_product_url": str(selected.get("source_product_url") or ""),
        "source_official_url": str(selected.get("source_official_url") or ""),
        "relationship_state": "safe_auto",
        "relationship_label": "Vínculo automático seguro por URL oficial idêntica",
        "status": "update_available" if _version_key(target) > _version_key(current_version) else "updated",
        "decision": "approve_update",
        "queue_type": "update",
    }
    return {
        "ok": True,
        "state": approval["status"] if approval["status"] == "update_available" else "already_updated",
        "message": (
            f"Correspondência segura encontrada: {current_version or '—'} → {target}."
            if approval["status"] == "update_available"
            else f"Correspondência segura encontrada; destino já está em {current_version or target}."
        ),
        "approval": approval,
        "provider": selected.get("provider"),
        "target_version": target,
        "safe_candidates": len(safe),
        "unsafe_candidates": len(name_only),
    }


__all__ = ["discover_safe_update"]
