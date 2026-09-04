from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
from pathlib import Path
from typing import Any


_INSTALLED = False
_MARKER = b"CRAPSCRAPER_ORIGINAL_TARGET_MISSING_V1\n"
_REQUIRED_REMOTE_OPERATIONS = {"install-missing", "rollback-missing"}


def _marker_backup(job: dict[str, Any], attempt_dir: Path) -> Path:
    marker = attempt_dir / "backup" / "original-target-missing.marker"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(_MARKER)
    job["_target_missing_backup_sha"] = hashlib.sha256(_MARKER).hexdigest()
    return marker


def _patch_preflight() -> None:
    import app.updates.executor as executor_module
    from app.updates.target_preflight import TargetZipError

    if getattr(executor_module, "_missing_target_preflight_installed", False):
        return
    original = executor_module.check_target

    def check_target_allow_missing(installer: Any, job: dict[str, Any]) -> dict[str, Any]:
        try:
            return original(installer, job)
        except TargetZipError as error:
            if error.reason != "missing":
                raise
            # A URL/filename continua vindo do WooCommerce. Somente a ausência
            # física deixa de abortar: o estado original passa a ser "ausente"
            # e o rollback seguro precisa restaurar exatamente esse estado.
            job["_target_originally_missing"] = True
            job["_target_missing_path"] = error.path
            return {
                "ok": True,
                "checked": False,
                "missing": True,
                "target_filename": error.filename,
                "target_path": error.path,
            }

    executor_module.check_target = check_target_allow_missing
    executor_module._missing_target_preflight_installed = True


def _patch_filesystem_installer() -> None:
    from app.updates.adapters import FilesystemInstaller

    if getattr(FilesystemInstaller, "_missing_target_recovery_installed", False):
        return
    original_backup = FilesystemInstaller.backup
    original_install = FilesystemInstaller.install
    original_rollback = FilesystemInstaller.rollback
    original_validate = FilesystemInstaller.validate

    def backup(self: Any, job: dict[str, Any], attempt_dir: Path) -> Path:
        if not job.get("_target_originally_missing"):
            return original_backup(self, job, attempt_dir)
        target = self._target(job)
        if target.exists():
            job.pop("_target_originally_missing", None)
            return original_backup(self, job, attempt_dir)
        return _marker_backup(job, attempt_dir)

    def install(self: Any, job: dict[str, Any], artifact: Path, backup_path: Path) -> None:
        if not job.get("_target_originally_missing"):
            return original_install(self, job, artifact, backup_path)
        target = self._target(job)
        if os.path.lexists(target):
            raise RuntimeError(
                "O ZIP de destino apareceu depois do preflight; atualização interrompida para não sobrescrever um arquivo novo."
            )
        temporary = target.with_suffix(target.suffix + ".crapscraper-missing-install")
        if os.path.lexists(temporary):
            temporary.unlink()
        shutil.copy2(artifact, temporary)
        new_sha = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != new_sha:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("SHA-256 do staging local divergiu antes de recriar o ZIP ausente.")
        os.replace(temporary, target)
        job["_target_missing_installed_sha"] = new_sha

    def rollback(self: Any, job: dict[str, Any], backup_path: Path) -> None:
        if not job.get("_target_originally_missing"):
            return original_rollback(self, job, backup_path)
        target = self._target(job)
        expected = str(job.get("_target_missing_installed_sha") or "")
        if target.exists():
            observed = hashlib.sha256(target.read_bytes()).hexdigest()
            if not expected or observed != expected:
                raise RuntimeError(
                    "Rollback do ZIP originalmente ausente foi bloqueado: o arquivo atual não corresponde ao artefato instalado por esta tentativa."
                )
            target.unlink()
        job["_target_missing_rollback_done"] = True

    def validate(self: Any, job: dict[str, Any], sha256: str) -> bool:
        marker_sha = str(job.get("_target_missing_backup_sha") or "")
        if job.get("_target_originally_missing") and marker_sha and sha256 == marker_sha:
            return not os.path.lexists(self._target(job))
        return original_validate(self, job, sha256)

    FilesystemInstaller.backup = backup
    FilesystemInstaller.install = install
    FilesystemInstaller.rollback = rollback
    FilesystemInstaller.validate = validate
    FilesystemInstaller._missing_target_recovery_installed = True


def _patch_sftp_installer() -> None:
    from app.updates.adapters import SFTPInstaller

    if getattr(SFTPInstaller, "_missing_target_recovery_installed", False):
        return
    original_backup = SFTPInstaller.backup
    original_install = SFTPInstaller.install
    original_rollback = SFTPInstaller.rollback
    original_validate = SFTPInstaller.validate
    original_helper = SFTPInstaller._helper
    original_check = SFTPInstaller.check

    def _run_capabilities(self: Any) -> dict[str, Any]:
        client, sftp = self._connect()
        try:
            args = [
                "sudo", "-n", "-u", "plugi2090",
                "/usr/local/sbin/crapscraper-zip-helper", "capabilities",
            ]
            _stdin, stdout, stderr = client.exec_command(shlex.join(args), timeout=30)
            status = stdout.channel.recv_exit_status()
            raw = stdout.read().decode("utf-8", "replace")
            failure = stderr.read().decode("utf-8", "replace").strip()
            if status != 0:
                raise RuntimeError(failure or raw.strip() or "helper sem suporte a capabilities")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get("ok") is not True:
                raise RuntimeError("helper remoto não confirmou capabilities")
            return payload
        finally:
            sftp.close()
            client.close()

    def check(self: Any) -> dict[str, Any]:
        base = original_check(self)
        if not base.get("ok"):
            return base
        try:
            capabilities = _run_capabilities(self)
            operations = {str(item) for item in capabilities.get("operations") or []}
            version = int(capabilities.get("helper_version") or 0)
            missing = sorted(_REQUIRED_REMOTE_OPERATIONS - operations)
            if version < 2 or missing:
                return {
                    "ok": False,
                    "message": (
                        "Helper remoto do CrapScraper está desatualizado. "
                        "Instale a versão do repositório antes de executar atualizações."
                    ),
                    "helper_version": version,
                    "missing_operations": missing,
                }
            return {
                **base,
                "helper_version": version,
                "message": f"{base.get('message') or self.root} · helper v{version} validado",
            }
        except Exception as error:
            return {
                "ok": False,
                "message": (
                    "Não foi possível validar o helper remoto do CrapScraper. "
                    f"Atualizações foram bloqueadas até o helper ser implantado: {error}"
                ),
            }

    def helper(
        self: Any,
        client: Any,
        operation: str,
        job: dict[str, Any],
        *,
        old_sha: str = "",
        new_sha: str = "",
    ) -> dict[str, Any]:
        if operation not in {"install-missing", "rollback-missing"}:
            return original_helper(self, client, operation, job, old_sha=old_sha, new_sha=new_sha)
        artifacts = self._artifacts(job)
        name = os.path.basename(artifacts["production"])
        job_id = str(job["job_id"])
        normalized = str(new_sha or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ValueError("SHA-256 inválido para o helper")
        args = [
            "sudo", "-n", "-u", "plugi2090", "/usr/local/sbin/crapscraper-zip-helper",
            operation, "--file", name, "--job-id", job_id,
            "--expected-new-sha256", normalized,
        ]
        _stdin, stdout, stderr = client.exec_command(shlex.join(args), timeout=90)
        status = stdout.channel.recv_exit_status()
        raw = stdout.read().decode("utf-8", "replace")
        failure = stderr.read().decode("utf-8", "replace").strip()
        if status != 0:
            raise RuntimeError("Helper remoto recusou a operação: " + (failure or raw.strip() or "falha sem detalhe"))
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Helper remoto retornou resposta inválida") from error
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("Helper remoto não confirmou sucesso")
        return result

    def backup(self: Any, job: dict[str, Any], attempt_dir: Path) -> Path:
        if not job.get("_target_originally_missing"):
            return original_backup(self, job, attempt_dir)
        client, sftp = self._connect()
        try:
            try:
                sftp.stat(self._remote(job))
            except (FileNotFoundError, OSError) as error:
                if isinstance(error, FileNotFoundError) or getattr(error, "errno", None) == 2:
                    return _marker_backup(job, attempt_dir)
                raise
            job.pop("_target_originally_missing", None)
        finally:
            sftp.close()
            client.close()
        return original_backup(self, job, attempt_dir)

    def install(self: Any, job: dict[str, Any], artifact: Path, backup_path: Path) -> None:
        if not job.get("_target_originally_missing"):
            return original_install(self, job, artifact, backup_path)
        artifacts = self._artifacts(job)
        temporary = artifacts["upload"]
        new_sha = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        client, sftp = self._connect()
        try:
            try:
                sftp.stat(self._remote(job))
            except (FileNotFoundError, OSError) as error:
                if not isinstance(error, FileNotFoundError) and getattr(error, "errno", None) != 2:
                    raise
            else:
                raise RuntimeError(
                    "O ZIP de destino apareceu depois do preflight; atualização interrompida para não sobrescrever um arquivo novo."
                )
            sftp.put(str(artifact), temporary)
            sftp.chmod(temporary, 0o644)
            self._helper(client, "prepare", job, new_sha=new_sha)
            self._helper(client, "install-missing", job, new_sha=new_sha)
            job["_target_missing_installed_sha"] = new_sha
        finally:
            try:
                sftp.remove(temporary)
            except OSError:
                pass
            sftp.close()
            client.close()

    def rollback(self: Any, job: dict[str, Any], backup_path: Path) -> None:
        if not job.get("_target_originally_missing"):
            return original_rollback(self, job, backup_path)
        new_sha = str(job.get("_target_missing_installed_sha") or "")
        if not new_sha:
            raise RuntimeError("SHA-256 instalado não está disponível para restaurar o estado originalmente ausente.")
        client, sftp = self._connect()
        try:
            self._helper(client, "rollback-missing", job, new_sha=new_sha)
            job["_target_missing_rollback_done"] = True
        finally:
            sftp.close()
            client.close()

    def validate(self: Any, job: dict[str, Any], sha256: str) -> bool:
        marker_sha = str(job.get("_target_missing_backup_sha") or "")
        if job.get("_target_originally_missing") and marker_sha and sha256 == marker_sha:
            client, sftp = self._connect()
            try:
                try:
                    sftp.stat(self._remote(job))
                except (FileNotFoundError, OSError) as error:
                    return isinstance(error, FileNotFoundError) or getattr(error, "errno", None) == 2
                return False
            finally:
                sftp.close()
                client.close()
        return original_validate(self, job, sha256)

    SFTPInstaller._helper = helper
    SFTPInstaller.backup = backup
    SFTPInstaller.install = install
    SFTPInstaller.rollback = rollback
    SFTPInstaller.validate = validate
    SFTPInstaller.check = check
    SFTPInstaller._missing_target_recovery_installed = True


def install_missing_target_recovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_preflight()
    _patch_filesystem_installer()
    _patch_sftp_installer()
    _INSTALLED = True


__all__ = ["install_missing_target_recovery"]
