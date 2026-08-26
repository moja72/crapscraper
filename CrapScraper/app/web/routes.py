from __future__ import annotations

from typing import Any
from app.web.api import ApplicationServices


def get_route(services: ApplicationServices, path: str) -> dict[str, Any]:
    routes = {
        "/api/health": lambda: {"ok": True},
        "/api/collect": services.domains.collection,
        "/api/compare": services.domains.decisions,
        "/api/update": lambda: services.domains.jobs("approve_update"),
        "/api/add": lambda: services.domains.jobs("approve_new_product"),
        "/api/store": services.domains.store,
    }
    if path not in routes: raise KeyError(path)
    return routes[path]()


def post_route(services: ApplicationServices, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if path.startswith("/api/collect/"):
        return services.domains.collection_action(path.rsplit("/", 1)[-1], payload)
    if path == "/api/store/monitor":
        return services.domains.monitor(bool(payload.get("enabled")))
    raise KeyError(path)
