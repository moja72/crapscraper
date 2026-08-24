from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import app.operations.runtime as runtime
import app.web as web
from app.operations.models import JobState, utc_now_iso


_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_SERVER: Callable[..., Any] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "queue_standardization_v1.js"


def _clean_job_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item or "").strip() for item in value if str(item or "").strip()))


def _cancel_selected_updates(job_ids: list[str]) -> dict[str, Any]:
    """Cancela apenas jobs ainda enfileirados da lista de atualização ativa."""
    with runtime._LOCK:
        active = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        now = utc_now_iso()
        canceled = 0
        ignored = 0
        for job_id in job_ids:
            job = runtime._JOBS.get(job_id)
            if job is None:
                ignored += 1
                continue
            if getattr(job, "queue_name", "default") != active or job.state != JobState.QUEUED:
                ignored += 1
                continue
            job.canceled_at = now
            job.queue_position = 0
            job.set_state(JobState.CANCELED, "Cancelado manualmente na seleção da fila")
            canceled += 1
        runtime._persist()
        return {
            "ok": True,
            "canceled": canceled,
            "ignored": ignored,
            "queue": runtime.queue_snapshot(),
        }


def _clear_completed_update_queue() -> dict[str, Any]:
    """Retira concluídos da lista visual sem apagar o histórico operacional."""
    with runtime._LOCK:
        active = str(runtime._QUEUE_CONTROL.get("active_queue") or "default")
        removed = 0
        for job in runtime._JOBS.values():
            if getattr(job, "queue_name", "default") != active or job.state != JobState.COMPLETED:
                continue
            job.queue_name = ""
            job.queue_position = 0
            job.queued_at = ""
            removed += 1
        runtime._persist()
        return {
            "ok": True,
            "removed": removed,
            "queue": runtime.queue_snapshot(),
        }


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-queue-standardization-v1>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    class QueueStandardizationHandler(handler_class):
        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path or "/"
            if path not in {
                "/atualizacoes/fila/cancelar-selecionados",
                "/atualizacoes/fila/limpar-concluidos",
            }:
                return super().do_POST()

            try:
                size = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(size) if size > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}") if raw else {}
                if not isinstance(payload, dict):
                    payload = {}

                if path == "/atualizacoes/fila/cancelar-selecionados":
                    job_ids = _clean_job_ids(payload.get("job_ids"))
                    if not job_ids:
                        self._send_json({"ok": False, "message": "Selecione ao menos um item."}, code=400)
                        return
                    self._send_json(_cancel_selected_updates(job_ids))
                    return

                self._send_json(_clear_completed_update_queue())
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": str(error)}, code=500)

    base = _BASE_SERVER or web.PTThreadingHTTPServer
    return base(server_address, QueueStandardizationHandler, *args, **kwargs)


def install_queue_standardization_policy() -> None:
    """Instala a fila canônica compartilhada entre Atualizar e Adicionar."""
    global _INSTALLED, _BASE_RENDER, _BASE_SERVER
    if _INSTALLED:
        return

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory
    _INSTALLED = True
