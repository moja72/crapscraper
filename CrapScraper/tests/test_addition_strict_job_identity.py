from __future__ import annotations

import pytest

from app.additions import strict_job_identity_runtime as strict
from app.additions import chatgpt_playwright as legacy
from app.additions import product_content_contract_runtime as product_contract


def _job(name: str, *, job_id: str = "add-aagan", source: str = "https://example.test/aagan"):
    return {
        "job_id": job_id,
        "comparison_item_id": "cmp-aagan",
        "product_name": name,
        "kind": "theme",
        "source_url": source,
        "source_version": "3.7",
    }


def test_identity_changes_when_product_changes_even_with_same_job_id():
    aagan = strict.job_identity_fingerprint(_job("Aagan - Agency Startup WordPress Theme"))
    admin = strict.job_identity_fingerprint(_job("Admin Columns Pro JetEngine"))
    assert aagan != admin


def test_bind_identity_invalidates_stale_admin_columns_chat_and_image(monkeypatch):
    state = {
        "product_identity_fingerprint": strict.job_identity_fingerprint(_job("Admin Columns Pro JetEngine")),
        "conversation_url": "https://chatgpt.com/g/g-p-project/c/admin-columns",
        "isolated_chat_version": 1,
        "isolated_chat_fingerprint": "old",
        "content_ready": True,
        "image_ready": True,
        "image_path": "admin-columns.png",
        "image_fingerprint": "admin-image",
    }
    written = {}

    monkeypatch.setattr(legacy, "_job_state", lambda _job_id: dict(state))

    def update(_job_id, **values):
        written.update(values)
        return dict(values)

    monkeypatch.setattr(legacy, "_update_job_state", update)
    strict.bind_job_identity(_job("Aagan - Agency Startup WordPress Theme"))

    assert written["conversation_url"] == ""
    assert written["content_ready"] is False
    assert written["image_ready"] is False
    assert written["image_path"] == ""
    assert written["product_identity_product_name"] == "Aagan - Agency Startup WordPress Theme"


def test_content_for_another_product_is_rejected(monkeypatch):
    monkeypatch.setattr(
        product_contract,
        "_ORIGINAL_PARSE",
        lambda _text, _job: {
            "product_name": "Admin Columns Pro JetEngine",
            "short_description": "x" * 400,
            "content": "<p>Um.</p><p>Dois.</p>",
            "categories": ["Plugin"],
            "tags": [],
            "developer": "Example",
            "official_url": "https://example.test",
        },
    )

    with pytest.raises(legacy.ChatGPTPlaywrightError, match="outro produto"):
        strict.strict_parse_content_response("{}", _job("Aagan - Agency Startup WordPress Theme"))


def test_matching_product_content_is_kept_for_current_job(monkeypatch):
    expected = "Aagan - Agency Startup WordPress Theme"
    monkeypatch.setattr(
        product_contract,
        "_ORIGINAL_PARSE",
        lambda _text, _job: {
            "product_name": expected,
            "short_description": "Descrição " + ("comercial " * 45),
            "content": "<p>Um.</p><p>Dois.</p>",
            "categories": ["Outra"],
            "tags": ["tag antiga"],
            "developer": "Example",
            "official_url": "https://example.test",
        },
    )
    result = strict.strict_parse_content_response("{}", _job(expected))
    assert result["product_name"] == expected
    assert result["categories"] == ["Tema"]
    assert result["tags"] == []
