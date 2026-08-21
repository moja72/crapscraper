from __future__ import annotations

import threading
import time
from typing import Any, Callable

import app.addition_operational_ui_policy as operational

_INSTALLED = False
_BASE_OPERATIONS_PAYLOAD: Callable[[str], dict[str, Any]] | None = None
_BASE_SYNC: Callable[[], dict[str, Any]] | None = None
_CACHE_LOCK = threading.RLock()
_SYNC_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LAST_SYNC_AT = 0.0
_READ_TTL_SECONDS = 1.25
_SYNC_DEDUP_SECONDS = 8.0


def _cached_operations_payload(path_query: str) -> dict[str, Any]:
    if _BASE_OPERATIONS_PAYLOAD is None:
        raise RuntimeError("Leitor operacional base indisponível")
    key = str(path_query or "")
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] <= _READ_TTL_SECONDS:
            return dict(cached[1])
    payload = _BASE_OPERATIONS_PAYLOAD(path_query)
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), dict(payload))
        if len(_CACHE) > 40:
            oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])[:10]
            for old_key, _value in oldest:
                _CACHE.pop(old_key, None)
    return payload


def _deduplicated_sync() -> dict[str, Any]:
    global _LAST_SYNC_AT
    if _BASE_SYNC is None:
        raise RuntimeError("Sincronização base indisponível")
    now = time.monotonic()
    if _LAST_SYNC_AT and now - _LAST_SYNC_AT < _SYNC_DEDUP_SECONDS:
        return {
            "ok": True,
            "message": "Aprovações já sincronizadas há poucos segundos; reutilizando o estado persistido.",
            "approved_total": operational._counts().get("total", 0),
            "created": 0,
            "changed": 0,
            "deactivated": 0,
            "cached": True,
        }
    if not _SYNC_LOCK.acquire(blocking=False):
        return {
            "ok": True,
            "message": "A sincronização de aprovações já está em andamento.",
            "approved_total": operational._counts().get("total", 0),
            "created": 0,
            "changed": 0,
            "deactivated": 0,
            "cached": True,
        }
    try:
        result = _BASE_SYNC()
        _LAST_SYNC_AT = time.monotonic()
        with _CACHE_LOCK:
            _CACHE.clear()
        return result
    finally:
        _SYNC_LOCK.release()


def install_addition_operational_performance_policy() -> None:
    global _INSTALLED, _BASE_OPERATIONS_PAYLOAD, _BASE_SYNC, _LAST_SYNC_AT
    if _INSTALLED:
        return
    _BASE_OPERATIONS_PAYLOAD = operational._operations_payload
    _BASE_SYNC = operational._sync_approved_operational
    # A policy operacional acabou de sincronizar durante o boot; evita repetir
    # o mesmo trabalho no carregamento inicial do navegador.
    _LAST_SYNC_AT = time.monotonic()
    operational._operations_payload = _cached_operations_payload
    operational._sync_approved_operational = _deduplicated_sync
    _INSTALLED = True
