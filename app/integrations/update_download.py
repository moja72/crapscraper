"""Adaptadores canônicos de download usados pela aba Atualizar."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.integrations.plugintheme_download import PluginThemeDownloadError, PluginThemeDownloader, SourceDownloader
from app.integrations.ultrapack_download import LocalZipArtifact, UltrapackDownloader


class CanonicalPluginThemeDownloader(PluginThemeDownloader):
    def authentication_probe(self, product_url: str) -> dict[str, Any]:
        response = self._get(
            product_url,
            stage="plugintheme_authenticated_product",
            headers={"Referer": "https://plugintheme.net/"},
        )
        product = self.product_data(product_url, response.text)
        product_id = product["id"]
        check = self._get(
            f"{self.API_BASE}/downloads/{product_id}/check-access",
            stage="plugintheme_access_probe",
            headers={"Referer": product_url, "Accept": "application/json,text/plain,*/*"},
        )
        try:
            raw = check.json()
        except Exception:
            raise PluginThemeDownloadError("Resposta inválida ao validar sessão do PluginTheme")
        access = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
        if not self.access_allowed(access):
            if self._credit_failure(raw):
                raise PluginThemeDownloadError("Créditos de download insuficientes no PluginTheme")
            raise PluginThemeDownloadError("Sessão do PluginTheme expirada ou sem acesso ao produto")
        return {
            "authenticated": True,
            "version": product.get("version", ""),
            "proof": "check_access_allowed",
        }

    def download(self, product_url: str, staging_dir: str | Path) -> tuple[LocalZipArtifact, str]:
        metadata, version = self._download_metadata(product_url)
        download_url = metadata["download_url"]
        response = self._get(
            download_url,
            stream=True,
            stage="plugintheme_final_download",
            headers={
                "Referer": product_url,
                "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
            },
        )
        target_dir = Path(staging_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact = self._validated_response_artifact(
            response,
            requested_url=download_url,
            target_dir=target_dir,
        )
        api_name = Path(str(metadata.get("file_name") or "")).name
        if api_name and api_name.lower().endswith(".zip") and Path(artifact.path).name != api_name:
            old = Path(artifact.path)
            target = target_dir / api_name
            if not target.exists():
                old.replace(target)
                artifact = LocalZipArtifact(
                    str(target), target.name, artifact.source_url,
                    artifact.size, artifact.sha256, artifact.entries,
                )
        return artifact, version


class CanonicalSourceDownloader(SourceDownloader):
    """Um único seletor de fonte para preparação individual e em lote."""

    def authentication_probe(self, url: str) -> dict[str, Any]:
        return self._for(url).authentication_probe(url)


def build_canonical_source_downloader(ultrapack_session: Any, plugintheme_session: Any) -> CanonicalSourceDownloader:
    return CanonicalSourceDownloader(
        UltrapackDownloader(ultrapack_session),
        CanonicalPluginThemeDownloader(plugintheme_session),
    )
