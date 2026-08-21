from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from app import settings
import app.download_credit_fallback_policy as credit_policy
import app.web as web
import app.wordpress_manual_update as manual


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MAKE_HANDLER: Callable[..., Any] | None = None
_BASE_START_WORKER: Callable[..., bool] | None = None
_BASE_PENDING: Callable[..., list[dict[str, Any]]] | None = None
_BASE_MONITOR_UPDATE: Callable[..., None] | None = None
_BASE_VISIBLE_WORKER_ALIVE: Callable[..., bool] | None = None
_STATE_LOCK = threading.RLock()
_STATE_PATH = Path(settings.DATA_DIR) / "wordpress_manual_monitor_control.json"
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_manual_monitor_control.js"


def _read_state() -> dict[str, Any]:
    with _STATE_LOCK:
        try:
            payload = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        return {
            "enabled": bool(payload.get("enabled", False)),
        }


def monitor_enabled() -> bool:
    return bool(_read_state().get("enabled"))


def _write_state(enabled: bool) -> None:
    with _STATE_LOCK:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = _STATE_PATH.with_suffix(".tmp")
        temp.write_text(
            json.dumps({"enabled": bool(enabled)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(_STATE_PATH)


def _apply_process_flag(enabled: bool) -> None:
    # O valor persistido do Windows deixa de decidir o comportamento da sessão.
    # A Loja é a fonte de verdade para ligar/desligar o monitor.
    os.environ["SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED"] = "1" if enabled else "0"


def _actual_worker_alive() -> bool:
    worker = getattr(web, "_WORDPRESS_MANUAL_WORKER", None)
    try:
        return bool(worker and worker.is_alive())
    except Exception:
        return False


def _visible_worker_alive() -> bool:
    if not monitor_enabled():
        return False
    base = _BASE_VISIBLE_WORKER_ALIVE
    if callable(base):
        try:
            return bool(base())
        except Exception:
            pass
    return _actual_worker_alive()


def _controlled_monitor_update(**values: Any) -> None:
    base = _BASE_MONITOR_UPDATE
    if base is None:
        return
    if not monitor_enabled():
        forced = dict(values)
        forced.update(
            enabled=False,
            monitor_status="disabled",
            state="Monitor desativado",
            next_check="",
            error="",
        )
        base(**forced)
        return
    base(**values)


def _controlled_pending(self: Any) -> list[dict[str, Any]]:
    if not monitor_enabled():
        return []
    base = _BASE_PENDING
    if base is None:
        return []
    return list(base(self) or [])


def _controlled_start_worker(manager: Any) -> bool:
    enabled = monitor_enabled()
    _apply_process_flag(enabled)
    if not enabled:
        if _BASE_MONITOR_UPDATE is not None:
            _BASE_MONITOR_UPDATE(
                enabled=False,
                monitor_status="disabled",
                state="Monitor desativado",
                next_check="",
                error="",
            )
        return False
    if _BASE_START_WORKER is None:
        return False
    return bool(_BASE_START_WORKER(manager))


def _configured() -> bool:
    return bool(
        str(os.getenv("SCRAPER_WP_BASE_URL", "") or "").strip()
        and str(os.getenv("SCRAPER_WORDPRESS_MANUAL_SECRET", "") or "").strip()
    )


def _control_snapshot() -> dict[str, Any]:
    enabled = monitor_enabled()
    snapshot = manual.manual_monitor_snapshot()
    return {
        "ok": True,
        "enabled": enabled,
        "configured": _configured(),
        "worker_alive": _visible_worker_alive(),
        "monitor_status": "disabled" if not enabled else str(snapshot.get("monitor_status") or "monitoring"),
        "state": "Monitor desativado" if not enabled else str(snapshot.get("state") or "Monitorando WordPress"),
    }


def _set_enabled(enabled: bool, manager: Any) -> dict[str, Any]:
    enabled = bool(enabled)
    if enabled and not _configured():
        raise ValueError("URL/segredo do monitor WordPress não estão configurados.")

    _write_state(enabled)
    _apply_process_flag(enabled)

    if enabled:
        if _actual_worker_alive():
            if _BASE_MONITOR_UPDATE is not None:
                _BASE_MONITOR_UPDATE(
                    enabled=True,
                    monitor_status="monitoring",
                    state="Monitorando WordPress",
                    error="",
                )
        else:
            _controlled_start_worker(manager)
    else:
        if _BASE_MONITOR_UPDATE is not None:
            _BASE_MONITOR_UPDATE(
                enabled=False,
                monitor_status="disabled",
                state="Monitor desativado",
                next_check="",
                error="",
            )
        manual.manual_monitor_log("Monitor WordPress desativado pela aba Loja.")

    return _control_snapshot()


def _patched_make_handler(app: Any, *, include_inline_assets: bool = False):
    base_factory = _BASE_MAKE_HANDLER or web.make_handler
    BaseHandler = base_factory(app, include_inline_assets=include_inline_assets)

    class StoreManualMonitorControlHandler(BaseHandler):
        def _route_get(self, path: str) -> bool:
            if path == "/loja/wordpress-manual/control":
                self._send_json(_control_snapshot())
                return True
            return super()._route_get(path)

        def _route_post(self, path: str, payload: dict[str, Any]) -> bool:
            if path == "/loja/wordpress-manual/control":
                try:
                    self._send_json(
                        _set_enabled(bool(payload.get("enabled")), app)
                    )
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return True
            return super()._route_post(path, payload)

    return StoreManualMonitorControlHandler


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-store-manual-monitor-control>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_store_manual_monitor_control_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_MAKE_HANDLER, _BASE_START_WORKER
    global _BASE_PENDING, _BASE_MONITOR_UPDATE, _BASE_VISIBLE_WORKER_ALIVE
    if _INSTALLED:
        return

    # Ausência do arquivo de controle = desligado. Isso também neutraliza um
    # antigo setx POLLING_ENABLED=1; o estado da Loja passa a ser autoritativo.
    _apply_process_flag(monitor_enabled())

    _BASE_START_WORKER = web._start_wordpress_manual_worker
    web._start_wordpress_manual_worker = _controlled_start_worker

    _BASE_PENDING = manual.WordPressManualQueueClient.pending
    manual.WordPressManualQueueClient.pending = _controlled_pending

    _BASE_MONITOR_UPDATE = manual.manual_monitor_update
    manual.manual_monitor_update = _controlled_monitor_update

    _BASE_VISIBLE_WORKER_ALIVE = credit_policy._monitor_worker_alive
    credit_policy._monitor_worker_alive = _visible_worker_alive

    _BASE_MAKE_HANDLER = web.make_handler
    web.make_handler = _patched_make_handler

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    if not monitor_enabled() and _BASE_MONITOR_UPDATE is not None:
        _BASE_MONITOR_UPDATE(
            enabled=False,
            monitor_status="disabled",
            state="Monitor desativado",
            next_check="",
            error="",
        )
    _INSTALLED = True
