from pathlib import Path

import app.new_product_workflow_policy as additions


def test_guess_kind_from_source_url():
    assert additions._guess_kind({"source_product_url": "https://www.ultrapackv2.com/temas/themeforest/foo/"}) == "theme"
    assert additions._guess_kind({"source_product_url": "https://www.ultrapackv2.com/plugins/codecanyon/foo/"}) == "plugin"


def test_prompt_contains_source_context():
    prompt = additions._prompt({
        "source_name": "Example Product",
        "source_version": "2.4.1",
        "source_product_url": "https://example.test/product",
        "source_official_url": "https://vendor.test/product",
        "kind": "plugin",
    })
    assert "Example Product" in prompt
    assert "2.4.1" in prompt
    assert "BREVE DESCRIÇÃO" in prompt
    assert "imagem quadrada 1:1" in prompt


def test_recalculate_state_requires_content_and_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(additions, "_DB_PATH", tmp_path / "additions.sqlite3")
    zip_path = tmp_path / "product.zip"
    zip_path.write_bytes(b"PK\x03\x04placeholder")
    now = additions._utc_now()
    with additions._db() as connection:
        connection.execute(
            """
            INSERT INTO addition_jobs (
                job_id, comparison_item_id, state, kind, source_name, title,
                short_description, description, zip_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "add-test", "comparison-test", "awaiting_content", "plugin",
                "Example", "Example", "Resumo", "Descrição", str(zip_path), now, now,
            ),
        )
    job = additions._recalculate_state("add-test")
    assert job["state"] == "ready_to_create"


def test_public_job_reports_missing_zip(tmp_path):
    job = additions._public_job({
        "state": "awaiting_content",
        "title": "Example",
        "short_description": "",
        "description": "",
        "zip_path": str(tmp_path / "missing.zip"),
        "kind": "theme",
    })
    assert job["zip_exists"] is False
    assert job["state_label"] == "Aguardando conteúdo"
