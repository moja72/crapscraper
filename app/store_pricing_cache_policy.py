from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import app.store_pricing as pricing
import app.web as web
from app import settings
from app.store_pricing_cache import (
    get_pack_snapshot,
    get_plan_snapshot,
    normalize_kinds,
    patch_pack_product,
    patch_plan_prices,
    set_pack_snapshot,
    set_plan_snapshot,
)

_INSTALLED = False
_BASE_MAKE_HANDLER: Callable[..., Any] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_BASE_APPLY_PRICES: Callable[..., dict[str, Any]] | None = None
_BASE_UPDATE_PACK: Callable[..., dict[str, Any]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "store_pricing_cache.js"
_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE: dict[str, str] = {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _job_key(target: str, kinds: Iterable[str] = ()) -> str:
    return target if target == "packs" else f"plans:{'+'.join(sorted(normalize_kinds(kinds)))}"


def _job_snapshot(job_id: str) -> dict[str, Any]:
    with _JOB_LOCK:
        item = _JOBS.get(job_id)
        if not item:
            raise KeyError("Atualização de preços não encontrada.")
        return dict(item)


def _update_job(job_id: str, **values: Any) -> None:
    with _JOB_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(values)


def _refresh_plans(kinds: tuple[str, ...], progress: Callable[[str, int, int, str], None]) -> dict[str, Any]:
    reference = pricing.read_store_price_reference_products(
        Path(settings.COMPARISON_IMPORTS_DIR), kinds, limit_per_kind=3
    )
    if not reference:
        raise ValueError("Nenhum produto de referência foi encontrado nos catálogos PluginTema.")
    snapshot = pricing.build_store_pricing_snapshot(
        web._build_store_woocommerce_client(), kinds, products=reference, progress=progress
    )
    return set_plan_snapshot(kinds, snapshot, source="woocommerce-refresh")


def _refresh_packs(progress: Callable[[str, int, int, str], None]) -> dict[str, Any]:
    progress("reading", 0, 0, "Localizando packs no WooCommerce")
    products = pricing.list_store_pack_products(web._build_store_woocommerce_client())
    progress("saving", len(products), len(products), "Salvando preços dos packs")
    return set_pack_snapshot(products, source="woocommerce-refresh")


def _start_refresh(target: str, kinds: Iterable[str] = (), *, force: bool = False) -> dict[str, Any]:
    target = "packs" if target == "packs" else "plans"
    selected = normalize_kinds(kinds) if target == "plans" else ()
    key = _job_key(target, selected)
    with _JOB_LOCK:
        active_id = _ACTIVE.get(key)
        if active_id and _JOBS.get(active_id, {}).get("status") in {"queued", "running"}:
            return dict(_JOBS[active_id])
        job_id = uuid4().hex
        job = {
            "ok": True,
            "job_id": job_id,
            "target": target,
            "kinds": list(selected),
            "status": "queued",
            "phase": "queued",
            "completed": 0,
            "total": 0,
            "message": "Atualização agendada.",
            "force": bool(force),
        }
        _JOBS[job_id] = job
        _ACTIVE[key] = job_id

    def progress(phase: str, completed: int, total: int, current: str = "") -> None:
        label = _text(current) or ("Lendo preços dos planos" if target == "plans" else "Lendo preços dos packs")
        _update_job(
            job_id,
            status="running",
            phase=phase,
            completed=max(0, int(completed or 0)),
            total=max(0, int(total or 0)),
            message=label,
        )

    def run() -> None:
        _update_job(job_id, status="running", phase="connecting", message="Conectando ao WooCommerce...")
        try:
            result = _refresh_packs(progress) if target == "packs" else _refresh_plans(selected, progress)
            cache = dict(result.get("cache") or {})
            _update_job(
                job_id,
                status="completed",
                phase="done",
                completed=int(result.get("total") or result.get("variation_count") or 0),
                total=int(result.get("total") or result.get("variation_count") or 0),
                cached_at=str(cache.get("cached_at") or ""),
                message=(
                    f"Preços dos packs atualizados: {int(result.get('total') or 0)} item(ns)."
                    if target == "packs"
                    else "Preços dos planos atualizados e salvos localmente."
                ),
            )
        except Exception as error:
            _update_job(job_id, status="error", phase="error", message=str(error), error=str(error))
        finally:
            with _JOB_LOCK:
                if _ACTIVE.get(key) == job_id:
                    _ACTIVE.pop(key, None)

    threading.Thread(target=run, name=f"store-pricing-refresh-{job_id[:8]}", daemon=True).start()
    return dict(job)


def _plan_placeholder(kinds: Iterable[str], job: Mapping[str, Any] | None = None) -> dict[str, Any]:
    selected = normalize_kinds(kinds)
    return {
        "ok": True,
        "product_count": 0,
        "variation_count": 0,
        "unmatched_variation_count": 0,
        "distribution": {"annual": [], "lifetime": []},
        "by_kind": {
            kind: {
                "product_count": 0,
                "variation_count": 0,
                "unmatched_variation_count": 0,
                "distribution": {"annual": [], "lifetime": []},
            }
            for kind in selected
        },
        "read_only": True,
        "cache": {
            "saved": False,
            "warming": True,
            "job_id": str((job or {}).get("job_id") or ""),
        },
    }


def _patched_apply_store_prices(*args: Any, **kwargs: Any) -> dict[str, Any]:
    base = _BASE_APPLY_PRICES
    if base is None:
        raise RuntimeError("Atualizador de preços base indisponível.")
    payload = args[1] if len(args) > 1 else kwargs.get("payload", {})
    result = base(*args, **kwargs)
    if result.get("ok") and isinstance(payload, Mapping):
        try:
            prices = pricing.normalize_prices(payload)
            kinds = payload.get("kinds", [])
            patch_plan_prices(kinds if isinstance(kinds, list) else [], prices)
        except Exception:
            pass
    return result


def _patched_update_pack_price(*args: Any, **kwargs: Any) -> dict[str, Any]:
    base = _BASE_UPDATE_PACK
    if base is None:
        raise RuntimeError("Atualizador de pack base indisponível.")
    result = base(*args, **kwargs)
    try:
        if result.get("ok") and isinstance(result.get("product"), Mapping):
            patch_pack_product(result["product"])
    except Exception:
        pass
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-store-pricing-cache>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _patched_make_handler(*args: Any, **kwargs: Any) -> Any:
    base = _BASE_MAKE_HANDLER
    if base is None:
        raise RuntimeError("Handler web base indisponível.")
    BaseHandler = base(*args, **kwargs)

    class StorePricingCacheHandler(BaseHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = self._request_path()
            if path == "/loja/precos":
                query = parse_qs(urlsplit(self.path).query or "")
                kinds = [value for value in query.get("tipo", []) if value in {"plugin", "theme"}]
                selected = normalize_kinds(kinds)
                cached = get_plan_snapshot(selected)
                if cached is not None:
                    self._send_json(cached)
                    return
                job = _start_refresh("plans", selected)
                self._send_json(_plan_placeholder(selected, job))
                return

            if path == "/loja/pacotes/precos":
                cached = get_pack_snapshot()
                if cached is not None:
                    self._send_json(cached)
                    return
                job = _start_refresh("packs")
                self._send_json({
                    "ok": True,
                    "products": [],
                    "total": 0,
                    "cache": {"saved": False, "warming": True, "job_id": job.get("job_id", "")},
                })
                return

            if path == "/loja/precos/cache/status":
                query = parse_qs(urlsplit(self.path).query or "")
                job_id = _text((query.get("job_id") or [""])[0])
                target = _text((query.get("target") or ["plans"])[0])
                kinds = [value for value in query.get("tipo", []) if value in {"plugin", "theme"}]
                try:
                    if job_id:
                        self._send_json({"ok": True, **_job_snapshot(job_id)})
                        return
                    cached = get_pack_snapshot() if target == "packs" else get_plan_snapshot(normalize_kinds(kinds))
                    self._send_json({
                        "ok": True,
                        "status": "completed" if cached else "missing",
                        "cached": bool(cached),
                        "cache": dict((cached or {}).get("cache") or {}),
                    })
                except KeyError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=404)
                return

            return super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            path = self._request_path()
            if path != "/loja/precos/cache/atualizar":
                return super().do_POST()
            try:
                payload = self._read_json_body()
                target = _text(payload.get("target") or "plans")
                kinds = payload.get("kinds", [])
                if not isinstance(kinds, list):
                    kinds = []
                job = _start_refresh(target, kinds, force=True)
                self._send_json(job, code=202)
            except Exception as error:
                self._send_json(web.build_error_payload(error), code=500)

    StorePricingCacheHandler.__name__ = getattr(BaseHandler, "__name__", "Handler")
    return StorePricingCacheHandler


def _prewarm() -> None:
    # Não bloqueia o boot. Só consulta a loja quando ainda não há informação salva.
    if get_plan_snapshot(("plugin", "theme")) is None:
        _start_refresh("plans", ("plugin", "theme"))
    if get_pack_snapshot() is None:
        _start_refresh("packs")


def install_store_pricing_cache_policy() -> None:
    global _INSTALLED, _BASE_MAKE_HANDLER, _BASE_RENDER, _BASE_APPLY_PRICES, _BASE_UPDATE_PACK
    if _INSTALLED:
        return

    _BASE_APPLY_PRICES = pricing.apply_store_prices
    pricing.apply_store_prices = _patched_apply_store_prices
    _BASE_UPDATE_PACK = pricing.update_store_pack_price
    pricing.update_store_pack_price = _patched_update_pack_price

    _BASE_MAKE_HANDLER = web.make_handler
    web.make_handler = _patched_make_handler
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _INSTALLED = True
    threading.Thread(target=_prewarm, name="store-pricing-cache-prewarm", daemon=True).start()
