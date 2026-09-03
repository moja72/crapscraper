from __future__ import annotations

from typing import Any
from app.web.api import ApplicationServices


def get_route(services: ApplicationServices, path: str, query: dict[str,Any] | None=None) -> dict[str, Any]:
    query=query or {}
    routes = {
        "/api/health": lambda: {"ok": True, "app": "CrapScraper", "store_write_enabled": bool(services.store.write_enabled)},
        "/api/credits": lambda: services.credits.get(
            str(query.get("site_key") or ""),
            str(query.get("account_key") or ""),
            refresh=str(query.get("refresh") or "") in {"1", "true"},
        ) if query.get("site_key") else services.credits.snapshot(
            refresh=str(query.get("refresh") or "") in {"1", "true"}
        ),
        "/api/collect": services.collection.context_payload,
        "/api/collection/context": lambda: services.collection.context_payload(query),
        "/api/collection/state": lambda: services.collection.state(query),
        "/api/collection/logs_full": lambda: services.collection.logs_full(query),
        "/api/collection/catalogs": services.collection.catalogs,
        "/api/collection/catalog-file": lambda: services.collection.catalog_file(query),
        "/api/collection/runs": lambda: services.collection.state(query),
        "/api/catalogs": lambda: services.catalogs.list(query),
        "/api/catalogs/preview": lambda: services.catalogs.preview(query),
        "/api/catalogs/generation": services.catalogs.generation_status,
        "/api/catalogs/generation/options": services.catalogs.generation_options,
        "/api/catalogs/generation/search": lambda: services.catalogs.search_products(query),
        "/api/compare": services.comparison.catalogs,
        "/api/comparison/catalogs": services.comparison.catalogs,
        "/api/comparison/approvals": services.comparison.approvals,
        "/api/update": lambda: services.updates.list(query),
        "/api/updates": lambda: services.updates.list(query),
        "/api/updates/jobs": lambda: services.updates.list(query),
        "/api/updates/job": lambda: services.updates.job(str(query.get("job_id") or "")),
        "/api/updates/history": lambda: services.updates.job(str(query.get("job_id") or "")),
        "/api/updates/logs": lambda: services.updates.job(str(query.get("job_id") or "")),
        "/api/updates/environment": services.updates.environment,
        "/api/add": lambda: services.additions.list(query),
        "/api/additions": lambda: services.additions.list(query),
        "/api/additions/jobs": lambda: services.additions.list(query),
        "/api/additions/job": lambda: services.additions.job(str(query.get("job_id") or "")),
        "/api/additions/history": lambda: services.additions.job(str(query.get("job_id") or "")),
        "/api/additions/logs": lambda: services.additions.job(str(query.get("job_id") or "")),
        "/api/store": services.store.summary,
        "/api/store/summary": services.store.summary,
        "/api/store/environment": services.store.environment,
        "/api/store/products": lambda: services.store.list_products(query),
        "/api/store/product": lambda: services.store.product(int(query.get("product_id") or 0)),
        "/api/store/monitor": services.store.monitor,
        "/api/store/monitor/history": services.store.monitor,
        "/api/store/monitor/logs": services.store.monitor,
        "/api/store/bundles": services.store.bundles,
        "/api/store/plans": services.store.plans,
        "/api/store/pricing/catalog": services.store.pricing_catalog,
        "/api/store/pricing/status": lambda: services.store.pricing.status(),
        "/api/store/categories": services.store.categories,
        "/api/store/quality": lambda: services.store.quality(query),
        "/api/store/quality/products": lambda: services.store.quality_products(query),
        "/api/store/quality/product": lambda: services.store.product(int(query.get("product_id") or 0)),
        "/api/sync/catalogs": services.sync.catalogs,
        "/api/sync/search": lambda: services.sync.search(query),
        "/api/sync/status": lambda: services.sync.status(str(query.get("job_id") or "")),
    }
    if path not in routes: raise KeyError(path)
    return routes[path]()


def post_route(services: ApplicationServices, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if path == "/api/collection/context": return services.collection.set_context(payload)
    if path == "/api/catalogs/generate": return services.catalogs.generate_plugintema(payload)
    if path == "/api/catalogs/name": return services.catalogs.set_name(payload)
    if path == "/api/catalogs/delete": return services.catalogs.delete(payload)
    if path == "/api/collection/runs/create": return services.collection.create_run(payload)
    if path == "/api/collection/runs/remove": return services.collection.remove_run(payload)
    if path == "/api/collection/queue": return services.collection.save_queue(payload)
    if path == "/api/collection/config": return services.collection.save_config(payload)
    if path.startswith("/api/collection/slots/"): return services.collection.slot_action(path.rsplit("/", 1)[-1], payload)
    if path == "/api/collection/start": return services.collection.start(payload)
    if path in {"/api/collection/pause", "/api/collection/resume", "/api/collection/stop"}: return services.collection.control(path.rsplit("/", 1)[-1],payload)
    if path in {"/api/comparison/run", "/api/comparison/results"}: return services.comparison.run(payload)
    if path == "/api/comparison/decision": return services.comparison.save_decision(payload)
    if path == "/api/comparison/decisions/bulk": return services.comparison.save_decisions_bulk(payload)
    if path == "/api/comparison/selection": return services.comparison.selection(payload)
    if path == "/api/comparison/decision/reset": return services.comparison.reset_decision(payload)
    if path == "/api/comparison/decision/history": return services.comparison.decision_history(payload)
    if path == "/api/comparison/candidates": return services.comparison.candidates(payload)
    if path == "/api/comparison/relationship": return services.comparison.save_relationship(payload)
    if path == "/api/updates/materialize": return services.updates.materialize()
    if path == "/api/updates/environment/check": return services.updates.verify_environment()
    if path == "/api/updates/reconcile": return services.updates.reconcile_errors()
    if path == "/api/updates/plugintheme/renew": return services.updates.renew_plugintheme(payload)
    if path == "/api/updates/selection": return services.updates.selection(payload)
    if path == "/api/updates/execute": return services.updates.execute(str(payload.get("job_id") or ""))
    if path == "/api/updates/retry": return services.updates.retry(str(payload.get("job_id") or ""))
    if path == "/api/updates/batch/start": return services.updates.batch_start(list(payload.get("job_ids") or []))
    if path in {"/api/updates/batch/pause","/api/updates/batch/resume","/api/updates/batch/cancel"}: return services.updates.batch_control(path.rsplit("/",1)[-1])
    if path == "/api/additions/materialize": return services.additions.materialize()
    if path == "/api/additions/execute": return services.additions.execute(str(payload.get("job_id") or ""))
    if path == "/api/additions/retry": return services.additions.retry(str(payload.get("job_id") or ""))
    if path == "/api/additions/batch/start": return services.additions.batch_start(list(payload.get("job_ids") or []))
    if path in {"/api/additions/batch/pause","/api/additions/batch/resume","/api/additions/batch/cancel"}: return services.additions.batch_control(path.rsplit("/",1)[-1])
    if path == "/api/store/monitor/run": return services.store.monitor_run()
    if path == "/api/store/environment/check": return services.store.environment(check=True)
    if path in {"/api/store/monitor/enable","/api/store/monitor/disable"}: return services.store.monitor_enable(path.endswith("enable"))
    if path == "/api/store/monitor": return services.store.monitor_enable(bool(payload.get("enabled")))
    if path == "/api/store/pricing/preview": return services.store.pricing_preview(payload)
    if path == "/api/store/pricing/apply": return services.store.pricing_apply(payload)
    if path == "/api/store/bundles/preview": return services.store.bundle_preview(payload)
    if path == "/api/store/bundles/apply": return services.store.bundle_apply(payload)
    if path == "/api/sync/resolve": return services.sync.resolve(payload)
    if path == "/api/sync/materialize": return services.sync.materialize(str(payload.get("resolution_id") or ""))
    if path == "/api/sync/execute": return services.sync.execute(str(payload.get("resolution_id") or ""))
    raise KeyError(path)