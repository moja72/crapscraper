#!/usr/bin/python3 -I
"""Restricted root helper for repairing legacy download ZIP ownership.

This helper does exactly one write operation: normalize owner/group/mode of one
regular ZIP inside the fixed PluginTema downloads directory. The caller must
provide the SHA-256 already observed by CrapScraper; no metadata is changed if
that hash no longer matches. Paths, symlinks and hard links are rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import NoReturn

DOWNLOAD_ROOT = Path("/home/plugintema.com/downloads")
EXPECTED_OWNER = "plugi2090"
EXPECTED_GROUP = "nobody"
EXPECTED_MODE = 0o674
HELPER_VERSION = 1
SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
FILE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9 ._()-]{0,199}\.zip\Z", re.IGNORECASE)


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


def validate_sha256(value: str) -> str:
    normalized = str(value or "").lower()
    if not SHA_RE.fullmatch(normalized):
        raise HelperError("invalid SHA-256")
    return normalized


def hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def production_identity() -> tuple[int, int]:
    if os.name != "posix":
        raise HelperError("permission helper requires POSIX")
    if os.geteuid() != 0:
        raise HelperError("permission helper must run as root")
    import grp
    import pwd
    owner = pwd.getpwnam(EXPECTED_OWNER)
    group = grp.getgrnam(EXPECTED_GROUP)
    return owner.pw_uid, group.gr_gid


def validate_root() -> None:
    info = os.lstat(DOWNLOAD_ROOT)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HelperError("fixed download root is not a real directory")


def repair(file_name: str, expected_sha256: str) -> dict[str, object]:
    name = validate_file_name(file_name)
    expected = validate_sha256(expected_sha256)
    owner_uid, group_gid = production_identity()
    validate_root()
    path = DOWNLOAD_ROOT / name
    if path.parent != DOWNLOAD_ROOT:
        raise HelperError("path escaped fixed root")

    try:
        before = os.lstat(path)
    except FileNotFoundError:
        raise HelperError("production ZIP is missing") from None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise HelperError("production ZIP is not a regular non-symlink file")
    if before.st_nlink != 1:
        raise HelperError("production ZIP has suspicious hard links")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise HelperError("production ZIP changed while opening")
        observed = hash_fd(fd)
        if observed != expected:
            raise HelperError("SHA-256 mismatch; permission repair refused")

        # The write is intentionally limited to ownership metadata. The file
        # contents and pathname are never replaced by this helper.
        os.fchown(fd, owner_uid, group_gid)
        os.fchmod(fd, EXPECTED_MODE)
        os.fsync(fd)
        after = os.fstat(fd)
        if after.st_uid != owner_uid or after.st_gid != group_gid:
            raise HelperError("owner/group normalization was not confirmed")
        if stat.S_IMODE(after.st_mode) != EXPECTED_MODE:
            raise HelperError("mode normalization was not confirmed")
        if hash_fd(fd) != expected:
            raise HelperError("SHA-256 changed during permission repair")
    finally:
        os.close(fd)

    fsync_directory(DOWNLOAD_ROOT)
    return {
        "ok": True,
        "operation": "repair",
        "file": name,
        "sha256": expected,
        "owner": EXPECTED_OWNER,
        "group": EXPECTED_GROUP,
        "mode": f"{EXPECTED_MODE:04o}",
    }


def capabilities() -> dict[str, object]:
    return {
        "ok": True,
        "operation": "capabilities",
        "helper_version": HELPER_VERSION,
        "fixed_root": str(DOWNLOAD_ROOT),
        "operations": ["repair"],
    }


def parser() -> argparse.ArgumentParser:
    root = JsonArgumentParser(prog="crapscraper-zip-permission-helper")
    sub = root.add_subparsers(dest="operation", required=True)
    sub.add_parser("capabilities")
    repair_parser = sub.add_parser("repair")
    repair_parser.add_argument("--file", required=True)
    repair_parser.add_argument("--expected-sha256", required=True)
    return root


def emit_error(operation: str, error: Exception) -> NoReturn:
    print(json.dumps({"ok": False, "operation": operation, "error": str(error)}, sort_keys=True))
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "capabilities":
            result = capabilities()
        elif args.operation == "repair":
            result = repair(args.file, args.expected_sha256)
        else:
            raise HelperError("unsupported operation")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        emit_error(getattr(args, "operation", "unknown"), error)


if __name__ == "__main__":
    main()
