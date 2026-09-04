from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from deploy.crapscraper_zip_helper import EXPECTED_MODE, HelperError, ZipHelper, artifact_names


OLD = b"legacy current zip"
NEW = b"new canonical zip"
sha = lambda value: hashlib.sha256(value).hexdigest()


def _helper(root: Path) -> ZipHelper:
    info = os.stat(root)
    return ZipHelper(root, expected_uid=info.st_uid, expected_gid=info.st_gid,
                     owner_name="plugi2090", group_name="nobody")


def _write(path: Path, data: bytes, mode: int = EXPECTED_MODE) -> None:
    path.write_bytes(data)
    os.chmod(path, mode)


def test_backup_accepts_legacy_metadata_only_for_existing_production():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        helper = _helper(root)
        file_name, job_id = "Produto.zip", "JOB_legacy"
        current = root / file_name
        _write(current, OLD)

        strict = helper._validate
        calls = []

        def legacy_guard(path, expected_hash=None, *, metadata=True):
            calls.append((path.name, metadata))
            if path == current and metadata:
                raise HelperError("wrong owner for Produto.zip")
            return strict(path, expected_hash, metadata=metadata)

        helper._validate = legacy_guard
        result = helper.backup(file_name, job_id, sha(OLD))

        assert result["sha256"] == sha(OLD)
        assert (file_name, False) in calls
        backup_name = artifact_names(file_name, job_id)["backup"]
        assert (backup_name, True) in calls
        assert (root / backup_name).read_bytes() == OLD


def test_install_accepts_legacy_current_but_keeps_new_and_backup_strict():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        helper = _helper(root)
        file_name, job_id = "Produto.zip", "JOB_install"
        names = artifact_names(file_name, job_id)
        current = root / file_name
        _write(current, OLD)
        helper.backup(file_name, job_id, sha(OLD))
        _write(root / names["upload"], NEW, 0o600)
        helper.prepare(file_name, job_id, sha(NEW))

        strict = helper._validate
        calls = []

        def legacy_guard(path, expected_hash=None, *, metadata=True):
            calls.append((path.name, metadata))
            if path == current and metadata and path.read_bytes() == OLD:
                raise HelperError("wrong owner for Produto.zip")
            return strict(path, expected_hash, metadata=metadata)

        helper._validate = legacy_guard
        result = helper.install(file_name, job_id, sha(OLD), sha(NEW))

        assert result["sha256"] == sha(NEW)
        assert current.read_bytes() == NEW
        assert (file_name, False) in calls
        assert (names["new"], True) in calls
        assert (file_name, True) in calls
        assert (root / names["backup"]).read_bytes() == OLD
