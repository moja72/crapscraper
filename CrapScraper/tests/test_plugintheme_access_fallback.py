from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

from app import plugintheme_access_fallback as fallback
from app.updates import plugintheme_source_recovery as recovery


def zip_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin/readme.txt", b"ok")
    return stream.getvalue()


class Response:
    def __init__(self, *, content=b"", payload=None, content_type="application/octet-stream", url="https://api.plugintheme.net/api/file"):
        self.content = content
        self._payload = payload
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.status_code = 200
        self.text = "" if content else str(payload or "")

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class Source:
    api_base = "https://api.plugintheme.net/api"
    display_name = "PluginTheme"
    kind = "plugintheme"

    def __init__(self, response):
        self.response = response
        self.transport = SimpleNamespace(timeout=90)

    def _get(self, _url):
        return self.response


def test_denied_probe_can_prove_direct_file_is_valid_zip(monkeypatch, tmp_path):
    body = zip_bytes()
    source = Source(Response(content=body))
    monkeypatch.setattr(recovery, "_product_with_recovery", lambda *_args, **_kwargs: {"id": "product-id", "version": "4.4"})

    artifact = fallback._try_file_endpoint(source, {"source_url": "https://plugintheme.net/demo"}, tmp_path / "artifact.zip")

    assert artifact.size == len(body)
    assert artifact.sha256
    assert zipfile.is_zipfile(artifact.path)


def test_denied_probe_can_follow_signed_url(monkeypatch, tmp_path):
    source = Source(Response(payload={"data": {"downloadUrl": "https://files.example/demo.zip"}}, content_type="application/json"))
    expected = SimpleNamespace(path=tmp_path / "artifact.zip", size=123, sha256="abc")
    calls = []
    monkeypatch.setattr(recovery, "_product_with_recovery", lambda *_args, **_kwargs: {"id": "product-id", "version": "4.4"})
    monkeypatch.setattr(recovery, "_download_signed_url", lambda _source, url, target: calls.append((url, target)) or expected)

    result = fallback._try_file_endpoint(source, {"source_url": "https://plugintheme.net/demo"}, tmp_path / "artifact.zip")

    assert result is expected
    assert calls == [("https://files.example/demo.zip", tmp_path / "artifact.zip")]
