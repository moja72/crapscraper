from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

from app.store.models import StoreError


class StoreMonitorService:
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
            for request in requests:
                request_id = str(request.get("request_id") or "")
                product_id = int(request.get("product_id") or 0)
                fields = {
                    "product": str(request.get("product_name") or request.get("product") or f"Woo #{product_id}"),
                    "woo_product_id": product_id,
                    "request_state": "consulting",
                }
                self._progress(logs, f"Consultando pedido Woo #{product_id}.", current_product=fields["product"], woo_product_id=product_id, request_state="consulting")
                job = self._job(product_id)
                if not job:
                    self.queue.report(request_id, status="no_match", message="Produto sem aprovação de atualização materializada.")
                    fields["request_state"] = "no_match"
                    self._progress(logs, f"Woo #{product_id}: nenhum job aprovado.", request_state="no_match")
                    continue
                fields.update(current_version=job.get("current_version", ""), found_version=job.get("source_version", ""), source=job.get("source_name", ""), request_state="executing")
                self._progress(logs, f"Woo #{product_id}: encaminhado ao UpdateExecutor canônico.", current_product=fields["product"], woo_product_id=product_id, current_version=fields["current_version"], found_version=fields["found_version"], source=fields["source"], request_state="executing")
                self.queue.report(request_id, status="executing", job_id=job["job_id"], source=job["source_name"], previous_version=job.get("current_version", ""), new_version=job.get("source_version", ""), message="Executando pelo UpdateExecutor canônico.")
                result = self.updates.execute(job["job_id"])
                status = "completed" if result.get("ok") else "error"
                fields["request_state"] = status
                message = "Atualização concluída." if result.get("ok") else str(result.get("error", {}).get("message") or "Falha na atualização.")
                self.queue.report(request_id, status=status, job_id=job["job_id"], source=job["source_name"], previous_version=job.get("current_version", ""), new_version=job.get("source_version", ""), message=message)
                self._progress(logs, f"Woo #{product_id}: {status}.", request_state=status)
            self.repository.finish_run(run_id, "success", logs, **fields)
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
