from app.store.monitor import StoreMonitorService
from app.store.repository import StoreRepository


class Queue:
    configured = True

    def __init__(self, rows=None):
        self.reports = []
        self.rows = rows if rows is not None else [{"request_id": "r1", "product_id": 42, "product_name": "Demo"}]

    def pending(self):
        return self.rows

    def report(self, request_id, **payload):
        self.reports.append((request_id, payload))
        return {"ok": True}


class Updates:
    def __init__(self, state="update_available", target="2", ok=True):
        self.calls = []
        self.state = state
        self.target = target
        self.ok = ok

    def resolve_manual_request(self, product_id):
        return {
            "state": self.state,
            "message": "Produto já estava atualizado." if self.state == "already_updated" else "Atualização encontrada.",
            "item": {
                "job_id": "j1", "woo_product_id": product_id, "source_name": "UltraPackV2",
                "current_version": "1", "source_version": self.target,
            },
        }

    def execute(self, job_id):
        self.calls.append(job_id)
        if self.ok:
            return {"ok": True, "attempt_id": "j1-a2"}
        return {"ok": False, "attempt_id": "j1-a2", "error": {"message": "falha real", "stage": "installing"}}


def test_enable_disable_and_restart(tmp_path):
    repo = StoreRepository(tmp_path)
    service = StoreMonitorService(repo, Queue(), Updates())
    assert service.enable(True)["enabled"]
    assert StoreRepository(tmp_path).monitor()["enabled"]
    assert not service.enable(False)["enabled"]


def test_run_refreshes_target_and_delegates_to_canonical_executor(tmp_path):
    queue, updates = Queue(), Updates(target="4.2.3")
    service = StoreMonitorService(StoreRepository(tmp_path), queue, updates)
    result = service.run(force=True)
    assert result["ok"] and updates.calls == ["j1"]
    assert [payload["status"] for _, payload in queue.reports] == ["update_available", "executing", "completed"]
    assert queue.reports[-1][1]["target_version"] == "4.2.3"
    assert queue.reports[-1][1]["attempt_id"] == "j1-a2"
    assert service.snapshot()["history"][0]["result"] == "success"


def test_already_updated_is_terminal_healthy_noop_and_next_poll_works(tmp_path):
    queue, updates = Queue(), Updates(state="already_updated", target="1")
    service = StoreMonitorService(StoreRepository(tmp_path), queue, updates)
    service.run(force=True)
    service.run(force=True)
    assert updates.calls == []
    assert [payload["status"] for _, payload in queue.reports] == ["already_updated", "already_updated"]
    snapshot = service.snapshot()
    assert snapshot["state"] == "success" and snapshot["error"] is None
    assert snapshot["current_product"] == "" and snapshot["woo_product_id"] == 0


def test_same_request_id_is_not_executed_twice(tmp_path):
    queue, updates = Queue(), Updates()
    service = StoreMonitorService(StoreRepository(tmp_path), queue, updates)
    service.run(force=True)
    service.run(force=True)
    assert updates.calls == ["j1"]
    assert queue.reports[-1][1]["status"] == "completed"


def test_new_request_id_for_same_product_can_execute_new_target(tmp_path):
    queue, updates = Queue(), Updates(target="4.2.2")
    service = StoreMonitorService(StoreRepository(tmp_path), queue, updates)
    service.run(force=True)
    queue.rows = [{"request_id": "r2", "product_id": 42, "product_name": "Demo"}]
    updates.target = "4.2.3"
    service.run(force=True)
    assert updates.calls == ["j1", "j1"]
    assert service.repository.request("r1")["target_version"] == "4.2.2"
    assert service.repository.request("r2")["target_version"] == "4.2.3"


def test_real_failure_is_error_but_monitor_can_poll_again(tmp_path):
    queue, updates = Queue(), Updates(ok=False)
    service = StoreMonitorService(StoreRepository(tmp_path), queue, updates)
    service.run(force=True)
    assert queue.reports[-1][1]["status"] == "error"
    assert service.snapshot()["state"] == "error"
    queue.rows = []
    service.run(force=True)
    assert service.snapshot()["state"] == "success" and service.snapshot()["error"] is None


def test_no_match_preserves_normalized_external_contract(tmp_path):
    class NoMatch(Updates):
        def resolve_manual_request(self, product_id):
            return {"state": "no_match", "message": "Produto sem aprovação de atualização materializada."}

    queue = Queue()
    service = StoreMonitorService(StoreRepository(tmp_path), queue, NoMatch())
    service.run(force=True)
    assert queue.reports[0][1]["status"] == "no_match"
    assert queue.reports[0][1]["woo_product_id"] == 42
    assert queue.reports[0][1]["state"] == "no_match"


def test_concurrent_run_is_not_duplicated(tmp_path):
    service = StoreMonitorService(StoreRepository(tmp_path), Queue(), Updates())
    service.lock.acquire()
    assert service.run(force=True)["already_running"]
    service.lock.release()


def test_new_run_clears_current_error(tmp_path):
    repo = StoreRepository(tmp_path)
    repo.patch_monitor(current_error={"message": "old"})
    service = StoreMonitorService(repo, Queue(), Updates())
    service.run(force=True)
    assert service.snapshot()["error"] is None and service.snapshot()["history"]
