from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app import settings
import app.web as web

_INSTALLED = False
_BASE_QUEUE_SNAPSHOT: Callable[..., dict[str, Any]] | None = None


def _inventory() -> list[dict[str, Any]]:
    root = settings.DATA_DIR / "staging" / "updates"
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            relative = path.relative_to(root)
            stat = path.stat()
        except OSError:
            continue
        parts = relative.parts
        job_id = parts[0] if len(parts) > 1 else ""
        items.append({
            "job_id": job_id,
            "path": str(path),
            "filename": path.name,
            "size_bytes": int(stat.st_size),
            "modified_at": float(stat.st_mtime),
        })
    return items


def _patched_queue_snapshot(*args: Any, **kwargs: Any) -> dict[str, Any]:
    base = _BASE_QUEUE_SNAPSHOT or web.queue_snapshot
    snapshot = dict(base(*args, **kwargs))
    snapshot["local_staging_root"] = str(settings.DATA_DIR / "staging" / "updates")
    snapshot["local_staging_inventory"] = _inventory()
    return snapshot


def install_local_staging_inventory_policy() -> None:
    global _INSTALLED, _BASE_QUEUE_SNAPSHOT
    if _INSTALLED:
        return
    _BASE_QUEUE_SNAPSHOT = web.queue_snapshot
    web.queue_snapshot = _patched_queue_snapshot
    _INSTALLED = True
