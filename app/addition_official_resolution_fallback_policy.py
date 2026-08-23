from __future__ import annotations

import html as html_lib
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import app.addition_conversation_capture_policy as capture


_INSTALLED = False
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
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("/l/?"):
        value = "https://duckduckgo.com" + value
    try:
        parsed = urlparse(value)
        query = parse_qs(parsed.query)
        for key in ("uddg", "url", "u", "target", "r"):
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
    path = str(parsed.path or "").lower()
    return (
        (host == expected or host == f"www.{expected}")
        and "/item/" in path
        and "full_screen_preview" not in path
    )


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
    text = html_lib.unescape(str(raw_html or "")).replace("\\/", "/")
    text = unquote(text)
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(
        rf"https?://(?:www\.)?{re.escape(expected)}/item/[A-Za-z0-9_\-/%]+(?:/\d+)?/?",
        re.I,
    )
    for match in pattern.finditer(text):
        value = match.group(0).rstrip(".,;)")
        if value in seen or not _marketplace_item_url(value, marketplace):
            continue
        seen.add(value)
        rows.append((value, ""))
    return rows


def _best_marketplace_candidate(name: str, marketplace: str, documents: list[str]) -> str:
    ranked: list[tuple[float, str]] = []
    for document in documents:
        for url, label in _extract_marketplace_candidates(document, marketplace):
            score = _name_similarity(name, url, label)
            if score >= 0.62:
                ranked.append((score, url))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return ranked[0][1] if ranked else ""


def _short_search_name(name: str) -> str:
    clean = " ".join(str(name or "").split()).strip()
    if not clean:
        return ""
    first = re.split(r"\s+[\-–—|]\s+", clean, maxsplit=1)[0].strip()
    return first if len(first) >= 4 else " ".join(clean.split()[:6])


def install_addition_official_resolution_fallback_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from app.addition_chat1_official_resolution_policy import install_addition_chat1_official_resolution_policy
    from app.addition_parallel_generation_policy import install_addition_parallel_generation_policy
    from app.addition_parallel_reference_fallback_policy import install_addition_parallel_reference_fallback_policy
    from app.addition_chat_binding_policy import install_addition_chat_binding_policy
    from app.addition_real_chat_url_policy import install_addition_real_chat_url_policy
    from app.addition_unique_chat_marker_policy import install_addition_unique_chat_marker_policy
    from app.addition_active_chat_capture_policy import install_addition_active_chat_capture_policy
    from app.addition_chat_title_policy import install_addition_chat_title_policy
    from app.addition_adaptive_chat_monitor_policy import install_addition_adaptive_chat_monitor_policy
    from app.addition_root_category_policy import install_addition_root_category_policy
    from app.addition_full_product_creation_policy import install_addition_full_product_creation_policy
    from app.addition_full_product_integrity_policy import install_addition_full_product_integrity_policy
    from app.addition_product_contract_policy import install_addition_product_contract_policy
    from app.addition_image_delivery_policy import install_addition_image_delivery_policy
    from app.addition_image_validation_policy import install_addition_image_validation_policy
    from app.addition_chat_reliability_policy import install_addition_chat_reliability_policy
    from app.addition_custom_fields_policy import install_addition_custom_fields_policy
    from app.comparison_operation_status_policy import install_comparison_operation_status_policy
    from app.product_custom_fields_guard_policy import install_product_custom_fields_guard_policy
    from app.addition_operational_ui_policy import install_addition_operational_ui_policy
    from app.addition_operational_legacy_suppression_policy import install_addition_operational_legacy_suppression_policy
    from app.addition_image_prompt_autosend_policy import install_addition_image_prompt_autosend_policy
    from app.addition_retry_recovery_policy import install_addition_retry_recovery_policy

    install_addition_chat1_official_resolution_policy()
    install_addition_parallel_generation_policy()
    install_addition_chat_binding_policy()
    install_addition_real_chat_url_policy()
    install_addition_unique_chat_marker_policy()
    install_addition_active_chat_capture_policy()
    install_addition_chat_title_policy()
    install_addition_adaptive_chat_monitor_policy()
    install_addition_root_category_policy()
    install_addition_full_product_creation_policy()
    install_addition_full_product_integrity_policy()
    # Final product contract: short prompts, generated image only and WooCommerce Licença taxonomy.
    install_addition_product_contract_policy()
    # Final image delivery: 500x500 WebP <=100 KB, SEO filename and readable chat titles.
    install_addition_image_delivery_policy()
    # Delivery validation replaces the old minimum-size heuristic for optimized WebP files.
    install_addition_image_validation_policy()
    # Runtime guard: persistent chat titles + safe handling of ChatGPT request-limit dialogs.
    install_addition_chat_reliability_policy()
    # Store metadata: external official URL and developer custom fields.
    install_addition_custom_fields_policy()
    # Final comparison projection: operation outcomes + source-neutral wording.
    install_comparison_operation_status_policy()
    # Final guard: after every update/addition, preserve or resolve the three catalog metadata fields.
    install_product_custom_fields_guard_policy()
    # Final guard for the active generator: missing/failed mockup must never abort Preparation.
    install_addition_parallel_reference_fallback_policy()
    # Operational UI/queue is installed after all business-flow wrappers.
    install_addition_operational_ui_policy()
    # Suppress only the legacy renderers; their endpoints and backend functions stay available.
    install_addition_operational_legacy_suppression_policy()
    # Final ChatGPT send contract: prompt image auto-submit + reference image already stored in the Project.
    install_addition_image_prompt_autosend_policy()
    # Final retry recovery: repair stale Woo content and reload PluginTheme auth/ZIP without repeating prepared stages.
    install_addition_retry_recovery_policy()
    _INSTALLED = True
