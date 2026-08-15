from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from deploy.crapscraper_zip_helper import (
    EXPECTED_MODE, HelperError, ZipHelper, artifact_names,
    main, parser, validate_file_name, validate_job_id,
)


OLD = b"old zip content"
NEW = b"new zip content"
sha = lambda value: hashlib.sha256(value).hexdigest()


class HelperCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        root_stat = os.stat(self.root)
        self.uid, self.gid = root_stat.st_uid, root_stat.st_gid
        self.file, self.job = "Produto.zip", "JOB_123"
        self.names = artifact_names(self.file, self.job)
        self.write(self.names["production"], OLD)
        self.helper = self.make_helper()

    def tearDown(self): self.temp.cleanup()

    def make_helper(self, **kwargs):
        return ZipHelper(self.root, expected_uid=kwargs.pop("uid", self.uid),
                         expected_gid=kwargs.pop("gid", self.gid),
                         owner_name="plugi2090", group_name="nobody", **kwargs)

    def write(self, name, content, mode=EXPECTED_MODE):
        path = self.root / name
        path.write_bytes(content)
        os.chmod(path, mode)
        return path

    def prepare(self):
        self.write(self.names["upload"], NEW, 0o600)
        return self.helper.prepare(self.file, self.job, sha(NEW))

    def install(self):
        self.prepare()
        return self.helper.install(self.file, self.job, sha(OLD), sha(NEW))

    def test_valid_basename_and_inspect_json(self):
        self.assertEqual(validate_file_name(self.file), self.file)
        result = self.helper.inspect(self.file)
        self.assertTrue(result["ok"])
        self.assertEqual(json.loads(json.dumps(result))["mode"], "0674")

    def test_path_traversal_absolute_slashes_and_extension_rejected(self):
        for value in ("../Produto.zip", "/tmp/Produto.zip", "a/b.zip", "a\\b.zip", "Produto.tar", "", "a..b.zip"):
            with self.subTest(value=value), self.assertRaises(HelperError):
                validate_file_name(value)

    def test_job_id_validation(self):
        self.assertEqual(validate_job_id("A-b_9"), "A-b_9")
        for value in ("", "../x", "a;b", "a b", "x" * 65):
            with self.subTest(value=value), self.assertRaises(HelperError): validate_job_id(value)

    def test_symlink_and_nonregular_rejected(self):
        link = self.root / "Link.zip"
        try:
            link.symlink_to(self.root / self.file)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(HelperError): self.helper.inspect("Link.zip")
        (self.root / "Directory.zip").mkdir()
        with self.assertRaises(HelperError): self.helper.inspect("Directory.zip")

    def test_suspicious_hardlink_rejected(self):
        try:
            os.link(self.root / self.file, self.root / "Hard.zip")
        except OSError:
            self.skipTest("hardlinks unavailable")
        with self.assertRaises(HelperError): self.helper.inspect("Hard.zip")

    def test_incorrect_staging_and_new_hash(self):
        with self.assertRaisesRegex(HelperError, "missing"):
            self.helper.prepare(self.file, self.job, sha(NEW))
        self.write(self.names["upload"], b"wrong", 0o600)
        with self.assertRaisesRegex(HelperError, "staging"):
            self.helper.prepare(self.file, self.job, sha(NEW))
        self.assertFalse((self.root / self.names["new"]).exists())

    def test_prepare_creates_owned_mode_and_hash_validated_copy(self):
        result = self.prepare()
        self.assertEqual(result["sha256"], sha(NEW))
        self.assertEqual(result["owner"], "plugi2090")
        self.assertEqual(result["group"], "nobody")
        self.assertEqual(result["mode"], "0674")
        self.assertEqual((self.root / self.names["new"]).read_bytes(), NEW)

    def test_prepare_consumes_world_readable_sftp_staging(self):
        self.write(self.names["upload"], NEW, 0o644)
        result = self.helper.prepare(self.file, self.job, sha(NEW))
        self.assertEqual(result["sha256"], sha(NEW))
        self.assertEqual(result["mode"], "0674")

    def test_setgid_probe_is_disposable_and_reports_inherited_identity(self):
        result = self.helper.probe_setgid()
        self.assertEqual(result["owner"], "plugi2090")
        self.assertEqual(result["group"], "nobody")
        self.assertTrue(result["removed"])
        self.assertFalse(any(self.root.glob("CrapScraperSetgidProbe*")))

    def test_prepare_blocks_instead_of_changing_wrong_inherited_group(self):
        self.write(self.names["upload"], NEW, 0o600)
        helper = self.make_helper(gid=self.gid + 1)
        with self.assertRaisesRegex(HelperError, "inherit group nobody"):
            helper.prepare(self.file, self.job, sha(NEW))
        self.assertFalse((self.root / self.names["new"]).exists())

    def test_old_hash_mismatch_fails_before_rename(self):
        self.prepare()
        with self.assertRaisesRegex(HelperError, "mismatch"):
            self.helper.install(self.file, self.job, "0" * 64, sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)

    def test_new_hash_mismatch_fails_before_rename(self):
        self.prepare()
        with self.assertRaisesRegex(HelperError, "mismatch"):
            self.helper.install(self.file, self.job, sha(OLD), "0" * 64)
        self.assertEqual((self.root / self.file).read_bytes(), OLD)

    def test_existing_backup_blocks_install(self):
        self.prepare(); self.write(self.names["backup"], b"collision")
        with self.assertRaisesRegex(HelperError, "already exists"):
            self.helper.install(self.file, self.job, sha(OLD), sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)

    def test_backup_is_validated_and_never_overwritten(self):
        result = self.helper.backup(self.file, self.job, sha(OLD))
        self.assertEqual(result["sha256"], sha(OLD))
        self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)
        with self.assertRaisesRegex(HelperError, "already exists"):
            self.helper.backup(self.file, self.job, sha(OLD))

    def test_backup_rejects_wrong_hash_and_symlink_inputs(self):
        with self.assertRaisesRegex(HelperError, "mismatch"):
            self.helper.backup(self.file, self.job, "0" * 64)
        self.assertFalse((self.root / self.names["backup"]).exists())
        original = self.root / self.file
        original.unlink()
        try: original.symlink_to(self.root / "actual.zip")
        except OSError: self.skipTest("symlinks unavailable")
        self.write("actual.zip", OLD)
        with self.assertRaisesRegex(HelperError, "non-symlink"):
            self.helper.backup(self.file, self.job, sha(OLD))

    def test_backup_partial_copy_and_fsync_failures_remove_partial(self):
        for stage in ("backup_during_copy", "backup_before_fsync"):
            with self.subTest(stage=stage):
                def fault(value):
                    if value == stage: raise OSError("injected")
                with self.assertRaises(OSError):
                    self.make_helper(fault=fault).backup(self.file, self.job, sha(OLD))
                self.assertEqual((self.root / self.file).read_bytes(), OLD)
                self.assertFalse((self.root / self.names["backup"]).exists())
        with patch("deploy.crapscraper_zip_helper.os.fsync", side_effect=OSError("fsync failed")):
            with self.assertRaisesRegex(OSError, "fsync failed"):
                self.helper.backup(self.file, self.job, sha(OLD))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)
        self.assertFalse((self.root / self.names["backup"]).exists())

    def test_install_with_prevalidated_backup_preserves_old_on_success_and_faults(self):
        self.helper.backup(self.file, self.job, sha(OLD)); self.prepare()
        self.helper.install(self.file, self.job, sha(OLD), sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), NEW)
        self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)
        for stage in ("install_before_first_rename", "install_between_renames", "install_after_second_rename"):
            with self.subTest(stage=stage):
                for name in self.names.values():
                    path = self.root / name
                    if path.exists() or path.is_symlink(): path.unlink()
                self.write(self.names["production"], OLD)
                helper = self.make_helper(); helper.backup(self.file, self.job, sha(OLD))
                self.prepare()
                def fault(value):
                    if value == stage: raise OSError("injected")
                with self.assertRaises(Exception):
                    self.make_helper(fault=fault).install(self.file, self.job, sha(OLD), sha(NEW))
                self.assertEqual((self.root / self.file).read_bytes(), OLD)
                self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)

    def test_failure_before_first_rename_changes_nothing(self):
        self.prepare()
        broken = self.make_helper(fault=lambda stage: (_ for _ in ()).throw(OSError("injected")) if stage == "install_before_first_rename" else None)
        with self.assertRaises(OSError): broken.install(self.file, self.job, sha(OLD), sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)
        self.assertFalse((self.root / self.names["backup"]).exists())

    def test_failure_between_renames_rolls_back_automatically(self):
        self.prepare()
        def fault(stage):
            if stage == "install_between_renames": raise OSError("injected")
        with self.assertRaisesRegex(HelperError, "original restored"):
            self.make_helper(fault=fault).install(self.file, self.job, sha(OLD), sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)
        self.assertFalse((self.root / self.names["backup"]).exists())

    def test_post_swap_validation_failure_rolls_back(self):
        self.prepare()
        def fault(stage):
            if stage == "install_after_second_rename": raise OSError("injected")
        with self.assertRaisesRegex(HelperError, "original restored"):
            self.make_helper(fault=fault).install(self.file, self.job, sha(OLD), sha(NEW))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)

    def test_success_preserves_backup_and_explicit_rollback(self):
        result = self.install()
        self.assertEqual(result["sha256"], sha(NEW))
        self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)
        rolled = self.helper.rollback(self.file, self.job, sha(OLD))
        self.assertEqual(rolled["sha256"], sha(OLD))
        self.assertEqual((self.root / self.file).read_bytes(), OLD)
        self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)
        self.assertFalse((self.root / self.names["rollback_current"]).exists())
        self.assertFalse((self.root / self.names["rollback_restore"]).exists())

    def test_explicit_rollback_failure_restores_pre_rollback_state(self):
        self.install()
        def fault(stage):
            if stage == "rollback_after_production_restored": raise OSError("injected")
        with self.assertRaisesRegex(HelperError, "pre-rollback production restored"):
            self.make_helper(fault=fault).rollback(self.file, self.job, sha(OLD))
        self.assertEqual((self.root / self.file).read_bytes(), NEW)
        self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)

    def test_rollback_faults_preserve_backup_and_known_production(self):
        stages = (
            "rollback_before_restore_copy", "rollback_during_restore_copy",
            "rollback_before_restore_fsync", "rollback_before_swap",
            "rollback_after_first_rename", "rollback_after_production_restored",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                for name in self.names.values():
                    path = self.root / name
                    if path.exists() or path.is_symlink(): path.unlink()
                self.write(self.names["production"], OLD)
                helper = self.make_helper(); helper.backup(self.file, self.job, sha(OLD))
                self.prepare(); helper.install(self.file, self.job, sha(OLD), sha(NEW))
                def fault(value):
                    if value == stage: raise OSError("injected")
                with self.assertRaises(HelperError):
                    self.make_helper(fault=fault).rollback(self.file, self.job, sha(OLD))
                self.assertEqual((self.root / self.file).read_bytes(), NEW)
                self.assertEqual((self.root / self.names["backup"]).read_bytes(), OLD)
                self.assertEqual(sha((self.root / self.names["backup"]).read_bytes()), sha(OLD))

    def test_rollback_rejects_invalid_or_symlink_backup(self):
        self.prepare(); self.helper.install(self.file, self.job, sha(OLD), sha(NEW))
        backup = self.root / self.names["backup"]
        backup.write_bytes(b"invalid")
        with self.assertRaisesRegex(HelperError, "mismatch"):
            self.helper.rollback(self.file, self.job, sha(OLD))
        self.assertEqual((self.root / self.file).read_bytes(), NEW)
        backup.unlink()
        try: backup.symlink_to(self.root / self.file)
        except OSError: self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(HelperError, "non-symlink"):
            self.helper.rollback(self.file, self.job, sha(OLD))

    def test_wrong_owner_group_and_mode_rejected(self):
        with self.assertRaisesRegex(HelperError, "owner"):
            self.make_helper(uid=self.uid + 1).inspect(self.file)
        with self.assertRaisesRegex(HelperError, "group"):
            self.make_helper(gid=self.gid + 1).inspect(self.file)
        os.chmod(self.root / self.file, 0o444)
        with self.assertRaisesRegex(HelperError, "mode"):
            self.helper.inspect(self.file)

    def test_cleanup_is_limited_and_never_removes_production(self):
        self.write(self.names["upload"], NEW)
        result = self.helper.cleanup(self.file, self.job, "upload")
        self.assertIn(".upload", result["removed"])
        self.assertTrue((self.root / self.file).exists())
        with self.assertRaises(HelperError): self.helper.cleanup(self.file, self.job, "production")

    def test_parser_rejects_arbitrary_command(self):
        with self.assertRaises(SystemExit): parser().parse_args(["shell", "--file", self.file])


class HelperCliDispatcherCase(unittest.TestCase):
    file = "Produto.zip"
    job = "JOB_123"
    old_hash = "1" * 64
    new_hash = "2" * 64

    def run_cli(self, argv, method):
        helper = Mock(spec=ZipHelper)
        getattr(helper, method).return_value = {
            "ok": True,
            "operation": argv[0],
            "file": self.file,
        }
        output = io.StringIO()
        with patch(
            "deploy.crapscraper_zip_helper.production_helper",
            return_value=helper,
        ), redirect_stdout(output):
            self.assertEqual(main(argv), 0)
        self.assertTrue(json.loads(output.getvalue())["ok"])
        return helper

    def test_cli_dispatches_inspect_file_as_file_name(self):
        helper = self.run_cli(["inspect", "--file", self.file], "inspect")
        helper.inspect.assert_called_once_with(file_name=self.file)

    def test_cli_dispatches_probe_setgid_without_arguments(self):
        helper = self.run_cli(["probe-setgid"], "probe_setgid")
        helper.probe_setgid.assert_called_once_with()

    def test_cli_dispatches_prepare_with_explicit_arguments(self):
        helper = self.run_cli([
            "prepare", "--file", self.file, "--job-id", self.job,
            "--expected-new-sha256", self.new_hash,
        ], "prepare")
        helper.prepare.assert_called_once_with(
            file_name=self.file, job_id=self.job,
            expected_new_sha256=self.new_hash,
        )

    def test_cli_dispatches_backup_with_explicit_arguments(self):
        helper = self.run_cli([
            "backup", "--file", self.file, "--job-id", self.job,
            "--expected-sha256", self.old_hash,
        ], "backup")
        helper.backup.assert_called_once_with(
            file_name=self.file, job_id=self.job, expected_sha256=self.old_hash,
        )

    def test_cli_dispatches_install_with_explicit_arguments(self):
        helper = self.run_cli([
            "install", "--file", self.file, "--job-id", self.job,
            "--expected-old-sha256", self.old_hash,
            "--expected-new-sha256", self.new_hash,
        ], "install")
        helper.install.assert_called_once_with(
            file_name=self.file, job_id=self.job,
            expected_old_sha256=self.old_hash,
            expected_new_sha256=self.new_hash,
        )

    def test_cli_dispatches_rollback_with_explicit_arguments(self):
        helper = self.run_cli([
            "rollback", "--file", self.file, "--job-id", self.job,
            "--expected-sha256", self.old_hash,
        ], "rollback")
        helper.rollback.assert_called_once_with(
            file_name=self.file, job_id=self.job,
            expected_sha256=self.old_hash,
        )

    def test_cli_dispatches_cleanup_with_explicit_arguments(self):
        helper = self.run_cli([
            "cleanup", "--file", self.file, "--job-id", self.job,
            "--artifact", "upload",
        ], "cleanup")
        helper.cleanup.assert_called_once_with(
            file_name=self.file, job_id=self.job, artifact="upload",
        )

    def test_cli_rejects_extra_arguments_before_dispatch(self):
        with patch("deploy.crapscraper_zip_helper.production_helper") as factory:
            with self.assertRaises(SystemExit):
                main(["inspect", "--file", self.file, "--job-id", self.job])
            factory.assert_not_called()

    def test_cli_rejects_arbitrary_operation_before_dispatch(self):
        with patch("deploy.crapscraper_zip_helper.production_helper") as factory:
            with self.assertRaises(SystemExit):
                main(["shell", "--file", self.file])
            factory.assert_not_called()


if __name__ == "__main__": unittest.main()
