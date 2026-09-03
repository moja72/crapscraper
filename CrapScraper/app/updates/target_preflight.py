from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class TargetZipError(RuntimeError):
    """Falha estruturada ao resolver ou ler o ZIP atual usado para backup."""

    def __init__(self, *, filename: str = "", path: str = "", reason: str = "missing") -> None:
        self.filename = os.path.basename(str(filename or ""))
        self.path = str(path or self.filename or "destino não resolvido")
        self.reason = reason
        if reason == "missing":
            self.code = "target_zip_not_found"
            message = "ZIP atual do produto não foi encontrado no repositório de downloads."
            diagnosis = (
                f"O WooCommerce aponta para '{self.filename or 'arquivo não resolvido'}', "
                f"mas o arquivo não existe em '{self.path}'. Corrija o arquivo de download atual antes de tentar a atualização novamente."
            )
        elif reason == "unreadable":
            self.code = "target_zip_unreadable"
            message = "ZIP atual do produto não pôde ser lido no repositório de downloads."
            diagnosis = (
                f"O arquivo '{self.filename or 'não resolvido'}' foi localizado em '{self.path}', "
                "mas não pôde ser aberto para leitura. Corrija as permissões antes de tentar novamente."
            )
        else:
            self.code = "target_zip_unresolved"
            message = "Não foi possível resolver o ZIP atual do produto."
            diagnosis = (
                "O WooCommerce não forneceu um nome de arquivo ZIP utilizável para o download atual. "
                "Corrija o arquivo associado ao produto antes de tentar a atualização novamente."
            )
        self.diagnosis = diagnosis
        self.details = {
            "target_filename": self.filename,
            "target_path": self.path,
            "reason": self.reason,
        }
        super().__init__(message)


def normalize_target_filename(value: Any) -> str:
    """Converte o basename da URL do WooCommerce no nome físico esperado."""
    decoded = unquote(str(value or "").strip()).replace("\\", "/")
    name = os.path.basename(decoded)
    if not name or name in {".", ".."} or not name.lower().endswith(".zip"):
        raise TargetZipError(filename=name, reason="unresolved")
    return name


def _missing(error: BaseException) -> bool:
    return isinstance(error, FileNotFoundError) or getattr(error, "errno", None) == 2


def _target_path(installer: Any, job: dict[str, Any]) -> str:
    try:
        remote = getattr(installer, "_remote", None)
        if callable(remote):
            return str(remote(job))
        local = getattr(installer, "_target", None)
        if callable(local):
            return str(local(job))
    except Exception:
        pass
    return str(job.get("target_filename") or "")


def translate_target_exception(installer: Any, job: dict[str, Any], error: BaseException) -> TargetZipError | None:
    """Traduz ENOENT tardio (ex.: corrida entre preflight e backup) sem mascarar outros erros."""
    if not _missing(error):
        return None
    filename = str(job.get("target_filename") or "")
    return TargetZipError(filename=filename, path=_target_path(installer, job), reason="missing")


def check_target(installer: Any, job: dict[str, Any]) -> dict[str, Any]:
    """Confirma existência, tipo de arquivo e leitura antes de gastar download da fonte."""
    filename = normalize_target_filename(job.get("target_filename"))
    job["target_filename"] = filename

    local_target = getattr(installer, "_target", None)
    if callable(local_target):
        target = Path(local_target(job))
        if not target.is_file():
            raise TargetZipError(filename=filename, path=str(target), reason="missing")
        try:
            with target.open("rb") as stream:
                stream.read(1)
        except FileNotFoundError as error:
            raise TargetZipError(filename=filename, path=str(target), reason="missing") from error
        except OSError as error:
            if _missing(error):
                raise TargetZipError(filename=filename, path=str(target), reason="missing") from error
            raise TargetZipError(filename=filename, path=str(target), reason="unreadable") from error
        return {"ok": True, "checked": True, "target_filename": filename, "target_path": str(target)}

    remote_target = getattr(installer, "_remote", None)
    connect = getattr(installer, "_connect", None)
    if callable(remote_target) and callable(connect):
        remote = str(remote_target(job))
        client, sftp = connect()
        try:
            try:
                attrs = sftp.stat(remote)
            except (FileNotFoundError, OSError) as error:
                if _missing(error):
                    raise TargetZipError(filename=filename, path=remote, reason="missing") from error
                raise TargetZipError(filename=filename, path=remote, reason="unreadable") from error
            mode = getattr(attrs, "st_mode", 0)
            if mode and not stat.S_ISREG(mode):
                raise TargetZipError(filename=filename, path=remote, reason="unreadable")
            stream = None
            try:
                stream = sftp.open(remote, "rb")
                stream.read(1)
            except (FileNotFoundError, OSError) as error:
                if _missing(error):
                    raise TargetZipError(filename=filename, path=remote, reason="missing") from error
                raise TargetZipError(filename=filename, path=remote, reason="unreadable") from error
            finally:
                if stream is not None:
                    stream.close()
        finally:
            sftp.close()
            client.close()
        return {"ok": True, "checked": True, "target_filename": filename, "target_path": remote}

    # Fakes/adaptadores externos sem contrato de caminho continuam compatíveis.
    return {"ok": True, "checked": False, "target_filename": filename, "target_path": ""}
