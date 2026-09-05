from __future__ import annotations

from types import SimpleNamespace

from app.additions.source_preflight_runtime import _AdditionSourceProxy


class RecoverableSource:
    kind = "ultrapackv2"
    display_name = "UltraPackV2"

    def __init__(self):
        self.calls = []

    def validate_access(self, job):
        self.calls.append(("validate_access", job["source_url"]))
        return {"version": "3.7", "download_url": "https://example.test/file.zip"}

    def validate_authentication(self):
        raise AssertionError("o executor não deve usar a validação rasa quando validate_access existe")

    def confirm_version(self, job):
        self.calls.append(("confirm_version", job["source_url"]))
        return "unexpected"

    def download(self, job, target):
        self.calls.append(("download", str(target)))
        return SimpleNamespace(path=target)


class LegacySource:
    kind = "legacy"
    display_name = "Legacy"

    def __init__(self):
        self.authenticated = False

    def validate_authentication(self):
        self.authenticated = True

    def confirm_version(self, _job):
        return "1.0"


def test_addition_preflight_uses_validate_access_and_reuses_version(tmp_path):
    job = {"source_url": "https://ultrapackv2.com/item/demo", "source_version": "3.7"}
    source = RecoverableSource()
    proxy = _AdditionSourceProxy(source, job)

    proxy.validate_authentication()
    assert proxy.confirm_version(job) == "3.7"
    artifact = proxy.download(job, tmp_path / "artifact.zip")

    assert artifact.path == tmp_path / "artifact.zip"
    assert source.calls == [
        ("validate_access", job["source_url"]),
        ("download", str(tmp_path / "artifact.zip")),
    ]


def test_addition_preflight_keeps_legacy_authentication_fallback():
    job = {"source_url": "https://example.test/product", "source_version": "1.0"}
    source = LegacySource()
    proxy = _AdditionSourceProxy(source, job)

    proxy.validate_authentication()

    assert source.authenticated is True
    assert proxy.confirm_version(job) == "1.0"
