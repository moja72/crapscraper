from __future__ import annotations

from typing import Any, Callable

import app.web as web
from app.deferred_runtime_bootstrap import is_runtime_ready, runtime_restore_status


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None

_BLOCKED_POST_PREFIXES = ("/atualizacoes/",)
_BLOCKED_POST_EXACT = {
    "/operacoes/simples/atualizar",
    "/operacoes/historico/apagar",
}

_SCRIPT = r'''(() => {
  "use strict";
  if (window.__crapScraperRuntimeBootGateInstalled) return;
  window.__crapScraperRuntimeBootGateInstalled = true;

  const ID = "cs_runtime_boot_notice";
  function ensureNotice() {
    let node = document.getElementById(ID);
    if (node) return node;
    node = document.createElement("div");
    node.id = ID;
    node.setAttribute("role", "status");
    node.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:2147483000;max-width:390px;padding:10px 13px;border:1px solid #34343d;border-radius:10px;background:#151519;color:#d7dce5;font:600 12px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 10px 28px rgba(0,0,0,.24);display:none";
    document.body.appendChild(node);
    return node;
  }

  async function poll() {
    const node = ensureNotice();
    try {
      const response = await fetch("/startup/runtime-status", {cache:"no-store", credentials:"same-origin"});
      const payload = await response.json();
      if (payload?.ready) {
        node.style.display = "none";
        return true;
      }
      node.style.display = "block";
      if (payload?.stage === "error") {
        node.textContent = "Histórico operacional não pôde ser carregado. Atualizações continuam bloqueadas; verifique o terminal.";
        return false;
      }
      node.textContent = "Painel aberto. Carregando histórico operacional de atualizações em segundo plano…";
    } catch (_error) {
      node.style.display = "none";
    }
    return false;
  }

  async function start() {
    for (;;) {
      const done = await poll();
      if (done) return;
      await new Promise(resolve => setTimeout(resolve, 1200));
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();'''


def _must_gate_post(path: str) -> bool:
    clean = str(path or "").strip()
    return clean in _BLOCKED_POST_EXACT or any(clean.startswith(prefix) for prefix in _BLOCKED_POST_PREFIXES)


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    escaped_script = _SCRIPT.replace("</script>", "<\\/script>")
    block = f"\n<script data-runtime-boot-gate>\n{escaped_script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class RuntimeBootGateHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/startup/runtime-status":
                self._send_json({"ok": True, **runtime_restore_status()})
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if _must_gate_post(path) and not is_runtime_ready():
                status = runtime_restore_status()
                message = (
                    "O histórico operacional de atualizações ainda está sendo carregado. "
                    "O painel já pode ser usado, mas ações de atualização ficam bloqueadas "
                    "até a restauração segura terminar."
                )
                if status.get("stage") == "error":
                    message = (
                        "O histórico operacional de atualizações não pôde ser restaurado. "
                        "A escrita foi bloqueada para proteger os dados persistidos."
                    )
                self._send_json({"ok": False, "message": message, "runtime": status}, code=503)
                return
            return super().do_POST()

    return _BASE_SERVER(server_address, RuntimeBootGateHandler, *args, **kwargs)


def install_startup_runtime_gate_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True


__all__ = ["install_startup_runtime_gate_policy", "_must_gate_post"]
