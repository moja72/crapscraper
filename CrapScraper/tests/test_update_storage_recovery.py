from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.updates import storage_recovery_runtime as runtime


def test_prepare_job_decodes_woo_download_filename():
    variations = [
        {
            "id": 10,
            "parent_id": 99,
            "meta_data": [],
            "downloads": [
                {
                    "file": "https://plugintema.test/downloads/AutomatorWP%20BuddyPress%201.5.3.zip"
                }
            ],
        }
    ]
    gateway = SimpleNamespace(_request=lambda *args, **kwargs: variations)
    job = {"woo_product_id": 99}

    runtime._prepare_job(gateway, job)

    assert job["target_filename"] == "AutomatorWP BuddyPress 1.5.3.zip"
    assert job["target_filename_raw"] == "AutomatorWP%20BuddyPress%201.5.3.zip"
    assert job["target_download_url"].endswith("AutomatorWP%20BuddyPress%201.5.3.zip")


def test_family_candidate_is_unique_and_version_aware():
    sftp = SimpleNamespace(
        listdir=lambda _root: [
            "automatorwp-buddypress-1.5.3.zip",
            "unrelated-plugin-7.0.zip",
        ]
    )
    result = runtime._find_recovery_candidate(
        sftp,
        "/downloads",
        "automatorwp-buddypress-1.5.4.zip",
    )
    assert result == ("automatorwp-buddypress-1.5.3.zip", "unique_version_family")


def test_multiple_family_candidates_block_automatic_recovery():
    sftp = SimpleNamespace(
        listdir=lambda _root: [
            "automatorwp-buddypress-1.5.2.zip",
            "automatorwp-buddypress-1.5.3.zip",
        ]
    )
    with pytest.raises(RuntimeError, match="múltiplos arquivos da mesma família"):
        runtime._find_recovery_candidate(
            sftp,
            "/downloads",
            "automatorwp-buddypress-1.5.4.zip",
        )


class FakeSftp:
    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
        self.closed = False

    def listdir(self, root: str):
        prefix = root.rstrip("/") + "/"
        return [path[len(prefix):] for path in self.files if path.startswith(prefix) and "/" not in path[len(prefix):]]

    def get(self, remote: str, local: str):
        if remote not in self.files:
            raise FileNotFoundError(2, "No such file", remote)
        Path(local).write_bytes(self.files[remote])

    def put(self, local: str, remote: str):
        self.files[remote] = Path(local).read_bytes()

    def chmod(self, remote: str, mode: int):
        assert remote in self.files
        assert mode == 0o644

    def open(self, remote: str, mode: str):
        if remote not in self.files:
            raise FileNotFoundError(2, "No such file", remote)
        return io.BytesIO(self.files[remote])

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_backup_repairs_missing_expected_path_from_unique_previous_version(tmp_path):
    root = "/downloads"
    previous = f"{root}/automatorwp-buddypress-1.5.3.zip"
    desired = f"{root}/automatorwp-buddypress-1.5.4.zip"
    payload = b"PK\x03\x04current-version"
    sftp = FakeSftp({previous: payload})
    client = FakeClient()
    helper_calls = []

    def sftp_sha(_sftp, path):
        import hashlib

        if path not in _sftp.files:
            raise FileNotFoundError(2, "No such file", path)
        return hashlib.sha256(_sftp.files[path]).hexdigest()

    installer = SimpleNamespace(
        root=root,
        _connect=lambda: (client, sftp),
        _sftp_sha=sftp_sha,
        _artifacts=lambda job: {"backup": f"{root}/{job['target_filename']}.crapscraper.job.bak"},
        _helper=lambda _client, operation, job, old_sha="", **kwargs: helper_calls.append((operation, job["target_filename"], old_sha)) or {"ok": True},
    )
    job = {
        "job_id": "job",
        "woo_product_id": 91438,
        "target_filename": "automatorwp-buddypress-1.5.4.zip",
        "target_download_url": "https://plugintema.test/downloads/automatorwp-buddypress-1.5.4.zip",
    }

    backup = runtime._backup(installer, job, tmp_path)

    assert backup.read_bytes() == payload
    assert sftp.files[desired] == payload
    assert job["storage_recovery"] == {
        "reason": "unique_version_family",
        "expected": "automatorwp-buddypress-1.5.4.zip",
        "recovered_from": "automatorwp-buddypress-1.5.3.zip",
    }
    assert helper_calls and helper_calls[0][0] == "backup"
    assert sftp.closed is True
    assert client.closed is True
