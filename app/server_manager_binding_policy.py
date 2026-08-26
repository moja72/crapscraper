from __future__ import annotations

from typing import Any

import app.web as web


_INSTALLED = False
_BASE_SERVER: Any = None


def _manager_from_handler(handler_class: type) -> Any | None:
    """Recover the ScraperRunManager captured by web.make_handler.

    Server-policy wrappers subclass the original Handler several times. Walking
    the MRO and method closures avoids creating a second, empty manager when a
    late route (such as retry-update) needs the active browser/session context.
    """
    for cls in getattr(handler_class, "__mro__", (handler_class,)):
        for name in ("do_GET", "do_POST", "_route_get", "_route_post"):
            method = getattr(cls, name, None)
            closure = getattr(method, "__closure__", None) or ()
            for cell in closure:
                try:
                    value = cell.cell_contents
                except ValueError:
                    continue
                try:
                    if web._is_run_manager(value):
                        return value
                except Exception:
                    continue
    return None


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = _manager_from_handler(handler_class)
    server = _BASE_SERVER(server_address, handler_class, *args, **kwargs)
    if manager is not None:
        try:
            server.scraper_manager = manager
            server.scraper_app = web._get_primary_app(manager)
        except Exception:
            pass
    return server


def install_server_manager_binding_policy() -> None:
    global _INSTALLED, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True


__all__ = ["install_server_manager_binding_policy", "_manager_from_handler"]
