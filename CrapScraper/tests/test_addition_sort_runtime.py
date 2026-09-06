from types import SimpleNamespace
import pytest
from app import addition_sort_runtime as runtime
from app.additions.repository import AdditionRepository
from tests.addition_fakes import approval


@pytest.fixture
def service(tmp_path):
    repo = AdditionRepository(tmp_path)
    for index, name in enumerate(("Beta", "Alpha", "Charlie")):
        repo.materialize([approval(item=name)])
        repo.patch(repo.job_id(name), product_name=name,
                   created_at=f"2026-09-0{index + 1}T10:00:00")
    return SimpleNamespace(repository=repo, batch=SimpleNamespace(state=lambda: {"running": False}))


@pytest.mark.parametrize(("sort_by", "order", "names"), [
    ("date", "asc", ["Beta", "Alpha", "Charlie"]),
    ("date", "desc", ["Charlie", "Alpha", "Beta"]),
    ("name", "asc", ["Alpha", "Beta", "Charlie"]),
    ("name", "desc", ["Charlie", "Beta", "Alpha"]),
])
def test_sort_before_paginating_entire_filtered_result(service, sort_by, order, names):
    pages = [runtime._list(service, {"sort_by": sort_by, "sort_order": order,
                                    "page": page, "page_size": 1}) for page in (1, 2, 3)]
    assert [p["items"][0]["product_name"] for p in pages] == names
    assert all(p["total"] == 3 for p in pages)


def test_filters_survive_sort(service):
    result = runtime._list(service, {"query": "Alpha", "group": "prepared",
        "stage": "prepared", "sources": "plugintheme", "sort_by": "name"})
    assert [item["product_name"] for item in result["items"]] == ["Alpha"]
    assert runtime._list(service, {"sources": "ultrapackv2"})["items"] == []
    assert runtime._list(service, {"sources": "__none__"})["items"] == []


def test_invalid_sort_rejected(service):
    with pytest.raises(ValueError, match="ordenação"):
        runtime._list(service, {"sort_by": "unknown"})
    with pytest.raises(ValueError):
        runtime._list(service, {"sort_order": "bad"})
