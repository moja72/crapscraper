from pathlib import Path
from types import SimpleNamespace

from app import addition_sort_runtime as runtime


class Repo:
    path = Path("additions.sqlite3")

    def __init__(self):
        self.items = [
            {"job_id": "b", "product_name": "Beta", "created_at": "2026-09-04T10:00:00"},
            {"job_id": "a", "product_name": "Alpha", "created_at": "2026-09-06T10:00:00"},
            {"job_id": "c", "product_name": "Charlie", "created_at": "2026-09-05T10:00:00"},
        ]

    def list(self, query="", group="", stage="", page=1, page_size=100):
        start = (page - 1) * page_size
        items = self.items[start : start + page_size]
        return {
            "items": list(items),
            "pages": 1,
            "counts": {"total": 3, "prepared": 3, "running": 0, "success": 0, "error": 0},
        }


def service():
    return SimpleNamespace(
        repository=Repo(),
        batch=SimpleNamespace(state=lambda: {"running": False}),
    )


def test_default_sort_is_most_recent_first():
    payload = runtime._list(service(), {"page": 1, "page_size": 5})
    assert [item["job_id"] for item in payload["items"]] == ["a", "c", "b"]
    assert payload["sort_by"] == "date"
    assert payload["sort_order"] == "desc"


def test_name_sort_matches_update_queue_contract():
    payload = runtime._list(service(), {"sort_by": "name", "sort_order": "asc", "page": 1, "page_size": 5})
    assert [item["product_name"] for item in payload["items"]] == ["Alpha", "Beta", "Charlie"]


def test_invalid_sort_is_rejected():
    try:
        runtime._list(service(), {"sort_by": "unknown"})
    except ValueError as error:
        assert "ordenação" in str(error).lower()
    else:
        raise AssertionError("sort inválido deveria falhar")
