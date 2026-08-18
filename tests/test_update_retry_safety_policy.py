from __future__ import annotations

from types import SimpleNamespace

from app.operations.models import JobState
import app.update_retry_safety_policy as policy


class _Woo:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_product(self, _product_id: int):
        self.calls.append("cached-product")
        return {"id": 1}

    def get_product_fresh(self, _product_id: int):
        self.calls.append("fresh-product")
        return {"id": 1}

    def list_variations(self, _product_id: int):
        self.calls.append("cached-variations")
        return []

    def list_variations_fresh(self, _product_id: int):
        self.calls.append("fresh-variations")
        return []


class _NoSSHStore:
    _client = None

    def sha256(self, _path: str, *, chunk_size: int = 1024 * 1024) -> str:
        return "0" * 64


class _Preparation:
    def __init__(self) -> None:
        self.woo = _Woo()
        self.storage = _NoSSHStore()
        self.logs: list[str] = []
        self.logger = self.logs.append


def test_prepare_temporarily_uses_fresh_woocommerce_readers(monkeypatch) -> None:
    service = _Preparation()
    original_product = service.woo.get_product
    original_variations = service.woo.list_variations

    def base(current, _job):
        current.woo.get_product(1)
        current.woo.list_variations(1)
        return "ok"

    monkeypatch.setattr(policy, "_BASE_PREPARE", base)
    assert policy._patched_prepare(service, object()) == "ok"
    assert service.woo.calls == ["fresh-product", "fresh-variations"]
    assert service.woo.get_product.__func__ is original_product.__func__
    assert service.woo.list_variations.__func__ is original_variations.__func__
    assert any("sem cache" in entry for entry in service.logs)


class _Channel:
    def __init__(self, status: int = 0) -> None:
        self.status = status

    def recv_exit_status(self) -> int:
        return self.status


class _Stream:
    def __init__(self, value: bytes, *, status: int = 0) -> None:
        self.value = value
        self.channel = _Channel(status)

    def read(self) -> bytes:
        return self.value


class _HashClient:
    def __init__(self, digest: str, *, status: int = 0, stderr: bytes = b"") -> None:
        self.digest = digest
        self.status = status
        self.stderr = stderr
        self.commands: list[tuple[str, int]] = []

    def exec_command(self, command: str, timeout: int):
        self.commands.append((command, timeout))
        return (
            None,
            _Stream(f"{self.digest}  product.zip\n".encode(), status=self.status),
            _Stream(self.stderr),
        )


class _HashStorage:
    def __init__(self, digest: str = "a" * 64) -> None:
        self.config = SimpleNamespace(username="ssh-user", password="ssh-secret")
        self._client = _HashClient(digest)
        self.original_calls = 0

    def _resolved_in_root(self, path: str, *, allow_root: bool = True) -> str:
        del allow_root
        if not path.startswith("/home/plugintema.com/downloads/"):
            raise AssertionError("path escaped")
        return path

    def sha256(self, _path: str, *, chunk_size: int = 1024 * 1024) -> str:
        del chunk_size
        self.original_calls += 1
        return "f" * 64


def test_remote_sha256_runs_on_server_without_reading_zip_over_sftp() -> None:
    storage = _HashStorage("b" * 64)
    path = "/home/plugintema.com/downloads/product.zip"

    digest = policy._remote_sha256(storage, path)

    assert digest == "b" * 64
    assert storage.original_calls == 0
    assert len(storage._client.commands) == 1
    command, timeout = storage._client.commands[0]
    assert command.startswith("sha256sum -- ")
    assert "product.zip" in command
    assert timeout == policy._SHA256_TIMEOUT_SECONDS


def test_fast_sha_reports_progress_and_restores_original_method() -> None:
    storage = _HashStorage("c" * 64)
    logs: list[str] = []
    original = storage.sha256

    saved, replaced = policy._patch_fast_sha(storage, logger=logs.append)
    assert replaced is True
    assert storage.sha256("/home/plugintema.com/downloads/product.zip") == "c" * 64
    assert storage.original_calls == 0
    assert any("Calculando SHA-256 remoto" in entry for entry in logs)
    assert any("SHA-256 remoto confirmado" in entry for entry in logs)

    policy._restore_sha(storage, saved, replaced)
    assert storage.sha256.__func__ is original.__func__


class _RemoteStore:
    def __init__(self, entries: dict[str, str]) -> None:
        self.entries = dict(entries)

    def exists(self, path: str) -> bool:
        return path in self.entries

    def sha256(self, path: str) -> str:
        return self.entries[path]


class _Helper:
    def __init__(self, staging: _RemoteStore, storage: _RemoteStore, upload: str, prepared: str) -> None:
        self.calls = []
        self.staging = staging
        self.storage = storage
        self.upload = upload
        self.prepared = prepared

    def invoke(self, request):
        self.calls.append(request)
        if request.operation == "cleanup" and request.artifact == "upload":
            self.staging.entries.pop(self.upload, None)
        if request.operation == "cleanup" and request.artifact == "new":
            self.storage.entries.pop(self.prepared, None)
        return {"ok": True}


class _Executor:
    def __init__(self, staging, storage, helper) -> None:
        self.staging = staging
        self.storage = storage
        self.helper = helper
        self.logs: list[str] = []
        self.authorizations = 0

    def authorize(self, _job, _plan, _confirmation) -> None:
        self.authorizations += 1

    def log(self, message: str) -> None:
        self.logs.append(message)


def _plan(upload: str, prepared: str, new_sha: str = "b" * 64):
    return {
        "current_zip": {"remote_path": "/home/plugintema.com/downloads/Ekko.zip"},
        "new_zip": {"sha256": new_sha},
        "remote_staging": {"upload_path": upload, "prepared_path": prepared},
    }


def test_execute_cleans_only_job_temporary_staging_before_retry(monkeypatch) -> None:
    upload = "/home/plugintema.com/downloads/Ekko.zip.crapscraper.job-ekko.upload"
    prepared = "/home/plugintema.com/downloads/Ekko.zip.crapscraper.job-ekko.new"
    staging = _RemoteStore({upload: "a" * 64})
    storage = _RemoteStore({prepared: "c" * 64})
    helper = _Helper(staging, storage, upload, prepared)
    executor = _Executor(staging, storage, helper)
    job = SimpleNamespace(
        job_id="job-ekko", state=JobState.ERROR, last_completed_step="backup_validated"
    )
    called = []

    def base(current, current_job, current_plan, confirmation):
        called.append((current, current_job, current_plan, confirmation))
        return {"ok": True}

    monkeypatch.setattr(policy, "_BASE_EXECUTE", base)
    result = policy._patched_execute(executor, job, _plan(upload, prepared), "EXECUTAR 95002")

    assert result == {"ok": True}
    assert executor.authorizations == 1
    assert [request.artifact for request in helper.calls] == ["upload", "new"]
    assert not staging.exists(upload)
    assert not storage.exists(prepared)
    assert len(called) == 1
    assert any("residual removido" in entry for entry in executor.logs)


def test_execute_keeps_temporaries_after_production_was_touched(monkeypatch) -> None:
    upload = "/home/plugintema.com/downloads/Ekko.zip.crapscraper.job-ekko.upload"
    prepared = "/home/plugintema.com/downloads/Ekko.zip.crapscraper.job-ekko.new"
    staging = _RemoteStore({upload: "a" * 64})
    storage = _RemoteStore({prepared: "c" * 64})
    helper = _Helper(staging, storage, upload, prepared)
    executor = _Executor(staging, storage, helper)
    job = SimpleNamespace(
        job_id="job-ekko", state=JobState.ERROR, last_completed_step="production_zip_installed"
    )

    monkeypatch.setattr(policy, "_BASE_EXECUTE", lambda *_args: {"ok": True})
    policy._patched_execute(executor, job, _plan(upload, prepared), "EXECUTAR 95002")

    assert helper.calls == []
    assert staging.exists(upload)
    assert storage.exists(prepared)
