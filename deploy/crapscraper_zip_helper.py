#!/usr/bin/python3 -I
"""Restricted, standalone ZIP deployment helper for CrapScraper.

Production entry points always use DOWNLOAD_ROOT.  ``ZipHelper`` accepts an
alternate root and numeric identity only so its filesystem behavior can be
tested locally without privileges.  This module imports only the stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Callable, NoReturn

DOWNLOAD_ROOT = Path("/home/plugintema.com/downloads")
EXPECTED_OWNER = "plugi2090"
EXPECTED_GROUP = "nobody"
EXPECTED_MODE = 0o674
JOB_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
FILE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.zip\Z", re.IGNORECASE)


class HelperError(RuntimeError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        print(json.dumps({"ok": False, "operation": "parse", "error": message}, sort_keys=True))
        raise SystemExit(2)


def validate_file_name(value: str) -> str:
    if not value or os.path.isabs(value) or value in {".", ".."}:
        raise HelperError("invalid ZIP basename")
    if "/" in value or "\\" in value or ".." in value or not FILE_RE.fullmatch(value):
        raise HelperError("invalid ZIP basename")
    return value


def validate_job_id(value: str) -> str:
    if not JOB_RE.fullmatch(value or ""):
        raise HelperError("invalid job_id")
    return value


def validate_sha256(value: str) -> str:
    normalized = (value or "").lower()
    if not SHA_RE.fullmatch(normalized):
        raise HelperError("invalid SHA-256")
    return normalized


def artifact_names(file_name: str, job_id: str) -> dict[str, str]:
    base = validate_file_name(file_name)
    job = validate_job_id(job_id)
    prefix = f"{base}.crapscraper.{job}"
    return {
        "production": base,
        "upload": prefix + ".upload",
        "new": prefix + ".new",
        "backup": prefix + ".bak",
        "rollback_current": prefix + ".rollback-current",
        "rollback_restore": prefix + ".rollback-restore",
        "failed_new": prefix + ".failed-new",
    }


class ZipHelper:
    def __init__(
        self,
        root: Path = DOWNLOAD_ROOT,
        *,
        expected_uid: int,
        expected_gid: int,
        owner_name: str = EXPECTED_OWNER,
        group_name: str = EXPECTED_GROUP,
        fault: Callable[[str], None] | None = None,
        posix_semantics: bool | None = None,
    ) -> None:
        self.root = Path(root)
        self.expected_uid = expected_uid
        self.expected_gid = expected_gid
        self.owner_name = owner_name
        self.group_name = group_name
        self.fault = fault or (lambda _stage: None)
        self.posix_semantics = os.name == "posix" if posix_semantics is None else posix_semantics

    def _path(self, name: str) -> Path:
        # All names reaching here originate from artifact_names or a validated basename.
        path = self.root / name
        if path.parent != self.root:
            raise HelperError("path escaped fixed root")
        return path

    def _lstat_regular(self, path: Path, *, metadata: bool = False) -> os.stat_result:
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            raise HelperError(f"required artifact is missing: {path.name}") from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise HelperError(f"artifact is not a regular non-symlink file: {path.name}")
        if info.st_nlink != 1:
            raise HelperError(f"artifact has suspicious hard links: {path.name}")
        if metadata:
            if info.st_uid != self.expected_uid:
                raise HelperError(f"wrong owner for {path.name}")
            if info.st_gid != self.expected_gid:
                raise HelperError(f"wrong group for {path.name}")
            actual_mode = stat.S_IMODE(info.st_mode)
            mode_ok = actual_mode == EXPECTED_MODE
            if not self.posix_semantics:
                mode_ok = bool(actual_mode & stat.S_IWUSR)
            if not mode_ok:
                raise HelperError(f"wrong mode for {path.name}")
        return info

    def _open_read(self, path: Path) -> int:
        before = self._lstat_regular(path)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        after = os.fstat(fd)
        if not stat.S_ISREG(after.st_mode) or after.st_nlink != 1 or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            os.close(fd)
            raise HelperError("artifact changed while opening")
        return fd

    @staticmethod
    def _hash_fd(fd: int) -> str:
        digest = hashlib.sha256()
        os.lseek(fd, 0, os.SEEK_SET)
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
        os.lseek(fd, 0, os.SEEK_SET)
        return digest.hexdigest()

    @staticmethod
    def _write_all(fd: int, chunk: bytes) -> None:
        view = memoryview(chunk)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise HelperError("short write while copying staging")
            view = view[written:]

    def _hash(self, path: Path) -> str:
        fd = self._open_read(path)
        try:
            return self._hash_fd(fd)
        finally:
            os.close(fd)

    def _validate(self, path: Path, expected_hash: str | None = None, *, metadata: bool = True) -> dict[str, object]:
        info = self._lstat_regular(path, metadata=metadata)
        digest = self._hash(path)
        if expected_hash is not None and digest != validate_sha256(expected_hash):
            raise HelperError(f"SHA-256 mismatch for {path.name}")
        return {
            "sha256": digest,
            "owner": self.owner_name if info.st_uid == self.expected_uid else str(info.st_uid),
            "group": self.group_name if info.st_gid == self.expected_gid else str(info.st_gid),
            "mode": f"{EXPECTED_MODE:04o}" if not self.posix_semantics else f"{stat.S_IMODE(info.st_mode):04o}",
            "size": info.st_size,
        }

    def _fsync_directory(self) -> None:
        if not self.posix_semantics:
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(self.root, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _set_metadata(self, fd: int, path: Path) -> None:
        info = os.fstat(fd)
        if info.st_uid != self.expected_uid:
            raise HelperError("helper-created temporary did not inherit owner plugi2090")
        if info.st_gid != self.expected_gid:
            raise HelperError("helper-created temporary did not inherit group nobody from setgid directory")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, EXPECTED_MODE)
        elif not self.posix_semantics:
            os.chmod(path, EXPECTED_MODE)
        else:
            raise HelperError("fchmod is unavailable")

    def inspect(self, file_name: str) -> dict[str, object]:
        name = validate_file_name(file_name)
        return self._result("inspect", name, None, self._validate(self._path(name)))

    def probe_setgid(self) -> dict[str, object]:
        """Create, validate and always remove one fixed disposable probe."""
        name = f"CrapScraperSetgidProbe.zip.crapscraper.{os.getpid()}.probe"
        path = self._path(name)
        fd = -1
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags, 0o600)
            born = os.fstat(fd)
            if born.st_uid != self.expected_uid:
                raise HelperError("setgid probe has wrong owner")
            if born.st_gid != self.expected_gid:
                raise HelperError("setgid probe did not inherit group nobody")
            self._set_metadata(fd, path)
            os.fsync(fd)
            details = {
                "owner": self.owner_name,
                "group": self.group_name,
                "mode": f"{EXPECTED_MODE:04o}",
                "probe": name,
                "removed": True,
            }
        finally:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(path)
                self._fsync_directory()
            except FileNotFoundError:
                pass
        return self._result("probe-setgid", "CrapScraperSetgidProbe.zip", None, details)

    def prepare(self, file_name: str, job_id: str, expected_new_sha256: str) -> dict[str, object]:
        names = artifact_names(file_name, job_id)
        expected = validate_sha256(expected_new_sha256)
        upload, new = self._path(names["upload"]), self._path(names["new"])
        source_fd = self._open_read(upload)
        new_fd = -1
        try:
            self.fault("prepare_before_create")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            new_fd = os.open(new, flags, 0o600)
            created = os.fstat(new_fd)
            if created.st_uid != self.expected_uid or created.st_nlink != 1:
                raise HelperError("helper-created temporary has wrong owner or links")
            digest = hashlib.sha256()
            while chunk := os.read(source_fd, 1024 * 1024):
                self._write_all(new_fd, chunk)
                digest.update(chunk)
            self._set_metadata(new_fd, new)
            os.fsync(new_fd)
            if digest.hexdigest() != expected:
                raise HelperError("SHA-256 mismatch for staging upload")
            os.close(new_fd)
            new_fd = -1
            details = self._validate(new, expected)
        except Exception:
            if new_fd >= 0:
                os.close(new_fd)
                new_fd = -1
            try:
                if new.exists() and not new.is_symlink():
                    os.unlink(new)
            except OSError:
                pass
            raise
        finally:
            os.close(source_fd)
            if new_fd >= 0:
                os.close(new_fd)
        return self._result("prepare", file_name, job_id, details)

    def backup(self, file_name: str, job_id: str, expected_sha256: str) -> dict[str, object]:
        names = artifact_names(file_name, job_id)
        expected = validate_sha256(expected_sha256)
        current, backup = self._path(names["production"]), self._path(names["backup"])
        self._validate(current, expected)
        if backup.exists():
            raise HelperError("backup already exists for job")
        source_fd = self._open_read(current)
        backup_fd = -1
        try:
            self.fault("backup_before_create")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            backup_fd = os.open(backup, flags, 0o600)
            while chunk := os.read(source_fd, 1024 * 1024):
                self._write_all(backup_fd, chunk)
                self.fault("backup_during_copy")
            self._set_metadata(backup_fd, backup)
            self.fault("backup_before_fsync")
            os.fsync(backup_fd)
        except Exception:
            if backup_fd >= 0: os.close(backup_fd); backup_fd = -1
            try: os.unlink(backup)
            except OSError: pass
            raise
        finally:
            os.close(source_fd)
            if backup_fd >= 0: os.close(backup_fd)
        self._fsync_directory()
        return self._result("backup", file_name, job_id, self._validate(backup, expected))

    def _restore_after_install_failure(self, current: Path, backup: Path, failed: Path, old_hash: str) -> None:
        if current.exists():
            if failed.exists():
                raise HelperError("cannot restore: recovery artifact already exists")
            os.rename(current, failed)
        os.rename(backup, current)
        self._fsync_directory()
        self._validate(current, old_hash)
        if failed.exists():
            os.unlink(failed)
            self._fsync_directory()

    def install(self, file_name: str, job_id: str, expected_old_sha256: str, expected_new_sha256: str) -> dict[str, object]:
        names = artifact_names(file_name, job_id)
        old_hash, new_hash = validate_sha256(expected_old_sha256), validate_sha256(expected_new_sha256)
        current, new = self._path(names["production"]), self._path(names["new"])
        backup, failed = self._path(names["backup"]), self._path(names["failed_new"])
        self._validate(current, old_hash)
        self._validate(new, new_hash)
        prebacked = backup.exists()
        if prebacked:
            try:
                self._validate(backup, old_hash)
            except HelperError:
                raise HelperError("incompatible backup already exists for job") from None
        if failed.exists():
            raise HelperError("incompatible artifact already exists for job")
        self.fault("install_before_first_rename")
        os.rename(current, failed if prebacked else backup)
        try:
            self.fault("install_between_renames")
            os.rename(new, current)
            self._fsync_directory()
            self.fault("install_after_second_rename")
            details = self._validate(current, new_hash)
            if prebacked:
                os.unlink(failed)
                self._fsync_directory()
        except Exception as original_error:
            try:
                if prebacked:
                    if current.exists(): os.unlink(current)
                    os.rename(failed, current)
                    self._fsync_directory()
                    self._validate(current, old_hash)
                else:
                    self._restore_after_install_failure(current, backup, failed, old_hash)
            except Exception as restore_error:
                raise HelperError(f"install failed and automatic rollback failed: {restore_error}") from original_error
            raise HelperError(f"install failed; original restored: {original_error}") from None
        return self._result("install", file_name, job_id, details)

    def rollback(self, file_name: str, job_id: str, expected_sha256: str) -> dict[str, object]:
        names = artifact_names(file_name, job_id)
        expected = validate_sha256(expected_sha256)
        current, backup = self._path(names["production"]), self._path(names["backup"])
        displaced = self._path(names["rollback_current"])
        restore = self._path(names["rollback_restore"])
        self._validate(current)
        self._validate(backup, expected)
        if displaced.exists() or restore.exists():
            raise HelperError("rollback temporary already exists")
        source_fd = self._open_read(backup)
        restore_fd = -1
        try:
            self.fault("rollback_before_restore_copy")
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            restore_fd = os.open(restore, flags, 0o600)
            while chunk := os.read(source_fd, 1024 * 1024):
                self._write_all(restore_fd, chunk)
                self.fault("rollback_during_restore_copy")
            self._set_metadata(restore_fd, restore)
            self.fault("rollback_before_restore_fsync")
            os.fsync(restore_fd)
            os.close(restore_fd); restore_fd = -1
            self._validate(restore, expected)
            self.fault("rollback_before_swap")
            os.rename(current, displaced)
            self.fault("rollback_after_first_rename")
            os.rename(restore, current)
            self._fsync_directory()
            self.fault("rollback_after_production_restored")
            details = self._validate(current, expected)
        except Exception as original_error:
            try:
                if displaced.exists():
                    if current.exists(): os.unlink(current)
                    os.rename(displaced, current)
                    self._fsync_directory()
                if restore.exists(): os.unlink(restore)
            except Exception as recovery_error:
                raise HelperError(f"rollback failed and current state requires intervention: {recovery_error}") from original_error
            raise HelperError(f"rollback failed; pre-rollback production restored: {original_error}") from None
        finally:
            os.close(source_fd)
            if restore_fd >= 0: os.close(restore_fd)
        os.unlink(displaced)
        self._fsync_directory()
        backup_details = self._validate(backup, expected)
        details["backup_preserved"] = True
        details["backup_sha256"] = backup_details["sha256"]
        return self._result("rollback", file_name, job_id, details)

    def cleanup(self, file_name: str, job_id: str, artifact: str) -> dict[str, object]:
        names = artifact_names(file_name, job_id)
        allowed = {"upload", "new", "backup", "rollback_current", "rollback_restore", "failed_new"}
        if artifact not in allowed:
            raise HelperError("cleanup artifact is not allowed")
        path = self._path(names[artifact])
        self._lstat_regular(path, metadata=False)
        os.unlink(path)
        self._fsync_directory()
        return self._result("cleanup", file_name, job_id, {"removed": path.name})

    def _result(self, operation: str, file_name: str, job_id: str | None, details: dict[str, object]) -> dict[str, object]:
        result: dict[str, object] = {"ok": True, "operation": operation, "file": file_name}
        if job_id is not None:
            result["job_id"] = job_id
        result.update(details)
        return result


def production_helper() -> ZipHelper:
    if os.name != "posix":
        raise HelperError("production helper requires POSIX")
    import grp
    import pwd
    owner = pwd.getpwnam(EXPECTED_OWNER)
    group = grp.getgrnam(EXPECTED_GROUP)
    if os.geteuid() != owner.pw_uid or os.getegid() != owner.pw_gid:
        raise HelperError("helper must run directly as plugi2090")
    root_info = os.lstat(DOWNLOAD_ROOT)
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise HelperError("fixed download root is not a real directory")
    if not root_info.st_mode & stat.S_ISVTX:
        raise HelperError("shared download root must have the sticky bit")
    return ZipHelper(expected_uid=owner.pw_uid, expected_gid=group.gr_gid)


def parser() -> argparse.ArgumentParser:
    common = JsonArgumentParser(add_help=False)
    common.add_argument("--file", required=True)
    job = JsonArgumentParser(add_help=False, parents=[common])
    job.add_argument("--job-id", required=True)
    root = JsonArgumentParser(prog="crapscraper-zip-helper")
    sub = root.add_subparsers(dest="operation", required=True)
    sub.add_parser("inspect", parents=[common])
    sub.add_parser("probe-setgid")
    prepare = sub.add_parser("prepare", parents=[job])
    prepare.add_argument("--expected-new-sha256", required=True)
    backup = sub.add_parser("backup", parents=[job])
    backup.add_argument("--expected-sha256", required=True)
    install = sub.add_parser("install", parents=[job])
    install.add_argument("--expected-old-sha256", required=True)
    install.add_argument("--expected-new-sha256", required=True)
    rollback = sub.add_parser("rollback", parents=[job])
    rollback.add_argument("--expected-sha256", required=True)
    cleanup = sub.add_parser("cleanup", parents=[job])
    cleanup.add_argument("--artifact", required=True, choices=["upload", "new", "backup", "rollback_current", "rollback_restore", "failed_new"])
    return root


def emit_error(operation: str, error: Exception) -> NoReturn:
    print(json.dumps({"ok": False, "operation": operation, "error": str(error)}, sort_keys=True))
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        helper = production_helper()
        operation = args.operation
        if operation == "inspect":
            result = helper.inspect(file_name=args.file)
        elif operation == "probe-setgid":
            result = helper.probe_setgid()
        elif operation == "prepare":
            result = helper.prepare(
                file_name=args.file,
                job_id=args.job_id,
                expected_new_sha256=args.expected_new_sha256,
            )
        elif operation == "backup":
            result = helper.backup(file_name=args.file, job_id=args.job_id,
                                   expected_sha256=args.expected_sha256)
        elif operation == "install":
            result = helper.install(
                file_name=args.file,
                job_id=args.job_id,
                expected_old_sha256=args.expected_old_sha256,
                expected_new_sha256=args.expected_new_sha256,
            )
        elif operation == "rollback":
            result = helper.rollback(
                file_name=args.file,
                job_id=args.job_id,
                expected_sha256=args.expected_sha256,
            )
        elif operation == "cleanup":
            result = helper.cleanup(
                file_name=args.file,
                job_id=args.job_id,
                artifact=args.artifact,
            )
        else:
            raise HelperError("unsupported operation")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        emit_error(getattr(args, "operation", "unknown"), error)


if __name__ == "__main__":
    main()
