from __future__ import annotations

import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import app.operational_reliability_policy as reliability


class _Cursor:
    def __init__(self, *, rows=None, row=None):
        self._rows = list(rows or [])
        self._row = row

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._row


class _HistoryConnection:
    def __init__(self, job):
        self.job = dict(job)
        self.inserted = []
        self.updated = []

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        if normalized.startswith("SELECT * FROM addition_jobs"):
            return _Cursor(rows=[self.job])
        if "SELECT 1 FROM addition_attempt_history" in normalized:
            return _Cursor(row=None)
        if "MAX(attempt_no)" in normalized:
            return _Cursor(row={"attempt_no": 0})
        if normalized.startswith("INSERT INTO addition_attempt_history"):
            self.inserted.append(tuple(params))
            return _Cursor()
        if normalized.startswith("UPDATE addition_jobs SET attempts"):
            self.updated.append(tuple(params))
            return _Cursor()
        raise AssertionError(normalized)


class OperationalReliabilityPolicyTests(unittest.TestCase):
    def test_missing_visual_reference_is_warning_not_fatal(self):
        emitted = []
        with patch.object(reliability, "_resolve_reference_file", return_value=None), \
             patch.object(reliability.addition_ui, "_persistent_emit", side_effect=lambda job_id, message, **kwargs: emitted.append((job_id, message, kwargs))):
            result = reliability._attach_reference_resilient(None, Path("app/static/exemplo tema.webp"), "job-1")

        self.assertTrue(result)
        self.assertTrue(emitted)
        self.assertIn("continuando", emitted[0][1].lower())

    def test_terminal_addition_error_is_backfilled_into_history(self):
        job = {
            "job_id": "add-error-1",
            "queue_state": "error",
            "operation_error": "Referência visual ausente",
            "error": "",
            "status_message": "Falhou na preparação",
            "attempts": 0,
            "current_step": "chatgpt_image",
            "progress": 35,
            "execution_logs": "[]",
            "source_name": "Produto teste",
            "title": "Produto teste",
            "source_version": "1.2.3",
            "source_product_url": "https://example.test/source",
            "source_official_url": "https://example.test/official",
            "desenvolvedor": "Dev",
            "site_oficial": "https://example.test/official",
            "kind": "theme",
            "category_name": "Tema",
            "woo_product_id": 0,
            "started_at": "2026-08-22T20:00:00+00:00",
            "created_at": "2026-08-22T19:59:00+00:00",
            "updated_at": "2026-08-22T20:01:00+00:00",
            "finished_at": "2026-08-22T20:01:00+00:00",
        }
        connection = _HistoryConnection(job)

        @contextmanager
        def fake_db():
            yield connection

        with patch.object(reliability.addition_ui, "_ensure_schema", return_value=None), \
             patch.object(reliability.additions, "_db", fake_db):
            inserted = reliability._backfill_terminal_addition_history()

        self.assertEqual(inserted, 1)
        self.assertEqual(len(connection.inserted), 1)
        params = connection.inserted[0]
        self.assertEqual(params[0], "add-error-1")
        self.assertEqual(params[2], "error")
        self.assertEqual(params[3], "Erro na preparação")
        self.assertEqual(params[7], "Referência visual ausente")

    def test_update_queue_snapshot_is_merged_into_jobs_payload(self):
        reliability._BASE_MATERIALIZE_UPDATES = lambda *args, **kwargs: []
        queued = {
            "job_id": "update-queued-1",
            "queue_type": "update",
            "queue_name": "default",
            "queue_position": 1,
            "state": "queued",
            "name": "Produto em fila",
        }
        with patch.object(reliability.update_runtime, "queue_snapshot", return_value={"queued": [queued], "executing": []}):
            result = reliability._materialize_updates_with_queue()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["job_id"], "update-queued-1")
        self.assertEqual(result[0]["state"], "queued")

    def test_frontend_fallback_has_no_polling_or_mutation_observer(self):
        script = Path("app/static/operational_reliability_v11.js").read_text(encoding="utf-8")
        self.assertIn("/atualizacoes/jobs", script)
        self.assertIn("updates_queue_jobs", script)
        self.assertNotIn("MutationObserver", script)
        self.assertNotIn("setInterval", script)


if __name__ == "__main__":
    unittest.main()
