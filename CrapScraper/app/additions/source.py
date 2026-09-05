from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urljoin, urlparse

import requests

from app.updates.sources import SourceRegistry


_SOCIAL_HOST_TOKENS = ("facebook", "twitter", "youtube", "instagram", "google", "pinterest", "linkedin")
_CSS_TOKENS = (
    "{",
    "}",
    ";",
    "@media",
    "border-",
    "background-",
    "font-size",
    "line-height",
    ".post-",
    "blockquote",
    "color:",
)


def clean_official_url(value: object) -> str:
    text = html_lib.unescape(str(value or "").strip())
    markdown = re.search(r"\[[^\]]*\]\((https?://[^)]+)\)", text, re.I)
    if markdown:
        text = markdown.group(1)
    match = re.search(r"https?://[^\s<>\]]+", text, re.I)
    if not match:
        return ""
    return match.group(0).rstrip(").,;\"'")


def clean_developer(value: object) -> str:
    text = html_lib.unescape(str(value or "")).strip()
    text = " ".join(text.split())
    if not (2 <= len(text) <= 80):
        return ""
    lowered = text.casefold()
    if any(token in lowered for token in _CSS_TOKENS):
        return ""
    if re.search(r"[<>]", text):
        return ""
    if len(re.findall(r"[^\w\s.&+_\-]", text, re.UNICODE)) > 3:
        return ""
    return text.strip(" -:|")


def _clean_visible_html(raw_html: str) -> str:
    cleaned = re.sub(r"<!--.*?-->", " ", raw_html or "", flags=re.S)
    cleaned = re.sub(
        r"<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)>",
        " ",
        cleaned,
        flags=re.I | re.S,
    )
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return " ".join(html_lib.unescape(cleaned).split())


def _developer_from_html(raw_html: str, page_url: str = "") -> str:
    if not raw_html:
        return ""

    # Envato expõe o vendedor através de links /user/<slug>; é um sinal muito
    # mais confiável do que procurar a palavra "author" no CSS da página.
    for pattern in (
        r"(?:themeforest|codecanyon)\.net/user/([A-Za-z0-9_.-]{2,80})",
        r"href=[\"'][^\"']*/user/([A-Za-z0-9_.-]{2,80})(?:[/?#\"']|$)",
        r"[\"']author_username[\"']\s*:\s*[\"']([^\"']{2,80})[\"']",
        r"[\"']author_name[\"']\s*:\s*[\"']([^\"']{2,80})[\"']",
    ):
        for match in re.finditer(pattern, raw_html, re.I):
            candidate = clean_developer(match.group(1))
            if candidate:
                return candidate

    # JSON-LD / dados estruturados.
    for pattern in (
        r'[\"\'](?:author|creator|brand)[\"\']\s*:\s*\{[^{}]{0,500}?[\"\']name[\"\']\s*:\s*[\"\']([^\"\']{2,80})[\"\']',
        r'[\"\'](?:author|creator|brand)[\"\']\s*:\s*[\"\']([^\"\']{2,80})[\"\']',
    ):
        match = re.search(pattern, raw_html, re.I | re.S)
        if match:
            candidate = clean_developer(match.group(1))
            if candidate:
                return candidate

    visible = _clean_visible_html(raw_html)
    for pattern in (
        r"(?:developer|desenvolvedor)\s*[:\-]\s*([^|\n]{2,80}?)(?=\s{2,}|\b(?:version|versão|updated|atualizado|category|categoria)\b|$)",
        r"(?:created\s+by|desenvolvido\s+por|por)\s+([A-Za-z0-9_.&+\- ]{2,80})(?=\s{2,}|\b(?:version|versão|updated|atualizado)\b|$)",
    ):
        match = re.search(pattern, visible, re.I)
        if match:
            candidate = clean_developer(match.group(1))
            if candidate:
                return candidate
    return ""


class ProductResearchService:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _get(self, url: str) -> str:
        if not url:
            return ""
        try:
            response = self.session.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return ""

    def resolve(self, job):
        official = clean_official_url(job.get("official_url"))
        developer = clean_developer(job.get("developer"))
        if official and developer:
            return {"official_url": official, "developer": developer}

        source_url = clean_official_url(job.get("source_url")) or str(job.get("source_url") or "").strip()
        source_html = self._get(source_url)
        if not source_html:
            raise RuntimeError("Não foi possível pesquisar a página da fonte")

        if not official:
            source_host = urlparse(source_url).netloc.lower()
            links = re.findall(r'href=["\']([^"\']+)["\']', source_html, re.I)
            for link in links:
                candidate = urljoin(source_url, html_lib.unescape(link))
                host = urlparse(candidate).netloc.lower()
                if not host or host == source_host or any(token in host for token in _SOCIAL_HOST_TOKENS):
                    continue
                if any(token in host for token in ("themeforest.net", "codecanyon.net", "wordpress.org", "woocommerce.com")):
                    official = clean_official_url(candidate)
                    break
            if not official:
                for link in links:
                    candidate = urljoin(source_url, html_lib.unescape(link))
                    host = urlparse(candidate).netloc.lower()
                    if host and host != source_host and not any(token in host for token in _SOCIAL_HOST_TOKENS):
                        official = clean_official_url(candidate)
                        if official:
                            break

        if not developer and official:
            # A página oficial é preferida para confirmar autoria. Se houver WAF,
            # o fallback usa apenas o HTML visível da fonte já autenticada.
            developer = _developer_from_html(self._get(official), official)
        if not developer:
            developer = _developer_from_html(source_html, source_url)

        if not official:
            raise RuntimeError("Página oficial não pôde ser confirmada sem inventar dados")
        if not developer:
            raise RuntimeError("Desenvolvedor não pôde ser confirmado por fonte confiável")
        return {"official_url": official, "developer": developer}


class AdditionSourceService:
    def __init__(self, registry=None):
        self.registry = registry or SourceRegistry()

    def source(self, job):
        return self.registry.get(job["source_kind"])


__all__ = ["AdditionSourceService", "ProductResearchService", "clean_developer", "clean_official_url"]
