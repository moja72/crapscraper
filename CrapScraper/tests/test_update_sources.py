import requests
from app.updates.sources import classify_source_error, PluginThemeSource, UltraPackSource
from app.updates.source_auth import register_source_session, clear_source_session

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
