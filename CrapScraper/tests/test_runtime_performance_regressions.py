from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from app.comparison import fast_view
from app.comparison import performance_runtime as comparison_runtime
from app.updates.fast_transaction import _authoritative_put
from app.updates.manual_discovery import discover_safe_update
from app.updates import performance_runtime as update_runtime


def test_manual_discovery_finds_aoki_by_exact_official_url(tmp_path):
    catalog = tmp_path / "slots" / "default" / "ultrapackv2" / "theme" / "catalog.csv"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        "nome_produto,versao_produto,link_produto,pagina_oficial,categoria_nome\n"
        "Aoki - Creative Design Agency Theme,1.9,https://www.ultrapackv2.com/item/aoki/,https://themeforest.net/item/aoki/123,Theme\n",
        encoding="utf-8",
    )
    product = {
        "id": 96391,
        "name": "Aoki – Creative Design Agency Theme",
        "meta_data": [{"key": "site_oficial", "value": "https://themeforest.net/item/aoki/123/"}],
    }
    result = discover_safe_update(product, "1.8", data_dir=tmp_path)
    assert result["state"] == "update_available"
    assert result["approval"]["woo_product_id"] == 96391
    assert result["approval"]["source_version"] == "1.9"
    assert result["approval"]["relationship_state"] == "safe_auto"


def test_manual_discovery_does_not_auto_authorize_name_only(tmp_path):
    catalog = tmp_path / "ultrapackv2.csv"
    catalog.write_text(
        "nome_produto,versao_produto,link_produto,pagina_oficial,categoria_nome\n"
        "Aoki Creative Design Agency Theme,1.9,https://www.ultrapackv2.com/item/aoki/,https://themeforest.net/item/other/999,Theme\n",
        encoding="utf-8",
    )
    product = {"id": 96391, "name": "Aoki Creative Design Agency Theme", "meta_data": []}
    result = discover_safe_update(product, "1.8", data_dir=tmp_path)
    assert result["state"] == "relationship_required"
    assert "approval" not in result


def test_fast_view_overlays_live_decision_without_rebuilding(monkeypatch):
    row = {
        "comparison_item_id": "aoki",
        "status": "update_available",
        "decision": "pending",
        "site_id": "96391",
        "site_name": "Aoki",
        "source_name": "Aoki",
        "site_version": "1.8",
        "source_version": "1.9",
        "match_candidate_count": 0,
        "match_score": 100,
    }
    calls = []
    monkeypatch.setattr(fast_view.matching, "_get_cached_comparison", lambda *a, **kw: calls.append(kw.get("force")) or {"rows": [row], "total_rows": 1})
    monkeypatch.setattr(fast_view.decisions, "get_decisions_map", lambda _ids: {"aoki": {"decision": "approve_update", "decision_label": "Aprovar atualização", "queue_type": "update"}})
    monkeypatch.setattr(fast_view.decisions, "get_decision_summary", lambda: {"counts": {"approve_update": 1}})
    result = fast_view.build_comparison_payload(source_path=Path("source.csv"), site_path=Path("site.csv"), decision="approve_update", force=False)
    assert calls == [False]
    assert result["pagination"]["total_rows"] == 1
    assert result["rows"][0]["decision"] == "approve_update"


def test_saved_decision_consumes_only_next_forced_rebuild(monkeypatch, tmp_path):
    source = tmp_path / "source.csv"; source.write_text("x\n", encoding="utf-8")
    site = tmp_path / "site.csv"; site.write_text("x\n", encoding="utf-8")
    class Repo:
        def resolve(self, value): return source if value == "source" else site
    service = SimpleNamespace(
        lock=threading.RLock(), source_id="source", site_id="site", repository=Repo(),
        _signature=((source.stat().st_mtime_ns, source.stat().st_size), (site.stat().st_mtime_ns, site.stat().st_size)),
        revision=1, last_run={}, _crapscraper_skip_next_forced_rebuild=True,
    )
    forced = []
    monkeypatch.setattr(comparison_runtime, "build_comparison_payload", lambda **kwargs: forced.append(kwargs["force"]) or {"summary": {"total_rows": 1}, "pagination": {"total_rows": 1}})
    comparison_runtime._run(service, {"force": True, "page": 1, "page_size": 5})
    comparison_runtime._run(service, {"force": True, "page": 1, "page_size": 5})
    assert forced == [False, True]


def test_update_materialization_is_not_rewritten_on_every_poll(monkeypatch):
    approvals = [{"comparison_item_id": "aoki", "updated_at": "now", "source_version": "1.9", "site_version": "1.8", "source_product_url": "https://u/aoki"}]
    monkeypatch.setattr(update_runtime.decisions, "list_approved_updates", lambda: approvals)
    class Repo:
        calls = 0
        def materialize(self, rows): self.calls += 1; return {"created": 1, "total": 1}
        def count(self): return 1
    service = SimpleNamespace(lock=threading.RLock(), repository=Repo())
    first = update_runtime._materialize(service)
    second = update_runtime._materialize(service)
    assert first["cached"] is False and second["cached"] is True
    assert service.repository.calls == 1


def test_batch_runs_eligible_jobs_and_skips_stale_selection():
    jobs = {
        "good-1": {"job_id": "good-1", "product_name": "Aoki"},
        "old": {"job_id": "old", "product_name": "Antigo"},
        "good-2": {"job_id": "good-2", "product_name": "Ewebot"},
    }
    class Repo:
        def get(self, job_id): return jobs[job_id]
    class Batch:
        def start(self, ids): self.ids = list(ids); return {"running": True, "total": len(ids)}
    batch = Batch()
    service = SimpleNamespace(
        _require_execution_environment=lambda: None,
        repository=Repo(), batch=batch,
        _execution=lambda job: {"allowed": job["job_id"] != "old", "blockers": [] if job["job_id"] != "old" else [{"code": "stale", "message": "não preparado"}]},
    )
    result = update_runtime._batch_start(service, ["good-1", "old", "good-2"])
    assert batch.ids == ["good-1", "good-2"]
    assert result["queued_count"] == 2 and result["skipped_count"] == 1


def test_exact_put_response_is_authoritative():
    evidence = {
        "confirmation_status": "put_confirmed", "http_status": 200, "product_id": 94600,
        "put": {"product_id": 94600, "status": "single", "count": 1, "value": "3.2.4"},
    }
    assert _authoritative_put(evidence, 94600, "3.2.4") is True
    assert _authoritative_put(evidence, 94600, "3.2.5") is False


def test_update_selection_fix_is_loaded():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app/static/js/app.js").read_text(encoding="utf-8")
    fix = (root / "app/static/js/update-selection-fix.js").read_text(encoding="utf-8")
    assert 'import "./update-selection-fix.js"' in app
    assert "stopImmediatePropagation" in fix
    assert 'post("/api/updates/batch/start"' in fix
    assert "clearSelection" in fix
