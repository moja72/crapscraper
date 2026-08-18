from __future__ import annotations

import base64
from pathlib import Path

import app.addition_workflow as additions


def _decision() -> dict[str, str]:
    return {
        "comparison_item_id": "new-source-product-123",
        "source_name": "Example Forms Pro",
        "source_version": "2.4.1",
        "source_product_url": "https://ultrapackv2.com/example-forms-pro/",
        "source_official_url": "https://example.com/forms-pro/",
    }


def test_materialize_approved_addition_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(additions, "DB_PATH", tmp_path / "additions.sqlite3")
    monkeypatch.setattr(additions, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(additions, "list_approved_additions", lambda: [_decision()])

    first = additions.materialize()
    second = additions.materialize()

    assert first["created"] == 1
    assert second["created"] == 0
    assert len(second["active"]) == 1
    job = second["active"][0]
    assert job["state"] == "approved"
    assert job["source_version"] == "2.4.1"
    assert job["source_product_url"].startswith("https://ultrapackv2.com/")


def test_chatgpt_prompt_keeps_content_generation_manual() -> None:
    prompt = additions._build_prompt({
        "source_name": "Example Theme",
        "source_version": "1.2.3",
        "source_product_url": "https://source.example/theme",
        "source_official_url": "https://vendor.example/theme",
        "item_type": "theme",
    })

    assert "Example Theme" in prompt
    assert "1.2.3" in prompt
    assert "BREVE DESCRIÇÃO" in prompt
    assert "DESCRIÇÃO COMPLETA" in prompt
    assert "IMAGEM" in prompt
    assert "Não invente" in prompt
    assert "manualmente" in prompt


def test_save_content_persists_editorial_data_and_image(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(additions, "DB_PATH", tmp_path / "additions.sqlite3")
    monkeypatch.setattr(additions, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(additions, "list_approved_additions", lambda: [_decision()])
    materialized = additions.materialize()
    job_id = materialized["active"][0]["job_id"]

    zip_dir = tmp_path / "staging" / job_id
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / "example.zip"
    zip_path.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    additions._update(job_id, zip_path=str(zip_path), zip_file_name=zip_path.name, state="awaiting_content")

    fake_png = b"\x89PNG\r\n\x1a\n" + b"test-image"
    image_data = "data:image/png;base64," + base64.b64encode(fake_png).decode("ascii")
    result = additions.save_content(job_id, {
        "item_type": "plugin",
        "title": "Example Forms Pro",
        "short_description": "Descrição curta.",
        "description": "<p>Descrição completa.</p>",
        "meta_description": "Meta description",
        "tags_text": "forms, wordpress",
        "image_data": image_data,
        "image_name": "example.png",
    })

    job = result["job"]
    assert job["state"] == "content_ready"
    assert job["has_content"] is True
    assert job["has_image"] is True
    assert Path(job["image_path"]).exists()


def test_remote_filename_is_safe_and_versioned() -> None:
    name = additions._remote_file_name({
        "title": "Tema Exemplo / Premium!",
        "source_name": "",
        "source_version": "4.2.1",
    })
    assert name == "tema-exemplo-premium-v4.2.1.zip"
    assert "/" not in name
    assert len(name) <= 195


def test_period_recognizes_annual_and_lifetime() -> None:
    assert additions._period({"attributes": [{"name": "Plano", "option": "Anual"}]}) == "annual"
    assert additions._period({"attributes": [{"name": "Plano", "option": "Vitalício"}]}) == "lifetime"
