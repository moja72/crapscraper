from pathlib import Path

import pytest

from app.updates.models import UpdateError
from app.updates.sources import SourceFailure, UltraPackSource
from app.updates import ultrapack_source_recovery as recovery


def _failure(*, code="source_download_failed", technical="", content_type=""):
    return SourceFailure(UpdateError(
        message="falha de fonte",
        code=code,
        stage="authenticating",
        source="UltraPackV2",
        technical_message=technical,
        content_type=content_type,
    ))


def test_preflight_renews_stale_ultrapack_session_once(monkeypatch):
    source = UltraPackSource()
    source.validate_authentication = lambda: None
    job = {
        "source_url": "https://www.ultrapackv2.com/item/acf-pro/",
        "source_version": "6.8.9",
    }

    inspect_calls = 0

    def inspect(_job):
        nonlocal inspect_calls
        inspect_calls += 1
        if inspect_calls == 1:
            raise _failure(technical="Botão autenticado de download não encontrado.")
        return job["source_url"] + "?f=novo-token", "6.8.9"

    source._inspect = inspect
    ensure_calls = []
    clear_calls = []
    states = []
    current = object()

    monkeypatch.setattr(recovery, "get_source_account", lambda _kind: "coproducaolancamentos")
    monkeypatch.setattr(recovery, "get_source_session", lambda *_args, **_kwargs: current)
    monkeypatch.setattr(recovery, "ensure_source_session", lambda kind, url, account="": ensure_calls.append((kind, url, account)) or current)
    monkeypatch.setattr(recovery, "clear_source_session", lambda kind, session=None, account_key="": clear_calls.append((kind, session, account_key)))
    monkeypatch.setattr(recovery, "set_source_state", lambda kind, state, account="": states.append((kind, state, account)))

    result = source.validate_access(job)

    assert inspect_calls == 2
    assert len(ensure_calls) == 2
    assert clear_calls == [("ultrapackv2", current, "coproducaolancamentos")]
    assert result["download_url"].endswith("?f=novo-token")
    assert result["version"] == "6.8.9"
    assert ("ultrapackv2", "expired", "coproducaolancamentos") in states
    assert states[-1] == ("ultrapackv2", "validated", "coproducaolancamentos")


def test_preflight_does_not_reauthenticate_for_credit_failure(monkeypatch):
    source = UltraPackSource()
    source.validate_authentication = lambda: None
    job = {
        "source_url": "https://www.ultrapackv2.com/item/acf-pro/",
        "source_version": "6.8.9",
    }
    source._inspect = lambda _job: (_ for _ in ()).throw(_failure(code="insufficient_credits"))

    monkeypatch.setattr(recovery, "get_source_account", lambda _kind: "coproducaolancamentos")
    monkeypatch.setattr(recovery, "ensure_source_session", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(recovery, "_renew_session", lambda *_args, **_kwargs: pytest.fail("não deve renovar sessão para falha de créditos"))

    with pytest.raises(SourceFailure):
        source.validate_access(job)


def test_download_rediscovers_one_time_url_after_auth_html(monkeypatch, tmp_path):
    source = UltraPackSource()
    job = {
        "source_url": "https://www.ultrapackv2.com/item/acf-pro/",
        "source_version": "6.8.9",
    }
    target = tmp_path / "acf-pro.zip"
    urls = iter([
        (job["source_url"] + "?f=token-antigo", "6.8.9"),
        (job["source_url"] + "?f=token-novo", "6.8.9"),
    ])
    downloads = []
    renewals = []
    artifact = object()

    monkeypatch.setattr(recovery, "_inspect_with_recovery", lambda *_args, **_kwargs: next(urls))
    monkeypatch.setattr(recovery, "_renew_session", lambda *_args, **_kwargs: renewals.append(True))

    def download_once(_source, url, _target):
        downloads.append(url)
        if len(downloads) == 1:
            raise _failure(content_type="text/html; charset=utf-8")
        return artifact

    monkeypatch.setattr(recovery, "_download_once", download_once)

    assert source.download(job, target) is artifact
    assert downloads[0].endswith("token-antigo")
    assert downloads[1].endswith("token-novo")
    assert renewals == [True]


def test_download_does_not_repeat_invalid_zip_without_auth_evidence(monkeypatch, tmp_path):
    source = UltraPackSource()
    job = {
        "source_url": "https://www.ultrapackv2.com/item/acf-pro/",
        "source_version": "6.8.9",
    }
    target = Path(tmp_path) / "acf-pro.zip"

    monkeypatch.setattr(recovery, "_inspect_with_recovery", lambda *_args, **_kwargs: (job["source_url"] + "?f=token", "6.8.9"))
    monkeypatch.setattr(recovery, "_download_once", lambda *_args, **_kwargs: (_ for _ in ()).throw(_failure(technical="O arquivo baixado não é um ZIP válido.")))
    monkeypatch.setattr(recovery, "_renew_session", lambda *_args, **_kwargs: pytest.fail("ZIP inválido sem evidência de autenticação não pode consumir uma segunda tentativa"))

    with pytest.raises(SourceFailure):
        source.download(job, target)
