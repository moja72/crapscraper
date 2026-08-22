from __future__ import annotations

import threading
import time
from typing import Any, Callable
from urllib.parse import parse_qs

import app.addition_operational_ui_policy as operational

_INSTALLED = False
_BASE_OPERATIONS_PAYLOAD: Callable[[str], dict[str, Any]] | None = None
_BASE_SYNC: Callable[[], dict[str, Any]] | None = None
_CACHE_LOCK = threading.RLock()
_SYNC_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LAST_SYNC_AT = 0.0
_LAST_APPROVED_TOTAL = 0
_READ_TTL_SECONDS = 1.25
_SYNC_DEDUP_SECONDS = 8.0


def _is_processes_scope(path_query: str) -> bool:
    query = parse_qs(str(path_query or ""), keep_blank_values=True)
    values = query.get("scope") or []
    return bool(values and str(values[0]).strip().lower() == "processes")


def _cached_operations_payload(path_query: str) -> dict[str, Any]:
    if _BASE_OPERATIONS_PAYLOAD is None:
        raise RuntimeError("Leitor operacional base indisponível")
    key = str(path_query or "")
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] <= _READ_TTL_SECONDS:
            return dict(cached[1])

    # A bridge do botão Processos só consome `processes`. O caminho base montava
    # primeiro o dashboard inteiro (counts + queue + processes) e só depois
    # descartava o restante. Em Windows/SQLite isso ainda podia disputar lock e
    # atrasar o boot da UI mesmo com a aba Adicionar fechada.
    if _is_processes_scope(path_query):
        payload = {"ok": True, "processes": operational._processes_snapshot()}
    else:
        payload = _BASE_OPERATIONS_PAYLOAD(path_query)

    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), dict(payload))
        if len(_CACHE) > 40:
            oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])[:10]
            for old_key, _value in oldest:
                _CACHE.pop(old_key, None)
    return payload


def _cached_sync_result(message: str) -> dict[str, Any]:
    return {
        "ok": True,
        "message": message,
        "approved_total": _LAST_APPROVED_TOTAL,
        "created": 0,
        "changed": 0,
        "deactivated": 0,
        "cached": True,
    }


def _deduplicated_sync() -> dict[str, Any]:
    global _LAST_SYNC_AT, _LAST_APPROVED_TOTAL
    if _BASE_SYNC is None:
        raise RuntimeError("Sincronização base indisponível")
    now = time.monotonic()
    if _LAST_SYNC_AT and now - _LAST_SYNC_AT < _SYNC_DEDUP_SECONDS:
        return _cached_sync_result(
            "Aprovações já sincronizadas há poucos segundos; reutilizando o estado persistido."
        )
    if not _SYNC_LOCK.acquire(blocking=False):
        return _cached_sync_result("A sincronização de aprovações já está em andamento.")
    try:
        result = _BASE_SYNC()
        _LAST_SYNC_AT = time.monotonic()
        _LAST_APPROVED_TOTAL = int(result.get("approved_total", _LAST_APPROVED_TOTAL) or 0)
        with _CACHE_LOCK:
            _CACHE.clear()
        return result
    finally:
        _SYNC_LOCK.release()


def install_addition_operational_performance_policy() -> None:
    global _INSTALLED, _BASE_OPERATIONS_PAYLOAD, _BASE_SYNC, _LAST_SYNC_AT, _LAST_APPROVED_TOTAL
    if _INSTALLED:
        return
    _BASE_OPERATIONS_PAYLOAD = operational._operations_payload
    _BASE_SYNC = operational._sync_approved_operational
    # A policy operacional acabou de sincronizar durante o boot. Capturamos a
    # contagem uma unica vez antes do servidor aceitar requisicoes; chamadas
    # deduplicadas do navegador nao precisam reabrir o SQLite apenas para contar.
    _LAST_APPROVED_TOTAL = int(operational._counts().get("total", 0) or 0)
    _LAST_SYNC_AT = time.monotonic()
    operational._operations_payload = _cached_operations_payload
    operational._sync_approved_operational = _deduplicated_sync
    _INSTALLED = True
