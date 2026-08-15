from __future__ import annotations

import unittest

from app.integrations.ssh_helper import RestrictedSSHHelperClient, SSHDeploymentArtifacts, SSHHelperRequest
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError


HASH = "a" * 64


class SSHHelperClientTests(unittest.TestCase):
    def test_remote_failure_preserves_sanitized_helper_reason(self):
        class Channel:
            def recv_exit_status(self): return 1
        class Stream:
            def __init__(self, value): self.value, self.channel = value, Channel()
            def read(self): return self.value
        class SSH:
            def exec_command(self, _command, timeout=60):
                return None, Stream(b''), Stream(b'{"ok":false,"error":"permission denied password=hidden"}')
        client = RestrictedSSHHelperClient(SSH(), execution_enabled=True)
        with self.assertRaisesRegex(IntegrationError, r"permission denied password=\[redacted\]"):
            client.invoke(SSHHelperRequest("backup", "Produto.zip", "JOB-1", expected_sha256=HASH))

    def test_builds_rigid_sftp_staging_name(self):
        paths = SSHDeploymentArtifacts("Produto.zip", "JOB-1").paths()
        self.assertEqual(paths["upload"], "/home/plugintema.com/downloads/Produto.zip.crapscraper.JOB-1.upload")

    def test_builds_only_fixed_sudo_helper_command(self):
        command = RestrictedSSHHelperClient.command(SSHHelperRequest(
            "install", "Produto.zip", "JOB-1",
            expected_old_sha256=HASH, expected_new_sha256="b" * 64,
        ))
        self.assertEqual(command.split()[:6], ["sudo", "-n", "-u", "plugi2090", "/usr/local/sbin/crapscraper-zip-helper", "install"])
        self.assertNotIn("bash", command)

    def test_backup_command_is_scoped_to_job_file_and_original_hash(self):
        argv = SSHHelperRequest("backup", "Produto.zip", "JOB-1", expected_sha256=HASH).argv()
        self.assertEqual(argv[-2:], ["--expected-sha256", HASH])
        self.assertIn("JOB-1", argv)

    def test_arbitrary_operation_and_shell_metacharacters_rejected(self):
        bad = (
            SSHHelperRequest("exec", "Produto.zip"),
            SSHHelperRequest("inspect", "Produto;id.zip"),
            SSHHelperRequest("prepare", "Produto.zip", "JOB$(id)", expected_new_sha256=HASH),
            SSHHelperRequest("rollback", "Produto.zip", "JOB", expected_sha256="a;id"),
        )
        for request in bad:
            with self.subTest(request=request), self.assertRaises(IntegrationError): request.argv()

    def test_extra_arguments_and_arbitrary_cleanup_rejected(self):
        with self.assertRaises(IntegrationError):
            SSHHelperRequest("inspect", "Produto.zip", job_id="JOB").argv()
        with self.assertRaises(IntegrationError):
            SSHHelperRequest("cleanup", "Produto.zip", "JOB", artifact="production").argv()

    def test_remote_execution_remains_disabled(self):
        with self.assertRaises(WriteOperationDisabledError):
            RestrictedSSHHelperClient().invoke(SSHHelperRequest("inspect", "Produto.zip"))


if __name__ == "__main__": unittest.main()
