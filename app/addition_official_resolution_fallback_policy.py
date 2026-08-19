from __future__ import annotations

import html as html_lib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Mapping
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import app.addition_conversation_capture_policy as capture
import app.new_product_workflow_policy as additions
import app.addition_one_click_policy as one_click


_INSTALLED = False
_ORIGINAL_RESOLVE = None

_MARKETPLACES = {
    "themeforest": "themeforest.net",
    "codecanyon": "codecanyon.net",
}


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.findall(r"[a-z0-9]+", text.encode("ascii", "ignore").decode().lower()))


def _marketplace_from_source(source_url: str) -> str:
    folded = _fold(source_url)
    for marker in _MARKETPLACES:
        if marker in folded:
            return marker
    return ""


def _unwrap_search_url(url: str) -> str:
    value = html_lib.unescape(str(url or "").strip())
    if not value:
        return ""
    try:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        for key in ("uddg", "url", "u", "target"):
            target = query.get(key)
            if target:
                candidate = unquote(str(target[0] or "")).strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate
    except Exception:
        pass
    return value


def _marketplace_item_url(url: str, marketplace: str) -> bool:
    expected = _MARKETPLACES.get(marketplace, "")
    if not expected:
        return False
    value = _unwrap_search_url(url)
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = str(parsed.hostname or "").lower()
    if not (host == expected or host == f"www.{expected}"):
        return False
    path = str(parsed.path or "").lower()
    return "/item/" in path and "full_screen_preview" not in path


def _name_similarity(name: str, url: str, label: str = "") -> float:
    wanted = _fold(name)
    if not wanted:
        return 0.0
    try:
        slug = str(urlparse(_unwrap_search_url(url)).path or "")
    except Exception:
        slug = ""
    haystack = _fold(f"{slug} {label}")
    if not haystack:
        return 0.0
    if wanted in haystack:
        return 1.0

    wanted_tokens = [token for token in wanted.split() if len(token) >= 2]
    hay_tokens = set(haystack.split())
    overlap = (
        sum(1 for token in wanted_tokens if token in hay_tokens) / len(wanted_tokens)
        if wanted_tokens
        else 0.0
    )
    sequence = SequenceMatcher(None, wanted, haystack).ratio()
    return max(overlap, sequence)


def _extract_marketplace_candidates(raw_html: str, marketplace: str) -> list[tuple[str, str]]:
    expected = _MARKETPLACES.get(marketplace, "")
    if not expected:
        return []

    text = html_lib.unescape(str(raw_html or ""))
    text = text.replace("\\/", "/")
    text = unquote(text)
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    pattern = re.compile(
        rf"https?://(?:www\.)?{re.escape(expected)}/item/[A-Za-z0-9_\-/%]+(?:/\d+)?/?(?:[#?][^\s\"'<>]*)?",
        re.I,
    )
    for match in pattern.finditer(text):
        url = _unwrap_search_url(match.group(0)).rstrip(".,;)")
        if url in seen or not _marketplace_item_url(url, marketplace):
            continue
        seen.add(url)
        candidates.append((url, ""))

    parser = capture._AnchorParser()
    try:
        parser.feed(text)
    except Exception:
        return candidates
    for row in parser.rows:
        href = _unwrap_search_url(str(row.get("href") or ""))
        label = str(row.get("text") or "")
        if href in seen or not _marketplace_item_url(href, marketplace):
            continue
        seen.add(href)
        candidates.append((href, label))
    return candidates


def _best_marketplace_candidate(name: str, marketplace: str, documents: list[str]) -> str:
    ranked: list[tuple[float, str]] = []
    for document in documents:
        for url, label in _extract_marketplace_candidates(document, marketplace):
            similarity = _name_similarity(name, url, label)
            if similarity < 0.62:
                continue
            item_id_bonus = 0.08 if re.search(r"/\d+/?(?:[?#].*)?$", url) else 0.0
            ranked.append((similarity + item_id_bonus, url))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1] if ranked else ""


def _search_documents(name: str, marketplace: str) -> list[str]:
    domain = _MARKETPLACES.get(marketplace, "")
    if not domain:
        return []
    query = quote_plus(f'site:{domain}/item "{name}"')
    targets = (
        f"https://html.duckduckgo.com/html/?q={query}",
        f"https://www.bing.com/search?q={query}",
    )
    documents: list[str] = []
    for target in targets:
        try:
            documents.append(capture._fetch_html(target))
        except Exception:
            continue
    return documents


def _resolve_by_marketplace(job: Mapping[str, Any]) -> tuple[str, str]:
    source_url = str(job.get("source_product_url") or "").strip()
    name = str(job.get("source_name") or job.get("title") or "").strip()
    marketplace = _marketplace_from_source(source_url)
    if not marketplace or not name:
        return "", ""

    documents: list[str] = []
    try:
        documents.append(capture._fetch_html(source_url))
    except Exception:
        pass

    official = _best_marketplace_candidate(name, marketplace, documents)
    if official:
        return official, f"HTML/metadata da fonte ({marketplace})"

    domain = _MARKETPLACES[marketplace]
    direct_search = f"https://{domain}/search/{quote_plus(name)}"
    try:
        documents.append(capture._fetch_html(direct_search))
    except Exception:
        pass
    official = _best_marketplace_candidate(name, marketplace, documents)
    if official:
        return official, f"busca direta no {marketplace}"

    search_docs = _search_documents(name, marketplace)
    official = _best_marketplace_candidate(name, marketplace, search_docs)
    if official:
        return official, f"busca web restrita a {domain}"
    return "", marketplace


def _resolve_official_with_fallback(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    source_url = str(job.get("source_product_url") or "").strip()
    current = str(job.get("source_official_url") or "").strip()

    if capture._is_official_candidate(current, source_url):
        return _ORIGINAL_RESOLVE(job_id)

    original_error: BaseException | None = None
    try:
        return _ORIGINAL_RESOLVE(job_id)
    except Exception as error:
        original_error = error

    one_click._emit(
        job_id,
        "O link oficial não veio no HTML simples da fonte; tentando identificar o marketplace e pesquisar o item oficial…",
        step="official_source",
        progress=5,
    )
    official, method = _resolve_by_marketplace(job)
    if official and capture._is_official_candidate(official, source_url):
        additions._update(job_id, source_official_url=official, error="")
        one_click._emit(
            job_id,
            f"Página oficial resolvida por {method}: {official}",
            step="official_source",
            progress=7,
        )
        return additions._row(job_id)

    marketplace = _marketplace_from_source(source_url)
    if marketplace:
        raise RuntimeError(
            f"A fonte indica {marketplace}, mas nenhum item oficial com correspondência segura ao nome do produto foi encontrado. "
            "O fluxo foi interrompido para evitar vincular um produto incorreto."
        ) from None
    if original_error is not None:
        raise original_error
    raise RuntimeError("A página oficial do produto não pôde ser identificada com segurança.")


def install_addition_official_resolution_fallback_policy() -> None:
    global _INSTALLED, _ORIGINAL_RESOLVE
    if _INSTALLED:
        return
    _ORIGINAL_RESOLVE = capture._resolve_official_for_job
    capture._resolve_official_for_job = _resolve_official_with_fallback
    _INSTALLED = True
