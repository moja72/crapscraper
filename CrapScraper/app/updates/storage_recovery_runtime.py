from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.updates.adapters import SFTPInstaller, WooCommerceGateway, version_metadata


def _clean_filename(value: str) -> str:
    """Converte o basename de URL para o nome real esperado no filesystem."""
    name = unquote(os.path.basename(str(value or ""))).strip()
    return unicodedata.normalize("NFC", name)


def _filename_key(value: str) -> str:
    return _clean_filename(value).casefold()


def _family_key(value: str) -> str:
    name = _clean_filename(value)
    stem = name[:-4] if name.lower().endswith(".zip") else name
    # Remove somente uma versão final claramente estruturada: 1.5.3, v2.0.1 etc.
    stem = re.sub(r"(?i)(?:[-_. ]+v?\d+(?:[._-]\d+){1,5})$", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem.casefold()).strip("-")


def _is_missing(error: BaseException) -> bool:
    return isinstance(error, FileNotFoundError) or (
        isinstance(error, OSError) and getattr(error, "errno", None) == 2
    )


def _prepare_job(self: WooCommerceGateway, job: dict[str, Any]) -> None:
    """Resolve o ZIP do Woo usando o basename já decodificado da URL.

    O código antigo preservava `%20`, `%28`, caracteres UTF-8 escapados etc. como se
    fossem parte literal do nome no servidor. Isso podia fazer o SFTP procurar um
    arquivo inexistente apesar de o download do Woo apontar para o arquivo correto.
    """
    variations = self._request(
        "GET",
        f"/products/{int(job['woo_product_id'])}/variations",
        params={"per_page": 100},
    )
    downloads: list[dict[str, str]] = []
    for variation in variations:
        for download in variation.get("downloads") or []:
            url = str(download.get("file") or "").strip()
            path = urlparse(url).path
            if not path.lower().endswith(".zip"):
                continue
            raw_name = os.path.basename(path)
            decoded_name = _clean_filename(raw_name)
            if decoded_name:
                downloads.append(
                    {
                        "url": url,
                        "raw_name": raw_name,
                        "name": decoded_name,
                    }
                )

    files = {item["name"] for item in downloads}
    if len(files) != 1:
        raise RuntimeError(
            "WooCommerce deve apontar para exatamente um ZIP; "
            f"encontrados: {sorted(files)}"
        )

    target = next(iter(files))
    selected = next(item for item in downloads if item["name"] == target)
    job["target_filename"] = target
    job["target_filename_raw"] = selected["raw_name"]
    job["target_download_url"] = selected["url"]
    job["woocommerce_version_scope"] = {
        "write_target": "parent",
        "parent_product_id": int(job["woo_product_id"]),
        "variations_read_only": [
            {
                "variation_id": int(variation.get("id") or 0),
                "parent_id": int(variation.get("parent_id") or 0),
                "pt_versao": version_metadata(variation),
            }
            for variation in variations
        ],
    }


def _remote_entries(sftp: Any, root: str) -> list[str]:
    try:
        return [str(name) for name in sftp.listdir(root)]
    except Exception:
        return []


def _find_recovery_candidate(sftp: Any, root: str, desired: str) -> tuple[str, str] | None:
    entries = [name for name in _remote_entries(sftp, root) if name.lower().endswith(".zip")]
    if not entries:
        return None

    equivalent = [name for name in entries if _filename_key(name) == _filename_key(desired)]
    if len(equivalent) == 1:
        return equivalent[0], "equivalent_filename"
    if len(equivalent) > 1:
        raise RuntimeError(
            "Mais de um ZIP equivalente ao nome esperado foi localizado; "
            "a recuperação automática foi bloqueada para evitar substituir o arquivo errado."
        )

    family = _family_key(desired)
    if not family:
        return None
    related = [name for name in entries if _family_key(name) == family]
    if len(related) == 1:
        return related[0], "unique_version_family"
    if len(related) > 1:
        raise RuntimeError(
            f"ZIP esperado {desired!r} não existe e há múltiplos arquivos da mesma família no servidor: "
            f"{sorted(related)[:8]}. A recuperação automática foi bloqueada."
        )
    return None


def _download_sha(sftp: Any, remote: str, local: Path) -> str:
    sftp.get(remote, str(local))
    return hashlib.sha256(local.read_bytes()).hexdigest()


def _backup(self: SFTPInstaller, job: dict[str, Any], attempt_dir: Path) -> Path:
    desired_name = _clean_filename(str(job.get("target_filename") or ""))
    if not desired_name or not desired_name.lower().endswith(".zip"):
        raise ValueError("Nome do ZIP de destino ausente ou inválido")
    job["target_filename"] = desired_name

    desired_remote = f"{self.root}/{desired_name}"
    backup = attempt_dir / "backup" / desired_name
    backup.parent.mkdir(parents=True, exist_ok=True)
    client, sftp = self._connect()
    try:
        try:
            old_sha = _download_sha(sftp, desired_remote, backup)
        except Exception as error:
            if not _is_missing(error):
                raise

            recovery = _find_recovery_candidate(sftp, self.root, desired_name)
            if recovery is None:
                download_hint = str(job.get("target_download_url") or "")
                raise FileNotFoundError(
                    "ZIP atual não encontrado no armazenamento remoto. "
                    f"Esperado: {desired_remote}. "
                    + (f"WooCommerce: {download_hint}. " if download_hint else "")
                    + "Nenhum arquivo equivalente seguro foi localizado; nada foi alterado."
                ) from error

            candidate_name, reason = recovery
            candidate_remote = f"{self.root}/{candidate_name}"
            old_sha = _download_sha(sftp, candidate_remote, backup)

            # Reconstitui o caminho exato que o WooCommerce espera usando somente o
            # conteúdo do único ZIP equivalente encontrado. Depois disso o fluxo
            # canônico (helper + backup + troca atômica) continua sem bypass.
            sftp.put(str(backup), desired_remote)
            sftp.chmod(desired_remote, 0o644)
            seeded_sha = self._sftp_sha(sftp, desired_remote)
            if seeded_sha != old_sha:
                try:
                    sftp.remove(desired_remote)
                except OSError:
                    pass
                raise RuntimeError("Falha ao reconstruir o ZIP de destino antes da atualização")
            job["storage_recovery"] = {
                "reason": reason,
                "expected": desired_name,
                "recovered_from": candidate_name,
            }

        remote_backup = self._artifacts(job)["backup"]
        try:
            existing_sha = self._sftp_sha(sftp, remote_backup)
        except Exception as error:
            if _is_missing(error):
                existing_sha = ""
            else:
                raise
        if existing_sha and existing_sha != old_sha:
            raise RuntimeError("Backup remoto existente diverge do ZIP atual; retry bloqueado")
        if not existing_sha:
            self._helper(client, "backup", job, old_sha=old_sha)
    finally:
        sftp.close()
        client.close()
    return backup


def install_storage_recovery_runtime() -> None:
    if getattr(SFTPInstaller, "_crapscraper_storage_recovery_installed", False):
        return
    WooCommerceGateway.prepare_job = _prepare_job
    SFTPInstaller.backup = _backup
    SFTPInstaller._crapscraper_storage_recovery_installed = True


install_storage_recovery_runtime()

__all__ = [
    "install_storage_recovery_runtime",
    "_clean_filename",
    "_family_key",
    "_find_recovery_candidate",
]
