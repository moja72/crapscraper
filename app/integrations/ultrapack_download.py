"""Descoberta e download autenticado de ZIPs do Ultrapack para staging local."""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

from app.integrations.download_validation import (
    InvalidDownloadPayload,
    extract_distinct_download_candidate,
    safe_url,
    validate_zip_file,
    write_validated_zip_response,
)
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
    def __init__(self, message: str, *, diagnostic: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostic = dict(diagnostic or {})


class UltrapackDownloader:
    """Usa a Session autenticada fornecida pelo fluxo existente; nunca registra cookies."""

    def __init__(self, session: Any, *, timeout: float = 30, retries: int = 2,
                 retry_delay: float = .25, max_bytes: int = 1024 * 1024 * 1024) -> None:
        self.session = session
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.retry_delay = max(0.0, float(retry_delay))
        self.max_bytes = int(max_bytes)
        self.request_trace: list[dict[str, Any]] = []
        self.last_download_diagnostic: dict[str, Any] = {}

    def _record_response(self, stage: str, requested_url: str, response: Any) -> None:
        history = list(getattr(response, "history", None) or []) + [response]
        redirects = [
            {
                "status": int(getattr(item, "status_code", 0) or 0),
                "url": self._safe_source_url(str(getattr(item, "url", "") or "")),
            }
            for item in history
        ]
        cookies = []
        cookie_jar = getattr(self.session, "cookies", None)
        if cookie_jar is not None:
            try:
                iterator = iter(cookie_jar)
            except TypeError:
                iterator = iter(())
            for cookie in iterator:
                cookies.append({
                    "name": str(getattr(cookie, "name", "") or ""),
                    "domain": str(getattr(cookie, "domain", "") or ""),
                    "path": str(getattr(cookie, "path", "") or "/"),
                })
        headers = getattr(self.session, "headers", {}) or {}
        self.request_trace.append({
            "stage": stage,
            "requested_url": self._safe_source_url(requested_url),
            "final_url": self._safe_source_url(str(getattr(response, "url", "") or requested_url)),
            "status": int(getattr(response, "status_code", 0) or 0),
            "redirects": redirects,
            "content_type": str(getattr(response, "headers", {}).get("Content-Type", "") or ""),
            "content_disposition": bool(
                str(getattr(response, "headers", {}).get("Content-Disposition", "") or "")
            ),
            "cookie_scope": cookies,
            "authenticated_cookie_present": bool(cookies),
            "referer": self._safe_source_url(str(headers.get("Referer", "") or "")),
            "user_agent_present": bool(str(headers.get("User-Agent", "") or "")),
        })
        self.request_trace[:] = self.request_trace[-30:]

    def _get(
        self,
        url: str,
        *,
        stream: bool = False,
        stage: str = "request",
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    stream=stream,
                    allow_redirects=True,
                    headers=dict(headers or {}),
                )
                self._record_response(stage, url, response)
                status = int(response.status_code)
                if status >= 400:
                    error = UltrapackDownloadError(
                        f"HTTP {status} em {stage}: {self._safe_source_url(url)}"
                    )
                    if status in {401, 403}:
                        raise error from None
                    raise error
                return response
            except Exception as error:
                last = error
                if isinstance(error, UltrapackDownloadError) and any(
                    marker in str(error).lower() for marker in ("http 401", "http 403")
                ):
                    break
                if attempt >= self.retries:
                    break
                time.sleep(self.retry_delay)
        if isinstance(last, UltrapackDownloadError):
            raise last
        raise UltrapackDownloadError("Falha no download Ultrapack: " + sanitize_text(last)) from None

    @staticmethod
    def discover_download_url(product_url: str, html: str) -> str:
        tags = re.findall(r'''<a\b[^>]*>''', html, re.I)
        for tag in tags:
            class_match = re.search(r'''\bclass\s*=\s*["']([^"']*)["']''', tag, re.I)
            classes = (class_match.group(1).lower().split() if class_match else [])
            if "single-bt-download-a" not in classes:
                continue

            for attribute in ("href", "data-url", "data-download"):
                match = re.search(rf'''\b{attribute}\s*=\s*["']([^"']+)["']''', tag, re.I)
                if not match:
                    continue
                raw = unescape(match.group(1)).strip()
                if raw and not raw.startswith(("#", "javascript:")):
                    resolved = urljoin(product_url, raw)
                    if resolved != product_url:
                        return resolved

            token_match = re.search(r'''\bdata-f\s*=\s*["']([^"']+)["']''', tag, re.I)
            if not token_match:
                raise UltrapackDownloadError("Botão de download sem URL ou identificador data-f")
            identifier = unescape(token_match.group(1)).strip()
            if not identifier:
                raise UltrapackDownloadError("Botão de download com identificador vazio")
            parts = urlsplit(product_url)
            query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                     if key != "f"]
            query.append(("f", identifier))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
        raise UltrapackDownloadError("Botão real de download não encontrado no produto autenticado")

    def inspect_product(self, product_url: str) -> tuple[str, str]:
        response = self._get(
            product_url,
            stage="authenticated_product_page",
            headers={"Referer": self._origin(product_url)},
        )
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

    def authentication_probe(self, product_url: str) -> dict[str, Any]:
        download_url, version = self.inspect_product(product_url)
        if not download_url:
            raise UltrapackDownloadError("Sessão não expôs um download autorizado no produto")
        return {
            "authenticated": True,
            "version": version,
            "download_url": self._safe_source_url(download_url),
            "proof": "authenticated_product_with_download_control",
        }

    @staticmethod
    def _origin(url: str) -> str:
        parts = urlsplit(str(url or ""))
        return f"{parts.scheme}://{parts.netloc}/" if parts.scheme and parts.netloc else ""

    @staticmethod
    def _safe_source_url(url: str) -> str:
        return safe_url(url)

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
            raise UltrapackDownloadError("Arquivo baixado não possui extensão .zip")
        try:
            size, digest, entries = validate_zip_file(path, source_url=source_url)
        except Exception as error:
            raise UltrapackDownloadError(str(error)) from None
        return LocalZipArtifact(str(path), path.name, source_url, size, digest, entries)

    def _validated_response_artifact(
        self,
        response: Any,
        *,
        requested_url: str,
        target_dir: Path,
    ) -> LocalZipArtifact:
        name = self._response_file_name(response, requested_url)
        target = target_dir / name
        try:
            size, sha256, entries, diag = write_validated_zip_response(
                response,
                requested_url=requested_url,
                target=target,
                max_bytes=self.max_bytes,
            )
        except InvalidDownloadPayload as error:
            self.last_download_diagnostic = dict(error.diagnostic)
            wrapped = UltrapackDownloadError(str(error), diagnostic=error.diagnostic)
            setattr(wrapped, "html_sample", getattr(error, "html_sample", b""))
            raise wrapped from None
        except Exception as error:
            raise UltrapackDownloadError(sanitize_text(error)) from None
        self.last_download_diagnostic = diag.to_dict()
        return LocalZipArtifact(
            str(target), target.name, self._safe_source_url(str(getattr(response, "url", "") or requested_url)),
            size, sha256, entries,
        )

    def download(self, product_url: str, staging_dir: str | Path) -> tuple[LocalZipArtifact, str]:
        download_url, version = self.inspect_product(product_url)
        target_dir = Path(staging_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        headers = {
            "Referer": product_url,
            "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
        }
        response = self._get(download_url, stream=True, stage="final_download", headers=headers)
        try:
            return self._validated_response_artifact(
                response, requested_url=download_url, target_dir=target_dir
            ), version
        except UltrapackDownloadError as first_error:
            diagnostic = dict(getattr(first_error, "diagnostic", {}) or {})
            if diagnostic.get("response_kind") != "html":
                raise
            cause = str(diagnostic.get("probable_cause") or "").lower()
            if any(token in cause for token in ("login", "sessão", "cloudflare", "recusado")):
                raise
            sample = getattr(first_error, "html_sample", b"")
            alternate = extract_distinct_download_candidate(
                sample,
                base_url=str(getattr(response, "url", "") or download_url),
                current_url=download_url,
            )
            if not alternate:
                raise
            second = self._get(
                alternate,
                stream=True,
                stage="intermediate_download_target",
                headers={
                    "Referer": str(getattr(response, "url", "") or product_url),
                    "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
                },
            )
            return self._validated_response_artifact(
                second, requested_url=alternate, target_dir=target_dir
            ), version
