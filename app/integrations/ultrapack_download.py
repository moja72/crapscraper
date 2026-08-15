"""Descoberta e download autenticado de ZIPs do Ultrapack para staging local."""
from __future__ import annotations

import hashlib
import re
import time
import zipfile
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

from app.integrations.wordpress import IntegrationError, sanitize_text


@dataclass(frozen=True)
class LocalZipArtifact:
    path: str
    file_name: str
    source_url: str
    size: int
    sha256: str
    entries: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UltrapackDownloadError(IntegrationError):
    pass


class UltrapackDownloader:
    """Usa a Session autenticada fornecida pelo fluxo existente; nunca registra cookies."""

    def __init__(self, session: Any, *, timeout: float = 30, retries: int = 2,
                 retry_delay: float = .25, max_bytes: int = 1024 * 1024 * 1024) -> None:
        self.session = session
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.retry_delay = max(0.0, float(retry_delay))
        self.max_bytes = int(max_bytes)

    def _get(self, url: str, *, stream: bool = False) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=self.timeout, stream=stream,
                                            allow_redirects=True)
                if int(response.status_code) >= 400:
                    raise UltrapackDownloadError(f"HTTP {response.status_code}")
                return response
            except Exception as error:
                last = error
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_delay)
        raise UltrapackDownloadError("Falha no download Ultrapack: " + sanitize_text(last)) from None

    @staticmethod
    def discover_download_url(product_url: str, html: str) -> str:
        # O botao real nao aponta para um ZIP. O JavaScript do Ultrapack le
        # data-f de .single-bt-download-a e navega para a pagina atual com ?f=.
        tags = re.findall(r'''<a\b[^>]*>''', html, re.I)
        for tag in tags:
            class_match = re.search(r'''\bclass\s*=\s*["']([^"']*)["']''', tag, re.I)
            classes = (class_match.group(1).lower().split() if class_match else [])
            if "single-bt-download-a" not in classes:
                continue
            token_match = re.search(r'''\bdata-f\s*=\s*["']([^"']+)["']''', tag, re.I)
            if not token_match:
                raise UltrapackDownloadError("Botao de download sem identificador data-f")
            identifier = unescape(token_match.group(1)).strip()
            if not identifier:
                raise UltrapackDownloadError("Botao de download com identificador vazio")
            parts = urlsplit(product_url)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                     if key != "f"]
            query.append(("f", identifier))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
        raise UltrapackDownloadError("Botao real de download nao encontrado no produto autenticado")

    def inspect_product(self, product_url: str) -> tuple[str, str]:
        response = self._get(product_url)
        html = response.text
        version = ""
        patterns = (
            r'''(?:vers[aã]o|version)\s*</?[^>]*>??\s*[:\-]?\s*v?([0-9]+(?:\.[0-9A-Za-z_-]+)+)''',
            r'''(?:vers[aã]o|version)\s*[:\-]\s*v?([0-9]+(?:\.[0-9A-Za-z_-]+)+)''',
        )
        plain = re.sub(r"<[^>]+>", " ", html)
        for pattern in patterns:
            match = re.search(pattern, plain, re.I)
            if match:
                version = match.group(1)
                break
        return self.discover_download_url(product_url, html), version

    @staticmethod
    def _safe_source_url(url: str) -> str:
        parts = urlsplit(str(url or ""))
        keys = [(key, "[redacted]") for key, _value in parse_qsl(parts.query, keep_blank_values=True)]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(keys), ""))

    @staticmethod
    def _response_file_name(response: Any, fallback_url: str) -> str:
        disposition = str(response.headers.get("Content-Disposition", "") or "")
        match = re.search(r'''filename\*?\s*=\s*(?:UTF-8''|["'])?([^"';]+)''', disposition, re.I)
        final_url = str(getattr(response, "url", "") or fallback_url)
        raw_name = unescape(match.group(1).strip()) if match else Path(urlparse(final_url).path).name
        name = Path(raw_name).name or "ultrapack-download.zip"
        if not name.lower().endswith(".zip"):
            name += ".zip"
        return name

    @staticmethod
    def validate_zip(path: Path, *, source_url: str = "") -> LocalZipArtifact:
        if path.suffix.lower() != ".zip":
            raise UltrapackDownloadError("Arquivo baixado nao possui extensao .zip")
        size = path.stat().st_size if path.exists() else 0
        if size <= 0:
            raise UltrapackDownloadError("Download vazio")
        head = path.read_bytes()[:512].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html", b"<body")):
            raise UltrapackDownloadError("Resposta HTML recebida no lugar do ZIP")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        try:
            with zipfile.ZipFile(path) as archive:
                bad = archive.testzip()
                entries = len(archive.infolist())
                if bad or entries == 0:
                    raise UltrapackDownloadError("ZIP corrompido ou sem conteudo")
        except (zipfile.BadZipFile, OSError):
            raise UltrapackDownloadError("ZIP corrompido") from None
        return LocalZipArtifact(str(path), path.name, source_url, size, digest.hexdigest(), entries)

    def download(self, product_url: str, staging_dir: str | Path) -> tuple[LocalZipArtifact, str]:
        download_url, version = self.inspect_product(product_url)
        target_dir = Path(staging_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        response = self._get(download_url, stream=True)
        content_type = str(response.headers.get("Content-Type", "")).lower()
        if "text/html" in content_type:
            raise UltrapackDownloadError("Resposta HTML recebida no lugar do ZIP")
        target = target_dir / self._response_file_name(response, download_url)
        total = 0
        with target.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_bytes:
                    target.unlink(missing_ok=True)
                    raise UltrapackDownloadError("ZIP excede o limite de tamanho")
                output.write(chunk)
        final_url = str(getattr(response, "url", "") or download_url)
        return self.validate_zip(target, source_url=self._safe_source_url(final_url)), version
