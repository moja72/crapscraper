from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import app.web as web
from app import settings
from app.plugintema_catalog_refresh import refresh_catalog, save_catalog_definition

_INSTALLED = False
_BASE_MAKE_HANDLER: Callable[..., Any] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_BASE_GENERATE: Callable[..., dict[str, Any]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "plugintema_catalog_refresh.js"
_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict[str, Any]] = {}
_ACTIVE_BY_CATALOG: dict[str, str] = {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"} or value is True


def _catalog_path(catalog_id: str) -> Path:
    catalog_id = _text(catalog_id)
    generated = {
        str(item.get("id") or ""): item
        for item in web._build_comparison_sources_payload().get("imported_catalogs", [])
        if str(item.get("filename") or "").startswith("plugintema-")
    }
    if catalog_id not in generated:
        raise ValueError("Catálogo PluginTema inválido.")
    path = web._resolve_comparison_catalog_path(catalog_id)
    if path is None:
        raise ValueError("Catálogo PluginTema não encontrado.")
    resolved = Path(path).resolve()
    root = Path(settings.COMPARISON_IMPORTS_DIR).resolve()
    if resolved.parent != root or not resolved.name.startswith("plugintema-") or resolved.suffix.lower() != ".csv":
        raise ValueError("Catálogo fora da área permitida.")
    return resolved


def _job_snapshot(job_id: str) -> dict[str, Any]:
    with _JOB_LOCK:
        item = _JOBS.get(job_id)
        if item is None:
            raise KeyError("Processo de atualização não encontrado.")
        snapshot = dict(item)
        if isinstance(snapshot.get("result"), Mapping):
            snapshot["result"] = dict(snapshot["result"])
        return snapshot


def _update_job(job_id: str, **values: Any) -> None:
    with _JOB_LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(values)


def _start_refresh(catalog_id: str, *, force_full: bool = False) -> dict[str, Any]:
    catalog_id = _text(catalog_id)
    path = _catalog_path(catalog_id)
    with _JOB_LOCK:
        active_id = _ACTIVE_BY_CATALOG.get(catalog_id)
        if active_id and _JOBS.get(active_id, {}).get("status") in {"queued", "running"}:
            return dict(_JOBS[active_id])

        job_id = uuid4().hex
        job = {
            "ok": True,
            "job_id": job_id,
            "catalog_id": catalog_id,
            "catalog": path.name,
            "status": "queued",
            "phase": "queued",
            "message": "Atualização adicionada à fila local.",
            "force_full": bool(force_full),
            "result": {},
        }
        _JOBS[job_id] = job
        _ACTIVE_BY_CATALOG[catalog_id] = job_id

    def progress(phase: str, page: int, completed: int, message: str) -> None:
        readable = _text(message) or "Atualizando catálogo..."
        _update_job(
            job_id,
            status="running",
            phase=phase,
            page=max(0, int(page or 0)),
            completed=max(0, int(completed or 0)),
            message=readable,
        )

    def run() -> None:
        _update_job(job_id, status="running", phase="starting", message="Conectando ao WooCommerce...")
        try:
            woo = web._build_readonly_woocommerce_client()
            result = refresh_catalog(
                path,
                woo,
                force_full=force_full,
                progress=progress,
            )
            cache = dict(result.get("cache") or {})
            cache_label = "incremental" if cache.get("mode") == "incremental" else "completa"
            message = (
                f"Catálogo atualizado: {result.get('after', 0)} itens; "
                f"+{result.get('added', 0)} novos; {result.get('removed', 0)} removidos; "
                f"{result.get('versions_updated', 0)} versões alteradas; varredura {cache_label}."
            )
            _update_job(job_id, status="completed", phase="done", message=message, result=result)
        except Exception as error:
            _update_job(job_id, status="error", phase="error", message=str(error), error=str(error))
        finally:
            with _JOB_LOCK:
                if _ACTIVE_BY_CATALOG.get(catalog_id) == job_id:
                    _ACTIVE_BY_CATALOG.pop(catalog_id, None)

    threading.Thread(
        target=run,
        name=f"plugintema-catalog-refresh-{job_id[:8]}",
        daemon=True,
    ).start()
    return dict(job)


def _save_definition_for_generated(
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
    before: set[Path],
) -> None:
    try:
        mode, filters = web._parse_plugintema_filters(payload)
    except Exception:
        return

    path: Path | None = None
    for key in ("catalog_id", "id"):
        catalog_id = _text(result.get(key))
        if not catalog_id:
            continue
        candidate = web._resolve_comparison_catalog_path(catalog_id)
        if candidate is not None:
            path = Path(candidate)
            break
    if path is None:
        filename = _text(result.get("filename"))
        if filename:
            candidate = Path(settings.COMPARISON_IMPORTS_DIR) / Path(filename).name
            if candidate.exists():
                path = candidate
    if path is None:
        after = set(Path(settings.COMPARISON_IMPORTS_DIR).glob("plugintema-*.csv"))
        created = sorted(after - before, key=lambda item: item.stat().st_mtime, reverse=True)
        if created:
            path = created[0]
    if path is not None and path.exists():
        save_catalog_definition(path, mode, filters, inferred=False)


def _patched_generate(payload: Mapping[str, Any], woo: Any) -> dict[str, Any]:
    base = _BASE_GENERATE
    if base is None:
        raise RuntimeError("Gerador de catálogo PluginTema indisponível.")
    root = Path(settings.COMPARISON_IMPORTS_DIR)
    before = set(root.glob("plugintema-*.csv")) if root.exists() else set()
    result = base(payload, woo)
    try:
        _save_definition_for_generated(payload, result, before)
    except Exception:
        # O CSV já foi gerado com sucesso; falha na sidecar não deve invalidá-lo.
        pass
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-plugintema-catalog-refresh>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _patched_make_handler(*args: Any, **kwargs: Any) -> Any:
    base = _BASE_MAKE_HANDLER
    if base is None:
        raise RuntimeError("Handler web base indisponível.")
    BaseHandler = base(*args, **kwargs)

    class CatalogRefreshHandler(BaseHandler):
        def do_POST(self) -> None:  # noqa: N802 - assinatura do BaseHTTPRequestHandler
            path = self._request_path()
            if path != "/plugintema/catalogo/atualizar":
                return super().do_POST()
            try:
                payload = self._read_json_body()
                job = _start_refresh(
                    payload.get("catalog_id", ""),
                    force_full=_bool(payload.get("force_full", False)),
                )
                self._send_json(job, code=202 if job.get("status") != "completed" else 200)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json(web.build_error_payload(error), code=500)

        def do_GET(self) -> None:  # noqa: N802 - assinatura do BaseHTTPRequestHandler
            path = self._request_path()
            if path != "/plugintema/catalogo/atualizar/status":
                return super().do_GET()
            query = parse_qs(urlsplit(self.path).query or "")
            job_id = _text((query.get("job_id") or [""])[0])
            try:
                self._send_json(_job_snapshot(job_id))
            except KeyError as error:
                self._send_json({"ok": False, "message": str(error)}, code=404)
            except Exception as error:
                self._send_json(web.build_error_payload(error), code=500)

    CatalogRefreshHandler.__name__ = getattr(BaseHandler, "__name__", "Handler")
    return CatalogRefreshHandler


def install_plugintema_catalog_refresh_policy() -> None:
    global _INSTALLED, _BASE_MAKE_HANDLER, _BASE_RENDER, _BASE_GENERATE
    if _INSTALLED:
        return

    _BASE_GENERATE = web._generate_plugintema_comparison_catalog
    web._generate_plugintema_comparison_catalog = _patched_generate

    _BASE_MAKE_HANDLER = web.make_handler
    web.make_handler = _patched_make_handler

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
