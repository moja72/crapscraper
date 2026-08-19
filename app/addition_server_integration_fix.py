from __future__ import annotations

from typing import Any

import app.web as web
import app.new_product_workflow_policy as additions
import app.chatgpt_browser_assist as chatgpt_assist
from app.integrations.wordpress import sanitize_text

_INSTALLED = False
_BASE_SERVER: Any = None


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    """Acopla as rotas de adição ao servidor realmente usado por web.serve()."""
    manager = additions._manager_from_handler(handler_class)

    class AdditionHandler(handler_class):
        def do_GET(self) -> None:
            path = self._request_path()
            if path == "/adicoes/data":
                try:
                    payload = additions._snapshot()
                    payload["approved_total"] = len(additions.list_approved_additions())
                    self._send_json(payload)
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return
            if path == "/adicoes/chatgpt/config":
                try:
                    self._send_json(chatgpt_assist.public_config())
                except Exception as error:
                    self._send_json({"ok": False, "message": str(error)}, code=500)
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if not path.startswith("/adicoes/"):
                return super().do_POST()
            try:
                payload = self._read_json_body()
                if path == "/adicoes/conteudo":
                    result = additions._save_content(payload)
                elif path == "/adicoes/preparar-arquivo":
                    result = additions._download_source(additions._normalize(payload.get("job_id")), manager)
                elif path == "/adicoes/criar-rascunho":
                    result = additions._create_or_resume_draft(
                        additions._normalize(payload.get("job_id")),
                        str(payload.get("confirmation", "") or ""),
                    )
                elif path == "/adicoes/publicar":
                    result = additions._publish(
                        additions._normalize(payload.get("job_id")),
                        str(payload.get("confirmation", "") or ""),
                    )
                elif path == "/adicoes/resetar":
                    result = additions._reset_job(additions._normalize(payload.get("job_id")))
                elif path == "/adicoes/sincronizar":
                    additions._sync_approved()
                    result = additions._snapshot()
                    result["approved_total"] = len(additions.list_approved_additions())
                    result["message"] = (
                        f"{result['approved_total']} aprovação(ões) de cadastro novo encontrada(s); "
                        f"{result['total']} job(s) materializado(s)."
                    )
                elif path == "/adicoes/chatgpt/config":
                    result = chatgpt_assist.save_conversation_url(
                        str(payload.get("conversation_url", "") or "")
                    )
                elif path == "/adicoes/chatgpt/abrir":
                    result = chatgpt_assist.open_for_job(
                        additions._normalize(payload.get("job_id"))
                    )
                elif path == "/adicoes/chatgpt/importar-texto":
                    result = chatgpt_assist.import_text(
                        additions._normalize(payload.get("job_id")),
                        str(payload.get("text", "") or ""),
                    )
                elif path == "/adicoes/chatgpt/importar-imagem":
                    result = chatgpt_assist.import_latest_image(
                        additions._normalize(payload.get("job_id"))
                    )
                else:
                    self._send_json({"ok": False, "message": "Rota de adição não encontrada."}, code=404)
                    return
                self._send_json(result)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, AdditionHandler, *args, **kwargs)


def install_addition_server_integration_fix() -> None:
    global _INSTALLED, _BASE_SERVER
    if _INSTALLED:
        return
    # web.serve() instancia PTThreadingHTTPServer, não ThreadingHTTPServer.
    # A primeira implementação da aba Adicionar interceptava a classe errada,
    # deixando a UI visível sem as rotas /adicoes/* realmente registradas.
    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
