from __future__ import annotations

import pytest

from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.service import UpdateExecutionBlocked, UpdateService
from app.updates.sources import SourceRegistry
from tests.update_fakes import FakeInstaller, FakeSource, FakeWoo, approval


class PreflightWoo(FakeWoo):
    base = "https://example.test/wp-json/wc/v3"
    auth = ("key", "secret")

    def __init__(self, available: bool = True):
        super().__init__()
        self.available = available

    def check_connection(self):
        return {"ok": self.available}


class PreflightInstaller(FakeInstaller):
    root = "/downloads"

    def __init__(self, available: bool = True):
        super().__init__()
        self.available = available

    def check(self):
        return {"ok": self.available, "message": "storage testado"}


class PreflightSource(FakeSource):
    authenticated = True

    def validate_access(self, job):
        self.calls.append("preflight")
        if not self.authenticated:
            raise RuntimeError("Sessão PluginTheme expirada.")
        return {"version": job["source_version"]}


class PluginCredits:
    def __init__(self, authenticated: bool = True):
        self.authenticated = authenticated

    def refresh(self, _site, _account):
        if self.authenticated:
            return {"ok": True, "authenticated": True, "credits": 12, "status": "success", "logs": []}
        return {"ok": False, "authenticated": False, "credits": None, "status": "expired", "message": "Sessão PluginTheme expirada.", "logs": []}

    def cached(self, site, account):
        return self.refresh(site, account)


def build_service(
    tmp_path,
    monkeypatch,
    approvals,
    *,
    plugin_authenticated: bool = True,
    woo_available: bool = True,
    storage_available: bool = True,
    enabled: bool = True,
    allowed: frozenset[int] = frozenset(),
):
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    monkeypatch.setattr("app.updates.service.get_source_account", lambda _site: "account-a")
    monkeypatch.setattr("app.updates.service.profile_diagnostic", lambda _account: {"configured": True, "profile_exists": True, "cookie_count": 3})
    monkeypatch.setattr("app.plugintheme_profile.profile_diagnostic", lambda _account: {
        "configured": plugin_authenticated, "profile_exists": plugin_authenticated})
    repository = UpdateRepository(tmp_path)
    repository.materialize(approvals)
    sources = []
    kinds = {item["source_name"] for item in approvals}
    if "UltraPackV2" in kinds:
        sources.append(PreflightSource("ultrapackv2"))
    if "PluginTheme" in kinds:
        plugin_source = PreflightSource("plugintheme")
        plugin_source.authenticated = plugin_authenticated
        sources.append(plugin_source)
    woo = PreflightWoo(woo_available)
    installer = PreflightInstaller(storage_available)
    executor = UpdateExecutor(
        repository,
        sources=SourceRegistry(sources),
        woo=woo,
        installer=installer,
        enabled=enabled,
        allowed_product_ids=allowed,
    )
    service = UpdateService(tmp_path, repository=repository, executor=executor, credits=PluginCredits(plugin_authenticated))
    return service, repository, woo, installer


def item_for(service: UpdateService, woo_id: int):
    result = service.list({"query": str(woo_id), "page_size": 20})
    assert result["total"] == 1
    return result["items"][0]


def blocker_codes(item):
    return {blocker["code"] for blocker in item["execution"]["blockers"]}


def test_prepared_with_valid_requirements_is_executable(tmp_path, monkeypatch):
    service, _, _, _ = build_service(tmp_path, monkeypatch, [approval(kind="UltraPackV2", woo=95422)])
    service.verify_environment()

    item = item_for(service, 95422)

    assert item["state"] == "ready" and item["stage"] == "prepared" and item["attempts"] == 0
    assert item["execution"] == {"allowed": True, "action": "execute", "blockers": []}


def test_invalid_plugintheme_does_not_block_ultrapack_job(tmp_path, monkeypatch):
    service, _, _, _ = build_service(
        tmp_path,
        monkeypatch,
        [approval(kind="UltraPackV2", woo=95422)],
        plugin_authenticated=False,
    )
    environment = service.verify_environment()

    assert next(check for check in environment["checks"] if check["key"] == "source")["value"] == "VALIDADA"
    assert item_for(service, 95422)["execution"]["allowed"] is True


def test_invalid_plugintheme_blocks_only_plugintheme_job(tmp_path, monkeypatch):
    service, _, _, _ = build_service(
        tmp_path,
        monkeypatch,
        [approval(kind="PluginTheme", woo=95191)],
        plugin_authenticated=False,
    )
    service.verify_environment()

    item = item_for(service, 95191)

    assert item["execution"]["allowed"] is False
    assert "source_unavailable" in blocker_codes(item)
    assert "PluginTheme" in item["execution"]["blockers"][0]["message"]


def test_one_click_runs_missing_preflight_and_failure_creates_no_attempt(tmp_path, monkeypatch):
    service, repository, _, _ = build_service(tmp_path, monkeypatch, [approval(kind="UltraPackV2", woo=95422)], woo_available=False)
    item = item_for(service, 95422)

    assert item["execution"]["allowed"] and item["execution"]["preflight_required"]
    assert {"woocommerce_not_validated", "storage_not_validated", "source_not_validated"} <= {
        warning["code"] for warning in item["execution"]["warnings"]}
    with pytest.raises(RuntimeError, match="WooCommerce"):
        service.execute(item["job_id"])
    assert repository.get(item["job_id"])["attempts"] == 0
    assert repository.history(item["job_id"]) == []


def test_woocommerce_recovery_releases_prepared_job(tmp_path, monkeypatch):
    service, _, woo, _ = build_service(
        tmp_path,
        monkeypatch,
        [approval(kind="UltraPackV2", woo=95422)],
        woo_available=False,
    )
    service.verify_environment()
    assert "woocommerce_unavailable" in blocker_codes(item_for(service, 95422))

    woo.available = True
    service.verify_environment()

    assert item_for(service, 95422)["execution"]["allowed"] is True


def test_global_gate_and_allowlist_are_explicit_blockers(tmp_path, monkeypatch):
    disabled, _, _, _ = build_service(
        tmp_path / "disabled",
        monkeypatch,
        [approval("disabled", kind="UltraPackV2", woo=95422)],
        enabled=False,
    )
    disabled.verify_environment()
    assert "execution_disabled" in blocker_codes(item_for(disabled, 95422))

    restricted, _, _, _ = build_service(
        tmp_path / "restricted",
        monkeypatch,
        [approval("restricted", kind="UltraPackV2", woo=95191)],
        allowed=frozenset({95422}),
    )
    restricted.verify_environment()
    item = item_for(restricted, 95191)
    assert "product_not_allowed" in blocker_codes(item)
    assert "não autorizado" in item["execution"]["blockers"][0]["message"]


def test_error_retry_and_running_state_have_distinct_actions(tmp_path, monkeypatch):
    service, repository, _, _ = build_service(
        tmp_path,
        monkeypatch,
        [approval("retry", kind="UltraPackV2", woo=95422), approval("running", kind="UltraPackV2", woo=95191)],
    )
    service.verify_environment()
    jobs = {item["woo_product_id"]: item for item in repository.list(page_size=20)["items"]}
    retry_attempt = repository.begin_attempt(jobs[95422]["job_id"])
    repository.finish(
        jobs[95422]["job_id"],
        retry_attempt["attempt_id"],
        success=False,
        stage="rolled_back",
        error={"message": "falha recuperável", "recoverable": True},
    )
    repository.begin_attempt(jobs[95191]["job_id"])

    retry = item_for(service, 95422)
    running = item_for(service, 95191)

    assert retry["execution"] == {"allowed": True, "action": "retry", "blockers": []}
    assert running["execution"]["allowed"] is False
    assert running["execution"]["action"] == "none"
    assert blocker_codes(running) == {"job_running"}


def test_batch_accepts_eligible_jobs_and_never_dispatches_blocked_selection(tmp_path, monkeypatch):
    service, _, _, _ = build_service(
        tmp_path / "ok",
        monkeypatch,
        [approval("a", kind="UltraPackV2", woo=95422), approval("b", kind="UltraPackV2", woo=95191)],
    )
    service.verify_environment()
    eligible = service.selection({})["items"]
    calls = []
    service.batch.start = lambda ids: calls.append(ids) or {"running": True, "total": len(ids)}

    result = service.batch_start([item["job_id"] for item in eligible])

    assert result["batch"]["total"] == 2
    assert calls == [[item["job_id"] for item in eligible]]

    mixed, _, _, _ = build_service(
        tmp_path / "blocked",
        monkeypatch,
        [approval("ultra", kind="UltraPackV2", woo=95422), approval("plugin", kind="PluginTheme", woo=95191)],
        plugin_authenticated=False,
    )
    mixed.verify_environment()
    selected = mixed.selection({})["items"]
    dispatched = []
    mixed.batch.start = lambda ids: dispatched.extend(ids) or {"running": True, "total": len(ids)}
    result = mixed.batch_start([item["job_id"] for item in selected])
    assert dispatched == [item["job_id"] for item in selected if item["source_kind"] == "ultrapackv2"]
    assert result["skipped_count"] == 1
    assert "PluginTheme" in result["skipped"][0]["blockers"][0]["message"]
    with pytest.raises(UpdateExecutionBlocked, match="PluginTheme"):
        mixed.batch_start([item["job_id"] for item in selected if item["source_kind"] == "plugintheme"])
