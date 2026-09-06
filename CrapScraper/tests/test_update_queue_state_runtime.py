import threading
from pathlib import Path
from types import SimpleNamespace

from app import update_queue_state_runtime as runtime


class AliveThread:
    def is_alive(self):
        return True


class Repo:
    path = Path("updates.sqlite3")

    def __init__(self):
        self.items = [
            {"job_id": "a", "state": "ready", "group": "prepared", "stage": "prepared", "product_name": "A"},
            {"job_id": "b", "state": "ready", "group": "prepared", "stage": "prepared", "product_name": "B"},
            {"job_id": "c", "state": "ready", "group": "prepared", "stage": "prepared", "product_name": "C"},
        ]

    def list(self, **kwargs):
        page = int(kwargs.get("page") or 1)
        page_size = int(kwargs.get("page_size") or 100)
        start = (page - 1) * page_size
        visible = self.items[start : start + page_size]
        return {"items": visible, "pages": 1}

    def get(self, job_id):
        return next(dict(item) for item in self.items if item["job_id"] == job_id)

    def history(self, _job_id):
        return []


def service():
    batch = SimpleNamespace(
        lock=threading.RLock(),
        thread=AliveThread(),
        cancelled=False,
        ids=["a", "b", "c"],
        position=1,
        results=[],
        state=lambda: {"running": True, "total": 3, "processed": 0, "pending": 2},
    )
    return SimpleNamespace(
        batch=batch,
        repository=Repo(),
        _with_execution=lambda item: {**item, "execution": {"allowed": True, "action": "execute", "blockers": []}},
    )


def test_batch_projects_current_and_waiting_jobs_separately():
    current, queued = runtime._batch_roles(service())
    assert current == "a"
    assert queued == {"b", "c"}


def test_queued_filter_and_counts_do_not_leave_selected_jobs_as_prepared():
    svc = service()
    payload = runtime._list(svc, {"group": "queued", "page": 1, "page_size": 5})
    assert [item["job_id"] for item in payload["items"]] == ["b", "c"]
    assert all(item["state"] == "queued" for item in payload["items"])
    assert payload["counts"]["queued"] == 2
    assert payload["counts"]["running"] == 1
    assert payload["counts"]["prepared"] == 0
    assert payload["counts"]["total"] == 3


def test_queued_item_is_not_individually_executable():
    svc = service()
    projected = runtime._project_job(svc, svc.repository.get("b"))
    assert projected["state"] == "queued"
    assert projected["execution"]["allowed"] is False
    assert projected["execution"]["blockers"][0]["code"] == "job_queued"


def test_real_worker_advances_three_jobs_and_pause_cancel_preserve_pending():
    from app.updates.batch import UpdateBatchService
    svc = service()
    entered = {key: threading.Event() for key in "abc"}
    release = {key: threading.Event() for key in "abc"}

    def execute(job_id):
        job = next(row for row in svc.repository.items if row["job_id"] == job_id)
        job.update(state="running", group="running")
        entered[job_id].set()
        assert release[job_id].wait(5)
        job.update(state="success", group="success")
        return {"ok": True, "job_id": job_id}

    svc.batch = UpdateBatchService(SimpleNamespace(execute=execute))
    try:
        svc.batch.start(list("abc"))
        assert entered["a"].wait(5)
        first = runtime._list(svc)
        assert first["counts"] == {"total": 3, "prepared": 0, "queued": 2, "running": 1, "success": 0, "error": 0}
        svc.batch.pause()
        assert runtime._list(svc, {"group": "queued"})["total"] == 2
        release["a"].set()
        svc.batch.resume()
        assert entered["b"].wait(5)
        second = runtime._list(svc)
        assert second["counts"]["queued"] == 1
        assert second["counts"]["running"] == 1
        assert second["counts"]["success"] == 1
        release["b"].set()
        assert entered["c"].wait(5)
        release["c"].set()
        svc.batch.thread.join(5)
        final = runtime._list(svc)
        assert final["counts"]["queued"] == final["counts"]["running"] == 0
        assert final["counts"]["success"] == 3
    finally:
        for event in release.values():
            event.set()
        svc.batch.cancel()
        svc.batch.thread.join(5)


def test_cancel_releases_only_pending_jobs():
    svc = service()
    svc.repository.items[0].update(state="running", group="running")
    svc.batch.cancelled = True
    result = runtime._list(svc)
    assert result["counts"]["running"] == 1
    assert result["counts"]["prepared"] == 2
    assert result["counts"]["queued"] == 0
