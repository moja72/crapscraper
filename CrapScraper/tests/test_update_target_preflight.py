from __future__ import annotations

import zipfile

import pytest

from app.updates.adapters import FilesystemInstaller, SFTPInstaller, WooCommerceGateway
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.sources import SourceRegistry
from app.updates.target_preflight import TargetZipError, check_target, normalize_target_filename
from tests.update_fakes import FakeSource, FakeWoo, approval


class TargetWoo(FakeWoo):
    def __init__(self, filename: str, version: str = "1.0"):
        super().__init__(version)
        self.filename = filename

    def prepare_job(self, job):
        job["target_filename"] = self.filename


def build_executor(tmp_path, *, filename: str, source=None, woo=None):
    repository = UpdateRepository(tmp_path)
    repository.materialize([approval()])
    job = repository.list()["items"][0]
    source = source or FakeSource()
    woo = woo or TargetWoo(filename)
    root = tmp_path / "downloads"
    root.mkdir(exist_ok=True)
    executor = UpdateExecutor(
        repository,
        sources=SourceRegistry([source]),
        woo=woo,
        installer=FilesystemInstaller(root),
        staging_root=tmp_path / "stage",
        enabled=True,
        allowed_product_ids=frozenset(),
    )
    return repository, job, executor, source, woo, root


def write_zip(path, text="old"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("plugin/file.php", text)


def test_repository_finish_persists_finished_at(tmp_path):
    repository = UpdateRepository(tmp_path)
    repository.materialize([approval()])
    job = repository.list()["items"][0]
    attempt = repository.begin_attempt(job["job_id"])
    repository.finish(job["job_id"], attempt["attempt_id"], success=True, stage="completed")
    finished = repository.get(job["job_id"])["finished_at"]
    assert finished
    assert "T" in finished


def test_missing_filesystem_target_stops_before_source_download_and_put(tmp_path):
    repository, job, executor, source, woo, _root = build_executor(tmp_path, filename="missing.zip")
    result = executor.execute(job["job_id"])
    item = repository.get(job["job_id"])

    assert result["ok"] is False
    assert result["error"]["code"] == "target_zip_not_found"
    assert "ZIP atual do produto" in result["error"]["message"]
    assert item["stage"] == "staging"
    assert source.calls == []
    assert woo.set_calls == []


def test_retry_succeeds_after_missing_target_is_restored(tmp_path):
    repository, job, executor, source, woo, root = build_executor(tmp_path, filename="produto.zip")
    first = executor.execute(job["job_id"])
    assert first["ok"] is False
    assert first["error"]["code"] == "target_zip_not_found"
    assert source.calls == []

    write_zip(root / "produto.zip")
    second = executor.execute(job["job_id"])

    assert second["ok"] is True
    assert source.calls == ["auth", "version", "download"]
    assert woo.set_calls == ["2.0"]
    assert repository.get(job["job_id"])["state"] == "success"


def test_url_encoded_target_filename_is_decoded_before_filesystem_lookup(tmp_path):
    repository, job, executor, source, woo, root = build_executor(
        tmp_path,
        filename="AutomatorWP%20BuddyPress.zip",
    )
    write_zip(root / "AutomatorWP BuddyPress.zip")

    result = executor.execute(job["job_id"])

    assert result["ok"] is True
    assert source.calls == ["auth", "version", "download"]
    assert woo.set_calls == ["2.0"]


def test_woocommerce_prepare_job_decodes_url_filename():
    class Gateway(WooCommerceGateway):
        def _request(self, method, path, **kwargs):
            assert method == "GET"
            assert path == "/products/91438/variations"
            return [{
                "id": 1001,
                "parent_id": 91438,
                "meta_data": [],
                "downloads": [{"file": "https://plugintema.com/downloads/AutomatorWP%20BuddyPress%20%281%29.zip"}],
            }]

    job = {"woo_product_id": 91438}
    Gateway().prepare_job(job)
    assert job["target_filename"] == "AutomatorWP BuddyPress (1).zip"


def test_normalize_target_filename_decodes_encoded_parentheses_and_nested_path():
    assert normalize_target_filename("folder%2FAutomatorWP%20BuddyPress%20%281%29.zip") == "AutomatorWP BuddyPress (1).zip"


def test_sftp_artifact_names_accept_safe_spaces_and_parentheses():
    installer = SFTPInstaller()
    installer.root = "/home/plugintema.com/downloads"
    artifacts = installer._artifacts({"job_id": "upd-safe_name", "target_filename": "AutomatorWP BuddyPress (1).zip"})
    assert artifacts["production"].endswith("/AutomatorWP BuddyPress (1).zip")
    assert ".crapscraper.upd-safe_name.upload" in artifacts["upload"]


def test_sftp_artifact_names_still_reject_path_traversal():
    installer = SFTPInstaller()
    with pytest.raises(ValueError):
        installer._artifacts({"job_id": "upd-safe", "target_filename": "../evil.zip"})


def test_sftp_enoent_becomes_structured_target_error():
    class MissingSftp:
        def stat(self, _path):
            raise FileNotFoundError(2, "No such file")

        def close(self):
            pass

    class Client:
        def close(self):
            pass

    installer = SFTPInstaller()
    installer.root = "/home/plugintema.com/downloads"
    installer._connect = lambda: (Client(), MissingSftp())

    with pytest.raises(TargetZipError) as captured:
        check_target(installer, {"target_filename": "automatorwp-buddypress.zip"})

    error = captured.value
    assert error.code == "target_zip_not_found"
    assert error.details["target_filename"] == "automatorwp-buddypress.zip"
    assert error.details["target_path"] == "/home/plugintema.com/downloads/automatorwp-buddypress.zip"
    assert "No such file" not in str(error)
