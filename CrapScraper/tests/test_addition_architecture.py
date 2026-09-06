from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_addition_has_single_execution_request_owner():
    scripts = ROOT / "app/static/js"
    owners = [p.name for p in scripts.glob("*.js") if 'post(endpoint,{job_id:id})' in p.read_text(encoding="utf-8")]
    assert owners == ["add.js"]
    assert 'polling.register("addition-state"' in (scripts / "add.js").read_text(encoding="utf-8")
    assert "window.fetch =" not in (scripts / "add-sort-controls.js").read_text(encoding="utf-8")

def test_modular_addition_graph_owns_source_creative_and_publication():
    from app.additions.executor import AdditionExecutor
    from app.additions.repository import AdditionRepository
    assert AdditionExecutor.__module__ == "app.additions.executor"
    assert AdditionRepository.__module__ == "app.additions.repository"
    source = (ROOT / "app/additions/executor.py").read_text(encoding="utf-8")
    for owner in ("self.sources.source(job)", "self.content.generate(job)", "self.images.generate(job)",
                  "self.store.create_parent(", "self.store.validate("):
        assert owner in source
    assert "autoscraper.bat" not in source
