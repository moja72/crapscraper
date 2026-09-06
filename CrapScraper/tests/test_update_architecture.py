from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_update_has_single_execution_request_owner_and_central_polling():
    scripts = ROOT / "app/static/js"
    update = (scripts / "update.js").read_text(encoding="utf-8")
    assert 'polling.register("update-state"' in update
    owners = [p.name for p in scripts.glob("*.js") if 'await post(executionOf(job).action===' in p.read_text(encoding="utf-8")]
    assert owners == ["update.js"]
    assert "pendingExecutions.has(id)" in update
    assert "MutationObserver" not in (scripts / "update-individual-feedback.js").read_text(encoding="utf-8")

def test_batch_dispatches_through_the_modular_service():
    from app.updates.service import UpdateService
    from app.updates.executor import UpdateExecutor
    assert UpdateService.__module__ == "app.updates.service"
    assert UpdateExecutor.__module__ == "app.updates.executor"
    source = (ROOT / "app/updates/service.py").read_text(encoding="utf-8")
    assert "self.batch.execute_job = self._execute_batch_job" in source
    assert "return self.retry(job_id)" in source
