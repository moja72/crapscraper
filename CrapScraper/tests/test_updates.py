from app.updates.repository import UpdateRepository
from app.updates.adapters import WooCommerceGateway, WooCommerceRequestError
from tests.update_fakes import approval
from app.updates.executor import UpdateExecutor
from app.updates.service import UpdateService
from app.updates.sources import SourceRegistry
from tests.update_fakes import FakeInstaller, FakeSource, FakeWoo

def test_materialization_is_idempotent_and_source_is_immutable(tmp_path):
    repo=UpdateRepository(tmp_path)
    assert repo.materialize([approval()])=={"created":1,"total":1}
    assert repo.materialize([approval()])=={"created":0,"total":1}
    changed=approval();changed["source_name"]="UltraPackV2";changed["source_product_url"]="https://ultrapack.example/changed"
    repo.materialize([changed]);job=repo.list()["items"][0]
    assert job["source_kind"]=="plugintheme" and "plugintheme" in job["source_url"]
    counts=repo.list()["counts"]
    assert counts["total"]==sum(counts[x] for x in ("prepared","running","success","error"))

def test_update_woocommerce_gateway_uses_canonical_store_credentials(monkeypatch):
    monkeypatch.setenv("SCRAPER_WP_BASE_URL", "https://example.test")
    monkeypatch.delenv("SCRAPER_WOOCOMMERCE_URL", raising=False)
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_KEY", "key")
    monkeypatch.setenv("SCRAPER_WC_CONSUMER_SECRET", "secret")
    monkeypatch.delenv("SCRAPER_WOOCOMMERCE_KEY", raising=False)
    monkeypatch.delenv("SCRAPER_WOOCOMMERCE_SECRET", raising=False)
    gateway=WooCommerceGateway()
    assert gateway.base=="https://example.test/wp-json/wc/v3"
    assert gateway.auth==("key","secret")

def test_woocommerce_http_error_preserves_safe_rest_diagnostics(monkeypatch):
    class Response:
        status_code=403; url="https://example.test/wp-json/wc/v3/products/103985"; headers={"Content-Type":"application/json","Server":"WordPress"}; text='{"code":"woocommerce_rest_cannot_edit","message":"Sorry, you are not allowed to edit this resource."}'
        def json(self): return {"code":"woocommerce_rest_cannot_edit","message":"Sorry, you are not allowed to edit this resource."}
    monkeypatch.setattr("app.updates.adapters.requests.Session.request",lambda *args,**kwargs: Response())
    monkeypatch.setenv("SCRAPER_WP_BASE_URL","https://example.test");monkeypatch.setenv("SCRAPER_WC_CONSUMER_KEY","key");monkeypatch.setenv("SCRAPER_WC_CONSUMER_SECRET","secret")
    try: WooCommerceGateway().get_product(103985)
    except WooCommerceRequestError as error:
        assert error.status==403 and error.code=="woocommerce_rest_cannot_edit" and "secret" not in str(error)
    else: raise AssertionError("403 deveria ser propagado")

def test_success_and_error_groups_are_exclusive(tmp_path):
    repo=UpdateRepository(tmp_path); repo.materialize([approval("ok"),approval("bad",woo=102)])
    jobs=repo.list(page_size=5)["items"]; by_id={x["comparison_item_id"]:x for x in jobs}
    a=repo.begin_attempt(by_id["ok"]["job_id"]); repo.finish(by_id["ok"]["job_id"],a["attempt_id"],success=True,stage="completed")
    b=repo.begin_attempt(by_id["bad"]["job_id"]); repo.finish(by_id["bad"]["job_id"],b["attempt_id"],success=False,stage="validating",error={"message":"403","code":"woocommerce_http_error"})
    success=repo.list(group="success")["items"]; errors=repo.list(group="error")["items"]
    assert [x["woo_product_id"] for x in success]==[101]
    assert [x["woo_product_id"] for x in errors]==[102]

def test_new_approved_target_reopens_previous_success_without_duplicate(tmp_path):
    repo=UpdateRepository(tmp_path)
    first=approval("versioned"); first["source_version"]="1.9"; first["site_version"]="1.8"
    repo.materialize([first]); job=repo.list(page_size=5)["items"][0]
    attempt=repo.begin_attempt(job["job_id"]); repo.finish(job["job_id"],attempt["attempt_id"],success=True,stage="completed")
    newer=dict(first); newer["source_version"]="1.10"; newer["site_version"]="1.9"
    result=repo.materialize([newer]); assert result["created"]==0
    reopened=repo.get(job["job_id"])
    assert reopened["state"]=="ready" and reopened["stage"]=="prepared" and reopened["attempts"]==1
    assert reopened["source_version"]=="1.10"
    assert len(repo.history(job["job_id"]))==1

def test_legacy_completed_without_attempt_is_not_operational_success(tmp_path):
    repo=UpdateRepository(tmp_path)
    repo.materialize([approval("legacy")]); job=repo.list(page_size=5)["items"][0]
    with repo.connection() as db:
        db.execute("UPDATE update_jobs SET public_state='success', stage='completed', attempts=0 WHERE job_id=?", (job["job_id"],))
    repo.materialize([])
    current=repo.get(job["job_id"])
    assert current["state"]=="ready" and current["stage"]=="prepared"

def test_verify_prerequisites_runs_real_woo_storage_and_source_checks(tmp_path, monkeypatch):
    class Woo(FakeWoo):
        def check_connection(self):return {"ok":True}
    class Installer(FakeInstaller):
        def check(self):return {"ok":True,"message":"storage testado"}
    class Source(FakeSource):
        def validate_access(self,job):self.calls.append("preflight");return {"version":job["source_version"]}
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates",lambda:[approval()])
    repository=UpdateRepository(tmp_path);source=Source()
    executor=UpdateExecutor(repository,sources=SourceRegistry([source]),woo=Woo(),installer=Installer(),enabled=True,allowed_product_ids=frozenset())
    service=UpdateService(tmp_path,repository=repository,executor=executor)
    payload=service.verify_environment();checks={item["key"]:item for item in payload["checks"]}
    assert checks["woocommerce"]["value"]=="VALIDADO"
    assert checks["storage"]["value"]=="VALIDADO"
    assert checks["source"]["value"]=="VALIDADA" and source.calls==["preflight"]


def test_verify_prerequisites_always_validates_plugintheme_and_credits(tmp_path, monkeypatch):
    class Woo(FakeWoo):
        def check_connection(self): return {"ok": True}
    class Installer(FakeInstaller):
        def check(self): return {"ok": True, "message": "storage testado"}
    class Credits:
        def __init__(self): self.calls = []
        def refresh(self, site, account):
            self.calls.append((site, account))
            return {"ok": True, "authenticated": True, "credits": 12, "status": "success", "source": "api:quota", "logs": ["Saldo localizado: 12."]}
        def cached(self, _site, _account):
            return {"ok": True, "authenticated": True, "credits": 12, "status": "success", "source": "api:quota", "logs": ["Saldo localizado: 12."]}
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    monkeypatch.setattr("app.updates.service.get_source_account", lambda _site: "account-a")
    monkeypatch.setattr("app.updates.service.profile_diagnostic", lambda _account: {"configured": True, "profile_exists": True, "cookie_count": 7})
    repository = UpdateRepository(tmp_path)
    executor = UpdateExecutor(repository, woo=Woo(), installer=Installer(), enabled=True, allowed_product_ids=frozenset())
    credit_service = Credits()
    service = UpdateService(tmp_path, repository=repository, executor=executor, credits=credit_service)

    payload = service.verify_environment()
    checks = {item["key"]: item for item in payload["checks"]}

    assert credit_service.calls == [("plugintheme", "account-a")]
    assert checks["source"]["value"] == "VALIDADA"
    assert payload["plugintheme"]["status"] == "VALIDADA"
    assert payload["plugintheme"]["credits"] == 12
    assert payload["plugintheme"]["cookie_count"] == 7


def test_valid_session_without_credit_keeps_source_validated(tmp_path, monkeypatch):
    class Credits:
        def refresh(self, _site, _account):
            return {"ok": False, "authenticated": True, "credits": None, "status": "credit_unavailable", "message": "Saldo não localizado.", "logs": []}
        def cached(self, _site, _account):
            return {"ok": False, "authenticated": True, "credits": None, "status": "credit_unavailable", "message": "Saldo não localizado.", "logs": []}
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    monkeypatch.setattr("app.updates.service.get_source_account", lambda _site: "account-a")
    monkeypatch.setattr("app.updates.service.profile_diagnostic", lambda _account: {"configured": True, "profile_exists": True, "cookie_count": 2})
    service = UpdateService(tmp_path, credits=Credits())

    payload = service.verify_environment()

    assert payload["plugintheme"]["authenticated"] is True
    assert payload["plugintheme"]["credits"] is None
    assert payload["plugintheme"]["credit_status"] == "credit_unavailable"
    assert next(item for item in payload["checks"] if item["key"] == "source")["value"] == "VALIDADA"


def test_invalid_plugintheme_session_reports_configured_but_not_validated(tmp_path, monkeypatch):
    class Credits:
        def refresh(self, _site, _account):
            return {"ok": False, "authenticated": False, "credits": None, "status": "expired", "message": "Sessão expirada.", "logs": []}
        def cached(self, _site, _account):
            return {"ok": False, "authenticated": False, "credits": None, "status": "expired", "message": "Sessão expirada.", "logs": []}
    monkeypatch.setattr("app.updates.service.decisions.list_approved_updates", lambda: [])
    monkeypatch.setattr("app.updates.service.get_source_account", lambda _site: "account-a")
    monkeypatch.setattr("app.updates.service.profile_diagnostic", lambda _account: {"configured": True, "profile_exists": True, "cookie_count": 7})
    service = UpdateService(tmp_path, credits=Credits())

    payload = service.verify_environment()
    source = next(item for item in payload["checks"] if item["key"] == "source")

    assert source["value"] == "CONFIGURADA / SESSÃO NÃO VALIDADA"
    assert payload["plugintheme"]["authenticated"] is False
    assert payload["plugintheme"]["cookie_count"] == 7
