from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from deploy.crapscraper_zip_helper import (
    EXPECTED_MODE,
    HELPER_VERSION,
    HelperError,
    ZipHelper,
    artifact_names,
    validate_file_name,
)


NEW = b"new missing-target zip content"
sha = lambda value: hashlib.sha256(value).hexdigest()


class MissingTargetHelperCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        root_stat = os.stat(self.root)
        self.uid, self.gid = root_stat.st_uid, root_stat.st_gid
        self.file = "AutomatorWP BuddyPress (1).zip"
        self.job = "upd-safe_retry_1"
        self.names = artifact_names(self.file, self.job)
        self.helper = self.make_helper()

    def tearDown(self):
        self.temp.cleanup()

    def make_helper(self, **kwargs):
        return ZipHelper(
            self.root,
            expected_uid=kwargs.pop("uid", self.uid),
            expected_gid=kwargs.pop("gid", self.gid),
            owner_name="plugi2090",
            group_name="nobody",
            **kwargs,
        )

    def write(self, name, content=NEW, mode=0o644):
        path = self.root / name
        path.write_bytes(content)
        os.chmod(path, mode)
        return path

    def prepare(self):
        self.write(self.names["upload"])
        return self.helper.prepare(self.file, self.job, sha(NEW))

    def test_real_woocommerce_basename_with_spaces_and_parentheses_is_valid(self):
        self.assertEqual(validate_file_name(self.file), self.file)

    def test_capabilities_publish_missing_target_contract(self):
        payload = self.helper.capabilities()
        self.assertGreaterEqual(HELPER_VERSION, 2)
        self.assertEqual(payload["helper_version"], HELPER_VERSION)
        self.assertIn("install-missing", payload["operations"])
        self.assertIn("rollback-missing", payload["operations"])

    def test_prepare_is_idempotent_when_retry_staging_hash_matches(self):
        first = self.prepare()
        second = self.helper.prepare(self.file, self.job, sha(NEW))
        self.assertEqual(first["sha256"], sha(NEW))
        self.assertEqual(second["sha256"], sha(NEW))
        self.assertTrue(second["reused"])
        self.assertEqual((self.root / self.names["new"]).read_bytes(), NEW)

    def test_install_missing_and_rollback_missing_restore_original_absence(self):
        self.prepare()
        installed = self.helper.install_missing(self.file, self.job, sha(NEW))
        production = self.root / self.names["production"]
        self.assertTrue(installed["original_target_missing"])
        self.assertEqual(production.read_bytes(), NEW)
        self.assertFalse((self.root / self.names["new"]).exists())

        rolled = self.helper.rollback_missing(self.file, self.job, sha(NEW))
        self.assertTrue(rolled["restored_missing"])
        self.assertFalse(production.exists())

    def test_install_missing_refuses_target_that_appeared_after_preflight(self):
        self.prepare()
        self.write(self.names["production"], b"unexpected current", EXPECTED_MODE)
        with self.assertRaisesRegex(HelperError, "already exists"):
            self.helper.install_missing(self.file, self.job, sha(NEW))
        self.assertEqual((self.root / self.names["production"]).read_bytes(), b"unexpected current")

    def test_install_missing_failure_after_swap_restores_missing_state(self):
        self.prepare()

        def fault(stage):
            if stage == "install_missing_after_rename":
                raise OSError("injected")

        broken = self.make_helper(fault=fault)
        with self.assertRaisesRegex(HelperError, "original missing state restored"):
            broken.install_missing(self.file, self.job, sha(NEW))
        self.assertFalse((self.root / self.names["production"]).exists())
        self.assertEqual((self.root / self.names["new"]).read_bytes(), NEW)

    def test_rollback_missing_wrong_hash_does_not_remove_installed_file(self):
        self.prepare()
        self.helper.install_missing(self.file, self.job, sha(NEW))
        production = self.root / self.names["production"]
        with self.assertRaisesRegex(HelperError, "mismatch"):
            self.helper.rollback_missing(self.file, self.job, "0" * 64)
        self.assertEqual(production.read_bytes(), NEW)


if __name__ == "__main__":
    unittest.main()
