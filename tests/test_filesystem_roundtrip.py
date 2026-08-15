from __future__ import annotations

import io
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.integrations.ssh_storage import ControlledWriteSSHStorage, SSHStorageConfig
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError
from app.operations.filesystem_roundtrip import run_round_trip


ROOT = "/home/plugintema.com/downloads"
TARGET = ROOT + "/product.zip"


class MemoryFile(io.BytesIO):
    def __init__(self, sftp, path, mode, initial=b""):
        super().__init__(initial)
        self.sftp, self.path, self.mode = sftp, path, mode

    def close(self):
        if not self.closed and any(flag in self.mode for flag in ("w", "x", "a")):
            self.sftp.files[self.path] = self.getvalue()
            self.sftp.meta[self.path] = self.sftp.upload_meta
        super().close()


class MemorySFTP:
    def __init__(self, *, upload_meta=(1001, 99, 0o644)):
        self.files = {TARGET: b"same zip bytes"}
        self.meta = {TARGET: (1001, 99, 0o644)}
        self.upload_meta = upload_meta
        self.fail_rename_pair = None

    def normalize(self, path):
        return path

    def stat(self, path):
        if path == ROOT:
            return SimpleNamespace(st_size=0, st_mtime=1, st_mode=stat.S_IFDIR | 0o755, st_uid=1001, st_gid=99)
        if path not in self.files:
            error = FileNotFoundError(path); error.errno = 2; raise error
        uid, gid, mode = self.meta[path]
        return SimpleNamespace(st_size=len(self.files[path]), st_mtime=2, st_mode=stat.S_IFREG | mode, st_uid=uid, st_gid=gid)

    def open(self, path, mode):
        if "x" in mode and path in self.files:
            raise FileExistsError(path)
        return MemoryFile(self, path, mode, self.files.get(path, b"") if "r" in mode else b"")

    def rename(self, source, destination):
        if self.fail_rename_pair == (source, destination):
            self.fail_rename_pair = None
            raise OSError("injected rename failure")
        if destination in self.files:
            raise FileExistsError(destination)
        self.files[destination] = self.files.pop(source)
        self.meta[destination] = self.meta.pop(source)

    def remove(self, path):
        del self.files[path]; del self.meta[path]

    def close(self): pass


class MemoryClient:
    def __init__(self, sftp): self.sftp = sftp
    def connect(self, **_kwargs): pass
    def open_sftp(self): return self.sftp
    def exec_command(self, *_args, **_kwargs):
        class Stream:
            def read(self): return b"owner\ngroup\n"
        return None, Stream(), Stream()
    def close(self): pass


def storage_for(sftp, job="job-1"):
    client = MemoryClient(sftp)
    return ControlledWriteSSHStorage(
        SSHStorageConfig("h", 22, "u", "p"), job_id=job,
        target_path=TARGET, write_authorized=True, client_factory=lambda: client,
    )


class ControlledStorageTests(unittest.TestCase):
    def test_write_requires_explicit_opt_in(self):
        with self.assertRaises(WriteOperationDisabledError):
            ControlledWriteSSHStorage(SSHStorageConfig("h", 22, "u", "p"), job_id="j", target_path=TARGET)

    def test_path_traversal_and_arbitrary_delete_are_rejected(self):
        with storage_for(MemorySFTP()) as storage:
            with self.assertRaises(IntegrationError):
                storage.rename(ROOT + "/../outside", storage.temporary_path)
            with self.assertRaises(WriteOperationDisabledError):
                storage.delete(TARGET)
            with self.assertRaises(WriteOperationDisabledError):
                storage.delete_temporary(storage.temporary_path)

    def test_backup_existing_blocks_before_swap(self):
        sftp = MemorySFTP(); storage = storage_for(sftp)
        sftp.files[storage.backup_path] = b"old"; sftp.meta[storage.backup_path] = (1001, 99, 0o644)
        with tempfile.TemporaryDirectory() as directory, storage:
            result = run_round_trip(storage, product_id=89416, expected_hash=storage.sha256(TARGET), audit_path=Path(directory) / "audit.jsonl")
        self.assertEqual(result.result, "failed")
        self.assertIn(storage.backup_path, result.remaining_files)
        self.assertEqual(sftp.files[TARGET], b"same zip bytes")

    def test_round_trip_and_restore(self):
        sftp = MemorySFTP(); storage = storage_for(sftp)
        with tempfile.TemporaryDirectory() as directory, storage:
            expected = storage.sha256(TARGET)
            result = run_round_trip(storage, product_id=89416, expected_hash=expected, audit_path=Path(directory) / "audit.jsonl")
            self.assertTrue((Path(directory) / "audit.jsonl").exists())
        self.assertEqual(result.result, "rolled_back")
        self.assertTrue(result.rollback_ok)
        self.assertEqual(result.hash_after_rollback, expected)
        self.assertEqual(set(sftp.files), {TARGET})

    def test_mid_swap_failure_restores_backup(self):
        sftp = MemorySFTP(); storage = storage_for(sftp)
        sftp.fail_rename_pair = (storage.temporary_path, TARGET)
        with tempfile.TemporaryDirectory() as directory, storage:
            expected = storage.sha256(TARGET)
            result = run_round_trip(storage, product_id=89416, expected_hash=expected, audit_path=Path(directory) / "audit.jsonl")
        self.assertEqual(result.result, "failed_rolled_back")
        self.assertTrue(result.rollback_ok)
        self.assertEqual(sftp.files[TARGET], b"same zip bytes")

    def test_metadata_divergence_stops_before_swap_and_cleans_temp(self):
        sftp = MemorySFTP(upload_meta=(1001, 99, 0o600)); storage = storage_for(sftp)
        with tempfile.TemporaryDirectory() as directory, storage:
            result = run_round_trip(storage, product_id=89416, expected_hash=storage.sha256(TARGET), audit_path=Path(directory) / "audit.jsonl")
        self.assertEqual(result.result, "failed_pre_swap")
        self.assertEqual(set(sftp.files), {TARGET})


if __name__ == "__main__":
    unittest.main()
