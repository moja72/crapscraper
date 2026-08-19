from __future__ import annotations

import pytest

import app.addition_content_enrichment_policy as policy


class FakeWoo:
    def list_product_categories(self, *, page: int = 1, per_page: int = 100):
        if page > 1:
            return []
        return [
            {"id": 10, "name": "Plugins", "parent": 0},
            {"id": 20, "name": "Temas", "parent": 0},
            {"id": 30, "name": "Saúde", "parent": 20},
        ]


def test_specific_category_exact_match() -> None:
    assert policy._find_specific_category(FakeWoo(), "Saúde") == 30
    assert policy._find_specific_category(FakeWoo(), "saúde") == 30
    assert policy._find_specific_category(FakeWoo(), "Categoria inexistente") == 0


def test_requested_category_must_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(policy._CONTEXT, "category_name", "Categoria inexistente", raising=False)
    monkeypatch.setattr(policy, "_BASE_CATEGORY_ID", lambda _woo, _kind: 10)
    with pytest.raises(ValueError, match="não existe"):
        policy._patched_category_id(FakeWoo(), "plugin")
