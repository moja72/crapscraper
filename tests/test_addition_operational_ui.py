from __future__ import annotations

from pathlib import Path

import app.addition_operational_ui_policy as policy


def _seed_job(job_id: str = "add-test") -> None:
    now = "2026-08-21T00:00:00+00:00"
    with policy.additions._db() as connection:
        connection.execute(
            """
            INSERT INTO addition_jobs (
                job_id, comparison_item_id, state, kind, source_name, source_version,
                source_product_url, source_official_url, title, created_at, updated_at
            ) VALUES (?, ?, 'awaiting_content', 'plugin', 'Produto Teste', '1.2.3',
                      'https://example.test/item', '', 'Produto Teste', ?, ?)
            """,
            (job_id, "comparison-test", now, now),
        )


def test_operational_schema_migrates_existing_addition_database(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(policy.additions, "_DB_PATH", tmp_path / "addition_jobs.sqlite3")
    _seed_job()
    policy._ensure_schema()

    with policy.additions._db() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(addition_jobs)")}
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert {"queue_state", "attempts", "current_step", "execution_logs", "desenvolvedor", "site_oficial"} <= columns
    assert "addition_attempt_history" in tables
    assert "addition_queue_runtime" in tables


def test_attempt_history_survives_job_completion(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(policy.additions, "_DB_PATH", tmp_path / "addition_jobs.sqlite3")
    _seed_job()
    policy._ensure_schema()

    attempt_id = policy._create_attempt("add-test")
    policy._update_operation(
        "add-test",
        queue_state="completed",
        current_step="completed",
        progress=100,
        status_message="Concluído",
    )
    policy._finish_attempt("add-test", "completed", result="Concluído")

    with policy.additions._db() as connection:
        row = connection.execute("SELECT * FROM addition_attempt_history WHERE attempt_id=?", (attempt_id,)).fetchone()
        job = connection.execute("SELECT active_attempt_id, queue_state FROM addition_jobs WHERE job_id='add-test'").fetchone()

    assert row["status"] == "completed"
    assert row["finished_at"]
    assert job["active_attempt_id"] == 0
    assert job["queue_state"] == "completed"


def test_restart_marks_inflight_addition_as_interrupted(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(policy.additions, "_DB_PATH", tmp_path / "addition_jobs.sqlite3")
    _seed_job()
    policy._ensure_schema()
    policy._create_attempt("add-test")
    policy._update_operation("add-test", queue_state="executing", current_step="draft", progress=90)
    policy._set_queue_runtime("running")

    policy._recover_interrupted_state()

    job = policy._job_snapshot("add-test")
    runtime = policy._queue_runtime()
    with policy.additions._db() as connection:
        history = connection.execute("SELECT status, finished_at FROM addition_attempt_history ORDER BY attempt_id DESC LIMIT 1").fetchone()

    assert job["queue_state"] == "interrupted"
    assert job["active_attempt_id"] == 0
    assert runtime["status"] == "paused"
    assert history["status"] == "interrupted"
    assert history["finished_at"]


def test_operational_policy_reuses_final_addition_flow() -> None:
    source = Path("app/addition_operational_ui_policy.py").read_text(encoding="utf-8")
    assert "list_approved_additions" in source
    assert "simple._run_two_chats(job_id)" in source
    assert "full_creation._ensure_download_and_prices(job_id, manager)" in source
    assert "full_creation._create_complete_draft(job_id)" in source
    assert "full_creation._publish_complete(job_id)" in source
    assert "addition_attempt_history" in source
    assert "addition_queue_runtime" in source


def test_addition_ui_matches_operational_sections_without_mutation_observer() -> None:
    script = Path("app/static/addition_operational_ui.js").read_text(encoding="utf-8")
    for label in ("Resumo das adições", "Preparação", "Fila de adições", "Histórico de adições", "Log técnico da sessão"):
        assert label in script
    assert "/adicoes/operacoes?scope=overview" in script
    assert "/adicoes/fila/adicionar" in script
    assert "/adicoes/fila/retry" in script
    assert "/adicoes/fila/recuperar" in script
    assert "MutationObserver" not in script
    assert "setInterval(poll,3000)" in script


def test_legacy_addition_renderers_are_suppressed_but_backend_is_preserved() -> None:
    policy_source = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")
    workflow = Path("app/new_product_workflow_policy.py").read_text(encoding="utf-8")
    one_click = Path("app/addition_one_click_policy.py").read_text(encoding="utf-8")
    assert "data-new-product-workflow" in policy_source
    assert "data-addition-one-click" in policy_source
    assert 'path == "/adicoes/conteudo"' in workflow
    assert 'path == "/adicoes/automatico"' in one_click


def test_processes_bridge_uses_persisted_addition_processes() -> None:
    script = Path("app/static/addition_processes_bridge.js").read_text(encoding="utf-8")
    assert "/adicoes/operacoes?scope=processes" in script
    assert "#cs_processes_body" in script
    assert "crapscraper.process.history.v1" in script
