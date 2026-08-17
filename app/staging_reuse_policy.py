from __future__ import annotations

from contextlib import suppress
from pathlib import Path
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


def _patched_prepare(self: Any, job: Any):
    """Reusa somente artefato com prova persistida de SHA e versão."""
    original_download = self.downloader.download
    persisted_path, expected_sha, expected_version = _previous_artifact(job)

    def download_with_reuse(url: str, staging_dir: str | Path):
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
        return _BASE_PREPARE(self, job)  # type: ignore[misc]
    finally:
        self.downloader.download = original_download


def install_staging_reuse_policy() -> None:
    global _INSTALLED, _BASE_PREPARE
    if _INSTALLED:
        return
    _BASE_PREPARE = preparation.UpdatePreparationService._prepare
    preparation.UpdatePreparationService._prepare = _patched_prepare
    _INSTALLED = True
