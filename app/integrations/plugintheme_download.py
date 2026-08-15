"""Download legítimo do PluginTheme pela mesma API usada pelo frontend."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from app.integrations.ultrapack_download import (
    LocalZipArtifact, UltrapackDownloadError, UltrapackDownloader,
)


class PluginThemeDownloadError(UltrapackDownloadError):
    pass


class PluginThemeDownloader(UltrapackDownloader):
    API_BASE = "https://api.plugintheme.net/api"

    @staticmethod
    def access_allowed(payload: object) -> bool:
        """Aceita somente indicadores explícitos de autorização conhecidos pela API."""
        if not isinstance(payload, dict):
            return False
        for container_key in ("data", "result", "access"):
            nested = payload.get(container_key)
            if isinstance(nested, dict) and PluginThemeDownloader.access_allowed(nested):
                return True
        for key in ("canDownload", "can_download", "hasAccess", "has_access", "allowed", "isAllowed", "is_allowed", "authorized"):
            value = payload.get(key)
            if value is True or (isinstance(value, (int, str)) and str(value).strip().lower() in {"1", "true", "yes"}):
                return True
        return False

    @staticmethod
    def product_data(product_url: str, html: str) -> dict[str, str]:
        slug = Path(urlparse(product_url).path.rstrip("/")).name
        # O payload RSC do Next.js contém JSON escapado dentro do HTML.
        decoded = html.replace('\\"', '"').replace("\\u0026", "&")
        positions = [match.start() for match in re.finditer(
            rf'"slug"\s*:\s*"{re.escape(slug)}"', decoded, re.I
        )]
        for position in positions:
            start = max(0, position - 12000)
            window = decoded[start:position + 12000]
            anchor = position - start
            ids = list(re.finditer(r'"id"\s*:\s*"([0-9a-f-]{20,})"', window, re.I))
            versions = list(re.finditer(r'"version"\s*:\s*"([^"\\]+)"', window, re.I))
            if ids:
                nearest_id = min(ids, key=lambda item: abs(item.start() - anchor))
                version = min(versions, key=lambda item: abs(item.start() - anchor)).group(1) if versions else ""
                return {"id": nearest_id.group(1), "slug": slug, "version": version}
        raise PluginThemeDownloadError("Identificador do produto não encontrado no payload público")

    def inspect_product(self, product_url: str) -> tuple[str, str]:
        response = self._get(product_url)
        data = self.product_data(product_url, response.text)
        return product_url, data.get("version", "")

    def _download_metadata(self, product_url: str) -> tuple[dict[str, str], str]:
        response = self._get(product_url)
        product = self.product_data(product_url, response.text)
        product_id = product["id"]
        check = self._get(f"{self.API_BASE}/downloads/{product_id}/check-access")
        try:
            access = check.json()
            if isinstance(access.get("data"), dict):
                access = access["data"]
        except Exception:
            raise PluginThemeDownloadError("Resposta inválida ao verificar acesso no PluginTheme") from None
        allowed = self.access_allowed(access)
        if not allowed:
            raise PluginThemeDownloadError("Sessão do PluginTheme expirada ou sem acesso ao produto")
        metadata_response = self._get(f"{self.API_BASE}/downloads/{product_id}/file")
        try:
            metadata = metadata_response.json()
            if isinstance(metadata.get("data"), dict):
                metadata = metadata["data"]
        except Exception:
            raise PluginThemeDownloadError("Resposta inválida ao solicitar o arquivo no PluginTheme") from None
        download_url = str(metadata.get("downloadUrl") or metadata.get("url") or "").strip()
        if not download_url:
            raise PluginThemeDownloadError("PluginTheme não retornou uma URL de download")
        return {"download_url": download_url, "file_name": str(metadata.get("fileName") or "")}, product.get("version", "")

    def download(self, product_url: str, staging_dir: str | Path) -> tuple[LocalZipArtifact, str]:
        metadata, version = self._download_metadata(product_url)
        download_url = metadata["download_url"]
        response = self._get(download_url, stream=True)
        target_dir = Path(staging_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        name = Path(metadata["file_name"]).name if metadata["file_name"] else self._response_file_name(response, download_url)
        if not name.lower().endswith(".zip"):
            name += ".zip"
        target = target_dir / name
        total = 0
        with target.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_bytes:
                    target.unlink(missing_ok=True)
                    raise PluginThemeDownloadError("ZIP excede o limite de tamanho")
                output.write(chunk)
        return self.validate_zip(target, source_url=self._safe_source_url(download_url)), version


class SourceDownloader:
    """Seleciona o adaptador pela origem sem alterar o modelo de jobs legado."""
    def __init__(self, ultrapack: UltrapackDownloader, plugintheme: PluginThemeDownloader) -> None:
        self.ultrapack = ultrapack
        self.plugintheme = plugintheme
        self._session = None

    @staticmethod
    def is_plugintheme(url: str) -> bool:
        return urlparse(str(url or "")).hostname in {"plugintheme.net", "www.plugintheme.net"}

    @property
    def session(self):
        return self._session

    @session.setter
    def session(self, value):
        self._session = value
        self.ultrapack.session = value
        self.plugintheme.session = value

    def _for(self, url: str):
        return self.plugintheme if self.is_plugintheme(url) else self.ultrapack

    def inspect_product(self, url: str):
        return self._for(url).inspect_product(url)

    def download(self, url: str, staging_dir: str | Path):
        return self._for(url).download(url, staging_dir)
