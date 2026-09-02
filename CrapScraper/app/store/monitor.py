from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.store.models import StoreError


class StoreMonitorService:
    terminal_states = frozenset({"completed", "already_updated", "no_match", "error", "blocked", "rolled_back", "rollback_required"})
    def __init__(self, repository, queue, updates):
        self.repository = repository
        self.queue = queue
        self.updates = updates
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.worker = None
        self.interval = max(5, int(os.getenv("SCRAPER_WORDPRESS_MANUAL_POLL_SECONDS", "30")))
        if self.repository.monitor()["enabled"] and self.queue.configured:
            self.start_background()

    def snapshot(self):
        value = self.repository.monitor()
        value["configured"] = bool(self.queue.configured)
        value["history"] = self.repository.history()
        value["interval_seconds"] = self.interval
        value["worker_alive"] = bool(self.worker and self.worker.is_alive())
        return value

    def enable(self, enabled):
        if enabled and not self.queue.configured:
            raise ValueError("URL/segredo do monitor WordPress não estão configurados")
        value = self.repository.patch_monitor(
            enabled=1 if enabled else 0,
            state="idle",
            stage="monitoring" if enabled else "disabled",
            next_check_at=self._next() if enabled else "",
            current_error=None,
        )
        if enabled:
            if self.worker and self.worker.is_alive() and self.stop_event.is_set():
                self.worker.join(timeout=1)
            self.start_background()
        else:
            self.stop_event.set()
        return value

    def _next(self):
        return (datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()

    @staticmethod
    def _line(message):
        return f"[{datetime.now().astimezone().strftime('%H:%M:%S')}] {message}"

    def start_background(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()

        def loop():
            while not self.stop_event.wait(self.interval):
                if not self.repository.monitor()["enabled"]:
                    break
                self.run()
                self.repository.patch_monitor(next_check_at=self._next())

        self.worker = threading.Thread(target=loop, name="store-wordpress-monitor", daemon=True)
        self.worker.start()

    def _job(self, product_id):
        result = self.updates.list({"query": str(product_id), "page_size": 100})
        return next((item for item in result["items"] if int(item.get("woo_product_id") or 0) == int(product_id)), None)

    def _progress(self, logs, message, **fields):
        line = self._line(message)
        logs.append(line)
        self.repository.monitor_progress(line, **fields)

    @staticmethod
    def _report_payload(request_id, product_id, *, state, stage, message, job=None, attempt_id=""):
        job = job or {}
        current = str(job.get("current_version") or "")
        target = str(job.get("source_version") or "")
        return {
            "request_id": str(request_id), "woo_product_id": int(product_id),
            "operation_id": str(attempt_id or request_id),
            "status": state, "state": state, "stage": stage, "message": str(message),
            "job_id": str(job.get("job_id") or ""), "attempt_id": str(attempt_id or ""),
            "source": str(job.get("source_name") or ""),
            "current_version": current, "target_version": target,
            "previous_version": current, "new_version": target,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _report(self, request_id, product_id, *, state, stage, message, job=None, attempt_id=""):
        payload = self._report_payload(request_id, product_id, state=state, stage=stage, message=message, job=job, attempt_id=attempt_id)
        wire_payload = dict(payload)
        wire_payload.pop("request_id", None)
        self.queue.report(request_id, **wire_payload)
        self.repository.save_request(request_id, **wire_payload)
        return payload

    def run(self, force=False):
        state = self.repository.monitor()
        if not force and not state["enabled"]:
            raise ValueError("Monitor WordPress desativado")
        if not self.lock.acquire(blocking=False):
            return {"ok": True, "already_running": True, "monitor": self.snapshot()}
        run_id = "store-" + uuid.uuid4().hex
        logs = []
        fields = {}
        try:
            self.repository.begin_run(run_id)
            requests = self.queue.pending()
            self._progress(logs, f"{len(requests)} solicitação(ões) recebida(s).")
            if not requests:
                self._progress(logs, "Nenhuma solicitação pendente.")
            failed = None
            for request in requests:
                request_id = str(request.get("request_id") or "")
                product_id = int(request.get("product_id") or 0)
                fields = {
                    "product": str(request.get("product_name") or request.get("product") or f"Woo #{product_id}"),
                    "woo_product_id": product_id,
                    "request_state": "consulting",
                }
                self._progress(logs, f"Consultando pedido Woo #{product_id}.", current_product=fields["product"], woo_product_id=product_id, request_state="checking")
                previous = self.repository.request(request_id)
                if previous and previous.get("state") in self.terminal_states:
                    replay_job = {"job_id": previous.get("job_id"), "source_name": previous.get("source"), "current_version": previous.get("current_version"), "source_version": previous.get("target_version")}
                    self._report(request_id, product_id, state=previous["state"], stage=previous.get("stage") or "completed", message=previous.get("message") or "Solicitação já processada.", job=replay_job, attempt_id=previous.get("attempt_id"))
                    self._progress(logs, f"Woo #{product_id}: request_id já processado; resposta terminal reapresentada.", request_state=previous["state"])
                    continue
                try:
                    resolution = self.updates.resolve_manual_request(product_id)
                    job = resolution.get("item")
                    if not job:
                        message = str(resolution.get("message") or "Produto sem aprovação de atualização materializada.")
                        self._report(request_id, product_id, state="no_match", stage="checked", message=message)
                        fields["request_state"] = "no_match"
                        self._progress(logs, f"Woo #{product_id}: nenhum job aprovado.", request_state="no_match")
                        continue
                    fields.update(current_version=job.get("current_version", ""), found_version=job.get("source_version", ""), source=job.get("source_name", ""))
                    self._progress(logs, f"Woo #{product_id}: fonte aprovada consultada ao vivo; alvo {fields['found_version']}.", current_version=fields["current_version"], found_version=fields["found_version"], source=fields["source"], request_state="checked")
                    if resolution.get("state") == "already_updated":
                        message = str(resolution.get("message") or f"Produto já estava atualizado para a versão {fields['current_version']}.")
                        self._report(request_id, product_id, state="already_updated", stage="completed", message=message, job=job)
                        fields["request_state"] = "already_updated"
                        self._progress(logs, f"Woo #{product_id}: já atualizado; nenhuma execução necessária.", request_state="already_updated")
                        continue
                    fields["request_state"] = "executing"
                    self._report(request_id, product_id, state="update_available", stage="checked", message=str(resolution.get("message") or "Atualização encontrada."), job=job)
                    self._progress(logs, f"Woo #{product_id}: encaminhado ao UpdateExecutor canônico.", current_product=fields["product"], woo_product_id=product_id, current_version=fields["current_version"], found_version=fields["found_version"], source=fields["source"], request_state="executing")
                    self._report(request_id, product_id, state="executing", stage="executing", message="Executando pelo UpdateExecutor canônico.", job=job)
                    result = self.updates.execute(job["job_id"])
                    already = bool(result.get("already_current"))
                    status = "already_updated" if already else "completed" if result.get("ok") else "error"
                    fields["request_state"] = status
                    message = (f"Produto já estava atualizado para a versão {job.get('source_version', '')}." if already else "Atualização concluída." if result.get("ok") else str(result.get("error", {}).get("message") or "Falha na atualização."))
                    self._report(request_id, product_id, state=status, stage="completed" if result.get("ok") else str(result.get("error", {}).get("stage") or "failed"), message=message, job=job, attempt_id=result.get("attempt_id", ""))
                    self._progress(logs, f"Woo #{product_id}: {status}.", request_state=status)
                    if not result.get("ok"):
                        failed = result.get("error") or {"message": message}
                except Exception as exc:
                    error = StoreError(message=str(exc), technical_message=repr(exc), code="request_failed", operation="monitor", stage="processing").to_dict()
                    failed = error
                    fields["request_state"] = "error"
                    try:self._report(request_id, product_id, state="error", stage="failed", message=error["message"])
                    except Exception:pass
                    self._progress(logs, f"Woo #{product_id}: erro real: {error['message']}", request_state="error")
            self.repository.finish_run(run_id, "error" if failed else "success", logs, failed, **fields)
            if state["enabled"]:
                self.repository.patch_monitor(next_check_at=self._next())
            return {"ok": True, "run_id": run_id, "processed": len(requests), "monitor": self.snapshot()}
        except Exception as exc:
            error = StoreError(message=str(exc), technical_message=repr(exc), code="monitor_failed", operation="monitor", stage="polling").to_dict()
            logs.append(self._line(error["message"]))
            self.repository.finish_run(run_id, "error", logs, error, **fields)
            return {"ok": False, "run_id": run_id, "error": error, "monitor": self.snapshot()}
        finally:
            self.lock.release()
