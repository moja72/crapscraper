from __future__ import annotations

from contextlib import suppress
from pathlib import Path
import re
from typing import Any, Callable

from app.integrations.ultrapack_download import UltrapackDownloader
from app.operations import preparation

_INSTALLED = False
_BASE_PREPARE: Callable[..., Any] | None = None


def _previous_artifact(job: Any) -> tuple[str, str, str]:
    """Retorna caminho, SHA e versão persistidos anteriormente para o job."""
    path = str(getattr(job, "local_staging_path", "") or "").strip()
    sha256 = str(getattr(job, "new_sha256", "") or "").strip().lower()
    version = str(getattr(job, "effective_source_version", "") or "").strip()

    with suppress(Exception):
        from app.operations.runtime import get_preview

        preview = get_preview(str(getattr(job, "job_id", "") or "")) or {}
        artifact = preview.get("new_zip") or {}
        versions = preview.get("versions") or {}
        path = path or str(artifact.get("path") or "").strip()
        sha256 = sha256 or str(artifact.get("sha256") or "").strip().lower()
        version = version or str(
            versions.get("effective_source_version")
            or versions.get("ultrapack_found")
            or versions.get("ultrapack")
            or ""
        ).strip()

    version = version or str(
        getattr(job, "approved_source_version", "")
        or getattr(job, "ultrapack_version", "")
        or ""
    ).strip()
    return path, sha256, version


def _candidate_paths(staging_dir: str | Path, persisted_path: str) -> list[Path]:
    root = Path(staging_dir)
    candidates: list[Path] = []
    persisted = Path(persisted_path) if persisted_path else None
    if persisted is not None and persisted.exists() and persisted.is_file():
        candidates.append(persisted)
    if root.exists():
        for candidate in sorted(root.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def _version_tokens(version: str) -> tuple[str, ...]:
    normalized = str(version or "").strip().lower().lstrip("v")
    if not normalized:
        return ()
    compact = re.sub(r"[^0-9a-z]+", "", normalized)
    dashed = re.sub(r"[^0-9a-z]+", "-", normalized).strip("-")
    dotted = re.sub(r"[^0-9a-z]+", ".", normalized).strip(".")
    return tuple(dict.fromkeys(token for token in (normalized, compact, dashed, dotted) if token))


def _choose_recovery_candidate(candidates: list[Path], expected_version: str) -> Path | None:
    """Escolhe somente candidato inequívoco dentro da pasta exata do job."""
    valid: list[Path] = []
    for candidate in candidates:
        try:
            UltrapackDownloader.validate_zip(candidate, source_url="staging-recovery-probe")
        except Exception:
            continue
        valid.append(candidate)
    if len(valid) == 1:
        return valid[0]
    if len(valid) <= 1:
        return None
    tokens = _version_tokens(expected_version)
    matching = [
        candidate for candidate in valid
        if any(token in candidate.stem.lower().replace("_", "-") for token in tokens)
    ]
    return matching[0] if len(matching) == 1 else None


def _patched_prepare(self: Any, job: Any):
    """Reusa artefato persistido ou recupera com segurança o ZIP da pasta exata do job."""
    original_download = self.downloader.download
    original_inspect = self.downloader.inspect_product
    persisted_path, expected_sha, expected_version = _previous_artifact(job)
    job_dir = Path(self.staging_root) / str(getattr(job, "job_id", "") or "")
    candidates = _candidate_paths(job_dir, persisted_path)
    recovery_candidate: Path | None = None
    recovered_artifact: Any = None

    # Recuperação de legado: o arquivo existe no diretório UUID correto, porém
    # versões antigas do runtime não persistiram local_staging_path/new_sha256.
    if (not expected_sha or not persisted_path) and expected_version:
        recovery_candidate = _choose_recovery_candidate(candidates, expected_version)
        if recovery_candidate is not None:
            try:
                recovered_artifact = UltrapackDownloader.validate_zip(
                    recovery_candidate, source_url="staging-recovery"
                )
                self.logger(
                    f"♻ ZIP local legado recuperado: {recovery_candidate.name} · "
                    f"SHA-256 {recovered_artifact.sha256[:12]}…"
                )
            except Exception as error:
                self.logger(f"⚠ ZIP local legado inválido: {error}")
                recovery_candidate = None
                recovered_artifact = None

    # No modo de recuperação o download já aconteceu no passado. A versão usada
    # é a versão aprovada/efetiva persistida no próprio job; a preparação ainda
    # revalida WooCommerce, vínculo, ZIP atual, estado do produto e plano.
    if recovery_candidate is not None and recovered_artifact is not None:
        def inspect_from_recovered_job(url: str):
            self.logger(
                f"♻ Fonte reaproveitada do job: versão {expected_version}; "
                "nenhum novo download será solicitado."
            )
            return url, expected_version
        self.downloader.inspect_product = inspect_from_recovered_job

    def download_with_reuse(url: str, staging_dir: str | Path):
        if recovery_candidate is not None and recovered_artifact is not None:
            return recovered_artifact, expected_version

        if expected_sha and expected_version:
            for candidate in _candidate_paths(staging_dir, persisted_path):
                try:
                    artifact = UltrapackDownloader.validate_zip(candidate, source_url="staging-reuse")
                except Exception as error:
                    self.logger(f"⚠ ZIP local ignorado ({candidate.name}): {error}")
                    continue
                if artifact.sha256.lower() != expected_sha:
                    self.logger(f"⚠ ZIP local ignorado ({candidate.name}): SHA diferente do artefato persistido")
                    continue
                try:
                    _source_url, current_version = self.downloader.inspect_product(url)
                except Exception as error:
                    self.logger(f"⚠ Não foi possível confirmar a versão da fonte para reutilizar o ZIP: {error}")
                    break
                current_version = str(current_version or "").strip()
                if current_version != expected_version:
                    self.logger(
                        f"ℹ ZIP local não reutilizado: fonte mudou de {expected_version or '-'} para {current_version or '-'}"
                    )
                    break
                self.logger(
                    f"♻ Reaproveitando ZIP já baixado e validado: {candidate.name} · SHA-256 {artifact.sha256[:12]}…"
                )
                return artifact, current_version
        return original_download(url, staging_dir)

    self.downloader.download = download_with_reuse
    try:
        result = _BASE_PREPARE(self, job)  # type: ignore[misc]
        # O _prepare base grava local_staging_path/new_sha256 quando o preview fica
        # preparado. Persistimos o job imediatamente para que a evidência sobreviva
        # a reinícios antes mesmo da geração do plano.
        if recovery_candidate is not None and recovered_artifact is not None:
            with suppress(Exception):
                from app.operations.runtime import persist_job
                job.local_staging_path = str(recovery_candidate)
                job.new_sha256 = str(recovered_artifact.sha256 or "")
                job.effective_source_version = expected_version
                persist_job(job)
        return result
    finally:
        self.downloader.download = original_download
        self.downloader.inspect_product = original_inspect


def install_staging_reuse_policy() -> None:
    global _INSTALLED, _BASE_PREPARE
    if _INSTALLED:
        return
    _BASE_PREPARE = preparation.UpdatePreparationService._prepare
    preparation.UpdatePreparationService._prepare = _patched_prepare
    _INSTALLED = True
