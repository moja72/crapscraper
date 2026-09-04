from __future__ import annotations

import zipfile

from app.missing_target_recovery import install_missing_target_recovery
from app.updates.adapters import FilesystemInstaller
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.sources import SourceRegistry
from tests.update_fakes import FakeSource, FakeWoo, approval


class TargetWoo(FakeWoo):
    def __init__(self, filename: str, version: str = "1.0", fail_target_write: bool = False):
        super().__init__(version)
        self.filename = filename
        self.fail_target_write = fail_target_write

    def prepare_job(self, job):
        job["target_filename"] = self.filename

    def set_version(self, pid, version):
        self.set_calls.append(version)
        if self.fail_target_write and version == "2.0":
            raise RuntimeError("injected Woo target write failure")
        self.version = version
        return {"ok": True}


def build_executor(tmp_path, *, filename="AutomatorWP BuddyPress (1).zip", woo=None):
    install_missing_target_recovery()
    repository = UpdateRepository(tmp_path)
    repository.materialize([approval(woo=91438)])
    job = repository.list()["items"][0]
    source = FakeSource()
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


def test_missing_target_is_recreated_and_update_completes(tmp_path):
    repository, job, executor, source, woo, root = build_executor(tmp_path)
    target = root / "AutomatorWP BuddyPress (1).zip"
    assert not target.exists()

    result = executor.execute(job["job_id"])

    assert result["ok"] is True
    assert target.is_file()
    assert zipfile.is_zipfile(target)
    assert source.calls == ["auth", "version", "download"]
    assert woo.version == "2.0"
    stored = repository.get(job["job_id"])
    assert stored["state"] == "success"
    assert stored["stage"] == "completed"


def test_failure_after_missing_target_install_rolls_back_to_absence(tmp_path):
    woo = TargetWoo("AutomatorWP BuddyPress (1).zip", fail_target_write=True)
    repository, job, executor, source, woo, root = build_executor(tmp_path, woo=woo)
    target = root / "AutomatorWP BuddyPress (1).zip"

    result = executor.execute(job["job_id"])

    assert result["ok"] is False
    assert not target.exists()
    assert woo.version == "1.0"
    assert woo.set_calls == ["2.0", "1.0"]
    assert source.calls == ["auth", "version", "download"]
    stored = repository.get(job["job_id"])
    assert stored["state"] == "error"
    assert stored["stage"] == "rolled_back"


def test_missing_target_install_refuses_file_that_appears_after_preflight(tmp_path):
    _repository, job, _executor, _source, _woo, root = build_executor(tmp_path)
    installer = FilesystemInstaller(root)
    job["target_filename"] = "AutomatorWP BuddyPress (1).zip"
    job["_target_originally_missing"] = True
    artifact = tmp_path / "artifact.zip"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("plugin/file.php", "new")
    backup = tmp_path / "missing.marker"
    backup.write_text("missing", encoding="utf-8")
    target = root / job["target_filename"]
    target.write_bytes(b"appeared after preflight")

    try:
        installer.install(job, artifact, backup)
    except RuntimeError as error:
        assert "apareceu depois do preflight" in str(error)
    else:
        raise AssertionError("race de criação deveria ter sido bloqueada")
    assert target.read_bytes() == b"appeared after preflight"
