from types import SimpleNamespace

import requests
from app.updates.sources import classify_source_error, PluginThemeSource, UltraPackSource
from app.updates import source_auth
from app.updates.source_auth import register_source_session, clear_source_session, get_source_session


def test_ultrapack_preflight_authenticates_on_demand_without_collection(monkeypatch):
    calls=[]
    session=requests.Session()
    monkeypatch.setattr(
        "app.updates.sources.ensure_source_session",
        lambda kind, url: calls.append((kind,url)) or register_source_session(kind,session),
    )
    source=UltraPackSource()
    monkeypatch.setattr(source,"_inspect",lambda job:(job["source_url"]+"?f=token","2.0"))
    job={"source_url":"https://www.ultrapackv2.com/item/demo/","source_version":"2.0"}
    try:
        result=source.validate_access(job)
        assert calls==[("ultrapackv2",job["source_url"])]
        assert result["version"]=="2.0" and "?f=token" in result["download_url"]
    finally:
        clear_source_session("ultrapackv2",session)


def test_source_sessions_are_isolated_by_account():
    first=requests.Session();first.headers["X-Account"]="a"
    second=requests.Session();second.headers["X-Account"]="b"
    register_source_session("ultrapackv2",first,"account-a")
    register_source_session("ultrapackv2",second,"account-b")
    try:
        assert get_source_session("ultrapackv2","account-a").headers["X-Account"]=="a"
        assert get_source_session("ultrapackv2","account-b").headers["X-Account"]=="b"
        clear_source_session("ultrapackv2",account_key="account-a")
        assert get_source_session("ultrapackv2","account-a") is None
        assert get_source_session("ultrapackv2","account-b") is not None
    finally:
        clear_source_session("ultrapackv2",account_key="account-a")
        clear_source_session("ultrapackv2",account_key="account-b")


def test_plugintheme_browser_auth_uses_supported_item_type(monkeypatch):
    captured = {}

    class Context:
        async def cookies(self):
            return []

    class Browser:
        data = SimpleNamespace(user_agent="test")
        browser_context = Context()

        async def goto(self, url):
            captured["goto"] = url

    async def open_session(*_args, **kwargs):
        captured.update(kwargs)
        return Browser()

    async def close_session(_browser):
        captured["closed"] = True

    monkeypatch.setattr("app.collection.legacy_core.browser.open_authenticated_browser_session", open_session)
    monkeypatch.setattr("app.collection.legacy_core.browser.close_browser_session", close_session)

    session = source_auth._run(source_auth._browser_session(
        "plugintheme", "https://plugintheme.net/product/demo", "coproducaolancamentos"
    ))

    assert isinstance(session, requests.Session)
    assert captured["item_type_key"] == "plugin_theme"
    assert captured["closed"] is True

def test_explicit_credit_response_is_normalized_per_source():
    error=classify_source_error("PluginTheme",status=403,body='{"credits":0}')
    assert error.code=="insufficient_credits" and "PluginTheme" in error.message and "UltraPack" not in error.message

def test_plain_401_is_authentication_not_credit():
    error=classify_source_error("UltraPackV2",status=401,body="unauthorized")
    assert error.code=="authentication_access" and "UltraPackV2" in error.message

def test_ultrapack_source_reuses_authenticated_collection_session(monkeypatch):
    class Response:
        status_code = 200
        url = "https://www.ultrapackv2.com/item/aoki/"
        headers = {"Content-Type": "text/html"}
        text = '<a class="single-bt-download-a" data-f="abc123">Download</a><div>Versão: 1.9</div>'
    monkeypatch.setattr(requests.Session, "get", lambda self, *args, **kwargs: Response())
    session = requests.Session()
    register_source_session("ultrapackv2", session)
    monkeypatch.delenv("SCRAPER_ULTRAPACK_HEADERS_JSON", raising=False)
    monkeypatch.delenv("SCRAPER_ULTRAPACK_COOKIES_JSON", raising=False)
    try:
        source = UltraPackSource()
        source.validate_authentication()
        assert source.confirm_version({"source_url": "https://www.ultrapackv2.com/item/aoki/", "source_version": "1.9"}) == "1.9"
    finally:
        clear_source_session("ultrapackv2", session)

def test_shared_auth_survives_closing_collection_session():
    class Session(requests.Session):
        def get(self, *args, **kwargs):
            raise AssertionError("não deve usar a sessão temporária")
    temporary = Session()
    temporary.headers["X-Test"] = "authenticated"
    register_source_session("ultrapackv2", temporary)
    try:
        shared = __import__("app.updates.source_auth", fromlist=["get_source_session"]).get_source_session("ultrapackv2")
        assert shared is not temporary
        temporary.close()
        assert shared.headers["X-Test"] == "authenticated"
    finally:
        clear_source_session("ultrapackv2", temporary)

def test_plugintheme_final_download_reuses_shared_session(monkeypatch, tmp_path):
    shared=requests.Session();register_source_session("plugintheme",shared)
    source=PluginThemeSource()
    monkeypatch.setattr(source,"_product",lambda _job:{"id":"product-id","version":"2.0"})
    class Meta:
        def __init__(self,payload):self.payload=payload;self.url="https://api.plugintheme.net/file";self.text="";self.status_code=200;self.headers={}
        def json(self):return self.payload
    responses=iter([Meta({"data":{"allowed":True}}),Meta({"data":{"downloadUrl":"https://files.example/product.zip"}})])
    monkeypatch.setattr(source,"_get",lambda url: next(responses))
    calls=[]
    def download(self,**kwargs):
        calls.append(self.session);kwargs["target"].write_bytes(b"zip");return object()
    monkeypatch.setattr("app.updates.sources.HttpDownloadTransport.download",download)
    try:
        source.download({"source_url":"https://plugintheme.net/product/item","source_version":"2.0"},tmp_path/"artifact.zip")
        assert calls and calls[0] is not source.transport.session
    finally:clear_source_session("plugintheme",shared)
