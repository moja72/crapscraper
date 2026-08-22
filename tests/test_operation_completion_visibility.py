from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import app.operation_completion_visibility_policy as completion


def _create_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE addition_jobs (
                job_id TEXT PRIMARY KEY,
                comparison_item_id TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                queue_state TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                finished_at TEXT NOT NULL DEFAULT '',
                execution_logs TEXT NOT NULL DEFAULT '[]',
                source_name TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                source_version TEXT NOT NULL DEFAULT '',
                source_product_url TEXT NOT NULL DEFAULT '',
                source_official_url TEXT NOT NULL DEFAULT '',
                desenvolvedor TEXT NOT NULL DEFAULT '',
                site_oficial TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '',
                category_name TEXT NOT NULL DEFAULT '',
                woo_product_id INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE addition_attempt_history (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                attempt_no INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                result TEXT NOT NULL DEFAULT '',
                final_state TEXT NOT NULL DEFAULT '',
                current_step TEXT NOT NULL DEFAULT '',
                progress INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                logs TEXT NOT NULL DEFAULT '[]',
                source_name TEXT NOT NULL DEFAULT '',
                source_version TEXT NOT NULL DEFAULT '',
                source_product_url TEXT NOT NULL DEFAULT '',
                source_official_url TEXT NOT NULL DEFAULT '',
                desenvolvedor TEXT NOT NULL DEFAULT '',
                site_oficial TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT '',
                category_name TEXT NOT NULL DEFAULT '',
                woo_product_id INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT ''
            );
            """
        )
        connection.execute(
            """
            INSERT INTO addition_jobs (
                job_id, comparison_item_id, state, queue_state, attempts,
                created_at, updated_at, execution_logs, source_name,
                source_version, source_product_url, kind, woo_product_id
            ) VALUES (
                'add-1', 'comparison-1', 'completed', 'completed', 0,
                '2026-08-20T10:00:00+00:00', '2026-08-20T10:05:00+00:00',
                '["produto publicado"]', 'Produto de teste', '1.2.3',
                'https://example.com/item', 'plugin', 123
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_backfill_completed_addition_history_is_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "additions.sqlite3"
    _create_test_db(db_path)

    @contextmanager
    def fake_db():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    monkeypatch.setattr(completion.additions, "_db", fake_db)
    monkeypatch.setattr(completion.addition_operational, "_ensure_schema", lambda: None)

    assert completion._backfill_completed_addition_history() == 1
    assert completion._backfill_completed_addition_history() == 0

    with fake_db() as connection:
        row = connection.execute(
            "SELECT * FROM addition_attempt_history WHERE job_id='add-1'"
        ).fetchone()

    assert row is not None
    assert row["status"] == "completed"
    assert row["result"] == "Concluído"
    assert row["progress"] == 100
    assert row["woo_product_id"] == 123
    assert row["source_name"] == "Produto de teste"


def test_visibility_script_is_event_driven_and_has_no_dom_observer_loop():
    script = (Path(__file__).parents[1] / "app" / "static" / "operation_completion_visibility.js").read_text(encoding="utf-8")

    assert 'fetch("/operacoes/conclusoes"' in script
    assert "setInterval(" not in script
    assert "MutationObserver" not in script
    assert ".observe(" not in script
    assert "completionSignature" in script
    assert "scheduleDecorate" in script
    assert "tab_btn_comparacao" in script
    assert "tab_btn_atualizacoes" in script
    assert "tab_btn_adicoes" in script
    assert "Já adicionado" in script
    assert "Já atualizado" in script


def test_panel_patch_removes_history_loading_before_final_render():
    source = (Path(__file__).parents[1] / "app" / "panel_layout_standardization_policy.py").read_text(encoding="utf-8")

    assert 'state.loading.delete(scope);renderHistory();state.historyDirty=false' in source
    assert "install_operation_completion_visibility_policy" in source
