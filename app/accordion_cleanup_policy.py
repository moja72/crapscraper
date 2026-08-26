from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "accordion_cleanup.js"

_GLOBAL_UPDATE_OBSERVER = '''  refine();

  let timer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(refine, 70);
  });
  observer.observe(document.body, {childList:true, subtree:true, characterData:true});'''

_EVENT_DRIVEN_UPDATE_REFRESH = '''  refine();

  // A versão anterior observava TODA mutação de texto/DOM da página. A aba
  // Atualizar muda contadores, progresso, histórico e logs com frequência; cada
  // mudança disparava refine(), que por sua vez mexia no cache/skeleton e gerava
  // mais mutações. O resultado era piscar e sanfonas disputando estado.
  // Refinamentos visuais agora acontecem em pontos finitos e eventos reais.
  [120, 420, 1000, 2200].forEach(delay => window.setTimeout(refine, delay));

  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || "");
    if (key === "atualizacoes" || key === "comparacao") {
      window.setTimeout(refine, 45);
    }
  });

  document.addEventListener("click", event => {
    const id = event.target?.closest?.("button")?.id || "";
    if ([
      "tab_btn_atualizacoes",
      "updates_refresh_btn",
      "updates_clear_filters",
      "updates_prepare_selected",
      "updates_enqueue_selected"
    ].includes(id)) {
      window.setTimeout(refine, 90);
    }
  }, true);'''


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)

    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html

    # O observer global era uma policy visual antiga. Remova apenas o gatilho
    # contínuo; todas as funções de normalização/cache continuam preservadas.
    script = script.replace(_GLOBAL_UPDATE_OBSERVER, _EVENT_DRIVEN_UPDATE_REFRESH)
    script = script.replace("</script>", "<\\/script>")
    block = f"\n<script data-accordion-cleanup>\n{script}\n</script>\n"
    marker = "</body>"

    if marker in html:
        return html.replace(marker, block + marker, 1)
    return html + block


def install_accordion_cleanup_policy() -> None:
    global _INSTALLED, _BASE_RENDER
    if _INSTALLED:
        return

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
