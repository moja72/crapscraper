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
