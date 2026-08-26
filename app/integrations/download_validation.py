"""Validação compartilhada de respostas de download do fluxo Atualizar."""
from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.integrations.wordpress import IntegrationError


ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
HTML_PREFIXES = (b"<!doctype html", b"<html", b"<head", b"<body")
DEFAULT_MIN_ZIP_BYTES = 128
MAX_HTML_DIAGNOSTIC_BYTES = 32768


def safe_url(url: str) -> str:
    parts = urlsplit(str(url or ""))
    query = [(key, "[redacted]") for key, _value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


@dataclass(frozen=True)
class DownloadDiagnostic:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    content_disposition: str
    redirects: tuple[str, ...]
    probable_cause: str
    response_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvalidDownloadPayload(IntegrationError):
    def __init__(self, message: str, diagnostic: DownloadDiagnostic) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic.to_dict()


def _header(response: Any, name: str) -> str:
    headers = getattr(response, "headers", {}) or {}
    return str(headers.get(name, "") or "").strip()


def _history(response: Any) -> list[Any]:
    return list(getattr(response, "history", None) or [])


def classify_html(html: bytes | str, *, final_url: str = "", status: int = 200) -> str:
    if isinstance(html, bytes):
        text = html[:MAX_HTML_DIAGNOSTIC_BYTES].decode("utf-8", "replace")
    else:
        text = str(html or "")[:MAX_HTML_DIAGNOSTIC_BYTES]
    lowered = re.sub(r"\s+", " ", text).lower()
    final = str(final_url or "").lower()

    if status in {401, 403}:
        return "autenticação ou acesso recusado"
    if any(token in final for token in ("/login", "/auth/login", "/signin", "/entrar", "/minha-conta")):
        return "sessão expirada / redirecionamento para login"
    if any(token in lowered for token in (
        "cf-chl-", "cloudflare", "checking your browser", "just a moment",
        "verify you are human", "attention required",
    )):
        return "bloqueio ou desafio Cloudflare"
    if any(token in lowered for token in (
        "name=\"password\"", "type=\"password\"", "forgot password",
        "esqueci minha senha", "faça login", "fazer login", "sign in",
    )):
        return "sessão expirada / página de login"
    if any(token in lowered for token in (
        "access denied", "forbidden", "sem acesso", "não autorizado", "nao autorizado",
        "permission denied",
    )):
        return "acesso ao download recusado"
    if any(token in lowered for token in (
        "download", "aguarde", "preparing", "preparando", "redirect",
    )):
        return "página intermediária de download"
    if status >= 400:
        return f"página de erro HTTP {status}"
    return "servidor retornou uma página HTML em vez do arquivo"


def build_diagnostic(
    response: Any,
    *,
    requested_url: str,
    probable_cause: str = "",
    response_kind: str = "unknown",
) -> DownloadDiagnostic:
    final_url = str(getattr(response, "url", "") or requested_url)
    status = int(getattr(response, "status_code", 0) or 0)
    redirects = tuple(
        f"{int(getattr(item, 'status_code', 0) or 0)} {safe_url(str(getattr(item, 'url', '') or ''))}"
        for item in _history(response)
    )
    return DownloadDiagnostic(
        requested_url=safe_url(requested_url),
        final_url=safe_url(final_url),
        status=status,
        content_type=_header(response, "Content-Type"),
        content_disposition=_header(response, "Content-Disposition")[:240],
        redirects=redirects,
        probable_cause=probable_cause,
        response_kind=response_kind,
    )


def diagnostic_message(diagnostic: dict[str, Any] | DownloadDiagnostic) -> str:
    data = diagnostic.to_dict() if isinstance(diagnostic, DownloadDiagnostic) else dict(diagnostic or {})
    lines = [
        "Download inválido: servidor não entregou um ZIP utilizável.",
        f"URL solicitada: {data.get('requested_url') or '-'}",
        f"URL final: {data.get('final_url') or '-'}",
        f"Status HTTP: {data.get('status') or '-'}",
        f"Content-Type: {data.get('content_type') or '-'}",
    ]
    disposition = str(data.get("content_disposition") or "").strip()
    if disposition:
        lines.append(f"Content-Disposition: {disposition}")
    redirects = list(data.get("redirects") or [])
    if redirects:
        lines.append("Redirects: " + " → ".join(str(item) for item in redirects[-4:]))
    cause = str(data.get("probable_cause") or "").strip()
    if cause:
        lines.append(f"Diagnóstico provável: {cause}.")
    return "\n".join(lines)


def _looks_html(head: bytes, content_type: str) -> bool:
    clean = bytes(head or b"").lstrip().lower()
    mime = str(content_type or "").lower()
    return (
        "text/html" in mime
        or "application/xhtml" in mime
        or clean.startswith(HTML_PREFIXES)
    )


def _zip_magic_ok(head: bytes) -> bool:
    clean = bytes(head or b"")
    return any(clean.startswith(prefix) for prefix in ZIP_MAGIC_PREFIXES)


def validate_zip_file(
    path: Path,
    *,
    source_url: str = "",
    min_bytes: int = DEFAULT_MIN_ZIP_BYTES,
) -> tuple[int, str, int]:
    del source_url
    size = path.stat().st_size if path.exists() else 0
    if size < max(1, int(min_bytes)):
        raise IntegrationError(f"ZIP pequeno demais para ser plausível ({size} bytes)")
    with path.open("rb") as source:
        head = source.read(8)
    if not _zip_magic_ok(head):
        raise IntegrationError("Assinatura do arquivo não corresponde a um ZIP")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = len(archive.infolist())
            bad = archive.testzip()
            if entries <= 0 or bad:
                raise IntegrationError("ZIP corrompido ou sem conteúdo")
    except zipfile.BadZipFile:
        raise IntegrationError("Arquivo não pôde ser aberto como ZIP") from None
    return size, digest.hexdigest(), entries


def write_validated_zip_response(
    response: Any,
    *,
    requested_url: str,
    target: Path,
    max_bytes: int,
    min_bytes: int = DEFAULT_MIN_ZIP_BYTES,
    chunk_size: int = 1024 * 1024,
) -> tuple[int, str, int, DownloadDiagnostic]:
    status = int(getattr(response, "status_code", 0) or 0)
    content_type = _header(response, "Content-Type")
    final_url = str(getattr(response, "url", "") or requested_url)

    if status < 200 or status >= 300:
        cause = "autenticação ou acesso recusado" if status in {401, 403} else f"HTTP {status}"
        diag = build_diagnostic(
            response, requested_url=requested_url, probable_cause=cause, response_kind="http_error"
        )
        raise InvalidDownloadPayload(diagnostic_message(diag), diag)

    iterator: Iterable[bytes] = response.iter_content(chunk_size)
    first = b""
    pending: list[bytes] = []
    for chunk in iterator:
        if chunk:
            first = bytes(chunk)
            pending.append(first)
            break

    if not first:
        diag = build_diagnostic(
            response, requested_url=requested_url, probable_cause="resposta vazia", response_kind="empty"
        )
        raise InvalidDownloadPayload(diagnostic_message(diag), diag)

    if _looks_html(first, content_type):
        sample = first
        while len(sample) < MAX_HTML_DIAGNOSTIC_BYTES:
            try:
                chunk = next(iterator)
            except StopIteration:
                break
            if chunk:
                sample += bytes(chunk)
        cause = classify_html(sample, final_url=final_url, status=status)
        diag = build_diagnostic(
            response, requested_url=requested_url, probable_cause=cause, response_kind="html"
        )
        error = InvalidDownloadPayload(diagnostic_message(diag), diag)
        setattr(error, "html_sample", sample[:MAX_HTML_DIAGNOSTIC_BYTES])
        raise error

    if not _zip_magic_ok(first):
        cause = "assinatura/magic bytes não correspondem a ZIP"
        diag = build_diagnostic(
            response, requested_url=requested_url, probable_cause=cause, response_kind="binary_not_zip"
        )
        raise InvalidDownloadPayload(diagnostic_message(diag), diag)

    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with target.open("wb") as output:
            for chunk in pending:
                total += len(chunk)
                if total > max_bytes:
                    raise IntegrationError("ZIP excede o limite de tamanho")
                output.write(chunk)
            for chunk in iterator:
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise IntegrationError("ZIP excede o limite de tamanho")
                output.write(chunk)
        size, sha256, entries = validate_zip_file(target, min_bytes=min_bytes)
    except Exception:
        target.unlink(missing_ok=True)
        raise

    diag = build_diagnostic(
        response, requested_url=requested_url, probable_cause="ZIP validado", response_kind="zip"
    )
    return size, sha256, entries, diag


def extract_distinct_download_candidate(html: bytes | str, *, base_url: str, current_url: str) -> str:
    """Descobre um único destino diferente em páginas intermediárias legítimas."""
    if isinstance(html, bytes):
        text = html[:MAX_HTML_DIAGNOSTIC_BYTES].decode("utf-8", "replace")
    else:
        text = str(html or "")[:MAX_HTML_DIAGNOSTIC_BYTES]

    candidates: list[str] = []
    for match in re.finditer(r'''(?:href|data-url|data-download)\s*=\s*["']([^"']+)["']''', text, re.I):
        candidates.append(unescape(match.group(1)).strip())
    for match in re.finditer(r'''url\s*=\s*([^"'<>\s]+)''', text, re.I):
        candidates.append(unescape(match.group(1)).strip())

    current_safe = safe_url(current_url)
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in candidates:
        if not raw or raw.startswith(("#", "javascript:", "mailto:")):
            continue
        resolved = urljoin(base_url or current_url, raw)
        parts = urlsplit(resolved)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            continue
        if safe_url(resolved) == current_safe or resolved in seen:
            continue
        seen.add(resolved)
        lower = resolved.lower()
        score = 0
        if ".zip" in lower:
            score += 5
        if "download" in lower or "file" in lower:
            score += 3
        if "token" in lower or "signature" in lower:
            score += 1
        ranked.append((score, resolved))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else ""
