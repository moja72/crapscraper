from __future__ import annotations

import io
import os
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.integrations.ssh_storage import (
    ControlledStagingSSHStorage,
    ReadOnlySSHStorage,
    SSHStorageConfig,
    SSHStorageConfigurationError,
)
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError


ROOT = "/home/plugintema.com/downloads"
ZIP = ROOT + "/product.zip"


class FakeStream:
    def __init__(self, value: bytes):
        self.value = value

    def read(self):
        return self.value


class FakeSFTP:
    def __init__(self):
        self.content = b"read-only zip bytes"
        self.files = {ZIP: self.content}
        self.modes = {ZIP: 0o674}
        self.chmod_calls = []

    def normalize(self, path):
        if path == ROOT + "/../outside.zip":
            return "/home/plugintema.com/outside.zip"
        return path

    def stat(self, path):
        is_dir = path == ROOT
        if not is_dir and path not in self.files:
            error = FileNotFoundError(path); error.errno = 2; raise error
        return SimpleNamespace(
            st_size=0 if is_dir else len(self.files[path]), st_mtime=1770000000,
            st_mode=(stat.S_IFDIR | 0o2775) if is_dir else (stat.S_IFREG | self.modes[path]),
            st_uid=1001, st_gid=99,
        )

    lstat = stat

    def open(self, path, mode):
        if mode == "rb":
            return io.BytesIO(self.files[path])
        if mode == "wb":
            parent = self
            class Writer(io.BytesIO):
                def close(self):
                    if not self.closed:
                        parent.files[path] = self.getvalue()
                        parent.modes[path] = 0o600
                    super().close()
            return Writer()
        raise AssertionError("modo inesperado")

    def chmod(self, path, mode):
        self.chmod_calls.append((path, mode))
        self.modes[path] = mode

    def listdir_attr(self, path):
        return [SimpleNamespace(filename="product.zip")]

    def close(self):
        pass


class FakeClient:
    def __init__(self):
        self.sftp = FakeSFTP()
        self.connect_kwargs = None

    def connect(self, **kwargs):
        self.connect_kwargs = kwargs

    def open_sftp(self):
        return self.sftp

    def exec_command(self, command, timeout):
        output = b"plugin\nnobody\n" if command.startswith("stat ") else b"Filesystem Type 1K-blocks Used Available Use% Mounted on\n/dev/sda4 xfs 1 1 1 1% /\n"
        return None, FakeStream(output), FakeStream(b"")

    def close(self):
        pass


class SSHStorageTests(unittest.TestCase):
    def make_storage(self):
        client = FakeClient()
        storage = ReadOnlySSHStorage(
            SSHStorageConfig("host", 22, "user", "secret"),
            client_factory=lambda: client,
        )
        return storage, client

    def test_config_reads_environment_without_defaults(self):
        env = {
            "SCRAPER_SSH_HOST": "host", "SCRAPER_SSH_PORT": "22",
            "SCRAPER_SSH_USERNAME": "user", "SCRAPER_SSH_PASSWORD": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = SSHStorageConfig.from_env()
        self.assertEqual((config.host, config.port, config.username), ("host", 22, "user"))

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SSHStorageConfigurationError) as captured:
                SSHStorageConfig.from_env()
        self.assertNotIn("secret", str(captured.exception))

    def test_metadata_hash_listing_and_filesystem_are_read_only(self):
        storage, client = self.make_storage()
        with storage:
            info = storage.validate_file(ZIP)
            listing = storage.list(limit=1)
            identity = storage.identify_directory()
        self.assertEqual(info.size, len(client.sftp.content))
        self.assertEqual(info.owner, "plugin")
        self.assertEqual(len(info.sha256), 64)
        self.assertEqual(listing[0].resolved_path, ZIP)
        self.assertIn("xfs", identity["filesystem"])

    def test_path_escape_and_every_future_write_method_are_blocked(self):
        storage, _client = self.make_storage()
        with storage:
            with self.assertRaises(IntegrationError):
                storage.stat(ROOT + "/../outside.zip")
            for name in ("upload", "rename", "move", "delete", "unlink", "backup",
                         "restore", "mkdir", "chmod", "chown", "truncate", "write"):
                with self.subTest(name=name), self.assertRaises(WriteOperationDisabledError):
                    getattr(storage, name)()

    def test_storage_write_lock_cannot_be_enabled(self):
        with self.assertRaises(WriteOperationDisabledError):
            ReadOnlySSHStorage(SSHStorageConfig("h", 22, "u", "p"), write_enabled=True)

    def make_staging(self, *, job="JOB-1"):
        client = FakeClient()
        storage = ControlledStagingSSHStorage(
            SSHStorageConfig("host", 22, "adminpt", "secret"),
            file_name="product.zip", job_id=job, write_authorized=True,
            client_factory=lambda: client,
        )
        return storage, client

    def test_staging_upload_receives_exactly_0644(self):
        storage, client = self.make_staging()
        with storage:
            storage.upload_staging(io.BytesIO(b"zip"))
            info = storage.chmod_staging_upload(storage.upload_path)
        self.assertEqual(client.sftp.chmod_calls, [(storage.upload_path, 0o644)])
        self.assertEqual(info.mode, "-rw-r--r--")
        self.assertEqual(stat.S_IMODE(client.sftp.stat(storage.upload_path).st_mode), 0o644)

    def test_chmod_only_accepts_exact_upload_and_mode(self):
        storage, client = self.make_staging()
        with storage:
            storage.upload_staging(io.BytesIO(b"zip"))
            for path, mode in ((ZIP, 0o644), (ROOT + "/arbitrary.upload", 0o644),
                               (ROOT + "/../outside.upload", 0o644),
                               (storage.upload_path, 0o600)):
                with self.subTest(path=path, mode=mode), self.assertRaises(IntegrationError):
                    storage.chmod_staging_upload(path, mode)
        self.assertEqual(client.sftp.chmod_calls, [])

    def test_chmod_rejects_missing_and_symlink_staging(self):
        storage, client = self.make_staging()
        with storage:
            with self.assertRaises(IntegrationError):
                storage.chmod_staging_upload(storage.upload_path)
            client.sftp.files[storage.upload_path] = b"link"
            client.sftp.modes[storage.upload_path] = 0o644
            original = client.sftp.lstat
            client.sftp.lstat = lambda path: SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
            with self.assertRaises(IntegrationError):
                storage.chmod_staging_upload(storage.upload_path)
            client.sftp.lstat = original


if __name__ == "__main__":
    unittest.main()
