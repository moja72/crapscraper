from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app import settings
import app.process_history_credits_policy as credits
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.plugintheme_download import PluginThemeDownloader

_INSTALLED = False
_BASE_CREDIT_SNAPSHOT: Callable[..., dict[str, Any]] | None = None
_BASE_ULTRAPACK_DOWNLOAD: Callable[..., Any] | None = None
_BASE_PLUGINTHEME_DOWNLOAD: Callable[..., Any] | None = None
_LOCK = threading.RLock()
_USAGE_PATH = Path(settings.DATA_DIR) / "download_credit_usage.json"
_DEFAULT_LIMITS = {
    "ultrapackv2": 50,
    "plugintheme": 50,
}
_ENV_LIMITS = {
    "ultrapackv2": "SCRAPER_ULTRAPACKV2_DAILY_DOWNLOAD_LIMIT",
    "plugintheme": "SCRAPER_PLUGINTHEME_DAILY_DOWNLOAD_LIMIT",
}


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return max(0, int(default))


def _env_enabled(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on", "sim"}


def _daily_limit(site_key: str) -> int:
    default = _DEFAULT_LIMITS.get(site_key, 50)
    return max(1, _safe_int(os.getenv(_ENV_LIMITS.get(site_key, ""), ""), default))


def _read_usage() -> dict[str, Any]:
    try:
        data = json.loads(_USAGE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_usage(data: dict[str, Any]) -> None:
    _USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _USAGE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(_USAGE_PATH)


def _used_today(site_key: str) -> int:
    with _LOCK:
        data = _read_usage()
        day = data.get(_today())
        if not isinstance(day, dict):
            return 0
        return _safe_int(day.get(site_key), 0)


def _record_download(site_key: str) -> None:
    with _LOCK:
        data = _read_usage()
        today = _today()
        day = data.setdefault(today, {})
        if not isinstance(day, dict):
            day = {}
            data[today] = day
        day[site_key] = _safe_int(day.get(site_key), 0) + 1

        # O contador é diário. Mantemos apenas os 14 dias mais recentes para o
        # arquivo continuar pequeno e útil para diagnóstico.
        keys = sorted(str(key) for key in data.keys())
        for old in keys[:-14]:
            data.pop(old, None)
        _write_usage(data)


def _fallback(site_key: str, current: Any) -> dict[str, Any]:
    if isinstance(current, dict):
        remaining = current.get("remaining")
        limit = current.get("limit")
        try:
            if current.get("ok") and remaining is not None and limit is not None:
                return dict(current)
        except Exception:
            pass

    limit = _daily_limit(site_key)
    used = min(_used_today(site_key), limit)
    remaining = max(0, limit - used)
    label = "UltraPackV2" if site_key == "ultrapackv2" else "PluginTheme"
    return {
        "ok": True,
        "remaining": remaining,
        "limit": limit,
        "used": used,
        "estimated": True,
        "source": "crapscraper-local-ledger",
        "message": (
            f"{label}: estimativa local do CrapScraper. O painel não faz login remoto para consultar créditos, "
            "evitando travar a interface; o contador desconta os downloads feitos pelo CrapScraper neste computador."
        ),
    }


def _patched_credit_snapshot(manager: Any) -> dict[str, Any]:
    # O contador do cabeçalho precisa ser instantâneo. A implementação remota
    # anterior podia iniciar autenticação/navegador durante um simples GET do
    # painel, segurando a resposta e dando a impressão de que toda a interface
    # estava travada. Por padrão usamos o ledger local, que é atualizado pelos
    # próprios downloaders. A sondagem remota continua disponível apenas como
    # opt-in explícito para diagnóstico.
    remote_payload: dict[str, Any] = {}
    if _env_enabled("SCRAPER_DOWNLOAD_CREDITS_REMOTE_PROBE", False):
        base = _BASE_CREDIT_SNAPSHOT or credits._credit_snapshot
        try:
            candidate = base(manager)
            if isinstance(candidate, dict):
                remote_payload = candidate
        except Exception:
            remote_payload = {}

    return {
        "ok": True,
        "ultrapackv2": _fallback("ultrapackv2", remote_payload.get("ultrapackv2")),
        "plugintheme": _fallback("plugintheme", remote_payload.get("plugintheme")),
    }


def _patched_ultrapack_download(self: Any, *args: Any, **kwargs: Any) -> Any:
    base = _BASE_ULTRAPACK_DOWNLOAD
    if base is None:
        raise RuntimeError("Downloader UltraPackV2 não inicializado")
    result = base(self, *args, **kwargs)
    _record_download("ultrapackv2")
    return result


def _patched_plugintheme_download(self: Any, *args: Any, **kwargs: Any) -> Any:
    base = _BASE_PLUGINTHEME_DOWNLOAD
    if base is None:
        raise RuntimeError("Downloader PluginTheme não inicializado")
    result = base(self, *args, **kwargs)
    _record_download("plugintheme")
    return result


def install_download_credit_fallback_policy() -> None:
    global _INSTALLED, _BASE_CREDIT_SNAPSHOT
    global _BASE_ULTRAPACK_DOWNLOAD, _BASE_PLUGINTHEME_DOWNLOAD
    if _INSTALLED:
        return

    # A rota /processos/creditos chama esta função global em tempo de execução,
    # portanto o patch vale também para o handler já instalado.
    _BASE_CREDIT_SNAPSHOT = credits._credit_snapshot
    credits._credit_snapshot = _patched_credit_snapshot

    _BASE_ULTRAPACK_DOWNLOAD = UltrapackDownloader.download
    _BASE_PLUGINTHEME_DOWNLOAD = PluginThemeDownloader.download
    UltrapackDownloader.download = _patched_ultrapack_download
    PluginThemeDownloader.download = _patched_plugintheme_download
    _INSTALLED = True
