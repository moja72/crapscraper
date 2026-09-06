from __future__ import annotations

import stat
from pathlib import Path

from app.updates.adapters import FilesystemInstaller, SFTPInstaller
from app.updates.target_preflight import TargetZipError, check_target


def test_filesystem_resolves_single_case_only_difference(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    actual = root / "AutomatorWP-BuddyPress.zip"
    actual.write_bytes(b"zip")
    installer = FilesystemInstaller(root)
    job = {"target_filename": "automatorwp-buddypress.zip"}

    result = check_target(installer, job)

    assert result["ok"] is True
    assert result["target_filename"] == "AutomatorWP-BuddyPress.zip"
    assert (root / result["target_filename"]).samefile(actual)
    assert job["target_filename"] == "AutomatorWP-BuddyPress.zip"


def test_filesystem_does_not_fuzzy_match_different_filename(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "automatorwp-buddypress-pro.zip").write_bytes(b"zip")
    installer = FilesystemInstaller(root)

    try:
        check_target(installer, {"target_filename": "automatorwp-buddypress.zip"})
    except TargetZipError as error:
        assert error.code == "target_zip_not_found"
    else:
        raise AssertionError("fuzzy filename must never be selected")


def test_sftp_resolves_single_case_only_difference():
    class Attr:
        st_mode = stat.S_IFREG | 0o644

    class Stream:
        def read(self, _n): return b"x"
        def close(self): pass

    class Sftp:
        def stat(self, path):
            if path.endswith("/AutomatorWP-BuddyPress.zip"):
                return Attr()
            raise FileNotFoundError(2, "No such file")

        def listdir(self, _root):
            return ["AutomatorWP-BuddyPress.zip", "other.zip"]

        def open(self, path, _mode):
            assert path.endswith("/AutomatorWP-BuddyPress.zip")
            return Stream()

        def close(self): pass

    class Client:
        def close(self): pass

    installer = SFTPInstaller()
    installer.root = "/home/plugintema.com/downloads"
    installer._connect = lambda: (Client(), Sftp())
    job = {"target_filename": "automatorwp-buddypress.zip"}

    result = check_target(installer, job)

    assert result["target_filename"] == "AutomatorWP-BuddyPress.zip"
    assert job["target_filename"] == "AutomatorWP-BuddyPress.zip"
