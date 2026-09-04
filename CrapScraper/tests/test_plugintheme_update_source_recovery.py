import io
import zipfile
from types import SimpleNamespace

import pytest

from app.updates.models import UpdateError
from app.updates.sources import PluginThemeSource, SourceFailure
from app.updates import plugintheme_source_recovery as recovery


def _zip_bytes(name="plugin/readme.txt", body=b"ok"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, body)
    return stream.getvalue()


class Response:
    def __init__(self, *, payload=None, content=b"", content_type="application/json", url="https://api.plugintheme.net/api/test", status=200):
        self._payload = payload
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.url = url
        self.status_code = status
        self.text = "" if content else ("{}" if payload is None else str(payload))

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _auth_failure():
    return SourceFailure(UpdateError(
        message="PluginTheme recusou o acesso ao download; verifique a autenticação.",
        code="authentication_access",
        stage="authenticating",
        source="PluginTheme",
        recoverable=True,
    ))


def test_plugintheme_preflight_recovers_persisted_session_once(monkeypatch):
    source = PluginThemeSource()
    job = {"source_url": "https://plugintheme.net/product/demo", "source_version": "2.0"}
    calls = {"product": 0, "renew": 0}

    monkeypatch.setattr(recovery, "_prime_session", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(recovery, "_renew_session", lambda *_args, **_kwargs: calls.__setitem__("renew", calls["renew"] + 1) or object())
    monkeypatch.setattr(recovery, "set_source_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(recovery, "get_source_account", lambda _kind: "coproducaolancamentos")

    def product(_job):
        calls["product"] += 1
        if calls["product"] == 1:
            raise _auth_failure()
        return {"id": "product-id", "version": "2.0"}

    source._product = product

    result = source.validate_access(job)

    assert result["product_id"] == "product-id"
    assert result["version"] == "2.0"
    assert calls == {"product": 2, "renew": 1}


def test_plugintheme_direct_octet_stream_zip_is_accepted(monkeypatch, tmp_path):
    source = PluginThemeSource()
    job = {"source_url": "https://plugintheme.net/product/demo", "source_version": "2.0"}
    body = _zip_bytes()
    responses = iter([
        Response(payload={"data": {"allowed": True}}, url="https://api.plugintheme.net/api/downloads/product-id/check-access"),
        Response(content=body, content_type="application/octet-stream", url="https://api.plugintheme.net/api/downloads/product-id/file"),
    ])

    monkeypatch.setattr(recovery, "_product_with_recovery", lambda *_args, **_kwargs: {"id": "product-id", "version": "2.0"})
    source._get = lambda _url: next(responses)

    artifact = source.download(job, tmp_path / "artifact.zip")

    assert artifact.size == len(body)
    assert artifact.content_type == "application/octet-stream"
    assert zipfile.is_zipfile(artifact.path)
    assert artifact.sha256


def test_plugintheme_json_download_url_uses_signed_download(monkeypatch, tmp_path):
    source = PluginThemeSource()
    job = {"source_url": "https://plugintheme.net/product/demo", "source_version": "2.0"}
    responses = iter([
        Response(payload={"data": {"canDownload": True}}),
        Response(payload={"data": {"downloadUrl": "https://files.example/demo.zip"}}),
    ])
    sentinel = SimpleNamespace(path=tmp_path / "artifact.zip", size=123, sha256="abc")
    signed = []

    monkeypatch.setattr(recovery, "_product_with_recovery", lambda *_args, **_kwargs: {"id": "product-id", "version": "2.0"})
    monkeypatch.setattr(recovery, "_download_signed_url", lambda _source, url, target: signed.append((url, target)) or sentinel)
    source._get = lambda _url: next(responses)

    artifact = source.download(job, tmp_path / "artifact.zip")

    assert artifact is sentinel
    assert signed == [("https://files.example/demo.zip", tmp_path / "artifact.zip")]


def test_plugintheme_invalid_zip_without_auth_evidence_is_not_downloaded_twice(monkeypatch, tmp_path):
    source = PluginThemeSource()
    job = {"source_url": "https://plugintheme.net/product/demo", "source_version": "2.0"}
    calls = []
    failure = SourceFailure(UpdateError(
        message="PluginTheme recusou o download ou retornou um artefato inválido.",
        code="source_download_failed",
        stage="downloading",
        source="PluginTheme",
        technical_message="O arquivo baixado não é um ZIP válido.",
        content_type="application/octet-stream",
        recoverable=True,
    ))

    def cycle(*_args, **_kwargs):
        calls.append(True)
        raise failure

    monkeypatch.setattr(recovery, "_download_cycle", cycle)
    monkeypatch.setattr(recovery, "_renew_session", lambda *_args, **_kwargs: pytest.fail("não deve renovar sem evidência de autenticação"))

    with pytest.raises(SourceFailure):
        source.download(job, tmp_path / "artifact.zip")

    assert calls == [True]


def test_plugintheme_button_can_preflight_on_execute_when_profile_exists(monkeypatch):
    monkeypatch.setattr(recovery, "_ORIGINAL_EXECUTION", lambda _self, _job: {
        "allowed": False,
        "action": "execute",
        "blockers": [{"code": "source_unavailable", "message": "Fonte PluginTheme não autenticada."}],
    })
    monkeypatch.setattr(recovery, "get_source_account", lambda _kind: "coproducaolancamentos")

    import app.plugintheme_profile as profile
    monkeypatch.setattr(profile, "profile_diagnostic", lambda _account: {
        "configured": True,
        "profile_exists": True,
        "storage_state_exists": True,
    })

    result = recovery._execution(object(), {"source_kind": "plugintheme"})

    assert result["allowed"] is True
    assert result["preflight_required"] is True
    assert result["authentication_on_execute"] is True
    assert result["blockers"] == []
