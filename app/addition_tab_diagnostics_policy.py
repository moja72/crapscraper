from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import app.web as web
from app import settings

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "addition_tab_diagnostics.js"
_LOG_PATH = Path(settings.DATA_DIR) / "addition_tab_diagnostics.jsonl"
_LOCK = threading.RLock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=400)


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    event = dict(payload or {})
    event["server_time"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
    with _LOCK:
        _EVENTS.append(event)
        try:
            _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError:
            pass
    print("[ADDITION-DIAG] " + json.dumps(event, ensure_ascii=False, separators=(",", ":")), flush=True)
    return event


def _snapshot() -> dict[str, Any]:
    with _LOCK:
        events = list(_EVENTS)
    return {"ok": True, "events": events, "count": len(events), "log_path": str(_LOG_PATH)}


def _clear() -> dict[str, Any]:
    with _LOCK:
        _EVENTS.clear()
        try:
            _LOG_PATH.unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "message": "Diagnóstico limpo."}


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-addition-tab-diagnostics>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class AdditionTabDiagnosticsHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/adicoes/diagnostico":
                self._send_json(_snapshot())
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path == "/adicoes/diagnostico/event":
                try:
                    payload = self._read_json_body()
                except Exception:
                    payload = {}
                self._send_json({"ok": True, "event": _record(dict(payload or {}))})
                return
            if path == "/adicoes/diagnostico/limpar":
                self._send_json(_clear())
                return
            return super().do_POST()

    return _BASE_SERVER(server_address, AdditionTabDiagnosticsHandler, *args, **kwargs)


def install_addition_tab_diagnostics_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
