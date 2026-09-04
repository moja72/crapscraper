from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Callable


_INSTALLED = False
_BASE_BACKUP: Callable[..., Any] | None = None
_PERMISSION_HELPER = "/usr/local/sbin/crapscraper-zip-permission-helper"


def _is_legacy_permission_failure(error: BaseException) -> bool:
    text = str(error or "").lower()
    return (
        "permission denied" in text
        and ("operation\": \"backup" in text or "operation': 'backup" in text or "operation: backup" in text)
    )


def _safe_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _repair_legacy_target(self: Any, job: dict[str, Any], expected_sha256: str) -> dict[str, Any]:
    artifacts = self._artifacts(job)
    file_name = os.path.basename(str(artifacts["production"]))
    expected = str(expected_sha256 or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("SHA-256 inválido para o reparo de permissões")

    client, sftp = self._connect()
    try:
        args = [
            "sudo", "-n", _PERMISSION_HELPER, "repair",
            "--file", file_name,
            "--expected-sha256", expected,
        ]
        _stdin, stdout, stderr = client.exec_command(shlex.join(args), timeout=90)
        status = stdout.channel.recv_exit_status()
        raw = stdout.read().decode("utf-8", "replace").strip()
        failure = stderr.read().decode("utf-8", "replace").strip()
        if status != 0:
            detail = failure or raw or "falha sem detalhe"
            raise RuntimeError(
                "Reparo seguro das permissões legadas não pôde ser executado. "
                f"Confirme {_PERMISSION_HELPER} no servidor e o sudoers do CrapScraper. Detalhe: {detail}"
            )
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Helper de permissões retornou resposta inválida") from error
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Helper de permissões não confirmou o reparo")
        observed = str(result.get("sha256") or "").lower()
        if observed != expected:
            raise RuntimeError("Helper de permissões não confirmou o SHA-256 esperado")
        return result
    finally:
        try:
            sftp.close()
        finally:
            client.close()


def _patched_backup(self: Any, job: dict[str, Any], attempt_dir: Path) -> Any:
    if _BASE_BACKUP is None:
        raise RuntimeError("Backup SFTP base indisponível")
    try:
        return _BASE_BACKUP(self, job, attempt_dir)
    except RuntimeError as first_error:
        if not _is_legacy_permission_failure(first_error):
            raise

        # O backup local já foi obtido por SFTP antes de o helper padrão tentar
        # abrir o ZIP. Ele é a evidência imutável usada para autorizar o reparo:
        # o helper root só altera owner/grupo/mode se o arquivo remoto ainda tiver
        # exatamente o mesmo SHA-256.
        local_backup = (
            Path(attempt_dir)
            / "backup"
            / os.path.basename(str(self._remote(job)))
        )
        if not local_backup.is_file():
            raise RuntimeError(
                "O ZIP remoto tem permissões legadas, mas o backup local de evidência não foi criado."
            ) from first_error
        expected_sha = _safe_sha256(local_backup)
        try:
            evidence = _repair_legacy_target(self, job, expected_sha)
        except Exception as repair_error:
            raise RuntimeError(
                "O ZIP atual existe, mas suas permissões/proprietário impedem o helper transacional "
                "de criar o backup. O reparo automático restrito não foi concluído: "
                + str(repair_error)
            ) from first_error

        job["legacy_permission_repair"] = {
            "sha256": expected_sha,
            "owner": evidence.get("owner"),
            "group": evidence.get("group"),
            "mode": evidence.get("mode"),
        }
        return _BASE_BACKUP(self, job, attempt_dir)


def install_legacy_permission_recovery() -> None:
    global _INSTALLED, _BASE_BACKUP
    if _INSTALLED:
        return

    from app.updates.adapters import SFTPInstaller

    if getattr(SFTPInstaller, "_crapscraper_legacy_permission_recovery_installed", False):
        _INSTALLED = True
        return

    _BASE_BACKUP = SFTPInstaller.backup
    SFTPInstaller.backup = _patched_backup
    SFTPInstaller._crapscraper_legacy_permission_recovery_installed = True
    _INSTALLED = True


__all__ = [
    "install_legacy_permission_recovery",
    "_is_legacy_permission_failure",
    "_repair_legacy_target",
]
