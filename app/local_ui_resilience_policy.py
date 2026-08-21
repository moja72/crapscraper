from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

import app.store_pricing as store_pricing
import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_BASE_PACK_LIST: Callable[..., list[dict[str, Any]]] | None = None
_BASE_PACK_UPDATE: Callable[..., dict[str, Any]] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "frontend_request_resilience.js"

_PACK_CACHE_TTL_SECONDS = 2.5
_PACK_CACHE_LOCK = threading.RLock()
_PACK_FETCH_LOCK = threading.Lock()
_PACK_CACHE_AT = 0.0
_PACK_CACHE_ROWS: list[dict[str, Any]] = []

_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)

# addition_operational_ui.js is intentionally not edited here. The user's Windows
# checkout can carry local UI work, so the final resilience layer patches only the
# known boot snippet in the rendered HTML. This keeps the correction compatible
# with a dirty worktree while preventing a hidden tab from doing expensive work.
_ADDITION_TAB_REFRESH_LISTENER = '    $("#tab_btn_adicoes")?.addEventListener("click",()=>setTimeout(()=>{if(panelVisible())refreshAll({history:false,silent:true});},0));\n'
_ADDITION_BACKGROUND_SYNC_START = '  async function backgroundSyncOnce(){try{'
_ADDITION_BACKGROUND_SYNC_GUARDED = '  async function backgroundSyncOnce(){if(!panelVisible())return;try{'
_ADDITION_BOOT = '  function boot(){if(state.started)return;state.started=true;installUi();if(!$("#addition_operational_root"))return;if(panelVisible())refreshAll({history:false});setTimeout(backgroundSyncOnce,350);setInterval(poll,3000);}'
_ADDITION_LAZY_BOOT = '''  function activateOperationalUi(){
    if(!panelVisible())return;
    if(!$("#addition_operational_root"))installUi();
    if(!$("#addition_operational_root"))return;
    if(!state.started){
      state.started=true;
      refreshAll({history:false});
      setTimeout(()=>{if(panelVisible())backgroundSyncOnce();},350);
      setInterval(poll,3000);
      return;
    }
    refreshAll({history:false,silent:true});
  }
  function boot(){
    $("#tab_btn_adicoes")?.addEventListener("click",()=>setTimeout(activateOperationalUi,0));
    if(panelVisible())activateOperationalUi();
  }'''


def _clone_rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in (rows or []) if isinstance(item, dict)]


def _invalidate_pack_cache() -> None:
    global _PACK_CACHE_AT, _PACK_CACHE_ROWS
    with _PACK_CACHE_LOCK:
        _PACK_CACHE_AT = 0.0
        _PACK_CACHE_ROWS = []


def _cached_pack_list(woo: Any) -> list[dict[str, Any]]:
    """Coalesce leituras pesadas de packs/planos feitas quase ao mesmo tempo."""
    global _PACK_CACHE_AT, _PACK_CACHE_ROWS
    if _BASE_PACK_LIST is None:
        raise RuntimeError("Leitor de packs/planos base indisponível")

    now = time.monotonic()
    with _PACK_CACHE_LOCK:
        if _PACK_CACHE_AT and now - _PACK_CACHE_AT <= _PACK_CACHE_TTL_SECONDS:
            return _clone_rows(_PACK_CACHE_ROWS)

    # O endpoint percorre produtos/categorias e pode carregar variações. Duas UIs
    # antigas conseguiam dispará-lo em paralelo; somente uma leitura remota deve
    # acontecer e as demais reutilizam o resultado recém-obtido.
    with _PACK_FETCH_LOCK:
        now = time.monotonic()
        with _PACK_CACHE_LOCK:
            if _PACK_CACHE_AT and now - _PACK_CACHE_AT <= _PACK_CACHE_TTL_SECONDS:
                return _clone_rows(_PACK_CACHE_ROWS)

        rows = _clone_rows(_BASE_PACK_LIST(woo))
        with _PACK_CACHE_LOCK:
            _PACK_CACHE_AT = time.monotonic()
            _PACK_CACHE_ROWS = _clone_rows(rows)
        return rows


def _cached_pack_update(woo: Any, payload: Any) -> dict[str, Any]:
    if _BASE_PACK_UPDATE is None:
        raise RuntimeError("Atualizador de packs/planos base indisponível")
    result = _BASE_PACK_UPDATE(woo, payload)
    _invalidate_pack_cache()
    return result


def _is_client_disconnect(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _CLIENT_DISCONNECT_ERRORS):
            return True
        current = current.__cause__ or current.__context__
    return False


def _mark_client_disconnected(handler: Any) -> None:
    try:
        handler.close_connection = True
    except Exception:
        pass


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class LocalUiResilientHandler(handler_class):
        """Trata abort/reset/broken pipe como término normal da requisição."""

        def _send_bytes(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return super()._send_bytes(*args, **kwargs)
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

        def _send_empty(self, *args: Any, **kwargs: Any) -> Any:
            try:
                return super()._send_empty(*args, **kwargs)
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

        def do_GET(self) -> None:
            try:
                return super().do_GET()
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

        def do_POST(self) -> None:
            try:
                return super().do_POST()
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

        def do_OPTIONS(self) -> None:
            try:
                return super().do_OPTIONS()
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

        def finish(self) -> None:
            try:
                return super().finish()
            except _CLIENT_DISCONNECT_ERRORS:
                _mark_client_disconnected(self)
                return None

    return _BASE_SERVER(server_address, LocalUiResilientHandler, *args, **kwargs)


def _patch_hidden_addition_boot(html: str) -> str:
    """Do not mount/sync the Adições UI until the user actually opens that tab."""
    result = str(html or "")
    result = result.replace(_ADDITION_TAB_REFRESH_LISTENER, "")
    result = result.replace(_ADDITION_BACKGROUND_SYNC_START, _ADDITION_BACKGROUND_SYNC_GUARDED)
    result = result.replace(_ADDITION_BOOT, _ADDITION_LAZY_BOOT)
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = _patch_hidden_addition_boot(base(*args, **kwargs))
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-local-ui-resilience>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def install_local_ui_resilience_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER, _BASE_PACK_LIST, _BASE_PACK_UPDATE
    if _INSTALLED:
        return

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory

    # store_pack_variation_policy já foi instalado antes desta policy e, por
    # isso, estas bases preservam packs, planos e variações sem remover recurso.
    _BASE_PACK_LIST = store_pricing.list_store_pack_products
    _BASE_PACK_UPDATE = store_pricing.update_store_pack_price
    store_pricing.list_store_pack_products = _cached_pack_list
    store_pricing.update_store_pack_price = _cached_pack_update

    _INSTALLED = True
