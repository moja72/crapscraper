from __future__ import annotations

import html
import re
from typing import Any

PLUGIN_CATEGORY_ID = 504
THEME_CATEGORY_ID = 525

_LIST_BLOCK_RE = re.compile(r"<(?:ul|ol)\b[^>]*>(.*?)</(?:ul|ol)>", re.I | re.S)
_LIST_ITEM_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)
_HEADING_RE = re.compile(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def category_name(kind: Any) -> str:
    return "Plugin" if str(kind or "").strip().casefold() == "plugin" else "Tema"


def category_id(kind: Any) -> int:
    return PLUGIN_CATEGORY_ID if str(kind or "").strip().casefold() == "plugin" else THEME_CATEGORY_ID


def strip_tags(value: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", str(value or ""))).split()).strip()


def prose_only_html(value: Any) -> str:
    """Normalize generated long description to paragraphs only.

    The catalog must not receive feature lists/headings from ChatGPT. If an old
    cached response contains them, preserve the information as prose instead of
    sending <ul>/<li>/<h2> markup to WooCommerce.
    """
    text = str(value or "").strip()
    if not text:
        return ""

    paragraphs: list[str] = []
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", text, re.I | re.S):
        cleaned = strip_tags(match.group(1))
        if cleaned:
            paragraphs.append(cleaned)

    # Convert any lists/headings that appeared outside/after paragraphs into
    # normal prose so old generated output cannot create list-style descriptions.
    for block in _LIST_BLOCK_RE.findall(text):
        items = [strip_tags(item) for item in _LIST_ITEM_RE.findall(block)]
        items = [item for item in items if item]
        if items:
            paragraphs.append(" ".join(items))
    for heading in _HEADING_RE.findall(text):
        cleaned = strip_tags(heading)
        if cleaned:
            paragraphs.append(cleaned)

    if not paragraphs:
        cleaned = strip_tags(text)
        if cleaned:
            paragraphs.append(cleaned)

    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for paragraph in paragraphs:
        key = paragraph.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(paragraph)

    return "".join(f"<p>{html.escape(paragraph, quote=False)}</p>" for paragraph in deduped)


def apply(job: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    clean = dict(result)
    clean["product_name"] = str(job.get("product_name") or clean.get("product_name") or "").strip()
    clean["short_description"] = " ".join(str(clean.get("short_description") or "").split())
    clean["content"] = prose_only_html(clean.get("content"))
    clean["categories"] = [category_name(job.get("kind"))]
    clean["category_ids"] = [category_id(job.get("kind"))]
    clean["tags"] = []
    return clean


def has_forbidden_list_markup(value: Any) -> bool:
    text = str(value or "").casefold()
    return any(token in text for token in ("<ul", "<ol", "<li", "<h1", "<h2", "<h3", "<h4", "<h5", "<h6"))


__all__ = [
    "PLUGIN_CATEGORY_ID",
    "THEME_CATEGORY_ID",
    "apply",
    "category_id",
    "category_name",
    "has_forbidden_list_markup",
    "prose_only_html",
]
