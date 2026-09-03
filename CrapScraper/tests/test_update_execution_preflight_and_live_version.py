from __future__ import annotations

from types import SimpleNamespace

from app.updates import performance_runtime as runtime


def test_execution_is_clickable_when_only_preflight_has_not_run(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_ORIGINAL_EXECUTION",
        lambda _self, _job: {
            "allowed": False,
            "action": "execute",
            "blockers": [
                {"code": "woocommerce_not_validated", "message": "WooCommerce não validado."},
                {"code": "storage_not_validated", "message": "Storage não validado."},
                {"code": "source_not_validated", "message": "Fonte não validada."},
            ],
        },
    )
    result = runtime._execution(SimpleNamespace(), {"job_id": "x"})
    assert result["allowed"] is True
    assert result["preflight_required"] is True
    assert result["blockers"] == []
    assert len(result["warnings"]) == 3


def test_real_validation_failure_still_blocks(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_ORIGINAL_EXECUTION",
        lambda _self, _job: {
            "allowed": False,
            "action": "execute",
            "blockers": [{"code": "source_unavailable", "message": "Sessão inválida."}],
        },
    )
    result = runtime._execution(SimpleNamespace(), {"job_id": "x"})
    assert result["allowed"] is False
    assert result["blockers"][0]["code"] == "source_unavailable"


def test_ensure_environment_runs_preflight_only_when_missing():
    calls = []
    service = SimpleNamespace(
        environment_validation={},
        verify_environment=lambda: calls.append("verified") or {"ok": True},
    )
    runtime._ensure_environment(service, {"ultrapackv2"})
    assert calls == ["verified"]

    service.environment_validation = {
        "woocommerce": {"ok": True},
        "storage": {"ok": True},
        "sources": {"ultrapackv2": {"ok": True}},
    }
    runtime._ensure_environment(service, {"ultrapackv2"})
    assert calls == ["verified"]


def test_live_source_version_newer_than_catalog_promotes_job():
    original = {
        "job_id": "job-1",
        "source_kind": "ultrapackv2",
        "source_version": "1.9",
        "current_version": "1.9",
    }
    refreshed = {**original, "source_version": "2.0"}

    class Repo:
        def get(self, _job_id):
            return dict(original)

        def refresh_objective(self, job_id, *, current_version, source_version):
            assert job_id == "job-1"
            assert current_version == "1.9"
            assert source_version == "2.0"
            return dict(refreshed)

    source = SimpleNamespace(validate_access=lambda _job: {"version": "2.0"})
    service = SimpleNamespace(
        repository=Repo(),
        executor=SimpleNamespace(sources=SimpleNamespace(get=lambda _kind: source)),
        _version_key=lambda value: tuple(int(part) for part in str(value).split(".")),
    )
    result = runtime._refresh_live_target(service, "job-1")
    assert result["source_version"] == "2.0"


def test_live_source_version_not_newer_keeps_catalog_target():
    original = {
        "job_id": "job-1",
        "source_kind": "ultrapackv2",
        "source_version": "2.0",
        "current_version": "1.9",
    }

    class Repo:
        def get(self, _job_id):
            return dict(original)

        def refresh_objective(self, *args, **kwargs):
            raise AssertionError("não deveria reduzir o alvo catalogado")

    source = SimpleNamespace(validate_access=lambda _job: {"version": "1.9"})
    service = SimpleNamespace(
        repository=Repo(),
        executor=SimpleNamespace(sources=SimpleNamespace(get=lambda _kind: source)),
        _version_key=lambda value: tuple(int(part) for part in str(value).split(".")),
    )
    result = runtime._refresh_live_target(service, "job-1")
    assert result["source_version"] == "2.0"


def test_execute_auto_checks_environment_before_canonical_executor(monkeypatch):
    events = []
    job = {"job_id": "job-1", "source_kind": "plugintheme", "source_version": "1.0", "current_version": "0.9"}
    service = SimpleNamespace(repository=SimpleNamespace(get=lambda _id: dict(job)))

    monkeypatch.setattr(runtime, "_ensure_environment", lambda _self, kinds: events.append(("preflight", kinds)))
    monkeypatch.setattr(runtime, "_refresh_live_target", lambda _self, _id: events.append(("live", _id)) or dict(job))
    monkeypatch.setattr(runtime, "_ORIGINAL_EXECUTE", lambda _self, _id: events.append(("execute", _id)) or {"ok": True})

    result = runtime._execute(service, "job-1")
    assert result["ok"] is True
    assert events == [
        ("preflight", {"plugintheme"}),
        ("live", "job-1"),
        ("execute", "job-1"),
    ]
