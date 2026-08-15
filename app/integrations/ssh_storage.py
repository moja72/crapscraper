from __future__ import annotations

import hashlib
import os
import shlex
import stat as stat_module
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any, BinaryIO, Callable

from app import settings
from app.configuration import names_for
from app.integrations.ssh_helper import SSHDeploymentArtifacts
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError, sanitize_text


class SSHStorageConfigurationError(IntegrationError):
    """Configuracao SSH ausente ou invalida, sem expor credenciais."""


@dataclass(frozen=True)
class SSHStorageConfig:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    root: str = settings.SSH_DOWNLOAD_ROOT

    @classmethod
    def from_env(cls) -> "SSHStorageConfig":
        names = names_for(group="ssh", stage="prepare")
        values = {name: os.getenv(name, "") for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise SSHStorageConfigurationError(
                "Variaveis SSH ausentes: " + ", ".join(missing)
            )
        try:
            port = int(values["SCRAPER_SSH_PORT"])
        except ValueError:
            raise SSHStorageConfigurationError("SCRAPER_SSH_PORT invalida") from None
        if not 1 <= port <= 65535:
            raise SSHStorageConfigurationError("SCRAPER_SSH_PORT fora do intervalo")
        return cls(values["SCRAPER_SSH_HOST"], port, values["SCRAPER_SSH_USERNAME"],
                   values["SCRAPER_SSH_PASSWORD"])


@dataclass(frozen=True)
class RemoteFileInfo:
    path: str
    resolved_path: str
    size: int
    mtime: int
    mode: str
    uid: int
    gid: int
    owner: str = ""
    group: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReadOnlySSHStorage:
    """Cliente SFTP cuja superficie publica e deliberadamente read-only."""

    def __init__(
        self,
        config: SSHStorageConfig,
        *,
        client_factory: Callable[[], Any] | None = None,
        write_enabled: bool = settings.SSH_STORAGE_WRITE_ENABLED,
    ) -> None:
        if write_enabled:
            raise WriteOperationDisabledError("Armazenamento exige write_enabled=False")
        self.config = config
        self._client_factory = client_factory
        self._client: Any = None
        self._sftp: Any = None

    @classmethod
    def from_env(cls) -> "ReadOnlySSHStorage":
        return cls(SSHStorageConfig.from_env())

    def connect(self) -> "ReadOnlySSHStorage":
        if self._client is not None:
            return self
        try:
            if self._client_factory is None:
                try:
                    import paramiko
                except ImportError:
                    raise SSHStorageConfigurationError(
                        "Paramiko nao instalado; instale requirements-ssh.txt"
                    ) from None
                client = paramiko.SSHClient()
                client.load_system_host_keys()
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
            else:
                client = self._client_factory()
            client.connect(
                hostname=self.config.host, port=self.config.port,
                username=self.config.username, password=self.config.password,
                look_for_keys=False, allow_agent=False, timeout=15,
                banner_timeout=15, auth_timeout=15,
            )
            self._client = client
            self._sftp = client.open_sftp()
            return self
        except (IntegrationError, SSHStorageConfigurationError):
            raise
        except Exception as error:
            safe = sanitize_text(error, self.config.username, self.config.password)
            raise IntegrationError(f"Falha na conexao SSH read-only: {safe}") from None

    def close(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
        if self._client is not None:
            self._client.close()
        self._sftp = self._client = None

    def __enter__(self) -> "ReadOnlySSHStorage":
        return self.connect()

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _ready(self) -> Any:
        if self._sftp is None:
            self.connect()
        return self._sftp

    def _resolved_in_root(self, path: str, *, allow_root: bool = True) -> str:
        candidate = str(PurePosixPath(path))
        resolved = str(PurePosixPath(self._ready().normalize(candidate)))
        root = str(PurePosixPath(self._ready().normalize(self.config.root)))
        valid = resolved == root if allow_root else False
        valid = valid or resolved.startswith(root.rstrip("/") + "/")
        if not valid:
            raise IntegrationError("Caminho remoto fora do diretorio permitido")
        return resolved

    def stat(self, path: str) -> RemoteFileInfo:
        resolved = self._resolved_in_root(path)
        attrs = self._ready().stat(resolved)
        owner = group = ""
        if self._client is not None:
            command = "stat -c '%U\\n%G' -- " + shlex.quote(resolved)
            _stdin, stdout, _stderr = self._client.exec_command(command, timeout=15)
            lines = stdout.read().decode("utf-8", "replace").splitlines()
            if len(lines) >= 2:
                owner, group = lines[0], lines[1]
        return RemoteFileInfo(
            path=str(PurePosixPath(path)), resolved_path=resolved,
            size=int(attrs.st_size), mtime=int(attrs.st_mtime),
            mode=stat_module.filemode(attrs.st_mode), uid=int(attrs.st_uid),
            gid=int(attrs.st_gid), owner=owner, group=group,
        )

    def exists(self, path: str) -> bool:
        try:
            self.stat(path)
            return True
        except (FileNotFoundError, OSError) as error:
            if getattr(error, "errno", None) == 2:
                return False
            raise

    def list(self, path: str | None = None, *, limit: int = 100) -> list[RemoteFileInfo]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit deve estar entre 1 e 1000")
        directory = self._resolved_in_root(path or self.config.root)
        result: list[RemoteFileInfo] = []
        for attrs in self._ready().listdir_attr(directory)[:limit]:
            result.append(self.stat(str(PurePosixPath(directory) / attrs.filename)))
        return result

    def size(self, path: str) -> int:
        return self.stat(path).size

    def mtime(self, path: str) -> int:
        return self.stat(path).mtime

    def sha256(self, path: str, *, chunk_size: int = 1024 * 1024) -> str:
        resolved = self._resolved_in_root(path, allow_root=False)
        digest = hashlib.sha256()
        with self._ready().open(resolved, "rb") as remote:
            while chunk := remote.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    def validate_file(self, path: str) -> RemoteFileInfo:
        info = self.stat(path)
        if not stat_module.S_ISREG(self._ready().stat(info.resolved_path).st_mode):
            raise IntegrationError("Caminho remoto nao e arquivo regular")
        if PurePosixPath(info.resolved_path).suffix.lower() != ".zip":
            raise IntegrationError("Arquivo remoto nao possui extensao .zip")
        return RemoteFileInfo(**{**info.to_dict(), "sha256": self.sha256(info.resolved_path)})

    def identify_directory(self) -> dict[str, Any]:
        info = self.stat(self.config.root)
        command = "df -T -- " + shlex.quote(info.resolved_path)
        _stdin, stdout, _stderr = self._client.exec_command(command, timeout=15)
        lines = stdout.read().decode("utf-8", "replace").splitlines()
        return {"directory": info.to_dict(), "filesystem": lines[-1] if lines else ""}

    def _write_disabled(self, *_args: Any, **_kwargs: Any) -> None:
        raise WriteOperationDisabledError("Operacao de escrita SSH/SFTP desabilitada")

    upload = rename = move = delete = unlink = backup = restore = _write_disabled
    mkdir = chmod = chown = truncate = write = _write_disabled


class ControlledWriteSSHStorage(ReadOnlySSHStorage):
    """SFTP write session restricted to artifacts belonging to one job.

    The process-wide setting remains disabled.  A caller must explicitly opt in
    for one job and one existing ZIP.  Arbitrary deletion and metadata changes
    are intentionally absent.
    """

    def __init__(
        self,
        config: SSHStorageConfig,
        *,
        job_id: str,
        target_path: str,
        write_authorized: bool = False,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(config, client_factory=client_factory, write_enabled=False)
        if not write_authorized:
            raise WriteOperationDisabledError("Escrita SSH exige autorizacao explicita do job")
        if not job_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in job_id):
            raise IntegrationError("job_id invalido para nomes remotos")
        target = PurePosixPath(target_path)
        if target.suffix.lower() != ".zip" or str(target.parent) != str(PurePosixPath(config.root)):
            raise IntegrationError("Arquivo alvo deve ser ZIP diretamente no diretorio permitido")
        self.job_id = job_id
        self.target_path = str(target)
        self.temporary_path = self.target_path + f".crapscraper.{job_id}.tmp"
        self.backup_path = self.target_path + f".crapscraper.{job_id}.bak"
        self.discard_path = self.target_path + f".crapscraper.{job_id}.discard.tmp"
        self._created_temporaries: set[str] = set()

    @classmethod
    def from_env(
        cls, *, job_id: str, target_path: str, write_authorized: bool = False
    ) -> "ControlledWriteSSHStorage":
        return cls(
            SSHStorageConfig.from_env(), job_id=job_id, target_path=target_path,
            write_authorized=write_authorized,
        )

    def _allowed_path(self, path: str) -> str:
        resolved = self._resolved_in_root(path, allow_root=False)
        allowed = {
            self.target_path, self.temporary_path, self.backup_path, self.discard_path,
        }
        if resolved not in allowed:
            raise IntegrationError("Caminho fora do escopo de escrita deste job")
        return resolved

    def upload(self, source: BinaryIO, destination: str, *, chunk_size: int = 1024 * 1024) -> None:
        resolved = self._allowed_path(destination)
        if resolved not in {self.temporary_path, self.discard_path}:
            raise IntegrationError("Upload permitido apenas para temporario do job")
        if self.exists(resolved):
            raise FileExistsError(f"Temporario ja existe: {resolved}")
        # Paramiko's SFTPFile accepts ``x`` inconsistently across server/client
        # versions. Existence is checked immediately above and names are unique
        # per locally locked job, so use its portable writable mode here.
        with self._ready().open(resolved, "wb") as remote:
            self._created_temporaries.add(resolved)
            while chunk := source.read(chunk_size):
                remote.write(chunk)
            if hasattr(remote, "flush"):
                remote.flush()

    def copy_target_to_temporary(self, *, chunk_size: int = 1024 * 1024) -> str:
        with self._ready().open(self._allowed_path(self.target_path), "rb") as source:
            self.upload(source, self.temporary_path, chunk_size=chunk_size)
        return self.temporary_path

    def rename(self, source: str, destination: str) -> None:
        source_resolved = self._allowed_path(source)
        destination_resolved = self._allowed_path(destination)
        allowed_pairs = {
            (self.target_path, self.backup_path),
            (self.temporary_path, self.target_path),
            (self.target_path, self.discard_path),
            (self.backup_path, self.target_path),
        }
        if (source_resolved, destination_resolved) not in allowed_pairs:
            raise IntegrationError("Rename fora da sequencia transacional permitida")
        if self.exists(destination_resolved):
            raise FileExistsError(f"Destino ja existe: {destination_resolved}")
        self._ready().rename(source_resolved, destination_resolved)
        if source_resolved in self._created_temporaries:
            self._created_temporaries.remove(source_resolved)
            if destination_resolved in {self.temporary_path, self.discard_path}:
                self._created_temporaries.add(destination_resolved)
        elif destination_resolved == self.discard_path:
            self._created_temporaries.add(destination_resolved)

    def backup(self) -> None:
        if self.exists(self.backup_path):
            raise FileExistsError(f"Backup ja existe: {self.backup_path}")
        self.rename(self.target_path, self.backup_path)

    def restore(self) -> None:
        if not self.exists(self.backup_path):
            raise FileNotFoundError(f"Backup ausente: {self.backup_path}")
        self.rename(self.backup_path, self.target_path)

    def delete_temporary(self, path: str) -> None:
        resolved = self._allowed_path(path)
        if resolved not in self._created_temporaries or resolved not in {self.temporary_path, self.discard_path}:
            raise WriteOperationDisabledError("Delete permitido apenas para temporario criado pelo job")
        self._ready().remove(resolved)
        self._created_temporaries.remove(resolved)

    def recover_owned_temporary(self, path: str) -> None:
        """Delete an exact tmp/discard name left by this same job after failure."""
        resolved = self._allowed_path(path)
        if resolved not in {self.temporary_path, self.discard_path}:
            raise WriteOperationDisabledError("Recuperacao limitada a temporarios do job")
        if self.exists(resolved):
            self._created_temporaries.add(resolved)
            self.delete_temporary(resolved)

    move = unlink = delete = ReadOnlySSHStorage._write_disabled
    mkdir = chmod = chown = truncate = write = ReadOnlySSHStorage._write_disabled


class ControlledStagingSSHStorage(ReadOnlySSHStorage):
    """One-job SFTP writer limited to the helper's exact ``.upload`` path."""

    STAGING_MODE = 0o644

    def __init__(
        self,
        config: SSHStorageConfig,
        *,
        file_name: str,
        job_id: str,
        write_authorized: bool = False,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(config, client_factory=client_factory, write_enabled=False)
        if not write_authorized:
            raise WriteOperationDisabledError("Staging SFTP exige autorizacao explicita do job")
        paths = SSHDeploymentArtifacts(file_name, job_id).paths()
        self.file_name = file_name
        self.job_id = job_id
        self.production_path = paths["production"]
        self.upload_path = paths["upload"]

    @classmethod
    def from_env(
        cls, *, file_name: str, job_id: str, write_authorized: bool = False
    ) -> "ControlledStagingSSHStorage":
        return cls(
            SSHStorageConfig.from_env(), file_name=file_name, job_id=job_id,
            write_authorized=write_authorized,
        )

    def _exact_upload(self, path: str) -> str:
        resolved = self._resolved_in_root(path, allow_root=False)
        if resolved != self.upload_path:
            raise IntegrationError("Operacao permitida somente no .upload exato deste job")
        return resolved

    def upload_staging(self, source: BinaryIO, *, chunk_size: int = 1024 * 1024) -> str:
        destination = self._exact_upload(self.upload_path)
        if self.exists(destination):
            raise FileExistsError(f"Staging ja existe: {destination}")
        with self._ready().open(destination, "wb") as remote:
            while chunk := source.read(chunk_size):
                remote.write(chunk)
            if hasattr(remote, "flush"):
                remote.flush()
        return destination

    def chmod_staging_upload(self, path: str, mode: int = STAGING_MODE) -> RemoteFileInfo:
        if mode != self.STAGING_MODE:
            raise IntegrationError("Mode do staging deve ser exatamente 0644")
        resolved = self._exact_upload(path)
        try:
            before = self._ready().lstat(resolved)
        except FileNotFoundError:
            raise IntegrationError("Staging inexistente") from None
        if stat_module.S_ISLNK(before.st_mode) or not stat_module.S_ISREG(before.st_mode):
            raise IntegrationError("Staging deve ser arquivo regular e nao symlink")
        self._ready().chmod(resolved, self.STAGING_MODE)
        after = self._ready().lstat(resolved)
        if stat_module.S_ISLNK(after.st_mode) or not stat_module.S_ISREG(after.st_mode):
            raise IntegrationError("Staging mudou durante chmod")
        if stat_module.S_IMODE(after.st_mode) != self.STAGING_MODE:
            raise IntegrationError("Servidor nao confirmou mode 0644 no staging")
        return self.stat(resolved)

    upload = rename = move = delete = unlink = backup = restore = ReadOnlySSHStorage._write_disabled
    mkdir = chmod = chown = truncate = write = ReadOnlySSHStorage._write_disabled
