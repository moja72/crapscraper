from __future__ import annotations

import os
import threading
from typing import Any

from app.store.pricing import confirmation_token, money, period
from app.store.woocommerce import is_pack, is_plan, product_kind
from app.updates.logging import safe_message
from app.updates.source_auth import (
    clear_source_session,
    ensure_source_session,
    get_source_account,
    set_source_state,
)


_INSTALLED = False
_FALSE_VALUES = {"0", "false", "no", "off"}


def _completed_update_attempts(service: Any, job_id: str) -> list[dict[str, Any]]:
    attempts = list(service.repository.history(job_id) or [])
    completed: list[dict[str, Any]] = []
    for attempt in attempts:
        if str(attempt.get("result") or "").lower() != "success":
            continue
        stages = list(attempt.get("stages") or [])
        if not any(isinstance(item, dict) and str(item.get("stage") or "") == "completed" for item in stages):
            continue
        completed.append(attempt)
    return completed


def _decorate_update_item(service: Any, item: dict[str, Any]) -> dict[str, Any]:
    value = dict(item)
    completed = _completed_update_attempts(service, str(value.get("job_id") or ""))
    dates = [str(row.get("finished_at") or "") for row in completed if str(row.get("finished_at") or "")]
    value["updates_count"] = len(completed)
    value["last_updated_at"] = max(dates) if dates else ""
    state = str(value.get("state") or "")
    if state in {"success", "error"}:
        status_at = str(value.get("finished_at") or value.get("updated_at") or "")
    elif state == "running":
        status_at = str(value.get("started_at") or value.get("updated_at") or "")
    else:
        status_at = str(value.get("updated_at") or value.get("created_at") or "")
    value["status_at"] = status_at
    return value


def _validate_base_environment(service: Any) -> None:
    validation = service.environment_validation
    woo_state = validation.get("woocommerce") or {}
    if not woo_state.get("ok"):
        try:
            result = service.executor.woo.check_connection()
            validation["woocommerce"] = {
                "ok": bool(result.get("ok")),
                "message": "Leitura autenticada do WooCommerce confirmada." if result.get("ok") else "WooCommerce não confirmou leitura autenticada.",
                "details": result,
            }
        except Exception as error:
            validation["woocommerce"] = {"ok": False, "message": safe_message(error)}
    storage_state = validation.get("storage") or {}
    if not storage_state.get("ok"):
        try:
            result = service.executor.installer.check()
            validation["storage"] = {"ok": bool(result.get("ok")), "message": str(result.get("message") or "")}
        except Exception as error:
            validation["storage"] = {"ok": False, "message": safe_message(error)}


def _validate_job_source(service: Any, job: dict[str, Any], *, fresh: bool) -> dict[str, Any]:
    kind = str(job.get("source_kind") or "").strip()
    if not kind:
        raise RuntimeError("A atualização não informa a origem aprovada.")
    account = get_source_account(kind)
    if fresh:
        clear_source_session(kind, account_key=account)
        set_source_state(kind, "not_validated", account)
    ensure_source_session(
        kind,
        str(job.get("source_url") or ""),
        account,
        allow_profile_probe=kind == "plugintheme",
    )
    source = service.executor.sources.get(kind)
    probe = getattr(source, "validate_access", None)
    if callable(probe):
        details = dict(probe(job) or {})
    else:
        source.validate_authentication()
        details = {"version": source.confirm_version(job)}
    set_source_state(kind, "validated", account)
    row = {
        "source": kind,
        "ok": True,
        "status": "validated",
        "version": details.get("version"),
        "message": "Acesso autenticado confirmado com uma sessão atual.",
    }
    sources = service.environment_validation.setdefault("sources", {})
    sources[kind] = row
    required = set(service.environment_validation.get("required_sources") or [])
    required.add(kind)
    service.environment_validation["required_sources"] = sorted(required)
    service.environment_validation["source"] = service._source_summary(sources, required)
    return row


def _prepare_job_execution(service: Any, job_id: str, *, fresh_source: bool) -> dict[str, Any]:
    _validate_base_environment(service)
    job = service.repository.get(job_id)
    kind = str(job.get("source_kind") or "")
    source_state = (service.environment_validation.get("sources") or {}).get(kind) or {}
    if fresh_source or not source_state.get("ok"):
        try:
            _validate_job_source(service, job, fresh=fresh_source)
        except Exception as error:
            account = get_source_account(kind)
            message = safe_message(error)
            status = "expired" if any(term in message.lower() for term in ("login", "sess", "expir", "401", "403", "autent")) else "invalid"
            set_source_state(kind, status, account)
            row = {"source": kind, "ok": False, "status": status, "message": message}
            sources = service.environment_validation.setdefault("sources", {})
            sources[kind] = row
            required = set(service.environment_validation.get("required_sources") or [])
            required.add(kind)
            service.environment_validation["required_sources"] = sorted(required)
            service.environment_validation["source"] = service._source_summary(sources, required)
            raise RuntimeError(f"Fonte {service._source_label(kind)} não pôde ser revalidada: {message}") from None
    service._require_execution_environment()
    return service._require_job_execution(job_id)


def _patch_updates() -> None:
    from app.updates.service import UpdateService

    if getattr(UpdateService, "_current_app_recovery_installed", False):
        return
    original_init = UpdateService.__init__
    original_with_execution = UpdateService._with_execution
    original_resolve_manual = UpdateService.resolve_manual_request

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)

        def verify() -> None:
            try:
                self.verify_environment()
            except Exception:
                pass

        threading.Thread(target=verify, name="update-environment-bootstrap", daemon=True).start()

    def patched_with_execution(self: Any, job: dict[str, Any]) -> dict[str, Any]:
        return _decorate_update_item(self, original_with_execution(self, job))

    def patched_execute(self: Any, job_id: str) -> dict[str, Any]:
        return dispatch(self, job_id, retry=False)

    def patched_retry(self: Any, job_id: str) -> dict[str, Any]:
        return dispatch(self, job_id, retry=True)

    def dispatch(self: Any, job_id: str, *, retry: bool) -> dict[str, Any]:
        from app.update_queue_state_runtime import _batch_roles
        from app.updates.service import UpdateExecutionBlocked
        with self.lock:
            if job_id in self.active_requests:
                raise ValueError("Job já está em preparação ou execução")
            if job_id in _batch_roles(self)[1]:
                raise UpdateExecutionBlocked([{"code": "job_queued", "message": "Produto já está na fila."}])
            self.active_requests.add(job_id)
        try:
            job = self.repository.get(job_id)
            blockers = [item for item in self._execution(job).get("blockers", [])
                        if item["code"].startswith("job_") or item["code"] in {"execution_disabled", "product_not_allowed"}]
            if blockers:
                raise UpdateExecutionBlocked(blockers)
            fresh = retry and job.get("state") == "error"
            if fresh:
                from app.update_retry_live_objective import _refresh_retry_objective
                _refresh_retry_objective(self, job_id)
            _prepare_job_execution(self, job_id, fresh_source=fresh)
            return self.executor.execute(job_id)
        finally:
            with self.lock:
                self.active_requests.discard(job_id)

    def patched_resolve_manual_request(self: Any, product_id: int) -> dict[str, Any]:
        self.materialize()
        listing = self.repository.list(query=str(int(product_id)), page=1, page_size=100, sort_by="date", sort_order="desc")
        candidates = [item for item in listing["items"] if int(item.get("woo_product_id") or 0) == int(product_id)]
        seen: set[str] = set()
        for candidate in candidates:
            kind = str(candidate.get("source_kind") or "")
            if not kind or kind in seen:
                continue
            seen.add(kind)
            try:
                _validate_job_source(self, candidate, fresh=False)
            except Exception:
                pass
        return original_resolve_manual(self, product_id)

    UpdateService.__init__ = patched_init
    UpdateService._with_execution = patched_with_execution
    UpdateService.execute = patched_execute
    UpdateService.retry = patched_retry
    UpdateService.resolve_manual_request = patched_resolve_manual_request
    UpdateService._current_app_recovery_installed = True


def _patch_monitor() -> None:
    from app.store.monitor import StoreMonitorService

    if getattr(StoreMonitorService, "_current_app_recovery_installed", False):
        return
    original_init = StoreMonitorService.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        configured = bool(getattr(self.queue, "configured", False))
        automatic = os.getenv("SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED", "1").strip().lower() not in _FALSE_VALUES
        current = self.repository.monitor()
        virgin = not current.get("last_run_at") and str(current.get("stage") or "idle") == "idle"
        if configured and automatic and (current.get("enabled") or virgin):
            if not current.get("enabled"):
                self.repository.patch_monitor(
                    enabled=1,
                    state="idle",
                    stage="monitoring",
                    next_check_at=self._next(),
                    current_error=None,
                )
            self.start_background()

            def immediate_poll() -> None:
                try:
                    self.run(force=True)
                except Exception:
                    pass

            threading.Thread(target=immediate_poll, name="wordpress-manual-first-poll", daemon=True).start()

    StoreMonitorService.__init__ = patched_init
    StoreMonitorService._current_app_recovery_installed = True


def _pricing_item(service: Any, product: dict[str, Any]) -> dict[str, Any]:
    product_id = int(product.get("id") or 0)
    kind = product_kind(product)
    variable = str(product.get("type") or "").startswith("variable")
    variations = []
    if variable:
        for row in service._variations(product_id):
            variations.append({
                "id": int(row.get("id") or 0),
                "name": str(row.get("name") or f"Variação #{row.get('id')}"),
                "period": period(row) or "other",
                "regular_price": str(row.get("regular_price") or ""),
                "sale_price": str(row.get("sale_price") or ""),
            })
    return {
        "product_id": product_id,
        "product_name": str(product.get("name") or ""),
        "product_type": str(product.get("type") or ""),
        "kind": kind,
        "pricing_mode": "variations" if variations else "direct",
        "regular_price": str(product.get("regular_price") or ""),
        "sale_price": str(product.get("sale_price") or ""),
        "variations": variations,
    }


def _catalog(service: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    query = str(payload.get("query") or "").strip().casefold()
    kind = str(payload.get("type") or "").strip()
    page = max(1, int(payload.get("page") or 1))
    page_size = max(1, min(50, int(payload.get("page_size") or 10)))
    refresh = str(payload.get("refresh") or "").lower() in {"1", "true", "yes"}
    products = service._products(refresh=refresh)
    selectable = []
    counts = {"plugin": 0, "theme": 0}
    for product in products:
        item_kind = product_kind(product)
        if item_kind not in counts or is_pack(product) or is_plan(product):
            continue
        counts[item_kind] += 1
        haystack = f"{product.get('id')} {product.get('name', '')}".casefold()
        if kind and item_kind != kind:
            continue
        if query and query not in haystack:
            continue
        selectable.append(product)
    selectable.sort(key=lambda item: (str(item.get("name") or "").casefold(), int(item.get("id") or 0)))
    total = len(selectable)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    visible = selectable[(page - 1) * page_size:page * page_size]
    return {
        "ok": True,
        "write_enabled": service.write_enabled,
        "individual": {
            "items": [_pricing_item(service, product) for product in visible],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "available_products": counts,
        },
        "packs": {"items": service.bundles_service.list(products, "pack")},
        "plans": {"items": service.bundles_service.list(products, "plan")},
    }


def _product_price_preview(service: Any, payload: dict[str, Any]) -> dict[str, Any]:
    product_id = int(payload.get("product_id") or 0)
    product = service.gateway.product(product_id)
    kind = product_kind(product)
    if kind not in {"plugin", "theme"} or is_pack(product) or is_plan(product):
        raise ValueError("O produto selecionado não pertence a Plugins ou Temas.")
    variable = str(product.get("type") or "").startswith("variable")
    if variable:
        current = {int(row.get("id") or 0): row for row in service._variations(product_id)}
        targets = list(payload.get("variations") or [])
        if not targets:
            raise ValueError("Informe ao menos uma variação para alterar.")
        changes = []
        for target in targets:
            variation_id = int(target.get("id") or 0)
            if variation_id not in current:
                raise ValueError(f"Variação #{variation_id} não pertence ao produto.")
            regular = money(target.get("regular_price"))
            sale = money(target.get("sale_price"), False)
            row = current[variation_id]
            unchanged = str(row.get("regular_price") or "") == regular and str(row.get("sale_price") or "") == sale
            changes.append({
                "id": variation_id,
                "name": str(row.get("name") or f"Variação #{variation_id}"),
                "regular_price": regular,
                "sale_price": sale,
                "status": "unchanged" if unchanged else "change",
            })
        status = "unchanged" if all(row["status"] == "unchanged" for row in changes) else "change"
        return {"ok": True, "product_id": product_id, "product_name": str(product.get("name") or ""), "kind": kind, "pricing_mode": "variations", "variation_changes": changes, "status": status}
    regular = money(payload.get("regular_price"))
    sale = money(payload.get("sale_price"), False)
    unchanged = str(product.get("regular_price") or "") == regular and str(product.get("sale_price") or "") == sale
    return {"ok": True, "product_id": product_id, "product_name": str(product.get("name") or ""), "kind": kind, "pricing_mode": "direct", "regular_price": regular, "sale_price": sale, "variation_changes": [], "status": "unchanged" if unchanged else "change"}


def _product_price_apply(service: Any, payload: dict[str, Any]) -> dict[str, Any]:
    if not service.write_enabled:
        raise PermissionError("Escrita da Loja desabilitada por SCRAPER_STORE_WRITE_ENABLED")
    if confirmation_token(payload.get("confirmation")) not in {"ALTERAR PRECO", "ALTERAR PRECOS"}:
        raise ValueError('Digite "ALTERAR PREÇO" para confirmar')
    preview = _product_price_preview(service, payload)
    if preview["status"] == "unchanged":
        return {**preview, "updated": False, "changed": 0}
    product_id = int(preview["product_id"])
    variations = [
        {"id": row["id"], "regular_price": row["regular_price"], "sale_price": row["sale_price"]}
        for row in preview.get("variation_changes", []) if row["status"] == "change"
    ]
    if variations:
        changed = len(service.gateway.update_variations(product_id, variations))
    else:
        service.gateway.update_product_price(product_id, preview["regular_price"], preview["sale_price"])
        changed = 1
    with service.lock:
        service._variation_cache.pop(product_id, None)
        service._variation_cached_at.pop(product_id, None)
        service._cached_at = 0.0
    summary = {"product_id": product_id, "changed": changed, "kind": preview["kind"]}
    try:
        service.repository.pricing_run("success", payload, summary)
    except Exception:
        pass
    return {**preview, "updated": True, "changed": changed, "status": "changed"}


def _patch_store_pricing() -> None:
    from app.store.service import StoreService

    if getattr(StoreService, "_current_app_recovery_installed", False):
        return

    def pricing_catalog(self: Any, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return _catalog(self, payload)

    def product_price_preview(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        return _product_price_preview(self, payload)

    def product_price_apply(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
        return _product_price_apply(self, payload)

    StoreService.pricing_catalog = pricing_catalog
    StoreService.product_price_preview = product_price_preview
    StoreService.product_price_apply = product_price_apply
    StoreService._current_app_recovery_installed = True


def install_current_app_recovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_updates()
    _patch_monitor()
    _patch_store_pricing()
    _INSTALLED = True


__all__ = [
    "install_current_app_recovery",
    "_decorate_update_item",
    "_catalog",
    "_product_price_preview",
    "_product_price_apply",
]
