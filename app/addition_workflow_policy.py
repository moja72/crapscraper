from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.addition_workflow as workflow
import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Any = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "addition_workflow.js"

_PLACEHOLDER = '''<section
  class="tab-panel hidden"
  id="tab_panel_adicoes"
>
  <div class="card">
    <div class="section-title">Adições</div>

    <div class="notice">
      Nesta aba serão exibidos os produtos novos aprovados para cadastro na PluginTema.
      Nenhum produto será cadastrado automaticamente nesta fase.
    </div>
  </div>
</section>'''

_ADDITION_PANEL = '''<section class="tab-panel hidden" id="tab_panel_adicoes">
  <section class="addition-shell">
    <div class="card addition-hero">
      <div class="addition-hero-row">
        <div>
          <div class="section-title">Adicionar novos produtos</div>
          <div class="small">Cadastros aprovados na Comparação seguem por preparação do arquivo, conteúdo manual, rascunho, revisão e publicação.</div>
        </div>
        <button class="btn-secondary" id="add_refresh" type="button">Atualizar dados</button>
      </div>
      <div class="addition-flow">Comparação → ZIP → Conteúdo → Rascunho → Revisão → Publicação → Histórico</div>
      <div class="addition-kpis" id="add_kpis" aria-live="polite"></div>
    </div>

    <details class="card addition-chatgpt-card" id="add_chatgpt_settings">
      <summary><span>Conteúdo com ChatGPT</span><span class="addition-chevron">›</span></summary>
      <div class="addition-chatgpt-body">
        <div class="small">O CrapScraper prepara o briefing. A criação do texto e da imagem continua manual na conversa do ChatGPT escolhida por você.</div>
        <label for="add_chatgpt_url">Conversa do ChatGPT</label>
        <div class="addition-inline-form">
          <input id="add_chatgpt_url" type="url" placeholder="Cole a URL da conversa que você usa para criar produtos" autocomplete="off">
          <button class="btn-secondary" id="add_chatgpt_save" type="button">Salvar conversa</button>
          <button class="btn-secondary" id="add_chatgpt_open" type="button">Abrir conversa</button>
        </div>
      </div>
    </details>

    <div class="card addition-work-card">
      <div class="addition-toolbar">
        <div>
          <div class="section-title">Fila de adição</div>
          <div class="small">Somente itens aprovados como cadastro novo entram aqui.</div>
        </div>
        <div class="addition-toolbar-fields">
          <input id="add_search" type="search" placeholder="Nome, versão ou estado" autocomplete="off">
          <select id="add_state_filter">
            <option value="">Todos os estados</option>
            <option value="approved">Aguardando</option>
            <option value="preparing">Preparando arquivo</option>
            <option value="awaiting_content">Aguardando conteúdo</option>
            <option value="content_ready">Conteúdo pronto</option>
            <option value="creating_draft">Criando rascunho</option>
            <option value="draft_created">Rascunho criado</option>
            <option value="publishing">Publicando</option>
            <option value="blocked">Bloqueado</option>
            <option value="error">Erro</option>
          </select>
        </div>
      </div>
      <div id="add_active_jobs" aria-live="polite"><div class="notice">Carregando cadastros aprovados…</div></div>
    </div>

    <details class="card addition-history-card" id="add_history_section">
      <summary><span>Histórico de adições</span><span id="add_history_count" class="small">0 item(ns)</span></summary>
      <div id="add_history_jobs" class="addition-history-body" aria-live="polite"></div>
    </details>
  </section>
</section>'''


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    if _PLACEHOLDER in html:
        html = html.replace(_PLACEHOLDER, _ADDITION_PANEL, 1)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-addition-workflow>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def _closure_value(fn: Any, name: str) -> Any:
    closure = getattr(fn, "__closure__", None) or ()
    names = getattr(getattr(fn, "__code__", None), "co_freevars", ()) or ()
    for key, cell in zip(names, closure):
        if key == name:
            try:
                return cell.cell_contents
            except ValueError:
                return None
    return None


def _patch_handler(handler_cls: Any) -> None:
    if getattr(handler_cls, "_addition_workflow_patched", False):
        return
    original_get = handler_cls._route_get
    original_post = handler_cls._route_post
    manager = _closure_value(original_get, "manager") or _closure_value(original_post, "manager")

    def primary_app() -> Any:
        return web._get_primary_app(manager) if manager is not None else web._get_primary_app()

    def route_get(self: Any, path: str) -> bool:
        if path == "/adicoes/jobs":
            try:
                workflow.materialize()
                self._send_json(workflow.snapshot())
            except Exception as error:
                self._send_json({"ok": False, "message": str(error)}, code=500)
            return True
        return original_get(self, path)

    def route_post(self: Any, path: str, payload: dict[str, Any]) -> bool:
        if not path.startswith("/adicoes/"):
            return original_post(self, path, payload)
        try:
            if path == "/adicoes/materializar":
                self._send_json({"ok": True, **workflow.materialize()})
            elif path == "/adicoes/preparar":
                self._send_json(workflow.start_prepare(
                    str(payload.get("job_id") or ""), primary_app(),
                    item_type=str(payload.get("item_type") or ""),
                ), code=202)
            elif path == "/adicoes/conteudo":
                self._send_json(workflow.save_content(str(payload.get("job_id") or ""), payload))
            elif path == "/adicoes/rascunho":
                self._send_json(workflow.start_create_draft(
                    str(payload.get("job_id") or ""), str(payload.get("confirmation") or "")
                ), code=202)
            elif path == "/adicoes/publicar":
                self._send_json(workflow.start_publish(
                    str(payload.get("job_id") or ""), str(payload.get("confirmation") or "")
                ), code=202)
            elif path == "/adicoes/reprocessar":
                self._send_json(workflow.retry(str(payload.get("job_id") or ""), primary_app()), code=202)
            else:
                return original_post(self, path, payload)
        except ValueError as error:
            self._send_json({"ok": False, "message": str(error)}, code=400)
        except Exception as error:
            self._send_json({"ok": False, "message": str(error)}, code=500)
        return True

    handler_cls._route_get = route_get
    handler_cls._route_post = route_post
    handler_cls._addition_workflow_patched = True


def _patched_server(server_address: Any, handler_cls: Any, *args: Any, **kwargs: Any) -> Any:
    _patch_handler(handler_cls)
    return _BASE_SERVER(server_address, handler_cls, *args, **kwargs)


def install_addition_workflow_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return
    workflow.initialize()
    _BASE_RENDER = web.render_panel_page
    _BASE_SERVER = web.ThreadingHTTPServer
    web.render_panel_page = _patched_render_panel_page
    web.ThreadingHTTPServer = _patched_server
    _INSTALLED = True
