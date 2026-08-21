from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app import settings
import app.process_history_credits_policy as credits
import app.web as web
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.plugintheme_download import PluginThemeDownloader

_INSTALLED = False
_BASE_CREDIT_SNAPSHOT: Callable[..., dict[str, Any]] | None = None
_BASE_ULTRAPACK_DOWNLOAD: Callable[..., Any] | None = None
_BASE_PLUGINTHEME_DOWNLOAD: Callable[..., Any] | None = None
_BASE_SERVER: Any = None
_BASE_RENDER: Callable[..., str] | None = None
_LOCK = threading.RLock()
_USAGE_PATH = Path(settings.DATA_DIR) / "download_credit_usage.json"
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "download_credit_accuracy.js"
_DEFAULT_LIMITS = {
    "ultrapackv2": 40,
    "plugintheme": 50,
}
_ENV_LIMITS = {
    "ultrapackv2": "SCRAPER_ULTRAPACKV2_DAILY_DOWNLOAD_LIMIT",
    "plugintheme": "SCRAPER_PLUGINTHEME_DAILY_DOWNLOAD_LIMIT",
}
_REMOTE_TTL_SECONDS = 300.0
_REMOTE_RETRY_SECONDS = 45.0
_REMOTE_STATE: dict[str, Any] = {
    "payload": None,
    "at": 0.0,
    "attempt_at": 0.0,
    "refreshing": False,
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

        keys = sorted(str(key) for key in data.keys())
        for old in keys[:-14]:
            data.pop(old, None)
        _write_usage(data)


def _exact_credit(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("ok"):
        return None
    remaining = value.get("remaining")
    limit = value.get("limit")
    try:
        remaining_number = int(remaining)
        limit_number = int(limit)
    except (TypeError, ValueError):
        return None
    if remaining_number < 0 or limit_number <= 0:
        return None
    result = dict(value)
    result["remaining"] = min(remaining_number, limit_number)
    result["limit"] = limit_number
    result["used"] = max(0, limit_number - result["remaining"])
    result["estimated"] = False
    result.setdefault("source", "remote")
    return result


def _fallback(site_key: str, current: Any = None) -> dict[str, Any]:
    exact = _exact_credit(current)
    if exact:
        return exact

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
            f"{label}: estimativa local enquanto o saldo remoto é consultado em segundo plano. "
            "O valor desconta apenas downloads registrados por este CrapScraper."
        ),
    }


def _remote_payload_snapshot() -> dict[str, Any]:
    with _LOCK:
        payload = _REMOTE_STATE.get("payload")
        return dict(payload) if isinstance(payload, dict) else {}


def _refresh_remote_credits(manager: Any) -> None:
    try:
        base = _BASE_CREDIT_SNAPSHOT or credits._credit_snapshot
        candidate = base(manager)
        if not isinstance(candidate, dict):
            candidate = {}
        usable = {
            "ok": bool(
                _exact_credit(candidate.get("ultrapackv2"))
                or _exact_credit(candidate.get("plugintheme"))
            ),
            "ultrapackv2": candidate.get("ultrapackv2", {}),
            "plugintheme": candidate.get("plugintheme", {}),
        }
        with _LOCK:
            if usable["ok"]:
                _REMOTE_STATE["payload"] = usable
                _REMOTE_STATE["at"] = time.monotonic()
    finally:
        with _LOCK:
            _REMOTE_STATE["refreshing"] = False


def _schedule_remote_refresh(manager: Any) -> None:
    if manager is None:
        return
    now = time.monotonic()
    with _LOCK:
        cached_at = float(_REMOTE_STATE.get("at") or 0.0)
        attempt_at = float(_REMOTE_STATE.get("attempt_at") or 0.0)
        refreshing = bool(_REMOTE_STATE.get("refreshing"))
        fresh = bool(_REMOTE_STATE.get("payload")) and now - cached_at < _REMOTE_TTL_SECONDS
        retry_wait = attempt_at and now - attempt_at < _REMOTE_RETRY_SECONDS
        if fresh or refreshing or retry_wait:
            return
        _REMOTE_STATE["refreshing"] = True
        _REMOTE_STATE["attempt_at"] = now

    threading.Thread(
        target=_refresh_remote_credits,
        args=(manager,),
        name="download-credit-remote-refresh",
        daemon=True,
    ).start()


def _patched_credit_snapshot(manager: Any) -> dict[str, Any]:
    # Nunca bloqueia o GET do cabeçalho em autenticação remota. A consulta real
    # acontece em background e o último saldo confirmado é reutilizado.
    _schedule_remote_refresh(manager)
    remote_payload = _remote_payload_snapshot()
    ultrapack = _fallback("ultrapackv2", remote_payload.get("ultrapackv2"))
    plugintheme = _fallback("plugintheme", remote_payload.get("plugintheme"))
    return {
        "ok": True,
        "remote_refreshing": bool(_REMOTE_STATE.get("refreshing")),
        "ultrapackv2": ultrapack,
        "plugintheme": plugintheme,
    }


def _patched_ultrapack_download(self: Any, *args: Any, **kwargs: Any) -> Any:
    base = _BASE_ULTRAPACK_DOWNLOAD
    if base is None:
        raise RuntimeError("Downloader UltraPackV2 não inicializado")
    result = base(self, *args, **kwargs)
    _record_download("ultrapackv2")
    with _LOCK:
        _REMOTE_STATE["at"] = 0.0
    return result


def _patched_plugintheme_download(self: Any, *args: Any, **kwargs: Any) -> Any:
    base = _BASE_PLUGINTHEME_DOWNLOAD
    if base is None:
        raise RuntimeError("Downloader PluginTheme não inicializado")
    result = base(self, *args, **kwargs)
    _record_download("plugintheme")
    with _LOCK:
        _REMOTE_STATE["at"] = 0.0
    return result


def _monitor_worker_alive() -> bool:
    worker = getattr(web, "_WORDPRESS_MANUAL_WORKER", None)
    try:
        return bool(worker and worker.is_alive())
    except Exception:
        return False


def _wordpress_manual_configured() -> bool:
    enabled = os.getenv("SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on"
    }
    return bool(
        enabled
        and os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET", "").strip()
        and os.getenv("SCRAPER_WP_BASE_URL", "").strip()
    )


def _fast_manual_monitor_snapshot(manager: Any) -> dict[str, Any]:
    # Esta rota é deliberadamente local: não consulta WooCommerce nem WordPress.
    # Se o worker tiver morrido, apenas dispara sua reinicialização em background.
    restart_error = ""
    if _wordpress_manual_configured() and not _monitor_worker_alive() and manager is not None:
        try:
            web._start_wordpress_manual_worker(manager)
        except Exception as error:
            restart_error = str(error)

    from app.wordpress_manual_update import manual_monitor_snapshot

    payload = dict(manual_monitor_snapshot())
    payload["worker_alive"] = _monitor_worker_alive()
    payload["fast_path"] = True
    if restart_error:
        payload["worker_restart_error"] = restart_error
    return payload


def _manager_from_handler(handler_class: type) -> Any:
    try:
        return credits._manager_from_handler(handler_class)
    except Exception:
        return None


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)

    class CreditMonitorFastHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/loja/wordpress-manual/status":
                try:
                    self._send_json(_fast_manual_monitor_snapshot(manager))
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return
            return super().do_GET()

    return _BASE_SERVER(server_address, CreditMonitorFastHandler, *args, **kwargs)


def _script_block() -> str:
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-download-credit-accuracy>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_download_credit_fallback_policy() -> None:
    global _INSTALLED, _BASE_CREDIT_SNAPSHOT, _BASE_SERVER, _BASE_RENDER
    global _BASE_ULTRAPACK_DOWNLOAD, _BASE_PLUGINTHEME_DOWNLOAD
    if _INSTALLED:
        return

    _BASE_CREDIT_SNAPSHOT = credits._credit_snapshot
    credits._credit_snapshot = _patched_credit_snapshot

    _BASE_ULTRAPACK_DOWNLOAD = UltrapackDownloader.download
    _BASE_PLUGINTHEME_DOWNLOAD = PluginThemeDownloader.download
    UltrapackDownloader.download = _patched_ultrapack_download
    PluginThemeDownloader.download = _patched_plugintheme_download

    # Fast-path do monitor: evita que uma cadeia de rotas pesada transforme uma
    # leitura de memória em timeout de 8 segundos no painel.
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory

    # Complemento visual para deixar explícito quando o saldo ainda é estimado.
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
