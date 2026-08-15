"""Validated command builder for the future restricted SSH helper invocation."""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping

from app import settings
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError

HELPER_PATH = "/usr/local/sbin/crapscraper-zip-helper"
RUN_AS_USER = "plugi2090"
FILE_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.zip\Z", re.IGNORECASE)
JOB_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
OPERATIONS = frozenset({"inspect", "backup", "prepare", "install", "rollback", "cleanup"})
CLEANUP_ARTIFACTS = frozenset({"upload", "new", "backup", "rollback_current", "rollback_restore", "failed_new"})


def _file(value: str) -> str:
    if not value or "/" in value or "\\" in value or ".." in value or not FILE_RE.fullmatch(value):
        raise IntegrationError("Nome ZIP invalido para o helper")
    return value


def _job(value: str) -> str:
    if not JOB_RE.fullmatch(value or ""):
        raise IntegrationError("job_id invalido para o helper")
    return value


def _sha(value: str) -> str:
    normalized = (value or "").lower()
    if not SHA_RE.fullmatch(normalized):
        raise IntegrationError("SHA-256 invalido para o helper")
    return normalized


@dataclass(frozen=True)
class SSHDeploymentArtifacts:
    """Exact remote names an SFTP uploader and helper will share for one job."""
    file: str
    job_id: str

    def paths(self) -> Mapping[str, str]:
        file_name, job = _file(self.file), _job(self.job_id)
        prefix = f"{file_name}.crapscraper.{job}"
        root = PurePosixPath(settings.SSH_DOWNLOAD_ROOT)
        return {
            "production": str(root / file_name),
            "upload": str(root / (prefix + ".upload")),
            "new": str(root / (prefix + ".new")),
            "backup": str(root / (prefix + ".bak")),
        }


@dataclass(frozen=True)
class SSHHelperRequest:
    operation: str
    file: str
    job_id: str | None = None
    expected_old_sha256: str | None = None
    expected_new_sha256: str | None = None
    expected_sha256: str | None = None
    artifact: str | None = None

    def argv(self) -> list[str]:
        if self.operation not in OPERATIONS:
            raise IntegrationError("Operacao do helper nao autorizada")
        args = ["sudo", "-n", "-u", RUN_AS_USER, HELPER_PATH, self.operation, "--file", _file(self.file)]
        if self.operation == "inspect":
            if any((self.job_id, self.expected_old_sha256, self.expected_new_sha256, self.expected_sha256, self.artifact)):
                raise IntegrationError("Argumentos extras nao permitidos para inspect")
            return args
        args += ["--job-id", _job(self.job_id or "")]
        if self.operation == "backup":
            args += ["--expected-sha256", _sha(self.expected_sha256 or "")]
        elif self.operation == "prepare":
            args += ["--expected-new-sha256", _sha(self.expected_new_sha256 or "")]
        elif self.operation == "install":
            args += ["--expected-old-sha256", _sha(self.expected_old_sha256 or ""),
                     "--expected-new-sha256", _sha(self.expected_new_sha256 or "")]
        elif self.operation == "rollback":
            args += ["--expected-sha256", _sha(self.expected_sha256 or "")]
        elif self.operation == "cleanup":
            if self.artifact not in CLEANUP_ARTIFACTS:
                raise IntegrationError("Artefato de cleanup nao autorizado")
            args += ["--artifact", self.artifact]
        supplied = {
            "backup": (self.expected_old_sha256, self.expected_new_sha256, self.artifact),
            "prepare": (self.expected_old_sha256, self.expected_sha256, self.artifact),
            "install": (self.expected_sha256, self.artifact),
            "rollback": (self.expected_old_sha256, self.expected_new_sha256, self.artifact),
            "cleanup": (self.expected_old_sha256, self.expected_new_sha256, self.expected_sha256),
        }[self.operation]
        if any(supplied):
            raise IntegrationError("Argumentos extras nao permitidos para operacao")
        return args


class RestrictedSSHHelperClient:
    """No generic command API; remote execution remains disabled in this phase."""

    def __init__(self, ssh_client: Any = None, *, execution_enabled: bool = settings.SSH_HELPER_EXECUTION_ENABLED) -> None:
        self._ssh_client = ssh_client
        self.execution_enabled = bool(execution_enabled)

    @staticmethod
    def command(request: SSHHelperRequest) -> str:
        # shlex is defense in depth; every dynamic field was already allowlisted.
        return shlex.join(request.argv())

    def invoke(self, request: SSHHelperRequest) -> Mapping[str, Any]:
        if not self.execution_enabled:
            raise WriteOperationDisabledError("Execucao remota do helper desabilitada nesta fase")
        if self._ssh_client is None:
            raise IntegrationError("Conexao SSH nao configurada")
        command = self.command(request)
        _stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=60)
        status = stdout.channel.recv_exit_status()
        raw = stdout.read().decode("utf-8", "replace")
        raw_error = stderr.read().decode("utf-8", "replace")
        if status != 0:
            detail = raw_error.strip() or raw.strip()
            try:
                parsed = json.loads(detail)
                detail = str(parsed.get("error") or "") if isinstance(parsed, dict) else ""
            except (TypeError, json.JSONDecodeError):
                pass
            detail = re.sub(
                r"(?i)(password|senha|consumer[_ -]?(?:key|secret)|authorization|cookie)\s*[:=]\s*[^\s,;]+",
                lambda match: match.group(1) + "=[redacted]", detail,
            )
            raise IntegrationError(
                f"Helper remoto retornou falha: {detail}" if detail else "Helper remoto retornou falha"
            )
        try:
            result = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise IntegrationError("Resposta JSON invalida do helper") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise IntegrationError("Helper remoto nao confirmou sucesso")
        return result
