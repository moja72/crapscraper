from __future__ import annotations

import asyncio
import math
import re
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from app.collection.legacy_core import settings
from app.collection.legacy_core.adapters import AdapterDefinition, get_adapter
from app.collection.legacy_core.browser import (
    BrowserSession,
    check_pause_stop as browser_check_pause_stop,
    close_browser_session,
    controlled_sleep,
    open_authenticated_browser_session,
    safe_goto,
)
from app.collection.legacy_core.models import (
    RunOptions,
    ScraperContext,
    build_context,
    build_run_options,
)
from app.collection.legacy_core.storage import (
    build_context_paths,
    clean_queue_items,
    compare_complete_integrity,
    describe_product_changes,
    ensure_template_image_saved,
    ensure_trailing_slash,
    filter_categories_by_scope,
    filter_existing_products_by_scope,
    get_resume_info,
    is_category_cache_valid_normal,
    load_available_categories,
    load_categories_cache,
    load_existing_products_dict,
    load_progress_data,
    load_queue_cache,
    merge_existing_product,
    normalize_available_categories_list,
    now_iso,
    save_available_categories,
    save_catalog_state,
    save_full_logs_text,
    save_individual_category_cache,
    save_status_text,
    to_int,
)

try:
    from app.core.exceptions import EngineError, StopScraper
except Exception:  # pragma: no cover
    from app.collection.legacy_core.browser import StopScraper

    class EngineError(RuntimeError):
        pass


# ============================================================
# HELPERS BÁSICOS
# ============================================================


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _log(app: Any, message: str) -> None:
    if app is None:
        return

    logger = getattr(app, "log", None)
    if callable(logger):
        with suppress(Exception):
            logger(str(message))


def _state_update(app: Any, **kwargs: Any) -> None:
    if app is None:
        return

    state = getattr(app, "state", None)
    if state is None:
        return

    updater = getattr(state, "update", None)
    if callable(updater):
        with suppress(Exception):
            updater(**kwargs)


def _state_snapshot_data(app: Any) -> dict[str, Any]:
    if app is None:
        return {}

    state = getattr(app, "state", None)
    if state is None:
        return {}

    snapshot = getattr(state, "snapshot", None)
    if callable(snapshot):
        with suppress(Exception):
            data = snapshot()
            if isinstance(data, Mapping):
                if isinstance(data.get("data"), Mapping):
                    return dict(data.get("data", {}))
                return dict(data)

    data = getattr(state, "data", None)
    if isinstance(data, Mapping):
        return dict(data)

    return {}


def _control_payload(control: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}

    current_run_mode = getattr(control, "current_run_mode", None)
    if current_run_mode not in (None, ""):
        payload["run_mode"] = str(current_run_mode)

    current_run_payload = getattr(control, "current_run_payload", None)
    if isinstance(current_run_payload, Mapping):
        payload["run_payload"] = dict(current_run_payload)

    return payload


def _get_run_mode_full() -> str:
    return str(getattr(settings, "RUN_MODE_FULL", "full_sync") or "full_sync").strip().lower()


def _get_run_mode_categories_only() -> str:
    return str(getattr(settings, "RUN_MODE_CATEGORIES_ONLY", "categories_only") or "categories_only").strip().lower()


def _get_run_mode_links_only() -> str:
    return str(getattr(settings, "RUN_MODE_LINKS_ONLY", "links_only") or "links_only").strip().lower()


def _get_run_mode_existing_review() -> str:
    return str(getattr(settings, "RUN_MODE_EXISTING_REVIEW", "existing_review") or "existing_review").strip().lower()


def _get_run_mode_primary() -> str:
    return str(getattr(settings, "RUN_MODE_PRIMARY", "primary") or "primary").strip().lower()


def _get_run_modes() -> set[str]:
    raw = getattr(
        settings,
        "RUN_MODES",
        {
            _get_run_mode_full(),
            _get_run_mode_categories_only(),
            _get_run_mode_links_only(),
            _get_run_mode_existing_review(),
            _get_run_mode_primary(),
        },
    )
    try:
        return {str(value).strip().lower() for value in raw if str(value).strip()}
    except Exception:
        return {
            _get_run_mode_full(),
            _get_run_mode_categories_only(),
            _get_run_mode_links_only(),
            _get_run_mode_existing_review(),
            _get_run_mode_primary(),
        }


def _get_run_modes_with_detail() -> set[str]:
    raw = getattr(
        settings,
        "RUN_MODES_WITH_DETAIL",
        {
            _get_run_mode_full(),
            _get_run_mode_existing_review(),
        },
    )
    try:
        return {str(value).strip().lower() for value in raw if str(value).strip()}
    except Exception:
        return {
            _get_run_mode_full(),
            _get_run_mode_existing_review(),
        }


def _get_default_verify_mode() -> str:
    return str(getattr(settings, "DEFAULT_VERIFY_MODE", "normal") or "normal").strip().lower()


def _get_default_scope_mode() -> str:
    return str(getattr(settings, "DEFAULT_SCOPE_MODE", "all") or "all").strip().lower()


def _get_default_save_every_items() -> int:
    return max(1, to_int(getattr(settings, "DEFAULT_SAVE_EVERY_ITEMS", 5), 5))


def _get_default_save_every_minutes() -> int:
    return max(1, to_int(getattr(settings, "DEFAULT_SAVE_EVERY_MINUTES", 1), 1))


def _get_max_pages_fallback() -> int:
    return max(1, to_int(getattr(settings, "MAX_PAGINAS_FALLBACK", 200), 200))


def _get_test_mode() -> bool:
    return bool(getattr(settings, "TEST_MODE", False))


def _get_test_max_categories() -> int:
    return max(0, to_int(getattr(settings, "TESTE_MAX_CATEGORIAS", 2), 2))


def _get_test_max_items_per_category() -> int:
    return max(0, to_int(getattr(settings, "TESTE_MAX_ITENS_POR_CATEGORIA", 15), 15))


def _truncate_log_value(value: Any, limit: int = 220) -> str:
    text = _normalize_spaces(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _get_run_mode_label(run_mode: str | None) -> str:
    return settings.get_run_mode_label(run_mode or _get_run_mode_full())


def _normalize_run_mode(run_mode: str | None) -> str:
    mode = str(run_mode or "").strip().lower()

    if mode == _get_run_mode_primary():
        return _get_run_mode_full()

    if mode in _get_run_modes():
        return mode

    return _get_run_mode_full()


def _resolve_resume_info(meta: Mapping[str, Any] | None) -> dict[str, Any]:
    return get_resume_info(
        meta,
        allowed_run_modes_with_detail=_get_run_modes_with_detail(),
        run_mode_labels=getattr(settings, "RUN_MODE_LABELS", {}),
    )


def _persist_full_logs(app: Any, context: Any = None) -> None:
    with suppress(Exception):
        save_full_logs_text(app, context=context, also_save_status=True)


def _use_http_listing_for_plugintheme() -> bool:
    return bool(getattr(settings, "PLUGINTHEME_USE_HTTP_LISTING", True))


def _use_http_listing_for_ultrapackv2() -> bool:
    return bool(getattr(settings, "ULTRAPACKV2_USE_HTTP_LISTING", True))


def _use_http_listing_for_context(context: Any = None) -> bool:
    resolved_context = build_context(context)

    if resolved_context.site_key == "plugintheme":
        return _use_http_listing_for_plugintheme()

    if resolved_context.site_key == "ultrapackv2":
        return _use_http_listing_for_ultrapackv2()

    return False


def _get_http_timeout_seconds() -> int:
    timeout_ms = max(1, to_int(getattr(settings, "TIMEOUT", 30_000), 30_000))
    return max(10, int(timeout_ms / 1000))


def _get_http_retry_attempts() -> int:
    return max(1, to_int(getattr(settings, "HTTP_RETRY_ATTEMPTS", 4), 4))


def _get_http_retry_delay_seconds() -> float:
    try:
        return max(0.0, float(getattr(settings, "HTTP_RETRY_DELAY_SECONDS", 0.8)))
    except Exception:
        return 0.8


def _get_http_accept_header() -> str:
    return str(
        getattr(
            settings,
            "HTTP_ACCEPT_HEADER",
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        )
    )


def _get_http_accept_language() -> str:
    return str(
        getattr(
            settings,
            "HTTP_ACCEPT_LANGUAGE",
            "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        )
    )


def _get_http_accept_encoding() -> str:
    return str(getattr(settings, "HTTP_ACCEPT_ENCODING", "gzip, deflate"))


def _get_ultrapack_http_page_size() -> int:
    return max(1, to_int(getattr(settings, "ULTRAPACKV2_HTTP_PAGE_SIZE", 128), 128))


def _get_ultrapack_grouped_category_single_page() -> bool:
    return bool(getattr(settings, "ULTRAPACKV2_GROUPED_CATEGORY_SINGLE_PAGE", True))


def _get_ultrapack_http_category_cooldown_seconds() -> float:
    try:
        return max(0.0, float(getattr(settings, "ULTRAPACKV2_HTTP_CATEGORY_COOLDOWN_SECONDS", 0.45)))
    except Exception:
        return 0.45


def _should_use_single_page_grouped_category(
    grouped_category_url: str,
    *,
    context: Any = None,
) -> bool:
    resolved_context = build_context(context)
    url = ensure_trailing_slash(grouped_category_url).lower()

    if resolved_context.site_key != "ultrapackv2":
        return False

    if not _get_ultrapack_grouped_category_single_page():
        return False

    return any(
        token in url
        for token in (
            "/plugins/codecanyon/",
            "/temas/themeforest/",
        )
    )


def _replace_query_param(url: str, key: str, value: Any) -> str:
    normalized_url = _normalize_spaces(url)
    if not normalized_url:
        return ""

    split = urlsplit(normalized_url)
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(split.query, keep_blank_values=True)
        if str(k).strip().lower() != str(key).strip().lower()
    ]
    query_pairs.append((str(key), str(value)))
    new_query = urlencode(query_pairs, doseq=True)

    return urlunsplit(
        (split.scheme, split.netloc, split.path, new_query, split.fragment)
    )


def _build_ultrapack_http_page_candidates(
    category_url: str,
    page_number: int,
    page_size_value: int,
) -> list[str]:
    base_url = ensure_trailing_slash(category_url)
    if not base_url:
        return []

    page_number = max(1, int(page_number))
    page_size_value = max(1, int(page_size_value))

    candidates: list[str] = []
    seen: set[str] = set()

    def _push(url: str) -> None:
        normalized = _normalize_spaces(url)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    url_with_ppg = _replace_query_param(base_url, "ppg", page_size_value)

    if page_number <= 1:
        _push(url_with_ppg)
        _push(base_url)
        return candidates

    split = urlsplit(base_url)
    clean_path = split.path or "/"
    clean_path = re.sub(r"/page/\d+/?$", "/", clean_path, flags=re.IGNORECASE)
    clean_path = ensure_trailing_slash(clean_path)

    page_path = f"{clean_path}page/{page_number}/"
    page_url = urlunsplit((split.scheme, split.netloc, page_path, "", split.fragment))

    _push(_replace_query_param(page_url, "ppg", page_size_value))
    _push(_replace_query_param(url_with_ppg, "paged", page_number))

    paged_first = _replace_query_param(base_url, "paged", page_number)
    _push(_replace_query_param(paged_first, "ppg", page_size_value))

    return candidates


def _build_listing_page_candidates(
    category_url: str,
    page_number: int,
    *,
    page_size_value: int,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
    use_http_listing: bool | None = None,
) -> list[str]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    http_enabled = (
        _use_http_listing_for_context(resolved_context)
        if use_http_listing is None
        else bool(use_http_listing)
    )

    if http_enabled and resolved_context.site_key == "ultrapackv2":
        return _build_ultrapack_http_page_candidates(
            category_url,
            page_number,
            page_size_value,
        )

    return build_page_candidates(
        category_url,
        page_number,
        context=resolved_context,
        runtime_context=runtime_context,
        adapter=resolved_adapter,
    )


async def _get_browser_cookies_from_page(page: Any, target_url: str = "") -> list[dict[str, Any]]:
    context = getattr(page, "context", None)
    if callable(context):
        with suppress(Exception):
            context = context()

    if context is None:
        return []

    cookies: list[dict[str, Any]] = []

    try:
        if target_url:
            cookies = [dict(item) for item in (await context.cookies([target_url])) or []]
        else:
            cookies = [dict(item) for item in (await context.cookies()) or []]
    except Exception:
        cookies = []

    if not cookies:
        try:
            cookies = [dict(item) for item in (await context.cookies()) or []]
        except Exception:
            cookies = []

    return cookies


async def _get_browser_document_cookie_header(page: Any) -> str:
    try:
        value = await page.evaluate("() => document.cookie || ''")
        return _normalize_spaces(value)
    except Exception:
        return ""


def _merge_cookie_headers(base_cookie_header: str, extra_cookie_header: str) -> str:
    merged: list[str] = []
    positions: dict[str, int] = {}

    for raw_header in (base_cookie_header, extra_cookie_header):
        for raw_part in str(raw_header or "").split(";"):
            part = raw_part.strip()
            if not part or "=" not in part:
                continue

            name, value = part.split("=", 1)
            cookie_name = _normalize_spaces(name)
            cookie_value = value.strip()

            if not cookie_name:
                continue

            key = cookie_name.lower()
            piece = f"{cookie_name}={cookie_value}"

            if key in positions:
                merged[positions[key]] = piece
            else:
                positions[key] = len(merged)
                merged.append(piece)

    return "; ".join(merged)


def _prepare_authenticated_http_session(
    session: requests.Session,
    *,
    target_url: str,
    current_url: str,
    referer: str,
    browser_cookies: Sequence[Mapping[str, Any]] | None,
    document_cookie_header: str,
    preserve_existing_state: bool,
) -> None:
    session.trust_env = False

    if not preserve_existing_state:
        with suppress(Exception):
            session.headers.clear()
        with suppress(Exception):
            session.cookies.clear()

    headers = _build_browser_like_http_headers(
        target_url,
        current_url=current_url,
        referer=referer,
    )

    for key, value in headers.items():
        session.headers[key] = value

    if document_cookie_header:
        existing_cookie_header = session.headers.get("Cookie", "") if preserve_existing_state else ""
        merged_cookie_header = _merge_cookie_headers(
            existing_cookie_header,
            document_cookie_header,
        )
        if merged_cookie_header:
            session.headers["Cookie"] = merged_cookie_header

    for cookie in browser_cookies or []:
        name = _normalize_spaces(dict(cookie).get("name", ""))
        value = _normalize_spaces(dict(cookie).get("value", ""))
        domain = _normalize_spaces(dict(cookie).get("domain", ""))
        path = _normalize_spaces(dict(cookie).get("path", "")) or "/"

        if not name:
            continue

        try:
            if domain:
                session.cookies.set(name, value, domain=domain, path=path)
            else:
                session.cookies.set(name, value, path=path)
        except Exception:
            continue


def _build_http_referer_candidates(target_url: str, current_url: str = "") -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    parsed_target = urlparse(target_url)
    target_origin = ""
    if parsed_target.scheme and parsed_target.netloc:
        target_origin = f"{parsed_target.scheme}://{parsed_target.netloc}/"

    for raw_value in (current_url, target_url, target_origin, ""):
        value = _normalize_spaces(raw_value)
        if value in seen:
            continue
        seen.add(value)
        candidates.append(value)

    return candidates or [""]


def _build_browser_like_http_headers(
    target_url: str,
    *,
    current_url: str = "",
    referer: str = "",
) -> dict[str, str]:
    target_parsed = urlparse(target_url)
    current_parsed = urlparse(current_url) if current_url else None

    same_origin = bool(
        current_parsed
        and current_parsed.scheme == target_parsed.scheme
        and current_parsed.netloc == target_parsed.netloc
    )

    headers = {
        "User-Agent": str(getattr(settings, "PLAYWRIGHT_USER_AGENT", "Mozilla/5.0")),
        "Accept": _get_http_accept_header(),
        "Accept-Language": _get_http_accept_language(),
        "Accept-Encoding": _get_http_accept_encoding(),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Sec-GPC": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Site": "same-origin" if same_origin else ("cross-site" if current_url else "none"),
    }

    if referer:
        headers["Referer"] = referer

    return headers


async def _fetch_html_via_authenticated_http(
    page: Any,
    url: str,
    *,
    control: Any = None,
    app: Any = None,
    shared_session: requests.Session | None = None,
) -> str:
    await browser_check_pause_stop(control, app)

    target_url = _normalize_spaces(url)
    if not target_url:
        return ""

    current_url = _normalize_spaces(getattr(page, "url", "") or "")
    browser_cookies = await _get_browser_cookies_from_page(page, target_url)
    document_cookie_header = await _get_browser_document_cookie_header(page)
    referer_candidates = _build_http_referer_candidates(target_url, current_url)

    min_attempts = _get_http_retry_attempts()
    while len(referer_candidates) < min_attempts:
        referer_candidates.append(referer_candidates[-1] if referer_candidates else "")

    last_error: Exception | None = None
    owns_session = shared_session is None
    session = shared_session or requests.Session()
    session.trust_env = False

    try:
        if shared_session is not None and not bool(getattr(session, "_pt_http_warmup_done", False)):
            warmup_url = _normalize_spaces(current_url or "")
            if warmup_url:
                try:
                    _prepare_authenticated_http_session(
                        session,
                        target_url=warmup_url,
                        current_url=current_url,
                        referer=current_url,
                        browser_cookies=browser_cookies,
                        document_cookie_header=document_cookie_header,
                        preserve_existing_state=True,
                    )
                    response = session.get(
                        warmup_url,
                        timeout=_get_http_timeout_seconds(),
                        allow_redirects=True,
                    )
                    with suppress(Exception):
                        current_url = _normalize_spaces(response.url or current_url)
                except Exception:
                    pass

            setattr(session, "_pt_http_warmup_done", True)

        for attempt_index, referer in enumerate(referer_candidates, start=1):
            await browser_check_pause_stop(control, app)

            preserve_existing_state = attempt_index > 1 or shared_session is not None

            _prepare_authenticated_http_session(
                session,
                target_url=target_url,
                current_url=current_url,
                referer=referer,
                browser_cookies=browser_cookies,
                document_cookie_header=document_cookie_header,
                preserve_existing_state=preserve_existing_state,
            )

            try:
                response = session.get(
                    target_url,
                    timeout=_get_http_timeout_seconds(),
                    allow_redirects=True,
                )
                response.raise_for_status()

                with suppress(Exception):
                    current_url = _normalize_spaces(response.url or current_url)

                return response.text or ""

            except Exception as error:
                last_error = error

                if attempt_index < len(referer_candidates):
                    wait_seconds = _get_http_retry_delay_seconds()
                    error_text = str(error).lower()

                    if "403" in error_text:
                        wait_seconds = max(wait_seconds, 1.6 + ((attempt_index - 1) * 0.6))

                    error_text_full = str(error)
                    error_text_lower = error_text_full.lower()

                    if "403" in error_text_lower:
                        _log(
                            app,
                            f"   ↳ bloqueio HTTP temporário {attempt_index}/{len(referer_candidates)}: {error_text_full}",
                        )
                    else:
                        _log(
                            app,
                            f"   ↳ retry HTTP autenticado {attempt_index}/{len(referer_candidates)} falhou: {error_text_full}",
                        )
                    await controlled_sleep(
                        wait_seconds,
                        control=control,
                        app=app,
                    )

        if last_error is not None:
            raise last_error

        return ""
    finally:
        if owns_session:
            with suppress(Exception):
                session.close()


def _is_noise_product_title(text: str) -> bool:
    value = _normalize_spaces(text).lower()
    if not value:
        return True

    if value in {
        "view details",
        "ver detalhes",
        "add to cart",
        "adicionar ao carrinho",
        "most popular",
        "newest",
        "highest rated",
    }:
        return True

    if value.startswith("price:"):
        return True

    if value in {"sale", "novo", "new"}:
        return True

    if value.startswith("$"):
        return True

    return False


def _extract_plugintheme_listing_stats_from_html(html: str) -> tuple[int, int]:
    soup = BeautifulSoup(html or "", "html.parser")
    body_text = _normalize_spaces(soup.get_text(" ", strip=True))

    nav = soup.select_one("nav[aria-label='Pagination']")
    nav_text = _normalize_spaces(nav.get_text(" ", strip=True)) if nav else ""

    combined = " | ".join(part for part in (body_text, nav_text) if part)

    total_items = 0
    match = re.search(
        r"(?:Mostrando|Showing)\s+\d+\s*-\s*\d+\s+(?:de|of)\s+(\d+)\s+(?:produtos?|products?)",
        combined,
        flags=re.IGNORECASE,
    )
    if match:
        total_items = int(match.group(1))

    total_pages_candidates: list[int] = [1]

    match = re.search(
        r"\(\s*Page\s+\d+\s+of\s+(\d+)\s*\)",
        combined,
        flags=re.IGNORECASE,
    )
    if match:
        total_pages_candidates.append(int(match.group(1)))

    match = re.search(
        r"\bPage\s+\d+\s+of\s+(\d+)\b",
        combined,
        flags=re.IGNORECASE,
    )
    if match:
        total_pages_candidates.append(int(match.group(1)))

    for link in soup.select("nav[aria-label='Pagination'] a[href]"):
        text = _normalize_spaces(link.get_text(" ", strip=True))
        href = _normalize_spaces(link.get("href", ""))

        if text.isdigit():
            total_pages_candidates.append(int(text))

        match = re.search(r"[?&]page=(\d+)", href, flags=re.IGNORECASE)
        if match:
            total_pages_candidates.append(int(match.group(1)))

    return max(0, total_items), max(total_pages_candidates) if total_pages_candidates else 1


def _extract_plugintheme_items_from_html(html: str, page_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    body_text = _normalize_spaces(soup.get_text(" ", strip=True))

    if re.search(r"\b404\b", body_text, flags=re.IGNORECASE):
        return []
    if re.search(r"página não encontrada|page not found", body_text, flags=re.IGNORECASE):
        return []

    items: list[dict[str, str]] = []
    seen_links: set[str] = set()

    def _is_invalid_candidate(value: Any) -> bool:
        text = _normalize_spaces(value)
        if not text:
            return True

        lowered = text.lower()

        if lowered in {
            "",
            "view details",
            "ver detalhes",
            "add to cart",
            "adicionar ao carrinho",
            "most popular",
            "newest",
            "highest rated",
            "mais",
        }:
            return True

        if lowered.startswith("price:"):
            return True

        if text.startswith("$"):
            return True

        if re.fullmatch(r"\d+\s*(?:produtos?|products?)", text, flags=re.IGNORECASE):
            return True

        if re.search(
            r"marcas premium|total de produtos|arquivos originais|suporte disponível",
            lowered,
            flags=re.IGNORECASE,
        ):
            return True

        return False

    def _find_scope(link: Any) -> Any:
        for parent in getattr(link, "parents", []):
            tag_name = str(getattr(parent, "name", "") or "").lower()

            if tag_name in {"article", "section", "li"}:
                return parent

            if tag_name == "div":
                classes = parent.get("class", []) if hasattr(parent, "get") else []
                classes_text = " ".join(classes) if isinstance(classes, list) else str(classes or "")
                if re.search(r"product|card|group|rounded|shadow|border", classes_text, flags=re.IGNORECASE):
                    return parent

        return link

    def _resolve_name(link: Any, scope: Any) -> str:
        candidates: list[str] = []

        link_title = _normalize_spaces(link.get("title", "")) if hasattr(link, "get") else ""
        link_text = _normalize_spaces(link.get_text(" ", strip=True)) if hasattr(link, "get_text") else ""
        aria_label = _normalize_spaces(link.get("aria-label", "")) if hasattr(link, "get") else ""

        if link_title:
            candidates.append(link_title)
        if link_text:
            candidates.append(link_text)
        if aria_label:
            candidates.append(aria_label)

        with suppress(Exception):
            image = link.find("img", alt=True)
            if image is not None:
                image_alt = _normalize_spaces(image.get("alt", ""))
                if image_alt:
                    candidates.append(image_alt)

        selectors = (
            "h1",
            "h2",
            "h3",
            "h4",
            "strong",
            ".font-semibold",
            ".font-bold",
            ".product-title",
            ".wd-entities-title",
            "[class*='title']",
            "[class*='name']",
        )

        if scope is not None:
            for selector in selectors:
                with suppress(Exception):
                    for node in scope.select(selector):
                        text = _normalize_spaces(node.get_text(" ", strip=True))
                        if text:
                            candidates.append(text)

            with suppress(Exception):
                for image in scope.select("img[alt]"):
                    alt = _normalize_spaces(image.get("alt", ""))
                    if alt:
                        candidates.append(alt)

        for candidate in candidates:
            cleaned = _normalize_spaces(
                re.sub(r"\b\d+\s*(?:produtos?|products?)\b", "", candidate, flags=re.IGNORECASE)
            )
            if _is_invalid_candidate(cleaned):
                continue
            return cleaned

        return ""

    for link in soup.select("a[href*='/product/']"):
        if link.find_parent(["header", "nav", "footer", "aside"]) is not None:
            continue

        raw_href = _normalize_spaces(link.get("href", ""))
        if not raw_href:
            continue

        absolute_href = _normalize_spaces(urljoin(page_url, raw_href))
        absolute_href_lower = absolute_href.lower()

        if not absolute_href:
            continue
        if "/product/" not in absolute_href_lower:
            continue
        if "/product-category/" in absolute_href_lower:
            continue
        if absolute_href in seen_links:
            continue

        scope = _find_scope(link)
        product_name = _resolve_name(link, scope)

        if not product_name:
            continue

        seen_links.add(absolute_href)
        items.append(
            {
                "link_produto": absolute_href,
                "nome_lista": product_name,
                "versao_lista": "",
            }
        )

    return items


def _extract_plugintheme_categories_from_html(html: str, page_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for link in soup.select("a[href*='/product-category/']"):
        raw_href = _normalize_spaces(link.get("href", ""))
        if not raw_href:
            continue

        absolute_href = ensure_trailing_slash(urljoin(page_url, raw_href))
        if not absolute_href or absolute_href in seen:
            continue

        if "/product-category/" not in absolute_href.lower():
            continue

        if link.find_parent(["header", "nav", "footer", "aside"]) is not None:
            continue

        card = link.find_parent("article")
        if card is None:
            card = link.find_parent(
                "div",
                class_=lambda value: bool(
                    value and re.search(
                        r"group|card|rounded|shadow|border",
                        " ".join(value) if isinstance(value, (list, tuple)) else str(value),
                        flags=re.IGNORECASE,
                    )
                ),
            )

        scope = card or link
        card_text = _normalize_spaces(scope.get_text(" ", strip=True))

        total_match = re.search(
            r"(\d+)\s*(?:produtos?|products?)",
            card_text,
            flags=re.IGNORECASE,
        )
        total = int(total_match.group(1)) if total_match else 0

        if total <= 0:
            continue

        raw_text = _normalize_spaces(link.get_text(" ", strip=True))
        name = _normalize_spaces(
            re.sub(r"\b\d+\s*(?:produtos?|products?)\b", "", raw_text, flags=re.IGNORECASE)
        )

        if not name:
            for candidate in scope.select("h1, h2, h3, h4, strong, .font-semibold, .font-bold"):
                text = _normalize_spaces(candidate.get_text(" ", strip=True))
                if not text:
                    continue
                if re.fullmatch(r"\d+\s*(?:produtos?|products?)", text, flags=re.IGNORECASE):
                    continue
                if re.search(r"marcas premium|total de produtos|arquivos originais|suporte disponível", text, flags=re.IGNORECASE):
                    continue
                if text.lower() == "mais":
                    continue
                name = text
                break

        if not name:
            continue

        if name.lower() in {"marcas premium", "mais"}:
            continue

        if "total de produtos" in card_text.lower():
            continue

        seen.add(absolute_href)
        result.append(
            {
                "categoria_nome": name,
                "categoria_url": absolute_href,
                "total_esperado": total,
            }
        )

    return result

def _extract_ultrapack_listing_stats_from_html(
    html: str,
    *,
    page_size: int = 128,
) -> tuple[int, int]:
    soup = BeautifulSoup(html or "", "html.parser")

    total_text = _normalize_spaces(
        " ".join(
            node.get_text(" ", strip=True)
            for node in soup.select(".itens-total")
        )
    )

    total_items = 0
    match = re.search(r"(\d+)", total_text)
    if match:
        total_items = int(match.group(1))

    total_pages_candidates: list[int] = [1]

    pagination_roots = soup.select(
        ".pagination, .nav-links, .page-numbers, .pager, .navigation, .woocommerce-pagination"
    )

    for root in pagination_roots:
        for link in root.select("a[href], span"):
            text = _normalize_spaces(link.get_text(" ", strip=True))
            href = _normalize_spaces(link.get("href", "")) if getattr(link, "get", None) else ""

            if text.isdigit():
                total_pages_candidates.append(int(text))

            if href:
                match = re.search(r"[?&](?:paged|page)=(\d+)", href, flags=re.IGNORECASE)
                if match:
                    total_pages_candidates.append(int(match.group(1)))

                match = re.search(r"/page/(\d+)/?", href, flags=re.IGNORECASE)
                if match:
                    total_pages_candidates.append(int(match.group(1)))

    if total_items > 0 and page_size > 0:
        total_pages_candidates.append(
            max(1, (int(total_items) + int(page_size) - 1) // int(page_size))
        )

    total_pages = max(total_pages_candidates) if total_pages_candidates else 1
    return max(0, total_items), max(1, total_pages)


def _extract_ultrapack_items_from_html(html: str, page_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    body_text = _normalize_spaces(soup.get_text(" ", strip=True))

    if re.search(r"\b404\b", body_text, flags=re.IGNORECASE):
        return []
    if re.search(r"página não encontrada|page not found", body_text, flags=re.IGNORECASE):
        return []

    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def _resolve_product_link(raw_href: Any) -> str:
        href = _normalize_spaces(raw_href)
        if not href:
            return ""

        absolute = _normalize_spaces(urljoin(page_url, href))
        lowered = absolute.lower()

        if not absolute or "/item/" not in lowered:
            return ""

        invalid_fragments = (
            "/item/author/",
            "/item/category/",
            "/item/tag/",
            "/item/categoria/",
            "/item/etiqueta/",
        )
        if any(fragment in lowered for fragment in invalid_fragments):
            return ""

        return absolute

    def _resolve_product_name(scope: Any, preferred_link: Any = None) -> str:
        candidates: list[str] = []

        if preferred_link is not None:
            candidates.extend(
                [
                    _normalize_spaces(preferred_link.get("title", "")),
                    _normalize_spaces(preferred_link.get_text(" ", strip=True)),
                ]
            )
            with suppress(Exception):
                image = preferred_link.find("img", alt=True)
                if image is not None:
                    candidates.append(_normalize_spaces(image.get("alt", "")))

        selectors = (
            "h1",
            "h2",
            "h3",
            "h4",
            ".entry-title",
            ".post-title",
            ".product-title",
            "[class*='title']",
            "[class*='name']",
            "strong",
        )

        if scope is not None:
            for selector in selectors:
                with suppress(Exception):
                    for node in scope.select(selector):
                        candidates.append(_normalize_spaces(node.get_text(" ", strip=True)))

            with suppress(Exception):
                for image in scope.select("img[alt]"):
                    candidates.append(_normalize_spaces(image.get("alt", "")))

        for candidate in candidates:
            cleaned = _normalize_spaces(candidate)
            if not cleaned or _is_noise_product_title(cleaned):
                continue
            return cleaned

        return ""

    card_selectors = (
        ".new-post-display.new-posts2",
        ".new-post-display",
        ".new-posts2",
        "article",
        "li",
        "div[class*='post']",
    )

    cards: list[Any] = []
    for selector in card_selectors:
        with suppress(Exception):
            cards.extend(soup.select(selector))

    for card in cards:
        if card.find_parent(["header", "nav", "footer", "aside"]) is not None:
            continue

        link_node = None
        link = ""

        for selector in (
            "a.link-cover[href*='/item/']",
            "h1 a[href*='/item/']",
            "h2 a[href*='/item/']",
            "h3 a[href*='/item/']",
            "h4 a[href*='/item/']",
            "a[href*='/item/']",
        ):
            with suppress(Exception):
                for node in card.select(selector):
                    candidate_link = _resolve_product_link(node.get("href", ""))
                    if candidate_link:
                        link_node = node
                        link = candidate_link
                        break
            if link:
                break

        if not link or link in seen:
            continue

        name = _resolve_product_name(card, link_node)
        version = ""

        for selector in (".version", "[class*='version']", "[class*='versao']"):
            with suppress(Exception):
                node = card.select_one(selector)
                if node is not None:
                    version = _normalize_spaces(node.get_text(" ", strip=True))
                    if version:
                        break

        if not name:
            continue

        seen.add(link)
        items.append(
            {
                "link_produto": link,
                "nome_lista": name,
                "versao_lista": version,
            }
        )

    for link_el in soup.select("a[href*='/item/']"):
        if link_el.find_parent(["header", "nav", "footer", "aside"]) is not None:
            continue

        link = _resolve_product_link(link_el.get("href", ""))
        if not link or link in seen:
            continue

        scope = link_el.find_parent(["article", "li", "div"]) or link_el
        name = _resolve_product_name(scope, link_el)
        if not name:
            continue

        seen.add(link)
        items.append(
            {
                "link_produto": link,
                "nome_lista": name,
                "versao_lista": "",
            }
        )

    return items


def _extract_ultrapack_categories_from_html(html: str, page_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    normalized_page_url = ensure_trailing_slash(page_url)
    normalized_page_url_lower = normalized_page_url.lower()
    is_themeforest_group_page = "/temas/themeforest/" in normalized_page_url_lower

    candidate_links: list[Any] = []
    candidate_ids: set[int] = set()

    def _append_candidate(link: Any) -> None:
        if link is None:
            return

        marker = id(link)
        if marker in candidate_ids:
            return

        candidate_ids.add(marker)
        candidate_links.append(link)

    for link in soup.select("a.dev-link[href], a.themeforest-cat-links[href]"):
        _append_candidate(link)

    if is_themeforest_group_page:
        for link in soup.select("a[href]"):
            raw_href = _normalize_spaces(link.get("href", ""))
            if not raw_href:
                continue

            absolute_href = ensure_trailing_slash(urljoin(page_url, raw_href))
            absolute_href_lower = absolute_href.lower()

            if not absolute_href:
                continue
            if absolute_href_lower == normalized_page_url_lower:
                continue
            if "/temas/themeforest/" not in absolute_href_lower:
                continue
            if "/item/" in absolute_href_lower:
                continue
            if "/page/" in absolute_href_lower:
                continue

            _append_candidate(link)

    def _resolve_category_name(link: Any) -> str:
        candidates: list[str] = []

        direct_text = _normalize_spaces(link.get_text(" ", strip=True))
        title_text = _normalize_spaces(link.get("title", ""))
        aria_label = _normalize_spaces(link.get("aria-label", ""))

        if direct_text:
            candidates.append(direct_text)
        if title_text:
            candidates.append(title_text)
        if aria_label:
            candidates.append(aria_label)

        with suppress(Exception):
            image = link.find("img", alt=True)
            if image is not None:
                image_alt = _normalize_spaces(image.get("alt", ""))
                if image_alt:
                    candidates.append(image_alt)

        scope = link.find_parent(["article", "section", "li", "div"]) or link.parent or link

        if scope is not None:
            for selector in (
                "h1",
                "h2",
                "h3",
                "h4",
                "strong",
                "figcaption",
                ".themeforest-cat-name",
                "[class*='title']",
                "[class*='name']",
                "p",
                "span",
            ):
                with suppress(Exception):
                    for node in scope.select(selector):
                        text = _normalize_spaces(node.get_text(" ", strip=True))
                        if text:
                            candidates.append(text)

        for candidate in candidates:
            cleaned = _normalize_spaces(
                re.sub(r"\s*\(\d+\)\s*$", "", candidate, flags=re.IGNORECASE)
            )
            cleaned_lower = cleaned.lower()

            if not cleaned:
                continue
            if cleaned_lower in {"mais", "more"}:
                continue
            if re.fullmatch(r"\d+", cleaned):
                continue

            return cleaned

        return ""

    def _resolve_category_total(link: Any) -> int:
        texts: list[str] = []

        direct_text = _normalize_spaces(link.get_text(" ", strip=True))
        if direct_text:
            texts.append(direct_text)

        with suppress(Exception):
            count_node = link.select_one(".menu-cat-count")
            if count_node is not None:
                count_text = _normalize_spaces(count_node.get_text(" ", strip=True))
                if count_text:
                    texts.append(count_text)

        scope = link.find_parent(["article", "section", "li", "div"]) or link.parent or link
        if scope is not None:
            for selector in (
                ".menu-cat-count",
                "[class*='count']",
                "[class*='total']",
                "small",
                "span",
                "p",
            ):
                with suppress(Exception):
                    for node in scope.select(selector):
                        text = _normalize_spaces(node.get_text(" ", strip=True))
                        if text:
                            texts.append(text)

        for text in texts:
            match = re.search(r"\((\d+)\)\s*$", text)
            if match:
                return int(match.group(1))

            match = re.search(
                r"(\d+)\s*(?:itens|items|produtos|products?)\b",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                return int(match.group(1))

        return 0

    for link in candidate_links:
        raw_href = _normalize_spaces(link.get("href", ""))
        if not raw_href:
            continue

        absolute_href = ensure_trailing_slash(urljoin(page_url, raw_href))
        absolute_href_lower = absolute_href.lower()

        if not absolute_href or absolute_href in seen:
            continue

        if absolute_href_lower == normalized_page_url_lower:
            continue

        if "/item/" in absolute_href_lower:
            continue

        name = _resolve_category_name(link)
        total = _resolve_category_total(link)

        if not name:
            continue

        if total <= 0 and not is_themeforest_group_page:
            continue

        seen.add(absolute_href)
        result.append(
            {
                "categoria_nome": name,
                "categoria_url": absolute_href,
                "total_esperado": max(0, total),
            }
        )

    return result


def _first_soup_text(soup: BeautifulSoup, selectors: Sequence[str]) -> str:
    for selector in selectors or ():
        selector_text = str(selector or "").strip()
        if not selector_text:
            continue

        with suppress(Exception):
            node = soup.select_one(selector_text)
            if node is None:
                continue

            text = _normalize_spaces(node.get_text(" ", strip=True))
            if text:
                return text

    return ""


def _extract_version_from_text_value(value: Any) -> str:
    text = _normalize_spaces(value)
    if not text:
        return ""

    patterns = (
        r"\bv\s*(\d+(?:\.\d+){0,5})\b",
        r"(?:vers[aã]o|version)\s*[:#-]?\s*(\d+(?:\.\d+){0,5})",
        r"\b(\d+(?:\.\d+){1,5})\b",
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return ""


def _extract_version_from_soup(soup: BeautifulSoup, detail: Any) -> str:
    selectors: list[str] = []

    if getattr(detail, "version_tag_selector", ""):
        selectors.append(str(detail.version_tag_selector))
    if getattr(detail, "version_value_selector", ""):
        selectors.append(str(detail.version_value_selector))

    selectors.extend(
        [
            ".version",
            "[class*='version']",
            "[class*='calendar']",
            ".text-muted-foreground",
            "time[datetime]",
        ]
    )

    seen_texts: set[str] = set()

    for selector in selectors:
        selector_text = str(selector or "").strip()
        if not selector_text:
            continue

        with suppress(Exception):
            for node in soup.select(selector_text):
                candidates = [
                    _normalize_spaces(node.get_text(" ", strip=True)),
                    _normalize_spaces(node.get("datetime", "")),
                ]

                for candidate in candidates:
                    if not candidate or candidate in seen_texts:
                        continue

                    seen_texts.add(candidate)
                    parsed = _extract_version_from_text_value(candidate)
                    if parsed:
                        return parsed

    return ""


def _extract_image_data_from_soup(
    soup: BeautifulSoup,
    image_selector: str,
    page_url: str,
) -> tuple[str, str]:
    selector_text = str(image_selector or "").strip()
    if not selector_text:
        return "", ""

    for node in soup.select(selector_text):
        alt = _normalize_spaces(node.get("alt", ""))
        src = _normalize_spaces(
            node.get("src", "")
            or node.get("data-src", "")
            or (
                str(node.get("srcset", "")).split(",")[0].strip().split(" ")[0]
                if node.get("srcset")
                else ""
            )
        )

        absolute_src = _normalize_spaces(urljoin(page_url, src)) if src else ""
        if alt or absolute_src:
            return alt, absolute_src

    return "", ""


def _extract_official_page_from_soup(soup: BeautifulSoup, detail: Any, page_url: str) -> str:
    labels = {
        _normalize_spaces(value).lower()
        for value in getattr(detail, "official_page_button_labels", ()) or ()
        if _normalize_spaces(value)
    }

    if not labels:
        return ""

    for node in soup.select("a[href], [data-href]"):
        text = _normalize_spaces(node.get_text(" ", strip=True)).lower()
        if not text:
            continue

        if not any(label in text for label in labels):
            continue

        href = _normalize_spaces(node.get("href", "") or node.get("data-href", ""))
        if not href or href == "#" or href.lower().startswith("javascript:"):
            continue

        return _normalize_spaces(urljoin(page_url, href))

    return ""


def _extract_plugintheme_internal_categories_from_soup(soup: BeautifulSoup) -> str:
    selectors = (
        ".product_meta a[href*='/product-category/']",
        ".posted_in a[href*='/product-category/']",
        ".entry-summary a[href*='/product-category/']",
        ".summary a[href*='/product-category/']",
        ".woocommerce-breadcrumb a[href*='/product-category/']",
        "main a[href*='/product-category/']",
        "article a[href*='/product-category/']",
        "a[href*='/pt-BR/product-category/']",
    )

    texts: list[str] = []
    seen: set[str] = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = _normalize_spaces(node.get_text(" ", strip=True))
            if not text:
                continue

            key = text.lower()
            if key in seen:
                continue

            seen.add(key)
            texts.append(text)

    return " | ".join(texts)


def _extract_observation_from_soup(detail: Any, soup: BeautifulSoup) -> tuple[str, str]:
    selectors = getattr(detail, "observation_scope_selectors", ()) or ()
    skip_tokens = {
        token.strip().lower()
        for token in re.split(r"[,\s]+", str(getattr(detail, "skip_observation_class", "") or ""))
        if token.strip()
    }
    skip_container_selector = str(
        getattr(detail, "skip_observation_container_selector", "") or ""
    ).strip()
    min_length = max(1, int(getattr(detail, "observation_min_length", 15) or 15))

    preferred_class_tokens = (
        "item-desbloqueado",
        "item-descontinuado",
    )

    def _node_item_classes(node: Any) -> list[str]:
        raw_classes = node.get("class", [])
        if isinstance(raw_classes, str):
            raw_classes = raw_classes.split()

        return [
            _normalize_spaces(token)
            for token in raw_classes
            if _normalize_spaces(token).startswith("item-")
        ]

    def _is_valid_observation_node(node: Any) -> tuple[bool, str, str]:
        tag_name = str(getattr(node, "name", "") or "").lower()
        if tag_name in {"a", "button", "input", "label"}:
            return False, "", ""

        if skip_container_selector:
            with suppress(Exception):
                if node.closest(skip_container_selector):
                    return False, "", ""

        item_classes = _node_item_classes(node)
        if not item_classes:
            return False, "", ""

        lowered_classes = {token.lower() for token in item_classes}
        if skip_tokens and lowered_classes & skip_tokens:
            return False, "", ""

        text = _normalize_spaces(node.get_text(" ", strip=True))
        if not text or len(text) < min_length:
            return False, "", ""

        if re.fullmatch(r"v?\d+(?:\.\d+){0,5}", text, flags=re.IGNORECASE):
            return False, "", ""

        if re.search(
            r"^(vers[aã]o|version|p[áa]gina do item|item page)\b",
            text,
            flags=re.IGNORECASE,
        ):
            return False, "", ""

        return True, text, " ".join(item_classes)

    # 1) Prioridade máxima para observações explícitas
    for class_name in preferred_class_tokens:
        with suppress(Exception):
            for node in soup.select(f".{class_name}, [class*='{class_name}']"):
                ok, text, classes = _is_valid_observation_node(node)
                if ok:
                    return text, classes

    # 2) Depois usa os seletores configurados no adapter
    for selector in selectors:
        selector_text = str(selector or "").strip()
        if not selector_text:
            continue

        with suppress(Exception):
            for node in soup.select(selector_text):
                ok, text, classes = _is_valid_observation_node(node)
                if ok:
                    return text, classes

    return "", ""


def _extract_raw_details_from_html(
    html: str,
    page_url: str,
    *,
    context: Any = None,
    adapter: AdapterDefinition | None = None,
) -> dict[str, str]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    detail = resolved_adapter.detail
    soup = BeautifulSoup(html or "", "html.parser")

    nome_h1 = _first_soup_text(soup, detail.name_selectors)
    versao = _extract_version_from_soup(soup, detail)
    img_alt, imagem_url = _extract_image_data_from_soup(
        soup,
        str(detail.image_alt_selector or "").strip(),
        page_url,
    )

    og_title = ""
    with suppress(Exception):
        og_node = soup.select_one(str(detail.og_title_selector or "").strip())
        if og_node is not None:
            og_title = _normalize_spaces(og_node.get("content", ""))

    pagina_oficial = _extract_official_page_from_soup(soup, detail, page_url)
    observacao, observacao_classes = _extract_observation_from_soup(detail, soup)

    # Fallback extra e direto no HTML bruto para UltraPack:
    # pega observações como:
    # - <div class="item-desbloqueado">...</div>
    # - <div class="item-desbloqueado item-descontinuado">...</div>
    if not observacao and resolved_context.site_key == "ultrapackv2":
        raw_html = str(html or "")

        explicit_patterns = (
            (
                "item-desbloqueado",
                r'<(?:div|span)\b[^>]*class=["\'][^"\']*\bitem-desbloqueado\b[^"\']*["\'][^>]*>(.*?)</(?:div|span)>',
            ),
            (
                "item-descontinuado",
                r'<(?:div|span)\b[^>]*class=["\'][^"\']*\bitem-descontinuado\b[^"\']*["\'][^>]*>(.*?)</(?:div|span)>',
            ),
        )

        for class_name, pattern in explicit_patterns:
            match = re.search(pattern, raw_html, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue

            fragment_html = match.group(1)
            fragment_text = _normalize_spaces(
                BeautifulSoup(fragment_html, "html.parser").get_text(" ", strip=True)
            )

            if fragment_text:
                observacao = fragment_text
                observacao_classes = class_name
                break

    categorias_internas = ""
    product_type = ""
    if resolved_context.site_key == "plugintheme":
        categorias_internas = _extract_plugintheme_internal_categories_from_soup(soup)
        # O App Router do Next.js serializa o produto no payload RSC embutido.
        # Lemos somente campos públicos e estáveis, sem depender de hidratação/DOM.
        raw_html = str(html or "")
        def _rsc_value(field: str) -> str:
            match = re.search(
                rf'(?:\\?"{re.escape(field)}\\?"\s*:\s*\\?")([^"\\]+)',
                raw_html,
                flags=re.IGNORECASE,
            )
            return _normalize_spaces(match.group(1)) if match else ""

        versao = versao or _rsc_value("version")
        pagina_oficial = pagina_oficial or _rsc_value("demoUrl")
        type_matches = re.findall(
            r'(?:\\?"type\\?"\s*:\s*\\?")(PLUGIN|THEME)(?:\\?")',
            raw_html,
            flags=re.IGNORECASE,
        )
        product_type = type_matches[-1].lower() if type_matches else ""
        if not categorias_internas:
            category_names = re.findall(
                r'\\?"categories\\?"\s*:\s*\[(.*?)\](?:\s*,\s*\\?"|$)',
                raw_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if category_names:
                names = re.findall(
                    r'\\?"name\\?"\s*:\s*\\?"([^"\\]+)',
                    category_names[0],
                    flags=re.IGNORECASE,
                )
                categorias_internas = " | ".join(dict.fromkeys(map(_normalize_spaces, names)))

    return {
        "page_url": _normalize_spaces(page_url),
        "nome_h1": nome_h1,
        "versao": versao,
        "img_alt": img_alt,
        "imagem_url": imagem_url,
        "og_title": og_title,
        "pagina_oficial": pagina_oficial,
        "categorias_internas": categorias_internas,
        "product_type": product_type,
        "observacao": observacao,
        "observacao_classes": observacao_classes,
    }


def _build_available_categories(categories: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    payload = [
        {
            "nome": _normalize_spaces(
                dict(item).get(
                    "categoria_nome",
                    dict(item).get("name", dict(item).get("nome", "")),
                )
            ),
            "url": ensure_trailing_slash(
                dict(item).get("categoria_url", dict(item).get("url", ""))
            ),
            "total": to_int(
                dict(item).get(
                    "total_esperado",
                    dict(item).get("expected_total", dict(item).get("total", 0)),
                ),
                0,
            ),
        }
        for item in (categories or [])
    ]
    return normalize_available_categories_list(payload)


def _normalize_available_category_to_engine(
    category: Mapping[str, Any],
    context: ScraperContext,
) -> dict[str, Any]:
    return {
        "categoria_nome": _normalize_spaces(
            dict(category).get("categoria_nome")
            or dict(category).get("nome")
            or dict(category).get("name")
            or ""
        ),
        "categoria_url": ensure_trailing_slash(
            dict(category).get("categoria_url")
            or dict(category).get("url")
            or ""
        ),
        "total_esperado": max(
            0,
            to_int(
                dict(category).get(
                    "total_esperado",
                    dict(category).get("expected_total", dict(category).get("total", 0)),
                ),
                0,
            ),
        ),
        "tipo": context.item_type_key,
    }


def _sync_available_categories_state(app: Any, available_categories: Sequence[Mapping[str, Any]]) -> list[str]:
    snapshot = _state_snapshot_data(app)
    selected_current = snapshot.get("selected_categories", []) or []
    if not isinstance(selected_current, list):
        selected_current = []

    available_urls = {
        ensure_trailing_slash(dict(category).get("url", dict(category).get("categoria_url", "")))
        for category in available_categories
        if dict(category).get("url") or dict(category).get("categoria_url")
    }

    filtered_selected = [
        ensure_trailing_slash(url)
        for url in selected_current
        if ensure_trailing_slash(url) in available_urls
    ]

    _state_update(
        app,
        available_categories=list(available_categories),
        selected_categories=filtered_selected,
    )
    return filtered_selected


def _persist_catalog_snapshot(
    app: Any,
    context: Any,
    products_dict: Mapping[str, Mapping[str, Any]] | None,
    meta: Mapping[str, Any] | None,
    *,
    log_paths: bool = True,
) -> dict[str, Any]:
    result = save_catalog_state(products_dict or {}, meta=meta, context=context)
    progress_payload = result.get("progress", {}) if isinstance(result, Mapping) else {}
    progress_meta = progress_payload.get("meta", {}) if isinstance(progress_payload, Mapping) else {}
    if not isinstance(progress_meta, Mapping):
        progress_meta = {}

    resume_info = _resolve_resume_info(progress_meta)
    snapshot = _state_snapshot_data(app)
    total_saved = int(
        result.get("total_saved", len(products_dict or {}))
        if isinstance(result, Mapping)
        else len(products_dict or {})
    )

    _state_update(
        app,
        saved_count=total_saved,
        current_category=progress_meta.get("ultima_categoria", snapshot.get("current_category", "-")),
        current_item=progress_meta.get("ultimo_item_nome", snapshot.get("current_item", "-")),
        reused_categories=progress_meta.get("categorias_reutilizadas", snapshot.get("reused_categories", 0)),
        refetched_categories=progress_meta.get("categorias_refeitas", snapshot.get("refetched_categories", 0)),
        queue_detected_count=progress_meta.get("queue_detected_count", snapshot.get("queue_detected_count", 0)),
        new_links_detected=progress_meta.get("new_links_detected", snapshot.get("new_links_detected", 0)),
        existing_links_detected=progress_meta.get("existing_links_detected", snapshot.get("existing_links_detected", 0)),
        new_items_added=progress_meta.get("itens_novos_adicionados", snapshot.get("new_items_added", 0)),
        items_updated=progress_meta.get("itens_atualizados", snapshot.get("items_updated", 0)),
        items_unchanged=progress_meta.get("itens_sem_mudanca", snapshot.get("items_unchanged", 0)),
        save_every_items=progress_meta.get("save_every_items", snapshot.get("save_every_items", _get_default_save_every_items())),
        save_every_minutes=progress_meta.get("save_every_minutes", snapshot.get("save_every_minutes", _get_default_save_every_minutes())),
        can_continue=resume_info["can_continue"],
        primary_button_label="▶️ Retomar" if total_saved > 0 else "▶️ Iniciar",
        resume_run_mode=resume_info["run_mode"] or _get_run_mode_full(),
        resume_run_mode_label=resume_info["run_mode_label"] or _get_run_mode_label(_get_run_mode_full()),
        resume_queue_index=resume_info["queue_index"],
        resume_queue_total=resume_info["queue_total"],
        run_started_at=progress_meta.get("run_started_at", snapshot.get("run_started_at", "")),
        run_finished_at=progress_meta.get("run_finished_at", snapshot.get("run_finished_at", "")),
        timer_seconds=progress_meta.get("timer_seconds", snapshot.get("timer_seconds", 0)),
        timer_text=progress_meta.get("timer_text", snapshot.get("timer_text", "0:00:00")),
        current_phase=progress_meta.get("current_phase", snapshot.get("current_phase", "")),
        status=progress_meta.get("status", snapshot.get("status", "")),
    )

    with suppress(Exception):
        save_status_text(app, context=context)

    with suppress(Exception):
        save_full_logs_text(app, context=context, also_save_status=False)

    if log_paths:
        with suppress(Exception):
            paths = build_context_paths(context)
            _log(app, f"💾 CSV: {paths.output_csv_path}")
            _log(app, f"💾 JSON: {paths.output_json_path}")
            _log(app, f"💾 PROGRESS: {paths.progress_json_path}")

    return result

async def build_flat_catalog_fallback_category(
    page: Any,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> dict[str, Any] | None:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    catalog_url = ensure_trailing_slash(
        str(resolved_runtime_context.get("catalog_url", "") or "").strip()
    )
    if not catalog_url:
        return None

    use_http_listing = _use_http_listing_for_context(resolved_context)

    total_inside_catalog = 0
    sample_items: list[dict[str, str]] = []

    if use_http_listing:
        try:
            html = await _fetch_html_via_authenticated_http(
                page,
                catalog_url,
                control=control,
                app=app,
            )
        except Exception:
            html = ""

        if html:
            page_size_value = max(1, to_int(resolved_adapter.pagination.page_size_value, 128))

            if resolved_context.site_key == "plugintheme":
                total_inside_catalog, _ = _extract_plugintheme_listing_stats_from_html(html)
                sample_items = _extract_plugintheme_items_from_html(html, catalog_url)
            elif resolved_context.site_key == "ultrapackv2":
                total_inside_catalog, _ = _extract_ultrapack_listing_stats_from_html(
                    html,
                    page_size=page_size_value,
                )
                sample_items = _extract_ultrapack_items_from_html(html, catalog_url)
    else:
        listing = resolved_adapter.listing
        wait_candidates = [
            str(getattr(listing, "item_card_selector", "") or "").strip(),
            str(getattr(listing, "item_any_link_selector", "") or "").strip(),
        ]
        wait_selector = ", ".join(selector for selector in wait_candidates if selector)

        if wait_selector:
            with suppress(Exception):
                await page.wait_for_selector(
                    wait_selector,
                    timeout=getattr(settings, "TIMEOUT", 30_000),
                )

        with suppress(Exception):
            total_inside_catalog = await collect_total_items_in_category(
                page,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=resolved_adapter,
            )

        sample_items = await extract_cards_from_page(
            page,
            control,
            app,
            context=resolved_context,
            runtime_context=resolved_runtime_context,
            adapter=resolved_adapter,
        )

    if total_inside_catalog <= 0 and not sample_items:
        return None

    item_type_label = settings.get_item_type(
        resolved_context.item_type_key
    ).label_plural.upper()

    return {
        "categoria_nome": f"{item_type_label} | CATÁLOGO GERAL",
        "categoria_url": catalog_url,
        "total_esperado": max(0, total_inside_catalog),
        "tipo": resolved_context.item_type_key,
    }

# ============================================================
# CATEGORIAS
# ============================================================


async def extract_category_links_from_page(
    page: Any,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
    source_url: str | None = None,
) -> list[dict[str, Any]]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    target_url = str(
        source_url
        or resolved_runtime_context.get("catalog_url", "")
        or ""
    ).strip()

    catalog_path = urlparse(target_url).path or "/"
    if not catalog_path.endswith("/"):
        catalog_path += "/"

    selector = resolved_adapter.listing.category_link_selector
    item_fragment = str(resolved_adapter.listing.item_path_fragment or "/item/").strip()

    if _use_http_listing_for_context(resolved_context):
        html = await _fetch_html_via_authenticated_http(
            page,
            target_url,
            control=None,
            app=None,
        )

        if resolved_context.site_key == "plugintheme":
            categories = _extract_plugintheme_categories_from_html(html, target_url)
        elif resolved_context.site_key == "ultrapackv2":
            categories = _extract_ultrapack_categories_from_html(html, target_url)
        else:
            categories = []

        allow_zero_total = (
            resolved_context.site_key == "ultrapackv2"
            and "/temas/themeforest/" in ensure_trailing_slash(target_url).lower()
        )

        result: list[dict[str, Any]] = []
        seen: set[str] = set()

        for raw in categories or []:
            href = ensure_trailing_slash(dict(raw).get("categoria_url", ""))
            name_text = _normalize_spaces(dict(raw).get("categoria_nome", ""))
            total = max(0, to_int(dict(raw).get("total_esperado", 0), 0))

            if not href or href in seen:
                continue

            href_lower = href.lower()
            if item_fragment.lower() in href_lower:
                continue

            if total <= 0 and not allow_zero_total:
                continue

            name = resolved_adapter.clean_category_name(name_text)
            if not name:
                continue

            seen.add(href)
            result.append(
                {
                    "categoria_nome": name,
                    "categoria_url": href,
                    "total_esperado": total,
                    "tipo": resolved_context.item_type_key,
                }
            )

        return result

    categories = await page.evaluate(
        """
        (selector) => {
            return Array.from(document.querySelectorAll(selector)).map(a => {
                const text = (a.innerText || a.textContent || '').trim();
                return {
                    text,
                    href: a.href || ''
                };
            });
        }
        """,
        selector,
    )

    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in categories or []:
        href = ensure_trailing_slash(dict(raw).get("href", ""))
        text = _normalize_spaces(dict(raw).get("text", ""))

        if not href or href in seen:
            continue

        href_lower = href.lower()
        if item_fragment.lower() in href_lower:
            continue

        if catalog_path.lower() not in href_lower:
            continue

        match = re.search(r"\((\d+)\)\s*$", text)
        total = int(match.group(1)) if match else 0
        name = resolved_adapter.clean_category_name(text)

        seen.add(href)
        result.append(
            {
                "categoria_nome": name,
                "categoria_url": href,
                "total_esperado": total,
                "tipo": resolved_context.item_type_key,
            }
        )

    return result


async def warn_possible_grouped_category(
    page: Any,
    category: Mapping[str, Any],
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> bool:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    category_url = ensure_trailing_slash(dict(category).get("categoria_url", ""))

    try:
        subcategories = await extract_category_links_from_page(
            page,
            context=resolved_context,
            runtime_context=resolved_runtime_context,
            adapter=resolved_adapter,
            source_url=category_url,
        )

        valid_subcategories: list[dict[str, Any]] = []
        for subcategory in subcategories:
            sub_url = ensure_trailing_slash(subcategory.get("categoria_url", ""))
            if not sub_url or sub_url == category_url:
                continue
            valid_subcategories.append(subcategory)

        if len(valid_subcategories) >= 2:
            preview = ", ".join(
                _normalize_spaces(sub.get("categoria_nome", ""))
                for sub in valid_subcategories[:3]
                if _normalize_spaces(sub.get("categoria_nome", ""))
            )
            if len(valid_subcategories) > 3:
                preview += ", ..."

            _log(
                app,
                "⚠️ Possível categoria agrupadora detectada automaticamente: "
                f"{dict(category).get('categoria_nome', '-')} | "
                f"{len(valid_subcategories)} subcategorias encontradas"
                f"{' (' + preview + ')' if preview else ''}. "
                "Considere adicionar a URL em grouped_category_hints.",
            )
            return True

    except Exception as error:
        _log(
            app,
            "↳ não foi possível validar agrupamento automático em "
            f"{dict(category).get('categoria_nome', '-')} | {str(error)[:100]}",
        )

    return False


def _is_ultrapack_themeforest_root_url(url: str) -> bool:
    normalized_url = ensure_trailing_slash(url)
    if not normalized_url:
        return False

    normalized_path = ensure_trailing_slash(urlparse(normalized_url).path or "/").lower()
    return normalized_path == "/temas/themeforest/"


async def _resolve_ultrapack_subcategory_total_http(
    page: Any,
    subcategory_url: str,
    control: Any = None,
    app: Any = None,
    *,
    shared_session: requests.Session | None = None,
) -> tuple[int, str]:
    normalized_url = ensure_trailing_slash(subcategory_url)
    if not normalized_url:
        return 0, ""

    page_size_value = _get_ultrapack_http_page_size()
    candidates = _build_ultrapack_http_page_candidates(
        normalized_url,
        1,
        page_size_value,
    )

    if normalized_url not in candidates:
        candidates.append(normalized_url)

    best_total = 0
    best_source = ""

    for candidate_url in candidates:
        try:
            html = await _fetch_html_via_authenticated_http(
                page,
                candidate_url,
                control=control,
                app=app,
                shared_session=shared_session,
            )
        except Exception as error:
            _log(
                app,
                f"   ↳ falhou detecção de total da subcategoria: {candidate_url} | {str(error)[:100]}",
            )
            continue

        if not html:
            continue

        total_items, _ = _extract_ultrapack_listing_stats_from_html(
            html,
            page_size=page_size_value,
        )
        page_items = _extract_ultrapack_items_from_html(html, candidate_url)
        detected_total = max(0, total_items, len(page_items))

        if detected_total > best_total:
            best_total = detected_total
            best_source = candidate_url

    return best_total, best_source


async def _collect_grouped_subcategories_http(
    page: Any,
    grouped_category_url: str,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> list[dict[str, Any]]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    grouped_category_url = ensure_trailing_slash(grouped_category_url)
    if not grouped_category_url:
        return []

    use_http_listing = _use_http_listing_for_context(resolved_context)
    page_size_value = (
        _get_ultrapack_http_page_size()
        if use_http_listing and resolved_context.site_key == "ultrapackv2"
        else max(1, to_int(resolved_adapter.pagination.page_size_value, 128))
    )

    is_themeforest_group_page = (
        resolved_context.site_key == "ultrapackv2"
        and _is_ultrapack_themeforest_root_url(grouped_category_url)
    )

    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_signatures: set[str] = set()
    hydrated_subcategory_totals: dict[str, tuple[int, str]] = {}

    max_pages = 1 if _should_use_single_page_grouped_category(
        grouped_category_url,
        context=resolved_context,
    ) else _get_max_pages_fallback()

    http_session = requests.Session()

    try:
        if max_pages == 1:
            _log(app, f"   ↳ agrupadora tratada como página única: {grouped_category_url}")

        for page_number in range(1, max_pages + 1):
            await browser_check_pause_stop(control, app)

            candidates = _build_listing_page_candidates(
                grouped_category_url,
                page_number,
                page_size_value=page_size_value,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=resolved_adapter,
                use_http_listing=True,
            )

            if page_number == 1:
                normalized_grouped_url = _normalize_spaces(grouped_category_url)
                if normalized_grouped_url and normalized_grouped_url not in candidates:
                    candidates.append(normalized_grouped_url)

            best_page_categories: list[dict[str, Any]] = []
            best_source = ""
            best_score = (-1, -1, -1)
            best_signature = ""

            for candidate_url in candidates:
                try:
                    html = await _fetch_html_via_authenticated_http(
                        page,
                        candidate_url,
                        control=control,
                        app=app,
                        shared_session=http_session,
                    )
                except Exception as error:
                    _log(
                        app,
                        f"   ↳ falhou expansão HTTP p{page_number}: {candidate_url} | {str(error)[:100]}",
                    )
                    continue

                if not html:
                    continue

                if resolved_context.site_key == "plugintheme":
                    raw_categories = _extract_plugintheme_categories_from_html(html, candidate_url)
                elif resolved_context.site_key == "ultrapackv2":
                    raw_categories = _extract_ultrapack_categories_from_html(html, candidate_url)
                else:
                    raw_categories = []

                page_categories: list[dict[str, Any]] = []
                page_seen: set[str] = set()

                for raw in raw_categories or []:
                    href = ensure_trailing_slash(dict(raw).get("categoria_url", ""))
                    name_text = _normalize_spaces(dict(raw).get("categoria_nome", ""))
                    total = max(0, to_int(dict(raw).get("total_esperado", 0), 0))

                    if not href or href == grouped_category_url:
                        continue
                    if href in page_seen:
                        continue

                    name = resolved_adapter.clean_category_name(name_text)
                    if not name:
                        continue

                    if total <= 0 and is_themeforest_group_page:
                        if href not in hydrated_subcategory_totals:
                            detected_total, detected_source = await _resolve_ultrapack_subcategory_total_http(
                                page,
                                href,
                                control=control,
                                app=app,
                                shared_session=http_session,
                            )
                            hydrated_subcategory_totals[href] = (detected_total, detected_source)

                            if detected_total > 0:
                                _log(
                                    app,
                                    f"   ↳ total detectado na subcategoria: {name} | {detected_total} | {detected_source or href}",
                                )
                            else:
                                _log(
                                    app,
                                    f"   ↳ total não detectado na subcategoria: {name} | {href}",
                                )

                        detected_total, _detected_source = hydrated_subcategory_totals.get(href, (0, ""))
                        total = max(total, detected_total)

                    if total <= 0 and not is_themeforest_group_page:
                        continue

                    page_seen.add(href)
                    page_categories.append(
                        {
                            "categoria_nome": name,
                            "categoria_url": href,
                            "total_esperado": total,
                            "tipo": resolved_context.item_type_key,
                        }
                    )

                signature = "\n".join(
                    sorted(
                        ensure_trailing_slash(item.get("categoria_url", ""))
                        for item in page_categories
                        if ensure_trailing_slash(item.get("categoria_url", ""))
                    )
                )

                new_count = sum(
                    1
                    for item in page_categories
                    if ensure_trailing_slash(item.get("categoria_url", "")) not in seen_urls
                )

                _log(
                    app,
                    f"   ↳ agrupadora HTTP p{page_number}: {candidate_url} | "
                    f"encontradas: {len(page_categories)} | novas: {new_count}"
                    f"{' | assinatura repetida' if signature and signature in seen_signatures else ''}",
                )

                score = (
                    new_count,
                    1 if signature and signature not in seen_signatures else 0,
                    len(page_categories),
                )

                if score > best_score:
                    best_score = score
                    best_page_categories = list(page_categories)
                    best_source = candidate_url
                    best_signature = signature

            if not best_page_categories:
                if page_number == 1:
                    break
                _log(app, f"   ↳ sem subcategorias na página agrupadora {page_number}; encerrando expansão.")
                break

            if best_signature:
                if best_signature in seen_signatures:
                    _log(app, f"   ↳ assinatura repetida na página agrupadora {page_number}; encerrando expansão.")
                    break
                seen_signatures.add(best_signature)

            added_now = 0
            for subcategory in best_page_categories:
                sub_url = ensure_trailing_slash(subcategory.get("categoria_url", ""))
                if not sub_url or sub_url in seen_urls:
                    continue

                seen_urls.add(sub_url)
                collected.append(subcategory)
                added_now += 1

            _log(
                app,
                f"   ↳ página agrupadora {page_number} escolhida: {best_source} | novas adicionadas: {added_now}",
            )

            if added_now <= 0:
                _log(app, f"   ↳ nenhuma subcategoria nova na página agrupadora {page_number}; encerrando expansão.")
                break

        return collected
    finally:
        with suppress(Exception):
            http_session.close()


async def collect_categories(
    page: Any,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> list[dict[str, Any]]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    catalog_url = str(resolved_runtime_context.get("catalog_url", "") or "").strip()
    if not catalog_url:
        raise EngineError("catalog_url não definido para o contexto atual.")

    _state_update(app, current_phase="Coletando categorias", current_category="-", current_item="-")
    _log(app, f"📚 Abrindo catálogo: {catalog_url}")

    use_http_categories = _use_http_listing_for_context(resolved_context)

    if use_http_categories:
        _log(app, "🌐 Categorias/listagem via HTTP autenticado (requests + BeautifulSoup)")
    else:
        _log(app, "🖱️ Categorias/listagem via Playwright")

    if not use_http_categories:
        await safe_goto(page, catalog_url, control=control, app=app)

        wait_candidates = [
            str(resolved_adapter.listing.category_link_selector or "").strip(),
            str(resolved_adapter.listing.item_card_selector or "").strip(),
            str(resolved_adapter.listing.item_any_link_selector or "").strip(),
        ]
        wait_selector = ", ".join(selector for selector in wait_candidates if selector)

        if wait_selector:
            with suppress(Exception):
                await page.wait_for_selector(
                    wait_selector,
                    timeout=getattr(settings, "TIMEOUT", 30_000),
                )

    item_type_settings = settings.get_item_type(resolved_context.item_type_key)

    if not getattr(item_type_settings, "supports_categories", True):
        fallback_category = await build_flat_catalog_fallback_category(
            page,
            control,
            app,
            context=resolved_context,
            runtime_context=resolved_runtime_context,
            adapter=resolved_adapter,
        )

        if fallback_category:
            _log(
                app,
                "🧩 Tipo sem categorias; usando categoria virtual: "
                f"{fallback_category['categoria_nome']} | "
                f"URL: {fallback_category['categoria_url']}",
            )
            return [fallback_category]

        _log(app, f"⚠️ Nenhum item detectado no catálogo sem categorias: {catalog_url}")
        return []

    root_categories = await extract_category_links_from_page(
        page,
        context=resolved_context,
        runtime_context=resolved_runtime_context,
        adapter=resolved_adapter,
        source_url=catalog_url,
    )

    if not root_categories:
        fallback_category = await build_flat_catalog_fallback_category(
            page,
            control,
            app,
            context=resolved_context,
            runtime_context=resolved_runtime_context,
            adapter=resolved_adapter,
        )

        if fallback_category:
            _log(
                app,
                "🧩 Catálogo sem categorias visíveis; usando categoria virtual: "
                f"{fallback_category['categoria_nome']} | "
                f"URL: {fallback_category['categoria_url']}",
            )
            return [fallback_category]

        _log(app, f"⚠️ Nenhuma categoria detectada em: {catalog_url}")
        return []

    final_categories: list[dict[str, Any]] = []
    seen_final: set[str] = set()
    grouped_hints = resolved_adapter.grouped_hints_set(resolved_runtime_context)

    for category in root_categories:
        await browser_check_pause_stop(control, app)

        category_url = ensure_trailing_slash(category.get("categoria_url", ""))
        category_name = _normalize_spaces(category.get("categoria_nome", ""))

        if category_url.lower() in grouped_hints:
            _log(app, f"🧩 Categoria agrupadora detectada: {category_name}")

            try:
                if use_http_categories:
                    subcategories = await _collect_grouped_subcategories_http(
                        page,
                        category_url,
                        control,
                        app,
                        context=resolved_context,
                        runtime_context=resolved_runtime_context,
                        adapter=resolved_adapter,
                    )
                else:
                    await safe_goto(page, category_url, control=control, app=app)

                    subcategories = await extract_category_links_from_page(
                        page,
                        context=resolved_context,
                        runtime_context=resolved_runtime_context,
                        adapter=resolved_adapter,
                        source_url=category_url,
                    )

                valid_subcategories: list[dict[str, Any]] = []
                for subcategory in subcategories:
                    sub_url = ensure_trailing_slash(subcategory.get("categoria_url", ""))
                    if not sub_url or sub_url == category_url:
                        continue
                    valid_subcategories.append(subcategory)

                if valid_subcategories:
                    _log(
                        app,
                        f"   ↳ {len(valid_subcategories)} subcategorias encontradas dentro de {category_name}",
                    )
                    for subcategory in valid_subcategories:
                        sub_url = ensure_trailing_slash(subcategory.get("categoria_url", ""))
                        if not sub_url or sub_url in seen_final:
                            continue
                        seen_final.add(sub_url)
                        final_categories.append(subcategory)
                    continue

                _log(
                    app,
                    f"   ↳ nenhuma subcategoria válida encontrada em {category_name}; mantendo categoria principal.",
                )

            except Exception as error:
                _log(app, f"   ↳ erro ao expandir {category_name}: {str(error)[:100]}")

        if not category_url or category_url in seen_final:
            continue

        seen_final.add(category_url)
        final_categories.append(category)

    return final_categories


# ============================================================
# ITENS / PAGINAÇÃO
# ============================================================

async def collect_total_items_in_category(
    page: Any,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> int:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    selector = resolved_adapter.listing.category_total_selector

    if resolved_context.site_key == "plugintheme":
        payload = await page.evaluate(
            """
            () => {
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                const nav = document.querySelector("nav[aria-label='Pagination']");

                return {
                    body_text: normalize(document.body ? (document.body.innerText || document.body.textContent || '') : ''),
                    nav_text: normalize(nav ? (nav.innerText || nav.textContent || '') : ''),
                };
            }
            """
        )

        normalized_body = _normalize_spaces(dict(payload or {}).get("body_text", ""))
        normalized_nav = _normalize_spaces(dict(payload or {}).get("nav_text", ""))
        combined = " | ".join(value for value in (normalized_body, normalized_nav) if value)

        match = re.search(
            r"(?:Mostrando|Showing)\s+\d+\s*-\s*\d+\s+(?:de|of)\s+(\d+)\s+(?:produtos?|products?)",
            combined,
            flags=re.IGNORECASE,
        )
        if match:
            return int(match.group(1))

    text = await page.evaluate(
        """
        (selector) => {
            const el = document.querySelector(selector);
            return el ? (el.innerText || el.textContent || '').trim() : '';
        }
        """,
        selector,
    )

    normalized = _normalize_spaces(text)

    match = re.search(
        r"(?:Mostrando|Showing)\s+\d+\s*-\s*\d+\s+(?:de|of)\s+(\d+)\s+(?:produtos?|products?)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match:
        return int(match.group(1))

    numbers = re.findall(r"(\d+)", normalized)
    return int(numbers[-1]) if numbers else 0


async def collect_total_pages_in_category(
    page: Any,
    *,
    context: Any = None,
) -> int:
    resolved_context = build_context(context)

    if resolved_context.site_key != "plugintheme":
        return 1

    payload = await page.evaluate(
        """
        () => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
            const nav = document.querySelector("nav[aria-label='Pagination']");
            const links = nav
                ? Array.from(nav.querySelectorAll("a[href]")).map(link => ({
                    text: normalize(link.innerText || link.textContent || ''),
                    href: normalize(link.getAttribute('href') || link.href || ''),
                    rel: normalize(link.getAttribute('rel') || ''),
                    aria_current: normalize(link.getAttribute('aria-current') || ''),
                }))
                : [];

            return {
                body_text: normalize(document.body ? (document.body.innerText || document.body.textContent || '') : ''),
                nav_text: normalize(nav ? (nav.innerText || nav.textContent || '') : ''),
                links,
            };
        }
        """
    )

    raw = dict(payload or {})
    body_text = _normalize_spaces(raw.get("body_text", ""))
    nav_text = _normalize_spaces(raw.get("nav_text", ""))
    links = raw.get("links", []) or []

    candidates: list[int] = [1]

    match = re.search(
        r"\(\s*Page\s+\d+\s+of\s+(\d+)\s*\)",
        body_text,
        flags=re.IGNORECASE,
    )
    if match:
        candidates.append(int(match.group(1)))

    match = re.search(
        r"\bPage\s+\d+\s+of\s+(\d+)\b",
        f"{nav_text} {body_text}",
        flags=re.IGNORECASE,
    )
    if match:
        candidates.append(int(match.group(1)))

    for raw_link in links:
        link = dict(raw_link or {})
        text = _normalize_spaces(link.get("text", ""))
        href = _normalize_spaces(link.get("href", ""))

        if text.isdigit():
            candidates.append(int(text))

        match = re.search(r"[?&]page=(\d+)", href, flags=re.IGNORECASE)
        if match:
            candidates.append(int(match.group(1)))

    return max(candidates) if candidates else 1

async def scroll_to_page_end(
    page: Any,
    control: Any = None,
    app: Any = None,
) -> None:
    await browser_check_pause_stop(control, app)

    await page.evaluate(
        """
        async () => {
            const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
            let lastHeight = -1;

            for (let i = 0; i < 10; i++) {
                window.scrollTo(0, document.body.scrollHeight);
                await delay(700);

                const currentHeight = document.body.scrollHeight;
                if (currentHeight === lastHeight) {
                    break;
                }

                lastHeight = currentHeight;
            }

            window.scrollTo(0, 0);
        }
        """
    )

    await controlled_sleep(0.4, control=control, app=app)


async def extract_cards_from_page(
    page: Any,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> list[dict[str, str]]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    listing = resolved_adapter.listing

    wait_selector = f"{listing.item_card_selector}, {listing.item_any_link_selector}"

    try:
        await page.wait_for_selector(wait_selector, timeout=10_000)
    except Exception:
        return []

    await scroll_to_page_end(page, control, app)

    if resolved_context.site_key == "plugintheme":
        items = await page.evaluate(
            """
            () => {
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

                const bodyText = normalize(
                    document.body ? (document.body.innerText || document.body.textContent || '') : ''
                );

                if (/\\b404\\b/i.test(bodyText) || /página não encontrada/i.test(bodyText) || /page not found/i.test(bodyText)) {
                    return [];
                }

                const cards = Array.from(document.querySelectorAll("article.group, main article, section article"));
                const out = [];
                const seen = new Set();

                for (const card of cards) {
                    if (card.closest("header, nav, footer, aside")) continue;

                    const link =
                        card.querySelector("a[href*='/product/']") ||
                        card.querySelector("h1 a[href*='/product/'], h2 a[href*='/product/'], h3 a[href*='/product/'], h4 a[href*='/product/']");

                    if (!link) continue;

                    const href = normalize(link.href || link.getAttribute('href') || '');
                    if (!href || seen.has(href)) continue;

                    let nome = '';

                    const titleCandidates = Array.from(
                        card.querySelectorAll("h1, h2, h3, h4, [class*='title'], [class*='name'], strong")
                    );

                    for (const candidate of titleCandidates) {
                        const text = normalize(candidate.innerText || candidate.textContent || '');
                        if (!text) continue;
                        if (/^view details$/i.test(text)) continue;
                        if (/^ver detalhes$/i.test(text)) continue;
                        if (/^add to cart$/i.test(text)) continue;
                        if (/^adicionar ao carrinho$/i.test(text)) continue;
                        if (/^most popular$/i.test(text)) continue;
                        if (/^newest$/i.test(text)) continue;
                        if (/^highest rated$/i.test(text)) continue;
                        if (/^price:/i.test(text)) continue;
                        if (/^\\$/.test(text)) continue;
                        nome = text;
                        break;
                    }

                    if (!nome) {
                        nome = normalize(link.innerText || link.textContent || '');
                    }

                    if (!nome) continue;

                    seen.add(href);
                    out.push({
                        link_produto: href,
                        nome_lista: nome,
                        versao_lista: ''
                    });
                }

                return out;
            }
            """
        )
    else:
        items = await page.evaluate(
            """
            (config) => {
                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

                const buildFallbackItems = () => {
                    const links = Array.from(document.querySelectorAll(config.item_any_link_selector));
                    return links.map(link => ({
                        link_produto: link.href || '',
                        nome_lista: normalize(link.innerText || link.textContent || ''),
                        versao_lista: ''
                    })).filter(item => item.link_produto);
                };

                const cards = Array.from(document.querySelectorAll(config.item_card_selector));
                if (!cards.length) {
                    return buildFallbackItems();
                }

                return cards.map(card => {
                    const cover = card.querySelector(config.item_cover_link_selector);
                    const titleLink = card.querySelector(config.item_title_link_selector);
                    const link = (cover && cover.href) || (titleLink && titleLink.href) || '';

                    let nome = '';
                    if (titleLink) {
                        const clone = titleLink.cloneNode(true);
                        clone.querySelectorAll(config.item_version_selector).forEach(el => el.remove());
                        nome = normalize(clone.innerText || clone.textContent || '');
                    }

                    const versionEl = card.querySelector(config.item_version_selector);
                    const version = versionEl
                        ? normalize(versionEl.innerText || versionEl.textContent || '')
                        : '';

                    return {
                        link_produto: link,
                        nome_lista: nome,
                        versao_lista: version
                    };
                }).filter(item => item.link_produto);
            }
            """,
            {
                "item_card_selector": listing.item_card_selector,
                "item_cover_link_selector": listing.item_cover_link_selector,
                "item_title_link_selector": listing.item_title_link_selector,
                "item_any_link_selector": listing.item_any_link_selector,
                "item_version_selector": listing.item_version_selector,
            },
        )

    unique_items: list[dict[str, str]] = []
    seen: set[str] = set()

    for item in items or []:
        cleaned = resolved_adapter.normalize_list_item(item, category_name="", category_url="")
        link = cleaned["link_produto"]
        if not link or link in seen:
            continue
        seen.add(link)
        unique_items.append(cleaned)

    return unique_items


def build_page_candidates(
    category_url: str,
    page_number: int,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> list[str]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    candidates = resolved_adapter.build_page_candidates(category_url, int(page_number))
    result: list[str] = []
    seen: set[str] = set()

    for url in candidates:
        normalized = _normalize_spaces(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


async def go_to_next_listing_page_by_click(
    page: Any,
    target_page_number: int,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
) -> bool:
    resolved_context = build_context(context)

    if resolved_context.site_key not in {"plugintheme", "ultrapackv2"}:
        return False

    await browser_check_pause_stop(control, app)

    item_fragment = "/product/" if resolved_context.site_key == "plugintheme" else "/item/"

    before_state = await page.evaluate(
        """
        (payload) => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

            const getCurrentPage = () => {
                const current = document.querySelector(
                    "nav[aria-label='Pagination'] [aria-current='page'], .pagination .current, .page-numbers.current, .woocommerce-pagination .current"
                );
                if (current) {
                    const text = normalize(current.textContent || '');
                    if (/^\\d+$/.test(text)) return Number(text);
                }

                const bodyText = normalize(document.body ? (document.body.innerText || document.body.textContent || '') : '');
                let match = bodyText.match(/\\(\\s*Page\\s+(\\d+)\\s+of\\s+\\d+\\s*\\)/i);
                if (!match) {
                    match = bodyText.match(/\\bPage\\s+(\\d+)\\s+of\\s+\\d+\\b/i);
                }
                if (match) {
                    return Number(match[1]);
                }

                try {
                    const url = new URL(location.href);
                    const pageParam = normalize(url.searchParams.get('page') || '');
                    const pagedParam = normalize(url.searchParams.get('paged') || '');
                    if (/^\\d+$/.test(pageParam)) return Number(pageParam);
                    if (/^\\d+$/.test(pagedParam)) return Number(pagedParam);

                    const pathMatch = normalize(url.pathname).match(/\\/page\\/(\\d+)\\/?$/i);
                    if (pathMatch) return Number(pathMatch[1]);
                } catch (e) {}

                return 1;
            };

            const firstProductLink = document.querySelector(`a[href*="${payload.item_fragment}"]`);

            return {
                url: normalize(location.href),
                current_page: getCurrentPage(),
                first_product_link: normalize(
                    firstProductLink
                        ? (firstProductLink.href || firstProductLink.getAttribute('href') || '')
                        : ''
                ),
            };
        }
        """,
        {"item_fragment": item_fragment},
    )

    click_result = await page.evaluate(
        """
        (payload) => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

            const resolveAbsoluteHref = (link) => {
                const raw = normalize(link.getAttribute('href') || link.href || '');
                if (!raw) return '';
                try {
                    return normalize(new URL(raw, location.href).href);
                } catch (e) {
                    return raw;
                }
            };

            const hrefMatchesTargetPage = (href) => {
                if (!href) return false;
                try {
                    const url = new URL(href, location.href);

                    const pageParam = normalize(url.searchParams.get('page') || '');
                    const pagedParam = normalize(url.searchParams.get('paged') || '');
                    if (pageParam === String(payload.target_page)) return true;
                    if (pagedParam === String(payload.target_page)) return true;

                    const pathMatch = normalize(url.pathname).match(/\\/page\\/(\\d+)\\/?$/i);
                    if (pathMatch && String(pathMatch[1]) === String(payload.target_page)) return true;
                } catch (e) {}

                return false;
            };

            const nav = document.querySelector(
                "nav[aria-label='Pagination'], .pagination, .woocommerce-pagination, .nav-links, .page-numbers, .pager, .navigation"
            );

            const links = nav
                ? Array.from(nav.querySelectorAll("a[href]"))
                : Array.from(document.querySelectorAll(".pagination a[href], .woocommerce-pagination a[href], .nav-links a[href], .page-numbers a[href], .pager a[href], .navigation a[href]"));

            if (!links.length) {
                return { clicked: false, href: '' };
            }

            let targetLink = links.find((link) => normalize(link.textContent || '') === String(payload.target_page));

            if (!targetLink) {
                targetLink = links.find((link) => hrefMatchesTargetPage(resolveAbsoluteHref(link)));
            }

            if (!targetLink && Number(payload.target_page) > 1) {
                targetLink = links.find((link) => normalize(link.getAttribute('rel') || '').toLowerCase() === 'next');
            }

            if (!targetLink) {
                return { clicked: false, href: '' };
            }

            const href = resolveAbsoluteHref(targetLink);

            targetLink.scrollIntoView({ block: 'center', inline: 'center' });
            targetLink.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
            targetLink.click();

            return { clicked: true, href };
        }
        """,
        {
            "target_page": int(target_page_number),
        },
    )

    if not bool(dict(click_result or {}).get("clicked")):
        return False

    target_href = _normalize_spaces(dict(click_result or {}).get("href", ""))
    before_url = _normalize_spaces(dict(before_state or {}).get("url", ""))
    before_first_product_link = _normalize_spaces(dict(before_state or {}).get("first_product_link", ""))

    wait_payload = {
        "target_page": int(target_page_number),
        "target_href": target_href,
        "before_url": before_url,
        "before_first_product_link": before_first_product_link,
        "item_fragment": item_fragment,
    }

    async def _wait_until_page_changes() -> bool:
        try:
            await page.wait_for_function(
                """
                (payload) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

                    const getCurrentPage = () => {
                        const current = document.querySelector(
                            "nav[aria-label='Pagination'] [aria-current='page'], .pagination .current, .page-numbers.current, .woocommerce-pagination .current"
                        );
                        if (current) {
                            const text = normalize(current.textContent || '');
                            if (/^\\d+$/.test(text)) return Number(text);
                        }

                        const bodyText = normalize(document.body ? (document.body.innerText || document.body.textContent || '') : '');
                        let match = bodyText.match(/\\(\\s*Page\\s+(\\d+)\\s+of\\s+\\d+\\s*\\)/i);
                        if (!match) {
                            match = bodyText.match(/\\bPage\\s+(\\d+)\\s+of\\s+\\d+\\b/i);
                        }
                        if (match) {
                            return Number(match[1]);
                        }

                        try {
                            const url = new URL(location.href);
                            const pageParam = normalize(url.searchParams.get('page') || '');
                            const pagedParam = normalize(url.searchParams.get('paged') || '');
                            if (/^\\d+$/.test(pageParam)) return Number(pageParam);
                            if (/^\\d+$/.test(pagedParam)) return Number(pagedParam);

                            const pathMatch = normalize(url.pathname).match(/\\/page\\/(\\d+)\\/?$/i);
                            if (pathMatch) return Number(pathMatch[1]);
                        } catch (e) {}

                        return 1;
                    };

                    const firstProductLink = document.querySelector(`a[href*="${payload.item_fragment}"]`);
                    const firstHref = normalize(
                        firstProductLink
                            ? (firstProductLink.href || firstProductLink.getAttribute('href') || '')
                            : ''
                    );

                    const currentUrl = normalize(location.href);
                    const currentPage = getCurrentPage();
                    const pageMatches = Number(currentPage) === Number(payload.target_page);

                    if (!pageMatches) {
                        if (payload.target_href && currentUrl === normalize(payload.target_href)) {
                            return !!firstHref;
                        }
                        return false;
                    }

                    if (!payload.before_first_product_link) {
                        return !!firstHref;
                    }

                    return !!firstHref && (
                        firstHref !== normalize(payload.before_first_product_link)
                        || currentUrl !== normalize(payload.before_url)
                    );
                }
                """,
                wait_payload,
                timeout=15_000,
            )
            return True
        except Exception:
            return False

    changed = await _wait_until_page_changes()

    if not changed and target_href:
        try:
            await safe_goto(page, target_href, control=control, app=app)
            changed = await _wait_until_page_changes()
        except Exception:
            changed = False

    if not changed:
        return False

    with suppress(Exception):
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)

    with suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=15_000)

    await controlled_sleep(0.8, control=control, app=app)
    return True


async def collect_items_from_category(
    page: Any,
    category: Mapping[str, Any],
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> dict[str, Any]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    category_dict = resolved_adapter.normalize_category(category)
    category_name = category_dict["categoria_nome"]
    category_url = category_dict["categoria_url"]
    expected_total_from_catalog = category_dict["total_esperado"]

    _log(
        app,
        f"📂 Categoria: {category_name} | esperado no catálogo: {expected_total_from_catalog}",
    )

    items_by_link: dict[str, dict[str, str]] = {}
    page_signatures_seen: set[str] = set()
    page_snapshots: list[dict[str, Any]] = []
    collected_raw_total = 0
    repeated_pages = 0
    pages_without_gain = 0
    pages_visited = 0

    link_pages_map: dict[str, list[int]] = {}
    links_repeated_across_pages: dict[str, list[int]] = {}

    use_http_listing = _use_http_listing_for_context(resolved_context)
    page_size_value = (
        _get_ultrapack_http_page_size()
        if use_http_listing and resolved_context.site_key == "ultrapackv2"
        else max(1, to_int(resolved_adapter.pagination.page_size_value, 128))
    )

    first_candidates = _build_listing_page_candidates(
        category_url,
        1,
        page_size_value=page_size_value,
        context=resolved_context,
        runtime_context=resolved_runtime_context,
        adapter=resolved_adapter,
        use_http_listing=use_http_listing,
    )
    if category_url:
        normalized_category_url = _normalize_spaces(category_url)
        if normalized_category_url and normalized_category_url not in first_candidates:
            first_candidates.append(normalized_category_url)

    http_session = requests.Session() if use_http_listing else None

    total_inside_category = 0
    detected_total_pages = 1
    first_page_items: list[dict[str, str]] = []
    loaded_first_url = ""

    def _extract_items_from_http_html(html: str, page_url: str) -> tuple[int, int, list[dict[str, str]]]:
        if not html:
            return 0, 1, []

        if resolved_context.site_key == "plugintheme":
            total_items, total_pages = _extract_plugintheme_listing_stats_from_html(html)
            page_items = _extract_plugintheme_items_from_html(html, page_url)
            return total_items, total_pages, page_items

        if resolved_context.site_key in {"ultrapackv2", "plugintheme"}:
            total_items, total_pages = _extract_ultrapack_listing_stats_from_html(
                html,
                page_size=page_size_value,
            )
            page_items = _extract_ultrapack_items_from_html(html, page_url)
            return total_items, total_pages, page_items

        return 0, 1, []

    def _prepare_page_items(
        page_items: Sequence[Mapping[str, Any]] | None,
    ) -> tuple[list[dict[str, str]], int]:
        raw_items_count = len(list(page_items or []))
        cleaned_page_items: list[dict[str, str]] = []
        page_links: set[str] = set()

        for item in page_items or []:
            cleaned = resolved_adapter.normalize_list_item(
                item,
                category_name=category_name,
                category_url=category_url,
            )
            link = cleaned["link_produto"]
            if not link or link in page_links:
                continue
            page_links.add(link)
            cleaned_page_items.append(cleaned)

        return cleaned_page_items, raw_items_count

    def _page_signature(page_items: Sequence[Mapping[str, Any]] | None) -> str:
        links = sorted({
            _normalize_spaces(dict(item or {}).get("link_produto", ""))
            for item in (page_items or [])
            if _normalize_spaces(dict(item or {}).get("link_produto", ""))
        })
        return "\n".join(links)

    def _preview_page_items(
        page_items: Sequence[Mapping[str, Any]] | None,
        *,
        page_number: int,
        source_label: str,
    ) -> dict[str, Any]:
        cleaned_page_items, raw_items_count = _prepare_page_items(page_items)

        new_items = sum(
            1
            for cleaned in cleaned_page_items
            if cleaned["link_produto"] not in items_by_link
        )

        signature = _page_signature(cleaned_page_items)
        is_repeated = bool(signature) and signature in page_signatures_seen

        duplicate_links_across_pages_count = sum(
            1
            for cleaned in cleaned_page_items
            if cleaned["link_produto"] in link_pages_map
            and page_number not in link_pages_map.get(cleaned["link_produto"], [])
        )

        return {
            "page_number": int(page_number),
            "source_label": _normalize_spaces(source_label),
            "raw_items_count": raw_items_count,
            "items_count": len(cleaned_page_items),
            "new_items": new_items,
            "is_repeated": is_repeated,
            "duplicate_links_across_pages": duplicate_links_across_pages_count,
            "signature": signature,
        }

    def _candidate_sort_key(snapshot: dict[str, Any] | None) -> tuple[int, int, int, int]:
        if not isinstance(snapshot, Mapping):
            return (-1, -1, -1, -1)

        return (
            int(snapshot.get("new_items", 0)),
            1 if not bool(snapshot.get("is_repeated", False)) else 0,
            int(snapshot.get("items_count", 0)),
            int(snapshot.get("raw_items_count", 0)),
        )

    def _merge_page_items(
        page_items: Sequence[Mapping[str, Any]] | None,
        *,
        page_number: int,
        source_label: str,
    ) -> dict[str, Any]:
        nonlocal collected_raw_total
        nonlocal repeated_pages
        nonlocal pages_without_gain
        nonlocal pages_visited

        cleaned_page_items, raw_items_count = _prepare_page_items(page_items)
        collected_raw_total += raw_items_count

        before = len(items_by_link)

        for cleaned in cleaned_page_items:
            link = cleaned["link_produto"]

            pages_for_link = link_pages_map.setdefault(link, [])
            if page_number not in pages_for_link:
                pages_for_link.append(page_number)

            if len(pages_for_link) > 1:
                links_repeated_across_pages[link] = list(sorted(pages_for_link))

            items_by_link[link] = cleaned

        after = len(items_by_link)

        new_items = after - before
        signature = _page_signature(cleaned_page_items)
        is_repeated = bool(signature) and signature in page_signatures_seen

        if signature:
            page_signatures_seen.add(signature)

        if is_repeated:
            repeated_pages += 1
        if new_items <= 0:
            pages_without_gain += 1

        pages_visited += 1

        snapshot = {
            "page_number": int(page_number),
            "source_label": _normalize_spaces(source_label),
            "raw_items_count": raw_items_count,
            "items_count": len(cleaned_page_items),
            "new_items": new_items,
            "is_repeated": is_repeated,
            "duplicate_links_across_pages": sum(
                1
                for cleaned in cleaned_page_items
                if len(link_pages_map.get(cleaned["link_produto"], [])) > 1
            ),
            "signature": signature,
        }
        page_snapshots.append(snapshot)
        return snapshot

    def _build_result() -> dict[str, Any]:
        unique_count = len(items_by_link)
        expected_reference = max(
            0,
            to_int(total_inside_category, 0),
            to_int(expected_total_from_catalog, 0),
        )
        missing_estimated = max(0, expected_reference - unique_count) if expected_reference > 0 else 0
        duplicates_internal = max(0, collected_raw_total - unique_count)

        duplicate_samples = [
            {
                "link_produto": link,
                "paginas": list(pages),
            }
            for link, pages in sorted(
                links_repeated_across_pages.items(),
                key=lambda item: (-len(item[1]), item[1], item[0]),
            )[:25]
        ]

        return {
            "items": list(items_by_link.values()),
            "diagnostics": {
                "coletados_brutos": collected_raw_total,
                "coletados_unicos": unique_count,
                "duplicados_internos": duplicates_internal,
                "paginas_visitadas": pages_visited,
                "paginas_repetidas": repeated_pages,
                "paginas_sem_ganho": pages_without_gain,
                "links_repetidos_entre_paginas": len(links_repeated_across_pages),
                "amostras_links_repetidos": duplicate_samples,
                "faltantes_estimados": missing_estimated,
                "status_coleta": "ok" if missing_estimated <= 0 else "incompleta",
                "page_snapshots": list(page_snapshots),
            },
        }

    async def _load_first_page_via_browser(
        candidates: Sequence[str],
    ) -> tuple[int, int, list[dict[str, str]], str]:
        if page is None:
            return 0, 1, [], ""
        browser_total_inside_category = 0
        browser_detected_total_pages = 1
        browser_first_page_items: list[dict[str, str]] = []
        browser_loaded_url = ""

        for candidate_url in candidates or [category_url]:
            try:
                await safe_goto(page, candidate_url, control=control, app=app)

                candidate_total_inside_category = await collect_total_items_in_category(
                    page,
                    context=resolved_context,
                    runtime_context=resolved_runtime_context,
                    adapter=resolved_adapter,
                )

                candidate_detected_total_pages = 1
                if resolved_context.site_key == "plugintheme":
                    with suppress(Exception):
                        candidate_detected_total_pages = max(
                            1,
                            await collect_total_pages_in_category(
                                page,
                                context=resolved_context,
                            ),
                        )

                candidate_first_page_items = await extract_cards_from_page(
                    page,
                    control,
                    app,
                    context=resolved_context,
                    runtime_context=resolved_runtime_context,
                    adapter=resolved_adapter,
                )

                browser_total_inside_category = max(
                    browser_total_inside_category,
                    candidate_total_inside_category,
                )
                browser_detected_total_pages = max(
                    browser_detected_total_pages,
                    candidate_detected_total_pages,
                )

                if candidate_first_page_items:
                    browser_first_page_items = candidate_first_page_items
                    browser_loaded_url = candidate_url
                    break

            except Exception as error:
                _log(app, f"   ↳ falhou página 1 no browser: {str(error)[:100]}")

        return (
            browser_total_inside_category,
            browser_detected_total_pages,
            browser_first_page_items,
            browser_loaded_url,
        )

    async def _load_page_items_via_browser(
        page_number: int,
        candidates: Sequence[str],
        *,
        allow_click_navigation: bool,
    ) -> tuple[list[dict[str, str]], str]:
        if page is None:
            return [], ""
        if allow_click_navigation and resolved_context.site_key in {"plugintheme", "ultrapackv2"}:
            try:
                clicked = await go_to_next_listing_page_by_click(
                    page,
                    page_number,
                    control=control,
                    app=app,
                    context=resolved_context,
                )

                if clicked:
                    page_items = await extract_cards_from_page(
                        page,
                        control,
                        app,
                        context=resolved_context,
                        runtime_context=resolved_runtime_context,
                        adapter=resolved_adapter,
                    )
                    if page_items:
                        return page_items, f"click:{page_number}"
            except Exception as error:
                _log(app, f"   ↳ falhou clique na página {page_number}: {str(error)[:100]}")

        best_page_items: list[dict[str, str]] = []
        best_source = ""
        best_snapshot: dict[str, Any] | None = None

        for candidate_url in candidates:
            try:
                await safe_goto(page, candidate_url, control=control, app=app)

                page_items = await extract_cards_from_page(
                    page,
                    control,
                    app,
                    context=resolved_context,
                    runtime_context=resolved_runtime_context,
                    adapter=resolved_adapter,
                )
                if not page_items:
                    continue

                candidate_snapshot = _preview_page_items(
                    page_items,
                    page_number=page_number,
                    source_label=candidate_url,
                )

                if _candidate_sort_key(candidate_snapshot) > _candidate_sort_key(best_snapshot):
                    best_snapshot = candidate_snapshot
                    best_page_items = list(page_items)
                    best_source = candidate_url

            except Exception as error:
                _log(app, f"   ↳ falhou página {page_number}: {str(error)[:100]}")

        return best_page_items, best_source

    async def _load_best_http_candidate(
        page_number: int,
        candidates: Sequence[str],
        *,
        log_candidates: bool = True,
    ) -> tuple[int, int, list[dict[str, str]], str, dict[str, Any] | None]:
        best_total_inside_category = 0
        best_detected_total_pages = 1
        best_page_items: list[dict[str, str]] = []
        best_source = ""
        best_snapshot: dict[str, Any] | None = None

        for candidate_url in candidates or [category_url]:
            try:
                html = await _fetch_html_via_authenticated_http(
                    page,
                    candidate_url,
                    control=control,
                    app=app,
                    shared_session=http_session,
                )
            except Exception as error:
                _log(app, f"   ↳ falhou HTTP na página {page_number}: {str(error)[:100]}")
                html = ""

            if not html:
                continue

            candidate_total_inside_category, candidate_detected_total_pages, candidate_page_items = _extract_items_from_http_html(
                html,
                candidate_url,
            )

            best_total_inside_category = max(best_total_inside_category, candidate_total_inside_category)
            best_detected_total_pages = max(best_detected_total_pages, candidate_detected_total_pages)

            candidate_snapshot = _preview_page_items(
                candidate_page_items,
                page_number=page_number,
                source_label=candidate_url,
            )

            if log_candidates and len(candidates or []) > 1:
                _log(
                    app,
                    f"   ↳ candidata HTTP p{page_number}: {candidate_url} | "
                    f"brutos: {candidate_snapshot['raw_items_count']} | "
                    f"únicos: {candidate_snapshot['items_count']} | "
                    f"novos: {candidate_snapshot['new_items']}"
                    f"{' | assinatura repetida' if candidate_snapshot['is_repeated'] else ''}"
                    f"{' | links já vistos em outras páginas: ' + str(candidate_snapshot['duplicate_links_across_pages']) if candidate_snapshot['duplicate_links_across_pages'] else ''}",
                )

            if _candidate_sort_key(candidate_snapshot) > _candidate_sort_key(best_snapshot):
                best_snapshot = candidate_snapshot
                best_page_items = list(candidate_page_items)
                best_source = candidate_url

        return (
            best_total_inside_category,
            best_detected_total_pages,
            best_page_items,
            best_source,
            best_snapshot,
        )

            
    try:
        if use_http_listing:
            (
                candidate_total_inside_category,
                candidate_detected_total_pages,
                candidate_first_page_items,
                candidate_loaded_first_url,
                _candidate_first_snapshot,
            ) = await _load_best_http_candidate(
                1,
                first_candidates or [category_url],
                log_candidates=True,
            )

            total_inside_category = max(total_inside_category, candidate_total_inside_category)
            detected_total_pages = max(detected_total_pages, candidate_detected_total_pages)

            if candidate_first_page_items:
                first_page_items = candidate_first_page_items
                loaded_first_url = candidate_loaded_first_url

                cooldown_seconds = _get_ultrapack_http_category_cooldown_seconds()
                if cooldown_seconds > 0:
                    await controlled_sleep(
                        cooldown_seconds,
                        control=control,
                        app=app,
                    )

            if not first_page_items:
                (
                    browser_total_inside_category,
                    browser_detected_total_pages,
                    browser_first_page_items,
                    browser_loaded_url,
                ) = await _load_first_page_via_browser(first_candidates or [category_url])

                total_inside_category = max(total_inside_category, browser_total_inside_category)
                detected_total_pages = max(detected_total_pages, browser_detected_total_pages)

                if browser_first_page_items:
                    first_page_items = browser_first_page_items
                    loaded_first_url = browser_loaded_url
                    _log(app, "   ↳ página 1 recuperada via browser")
        else:
            (
                total_inside_category,
                detected_total_pages,
                first_page_items,
                loaded_first_url,
            ) = await _load_first_page_via_browser(first_candidates or [category_url])

        if loaded_first_url and loaded_first_url != category_url:
            _log(app, f"   ↳ página 1 carregada via URL alternativa: {loaded_first_url}")

        if not first_page_items:
            await warn_possible_grouped_category(
                page,
                category_dict,
                app,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=resolved_adapter,
            )

        first_snapshot = _merge_page_items(
            first_page_items,
            page_number=1,
            source_label=loaded_first_url or "pagina_1",
        )

        total_reference = total_inside_category or expected_total_from_catalog or 0
        total_for_log = total_reference or len(items_by_link)

        _log(
            app,
            f"   ↳ página 1: {first_snapshot['items_count']} itens | total da categoria: {total_for_log}",
        )
        if first_snapshot["is_repeated"]:
            _log(app, "   ↳ página 1: assinatura repetida detectada.")

        test_mode = _get_test_mode()
        test_max_items = _get_test_max_items_per_category()
        if test_mode and test_max_items and len(items_by_link) >= test_max_items:
            result = _build_result()
            result["items"] = result["items"][:test_max_items]
            result["diagnostics"]["coletados_unicos"] = len(result["items"])
            result["diagnostics"]["faltantes_estimados"] = max(
                0,
                max(0, to_int(total_inside_category, 0), to_int(expected_total_from_catalog, 0)) - len(result["items"]),
            )
            result["diagnostics"]["status_coleta"] = "ok" if result["diagnostics"]["faltantes_estimados"] <= 0 else "incompleta"
            return result

        if total_reference > 0:
            max_pages_from_total = max(1, (int(total_reference) + page_size_value - 1) // page_size_value)
            max_pages_from_total = min(max_pages_from_total, _get_max_pages_fallback())
        else:
            max_pages_from_total = _get_max_pages_fallback() if first_page_items else 1
            if max_pages_from_total > 1:
                _log(
                    app,
                    "   ↳ total não detectado; paginação seguirá por tentativa até parar de encontrar itens novos.",
                )

        max_pages = max(1, max_pages_from_total, detected_total_pages)
        max_pages = min(max_pages, _get_max_pages_fallback())

        if resolved_context.site_key in {"plugintheme", "ultrapackv2"}:
            _log(app, f"   ↳ páginas detectadas: {max_pages}")

        if max_pages > 1:
            if use_http_listing:
                for page_number in range(2, max_pages + 1):
                    await browser_check_pause_stop(control, app)

                    if test_mode and test_max_items and len(items_by_link) >= test_max_items:
                        break

                    found_new_items = False
                    candidates = _build_listing_page_candidates(
                        category_url,
                        page_number,
                        page_size_value=page_size_value,
                        context=resolved_context,
                        runtime_context=resolved_runtime_context,
                        adapter=resolved_adapter,
                        use_http_listing=use_http_listing,
                    )

                    (
                        candidate_total_inside_category,
                        candidate_detected_total_pages,
                        candidate_page_items,
                        candidate_source,
                        candidate_snapshot,
                    ) = await _load_best_http_candidate(
                        page_number,
                        candidates,
                        log_candidates=True,
                    )

                    total_inside_category = max(total_inside_category, candidate_total_inside_category)
                    detected_total_pages = max(detected_total_pages, candidate_detected_total_pages)

                    if candidate_page_items and candidate_snapshot and candidate_snapshot["new_items"] > 0:
                        snapshot = _merge_page_items(
                            candidate_page_items,
                            page_number=page_number,
                            source_label=candidate_source,
                        )

                        _log(
                            app,
                            f"   ↳ página {page_number}: {snapshot['items_count']} itens | novos: {snapshot['new_items']}",
                        )
                        if snapshot["is_repeated"]:
                            _log(app, f"   ↳ página {page_number}: assinatura repetida detectada.")

                        found_new_items = True

                    if not found_new_items:
                        missing_now = max(
                            0,
                            max(
                                to_int(total_inside_category, 0),
                                to_int(expected_total_from_catalog, 0),
                            ) - len(items_by_link),
                        )

                        if missing_now > 0 and page_number < max_pages:
                            _log(
                                app,
                                f"   ↳ página {page_number} sem ganho real via HTTP; seguindo para a próxima | faltantes estimados: {missing_now}",
                            )
                            continue

                        _log(app, f"   ↳ sem itens novos na página {page_number}; encerrando categoria.")
                        break

                if (
                    expected_total_from_catalog > 0
                    and len(items_by_link) < expected_total_from_catalog
                    and not (test_mode and test_max_items and len(items_by_link) >= test_max_items)
                ):
                    _log(
                        app,
                        "🛟 Categoria incompleta via HTTP; iniciando resgate no browser: "
                        f"{category_name} | coletados: {len(items_by_link)}/{expected_total_from_catalog}",
                    )

                    for page_number in range(1, max_pages + 1):
                        await browser_check_pause_stop(control, app)

                        if test_mode and test_max_items and len(items_by_link) >= test_max_items:
                            break

                        candidates = _build_listing_page_candidates(
                            category_url,
                            page_number,
                            page_size_value=page_size_value,
                            context=resolved_context,
                            runtime_context=resolved_runtime_context,
                            adapter=resolved_adapter,
                            use_http_listing=use_http_listing,
                        )

                        if page_number == 1 and category_url:
                            normalized_category_url = _normalize_spaces(category_url)
                            if normalized_category_url and normalized_category_url not in candidates:
                                candidates = list(candidates) + [normalized_category_url]

                        browser_page_items, browser_source = await _load_page_items_via_browser(
                            page_number,
                            candidates,
                            allow_click_navigation=page_number > 1,
                        )

                        if not browser_page_items:
                            continue

                        snapshot = _merge_page_items(
                            browser_page_items,
                            page_number=page_number,
                            source_label=browser_source or f"browser-rescue:{page_number}",
                        )

                        if snapshot["new_items"] > 0:
                            _log(
                                app,
                                f"   ↳ resgate browser página {page_number}: {snapshot['items_count']} itens | novos: {snapshot['new_items']}",
                            )

                        if len(items_by_link) >= expected_total_from_catalog:
                            break

                    if len(items_by_link) < expected_total_from_catalog:
                        _log(
                            app,
                            "⚠️ Categoria ainda incompleta após resgate: "
                            f"{category_name} | coletados: {len(items_by_link)}/{expected_total_from_catalog}",
                        )

                return _build_result()

            for page_number in range(2, max_pages + 1):
                await browser_check_pause_stop(control, app)

                if test_mode and test_max_items and len(items_by_link) >= test_max_items:
                    break

                candidates = build_page_candidates(
                    category_url,
                    page_number,
                    context=resolved_context,
                    runtime_context=resolved_runtime_context,
                    adapter=resolved_adapter,
                )

                page_items, page_source = await _load_page_items_via_browser(
                    page_number,
                    candidates,
                    allow_click_navigation=True,
                )

                if not page_items:
                    _log(app, f"   ↳ sem itens novos na página {page_number}; encerrando categoria.")
                    break

                snapshot = _merge_page_items(
                    page_items,
                    page_number=page_number,
                    source_label=page_source or f"browser:{page_number}",
                )

                _log(
                    app,
                    f"   ↳ página {page_number}: {snapshot['items_count']} itens | novos: {snapshot['new_items']}",
                )
                if snapshot["is_repeated"]:
                    _log(app, f"   ↳ página {page_number}: assinatura repetida detectada.")

                if snapshot["new_items"] <= 0:
                    _log(app, f"   ↳ sem itens novos na página {page_number}; encerrando categoria.")
                    break

        return _build_result()
    finally:
        if http_session is not None:
            with suppress(Exception):
                http_session.close()


# ============================================================
# DETALHES
# ============================================================


async def extract_raw_details(
    page: Any,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> dict[str, str]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    detail = resolved_adapter.detail

    data = await page.evaluate(
        """
        (config) => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();

            const firstText = (selectors) => {
                for (const selector of selectors || []) {
                    const el = document.querySelector(selector);
                    if (!el) continue;
                    const text = normalize(el.innerText || el.textContent || '');
                    if (text) return text;
                }
                return '';
            };

            const attr = (selector, attrName) => {
                if (!selector) return '';
                const el = document.querySelector(selector);
                if (!el) return '';
                return normalize(el.getAttribute(attrName) || '');
            };

            const absoluteAttr = (selector, attrName) => {
                if (!selector) return '';
                const el = document.querySelector(selector);
                if (!el) return '';

                let raw = '';
                if (attrName === 'src' && el.src) {
                    raw = el.src;
                } else {
                    raw = el.getAttribute(attrName) || '';
                }

                raw = normalize(raw);
                if (!raw) return '';

                try {
                    return normalize(new URL(raw, location.href).href);
                } catch (e) {
                    return raw;
                }
            };

                      const versionFromLabeledFields = () => {
                const extractVersion = (value) => {
                    const text = normalize(value || '');
                    if (!text) return '';

                    const withV = text.match(/\\bv\\s*(\\d+(?:\\.\\d+){0,5})\\b/i);
                    if (withV) return withV[1];

                    const labeled = text.match(/(?:vers[aã]o|version)\\s*[:#-]?\\s*(\\d+(?:\\.\\d+){0,5})/i);
                    if (labeled) return labeled[1];

                    const loose = text.match(/\\b(\\d+(?:\\.\\d+){1,5})\\b/);
                    if (loose) return loose[1];

                    return '';
                };

                const topCandidates = [
                    ".single-bt-item-version",
                    ".single-bt-right .text-muted-foreground",
                    ".summary .text-muted-foreground",
                    ".entry-summary .text-muted-foreground",
                    ".summary [class*='version']",
                    ".entry-summary [class*='version']",
                    ".summary [class*='calendar']",
                    ".entry-summary [class*='calendar']",
                    ".summary .elementor-icon-list-text",
                    ".entry-summary .elementor-icon-list-text",
                    ".text-muted-foreground",
                    "[class*='version']",
                    "[class*='calendar']",
                    "time[datetime]",
                ];

                for (const selector of topCandidates) {
                    const nodes = Array.from(document.querySelectorAll(selector));
                    for (const node of nodes) {
                        const parsed = extractVersion(node.innerText || node.textContent || '');
                        if (parsed) return parsed;
                    }
                }

                const tags = Array.from(document.querySelectorAll(config.version_tag_selector || ''));
                for (const tag of tags) {
                    const tagText = normalize(tag.innerText || tag.textContent || '');
                    const tagVersion = extractVersion(tagText);
                    if (tagVersion) return tagVersion;

                    const parent = tag.parentElement;
                    if (parent) {
                        if (config.version_value_selector) {
                            const valueInsideParent = parent.querySelector(config.version_value_selector);
                            if (valueInsideParent) {
                                const textValue = normalize(valueInsideParent.innerText || valueInsideParent.textContent || '');
                                const parsed = extractVersion(textValue);
                                if (parsed) return parsed;
                            }
                        }

                        const parentVersion = extractVersion(parent.innerText || parent.textContent || '');
                        if (parentVersion) return parentVersion;
                    }

                    let next = tag.nextElementSibling;
                    while (next) {
                        const textValue = normalize(next.innerText || next.textContent || '');
                        const parsed = extractVersion(textValue);
                        if (parsed) return parsed;
                        next = next.nextElementSibling;
                    }
                }

                if (config.version_value_selector) {
                    const valueNodes = Array.from(document.querySelectorAll(config.version_value_selector));
                    for (const node of valueNodes) {
                        const parsed = extractVersion(node.innerText || node.textContent || '');
                        if (parsed) return parsed;
                    }
                }

                const fallbackNodes = Array.from(
                    document.querySelectorAll(".single-bt-item-version, .text-muted-foreground, [class*='version'], [class*='calendar'], time[datetime]")
                );
                for (const node of fallbackNodes) {
                    const parsed = extractVersion(node.innerText || node.textContent || '');
                    if (parsed) return parsed;
                }

                return '';
            };

            const officialPageFromButtons = () => {
    const directSelectors = [
        ".single-bt-item-page a[href]",
        "div.single-bt-item-page a[href]",
    ];

    for (const selector of directSelectors) {
        const el = document.querySelector(selector);
        if (!el) continue;

        const href = normalize(el.href || el.getAttribute('href') || '');
        if (!href || href === '#' || href.toLowerCase().startsWith('javascript:')) {
            continue;
        }

        return href;
    }

    const labels = Array.isArray(config.official_page_button_labels)
        ? config.official_page_button_labels.map(value => normalize(value).toLowerCase()).filter(Boolean)
        : [];

    if (!labels.length) {
        return '';
    }

    const candidates = Array.from(
        document.querySelectorAll(".single-bt-item-page a[href], a[href], [data-href]")
    );

    for (const el of candidates) {
        const text = normalize(el.innerText || el.textContent || '').toLowerCase();
        if (!text) continue;
        if (!labels.some(label => text.includes(label))) continue;

        let href = '';

        if (el.tagName && el.tagName.toLowerCase() === 'a' && el.href) {
            href = normalize(el.href);
        } else {
            href = normalize(el.getAttribute('href') || el.getAttribute('data-href') || '');
            if (href) {
                try {
                    href = normalize(new URL(href, location.href).href);
                } catch (e) {}
            }
        }

        if (!href || href === '#' || href.toLowerCase().startsWith('javascript:')) {
            continue;
        }

        return href;
    }

    return '';
};
const productCategoriesFromInternalStore = () => {
    const selectors = [
        ".product_meta a[href*='/product-category/']",
        ".posted_in a[href*='/product-category/']",
        ".entry-summary a[href*='/product-category/']",
        ".summary a[href*='/product-category/']",
        ".woocommerce-breadcrumb a[href*='/product-category/']",
        "main a[href*='/product-category/']",
        "article a[href*='/product-category/']",
        "a[href*='/pt-BR/product-category/']",
    ];

    const texts = [];
    const seen = new Set();

    for (const selector of selectors) {
        const nodes = Array.from(document.querySelectorAll(selector));
        for (const node of nodes) {
            if (node.closest("header, nav, footer, aside")) continue;

            const text = normalize(node.innerText || node.textContent || '');
            if (!text) continue;

            const key = text.toLowerCase();
            if (seen.has(key)) continue;

            seen.add(key);
            texts.push(text);
        }
    }

    return texts.join(' | ');
};
let observacao = '';
let observacao_classes = '';

const skipTokens = new Set(
    String(config.skip_observation_class || '')
        .split(/[\s,]+/)
        .map(value => normalize(value).toLowerCase())
        .filter(Boolean)
);

const selectors = Array.isArray(config.observation_scope_selectors)
    ? config.observation_scope_selectors
    : [];
const nodes = selectors.length
    ? Array.from(document.querySelectorAll(selectors.join(',')))
    : [];

for (const el of nodes) {
    const tagName = String(el.tagName || '').toLowerCase();
    if (!tagName || ['a', 'button', 'input', 'label'].includes(tagName)) {
        continue;
    }

    const classes = Array.from(el.classList || []);
    const itemClasses = classes
        .map(cls => normalize(cls))
        .filter(cls => cls.startsWith('item-'));

    if (!itemClasses.length) {
        continue;
    }

    const loweredClasses = new Set(itemClasses.map(cls => cls.toLowerCase()));
    const hasSkippedClass = Array.from(loweredClasses).some(cls => skipTokens.has(cls));
    if (hasSkippedClass) {
        continue;
    }

    const insideHeader = config.skip_observation_container_selector
        ? !!el.closest(config.skip_observation_container_selector)
        : false;

    if (insideHeader) {
        continue;
    }

    const textoObs = normalize(el.innerText || el.textContent || '');
    if (!textoObs || textoObs.length < (config.observation_min_length || 15)) {
        continue;
    }

    observacao = textoObs;
    observacao_classes = itemClasses.join(' ');
    break;
}

            return {
                page_url: location.href,
                nome_h1: firstText(config.name_selectors || []),
                versao: versionFromLabeledFields(),
                img_alt: attr(config.image_alt_selector, 'alt'),
                imagem_url: absoluteAttr(config.image_alt_selector, 'src'),
                og_title: attr(config.og_title_selector, 'content'),
                pagina_oficial: officialPageFromButtons(),
                categorias_internas: productCategoriesFromInternalStore(),
                observacao,
                observacao_classes,
            };
        }
        """,
        {
            "name_selectors": list(detail.name_selectors),
            "version_tag_selector": detail.version_tag_selector,
            "version_value_selector": detail.version_value_selector,
            "image_alt_selector": detail.image_alt_selector,
            "og_title_selector": detail.og_title_selector,
            "official_page_button_labels": list(detail.official_page_button_labels),
            "observation_scope_selectors": list(detail.observation_scope_selectors),
            "skip_observation_container_selector": detail.skip_observation_container_selector,
            "skip_observation_class": detail.skip_observation_class,
            "observation_min_length": detail.observation_min_length,
        },
    )

    raw = dict(data or {})
    return {
        "page_url": _normalize_spaces(raw.get("page_url", "")),
        "nome_h1": _normalize_spaces(raw.get("nome_h1", "")),
        "versao": _normalize_spaces(raw.get("versao", "")),
        "img_alt": _normalize_spaces(raw.get("img_alt", "")),
        "imagem_url": _normalize_spaces(raw.get("imagem_url", "")),
        "og_title": _normalize_spaces(raw.get("og_title", "")),
        "pagina_oficial": _normalize_spaces(raw.get("pagina_oficial", "")),
        "categorias_internas": _normalize_spaces(raw.get("categorias_internas", "")),
        "observacao": _normalize_spaces(raw.get("observacao", "")),
        "observacao_classes": _normalize_spaces(raw.get("observacao_classes", "")),
    }


def choose_final_name(
    url: str,
    item: Mapping[str, Any] | None,
    raw_details: Mapping[str, Any] | None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
) -> str:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    raw = dict(raw_details or {})
    item_dict = dict(item or {})

    return resolved_adapter.choose_final_name(
        url,
        list_name=_normalize_spaces(item_dict.get("nome_lista", "")),
        raw_name=_normalize_spaces(raw.get("nome_h1", "")),
        image_alt=_normalize_spaces(raw.get("img_alt", "")),
        og_title=_normalize_spaces(raw.get("og_title", "")),
    )


def _resolve_product_type_from_internal_categories(
    item: Mapping[str, Any] | None,
    raw_details: Mapping[str, Any] | None,
    *,
    context: Any = None,
) -> str:
    resolved_context = build_context(context)
    item_dict = dict(item or {})
    raw = dict(raw_details or {})

    structured_type = _normalize_spaces(raw.get("product_type", "")).lower()
    if structured_type == "plugin":
        return "plugin"
    if structured_type == "theme":
        return "theme"

    current_type = _normalize_spaces(item_dict.get("tipo", ""))

    if resolved_context.site_key != "plugintheme":
        return current_type

    categories_text = _normalize_spaces(raw.get("categorias_internas", "")).lower()

    has_plugin = (
        "wordpress plugins" in categories_text
        or "plugins wordpress" in categories_text
    )
    has_theme = (
        "wordpress themes" in categories_text
        or "temas wordpress" in categories_text
    )

    if has_plugin and not has_theme:
        return "plugin"
    if has_theme and not has_plugin:
        return "theme"
    if has_plugin and has_theme:
        return "plugin/theme"

    if current_type == "plugin_theme":
        return "plugin/theme"

    return current_type


async def extract_item_details(
    page: Any,
    item: Mapping[str, Any] | None,
    control: Any = None,
    app: Any = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    adapter: AdapterDefinition | None = None,
    attempts: int | None = None,
    shared_session: requests.Session | None = None,
) -> dict[str, str]:
    resolved_context = build_context(context)
    resolved_adapter = adapter or get_adapter(resolved_context)
    resolved_runtime_context = resolved_adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    item_dict = resolved_adapter.normalize_list_item(
        item,
        category_name=_normalize_spaces(dict(item or {}).get("categoria_nome", "")),
        category_url=ensure_trailing_slash(dict(item or {}).get("categoria_url", "")),
    )
    url = item_dict["link_produto"]
    is_template = item_dict["tipo"] == "template"
    total_attempts = max(1, int(attempts or resolved_adapter.detail.detail_attempts or 1))

    for attempt in range(1, total_attempts + 1):
        await browser_check_pause_stop(control, app)

        try:
            html = await _fetch_html_via_authenticated_http(
                page,
                url,
                control=control,
                app=app,
                shared_session=shared_session,
            )

            if not html:
                raise EngineError(f"HTML vazio em {url}")

            raw = _extract_raw_details_from_html(
                html,
                url,
                context=resolved_context,
                adapter=resolved_adapter,
            )

            # Fallback: se a observação não veio no HTML HTTP,
            # abre o item no navegador real e tenta extrair do DOM renderizado.
            if page is not None and not _normalize_spaces(raw.get("observacao", "")):
                browser_raw: dict[str, Any] = {}

                try:
                    _log(app, f"↳ HTTP sem observação em {url}; abrindo DOM real para fallback.")
                    await safe_goto(
                        page,
                        url,
                        control=control,
                        app=app,
                        timeout=getattr(page, "default_timeout", None),
                        wait_until="domcontentloaded",
                        delay_seconds=0.6,
                    )
                    await controlled_sleep(0.6, control=control, app=app)
                except Exception as browser_nav_error:
                    _log(app, f"↳ fallback DOM falhou ao abrir {url}: {str(browser_nav_error)[:120]}")

                with suppress(Exception):
                    browser_raw = await extract_raw_details(
                        page,
                        context=resolved_context,
                        runtime_context=resolved_runtime_context,
                        adapter=resolved_adapter,
                    )

                if browser_raw:
                    browser_observation = _normalize_spaces(browser_raw.get("observacao", ""))
                    browser_observation_classes = _normalize_spaces(
                        browser_raw.get("observacao_classes", "")
                    )

                    if browser_observation:
                        raw["observacao"] = browser_observation
                        raw["observacao_classes"] = browser_observation_classes

                    if not _normalize_spaces(raw.get("pagina_oficial", "")):
                        raw["pagina_oficial"] = _normalize_spaces(
                            browser_raw.get("pagina_oficial", "")
                        )

                    if is_template and not _normalize_spaces(raw.get("imagem_url", "")):
                        raw["imagem_url"] = _normalize_spaces(
                            browser_raw.get("imagem_url", "")
                        )

                    if not _normalize_spaces(raw.get("og_title", "")):
                        raw["og_title"] = _normalize_spaces(
                            browser_raw.get("og_title", "")
                        )

                    if not _normalize_spaces(raw.get("img_alt", "")):
                        raw["img_alt"] = _normalize_spaces(
                            browser_raw.get("img_alt", "")
                        )

                    if not _normalize_spaces(raw.get("nome_h1", "")):
                        raw["nome_h1"] = _normalize_spaces(
                            browser_raw.get("nome_h1", "")
                        )

                    if not _normalize_spaces(raw.get("versao", "")):
                        raw["versao"] = _normalize_spaces(
                            browser_raw.get("versao", "")
                        )

            final_name = choose_final_name(
                url,
                item_dict,
                raw,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=resolved_adapter,
            )

            final_item_type = _resolve_product_type_from_internal_categories(
                item_dict,
                raw,
                context=resolved_context,
            )

            final_version = resolved_adapter.clean_version(
                raw.get("versao")
                or item_dict.get("versao_lista", "")
            )

            final_observation = resolved_adapter.build_observation(
                raw.get("observacao_classes", ""),
                raw.get("observacao", ""),
            )

            final_official_page = _normalize_spaces(raw.get("pagina_oficial", ""))
            final_image_url = _normalize_spaces(raw.get("imagem_url", "")) if is_template else ""

            if (
                final_name
                or final_version
                or final_observation
                or final_official_page
                or final_image_url
                or _normalize_spaces(raw.get("categorias_internas", ""))
            ):
                return {
                    "tipo": final_item_type,
                    "categoria_nome": item_dict["categoria_nome"],
                    "categoria_url": item_dict["categoria_url"],
                    "link_produto": url,
                    "imagem_url": final_image_url,
                    "imagem_path": "",
                    "pagina_oficial": final_official_page,
                    "nome_produto": final_name or _normalize_spaces(item_dict.get("nome_lista", "")),
                    "versao_produto": final_version,
                    "observacao": final_observation,
                }

        except StopScraper:
            raise
        except Exception as error:
            _log(
                app,
                f"↳ tentativa {attempt}/{total_attempts} falhou em {url}: {str(error)[:120]}",
            )
            await controlled_sleep(0.8, control=control, app=app)

    return {
        "tipo": item_dict["tipo"],
        "categoria_nome": item_dict["categoria_nome"],
        "categoria_url": item_dict["categoria_url"],
        "link_produto": url,
        "imagem_url": "",
        "imagem_path": "",
        "pagina_oficial": "",
        "nome_produto": resolved_adapter.clean_final_name(item_dict.get("nome_lista", "")),
        "versao_produto": resolved_adapter.clean_version(item_dict.get("versao_lista", "")),
        "observacao": "",
    }


# ============================================================
# FLUXOS AUXILIARES
# ============================================================


async def load_filtered_categories_online(
    app: Any,
    control: Any,
    page: Any,
    run_options: Mapping[str, Any] | RunOptions | None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    force_selected: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved_context = build_context(context)
    options = build_run_options(run_options)
    adapter = get_adapter(resolved_context)
    resolved_runtime_context = adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    categories = await collect_categories(
        page,
        control,
        app,
        context=resolved_context,
        runtime_context=resolved_runtime_context,
        adapter=adapter,
    )

    available_categories = _build_available_categories(categories)
    available_categories = save_available_categories(available_categories, resolved_context)
    _sync_available_categories_state(app, available_categories)

    options_payload = options.to_dict()
    if force_selected:
        options_payload["scope_mode"] = "selected"

    filtered_available = filter_categories_by_scope(available_categories, options_payload)
    filtered_categories = [
        _normalize_available_category_to_engine(category, resolved_context)
        for category in filtered_available
    ]

    return (
        [
            _normalize_available_category_to_engine(category, resolved_context)
            for category in available_categories
        ],
        filtered_categories,
    )


async def build_processing_queue_by_categories(
    app: Any,
    control: Any,
    page: Any,
    categories: Sequence[Mapping[str, Any]],
    products_dict: Mapping[str, Mapping[str, Any]] | None,
    verify_mode: str,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_context = build_context(context)
    adapter = get_adapter(resolved_context)
    resolved_runtime_context = adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    categories_cache = load_categories_cache(resolved_context)
    queue_cache = load_queue_cache(resolved_context)

    queue: list[dict[str, str]] = []
    seen_links: set[str] = set()
    existing_products = dict(products_dict or {})
    reused_categories = 0
    refetched_categories = 0
    new_links_detected = 0
    existing_links_detected = 0

    for category in categories:
        await browser_check_pause_stop(control, app)

        category_dict = adapter.normalize_category(category)
        category_key = ensure_trailing_slash(category_dict["categoria_url"])
        previous_queue_entry = dict((queue_cache.get("categories", {}) or {}).get(category_key, {}) or {})
        previous_queue_items = clean_queue_items(
            previous_queue_entry.get("itens", []) or [],
            default_item_type=resolved_context.item_type_key,
        )

        _state_update(
            app,
            current_phase="Montando fila",
            current_category=category_dict["categoria_nome"],
            current_item="-",
            reused_categories=reused_categories,
            refetched_categories=refetched_categories,
        )

        category_items: list[dict[str, str]] = []
        diagnostics: dict[str, Any] = {
            "coletados_brutos": 0,
            "coletados_unicos": 0,
            "duplicados_internos": 0,
            "paginas_visitadas": 0,
            "paginas_repetidas": 0,
            "paginas_sem_ganho": 0,
            "faltantes_estimados": 0,
            "resgatados_do_cache": 0,
            "status_coleta": "cache",
        }
        cache_source = "cache_reutilizado"
        should_persist_category_cache = False

        if verify_mode == "complete":
            _log(app, f"🧪 Verificação completa da categoria: {category_dict['categoria_nome']}")
            live_result = await collect_items_from_category(
                page,
                category_dict,
                control,
                app,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=adapter,
            )
            live_items = list(live_result.get("items", []) or [])
            diagnostics.update(dict(live_result.get("diagnostics", {}) or {}))

            ok_integrity, integrity_reason, live_signature, live_links_count = compare_complete_integrity(
                category_dict,
                categories_cache,
                queue_cache,
                live_items,
            )

            if ok_integrity:
                reused_categories += 1
                _log(
                    app,
                    f"✅ Integridade confirmada: {category_dict['categoria_nome']} | "
                    f"links_count: {live_links_count} | assinatura: {live_signature[:10]}",
                )
                cache_source = "complete_verified"
            else:
                refetched_categories += 1
                _log(
                    app,
                    f"🔄 Integridade mudou ou faltava assinatura: {category_dict['categoria_nome']} | "
                    f"motivo: {integrity_reason} | assinatura nova: {live_signature[:10]}",
                )
                cache_source = "complete_changed"

            category_items = live_items
            should_persist_category_cache = True

        else:
            valid, reason = is_category_cache_valid_normal(
                category_dict,
                categories_cache,
                queue_cache,
            )

            if valid:
                category_items = list(previous_queue_items)
                reused_categories += 1
                diagnostics.update(
                    {
                        "coletados_brutos": len(category_items),
                        "coletados_unicos": len(category_items),
                        "status_coleta": "cache",
                    }
                )
                _log(
                    app,
                    f"♻️ Categoria reaproveitada do cache: {category_dict['categoria_nome']} "
                    f"({len(category_items)} itens)",
                )
            else:
                refetched_categories += 1
                _log(app, f"🔄 Categoria será recatalogada: {category_dict['categoria_nome']} | motivo: {reason}")

                live_result = await collect_items_from_category(
                    page,
                    category_dict,
                    control,
                    app,
                    context=resolved_context,
                    runtime_context=resolved_runtime_context,
                    adapter=adapter,
                )
                category_items = list(live_result.get("items", []) or [])
                diagnostics.update(dict(live_result.get("diagnostics", {}) or {}))
                cache_source = "normal_recatalogada"
                should_persist_category_cache = True

        expected_total = max(0, to_int(category_dict.get("total_esperado", 0), 0))
        if expected_total > 0 and len(category_items) < expected_total and previous_queue_items:
            existing_current_links = {
                _normalize_spaces(dict(item or {}).get("link_produto", ""))
                for item in category_items
                if _normalize_spaces(dict(item or {}).get("link_produto", ""))
            }
            rescue_items: list[dict[str, str]] = []

            for cached_item in previous_queue_items:
                cleaned_cached = adapter.normalize_list_item(
                    cached_item,
                    category_name=category_dict["categoria_nome"],
                    category_url=category_dict["categoria_url"],
                )
                cached_link = cleaned_cached["link_produto"]
                if not cached_link or cached_link in existing_current_links:
                    continue

                existing_current_links.add(cached_link)
                rescue_items.append(cleaned_cached)

                if len(existing_current_links) >= expected_total:
                    break

            if rescue_items:
                category_items.extend(rescue_items)
                diagnostics["resgatados_do_cache"] = len(rescue_items)
                diagnostics["coletados_unicos"] = len(existing_current_links)
                diagnostics["faltantes_estimados"] = max(0, expected_total - len(existing_current_links))
                diagnostics["status_coleta"] = "ok_resgatado" if diagnostics["faltantes_estimados"] <= 0 else "incompleta_resgatada"

                _log(
                    app,
                    "🛟 Resgate orientado por faltantes reais no cache: "
                    f"{category_dict['categoria_nome']} | recuperados: {len(rescue_items)} | "
                    f"coletados: {len(existing_current_links)}/{expected_total}",
                )

        diagnostics["coletados_unicos"] = max(
            len({
                _normalize_spaces(dict(item or {}).get("link_produto", ""))
                for item in category_items
                if _normalize_spaces(dict(item or {}).get("link_produto", ""))
            }),
            to_int(diagnostics.get("coletados_unicos", 0), 0),
        )
        diagnostics["faltantes_estimados"] = max(
            0,
            expected_total - diagnostics["coletados_unicos"],
        ) if expected_total > 0 else 0

        if diagnostics["status_coleta"] == "cache":
            diagnostics["status_coleta"] = "ok" if diagnostics["faltantes_estimados"] <= 0 else "incompleta"

        _log(
            app,
            "🧪 Diagnóstico da categoria: "
            f"{category_dict['categoria_nome']} | "
            f"brutos: {to_int(diagnostics.get('coletados_brutos', 0), 0)} | "
            f"únicos: {to_int(diagnostics.get('coletados_unicos', 0), 0)} | "
            f"duplicados internos: {to_int(diagnostics.get('duplicados_internos', 0), 0)} | "
            f"páginas repetidas: {to_int(diagnostics.get('paginas_repetidas', 0), 0)} | "
            f"faltantes estimados: {to_int(diagnostics.get('faltantes_estimados', 0), 0)}",
        )

        duplicate_samples = diagnostics.get("amostras_links_repetidos", []) or []
        if isinstance(duplicate_samples, list) and duplicate_samples:
            _log(
                app,
                f"   ↳ links repetidos entre páginas: {to_int(diagnostics.get('links_repetidos_entre_paginas', 0), 0)}",
            )

            for sample in duplicate_samples[:10]:
                if not isinstance(sample, Mapping):
                    continue

                duplicate_link = _normalize_spaces(sample.get("link_produto", ""))
                duplicate_pages = sample.get("paginas", []) or []

                pages_text = ", ".join(
                    str(to_int(page_number, 0))
                    for page_number in duplicate_pages
                    if to_int(page_number, 0) > 0
                )

                if duplicate_link and pages_text:
                    _log(
                        app,
                        f"      • {duplicate_link} | páginas: {pages_text}",
                    )

        added_this_category = 0
        new_in_this_category = 0
        existing_in_this_category = 0

        for item in category_items:
            cleaned = adapter.normalize_list_item(
                item,
                category_name=category_dict["categoria_nome"],
                category_url=category_dict["categoria_url"],
            )
            link = cleaned["link_produto"]
            if not link or link in seen_links:
                continue

            seen_links.add(link)
            queue.append(cleaned)
            added_this_category += 1

            if link in existing_products:
                existing_links_detected += 1
                existing_in_this_category += 1
            else:
                new_links_detected += 1
                new_in_this_category += 1

        diagnostics["itens_novos_fila"] = new_in_this_category
        diagnostics["itens_existentes_fila"] = existing_in_this_category

        if should_persist_category_cache:
            saved = save_individual_category_cache(
                categories_cache,
                queue_cache,
                category_dict,
                category_items,
                cache_source,
                context=resolved_context,
                diagnostics=diagnostics,
            )
            categories_cache = saved["categories_cache"]
            queue_cache = saved["queue_cache"]

        _log(app, f"📦 Coletados únicos da categoria: {to_int(diagnostics.get('coletados_unicos', 0), 0)}")
        _log(app, f"📦 Adicionados à fila desta categoria: {added_this_category}")
        _log(
            app,
            f"📦 Separação da fila: novos={new_in_this_category} | existentes={existing_in_this_category}",
        )
        _log(app, f"📦 Itens pendentes acumulados: {len(queue)}")

        _state_update(
            app,
            reused_categories=reused_categories,
            refetched_categories=refetched_categories,
            queue_detected_count=len(queue),
            new_links_detected=new_links_detected,
            existing_links_detected=existing_links_detected,
        )

    _log(app, f"🔎 Total de links detectados para processamento: {len(queue)}")

    return {
        "items": queue,
        "categorias_reutilizadas": reused_categories,
        "categorias_refeitas": refetched_categories,
        "itens_novos_detectados": new_links_detected,
        "itens_existentes_detectados": existing_links_detected,
    }


async def process_queue_details(
    *,
    app: Any,
    control: Any,
    detail_page: Any,
    products_dict: dict[str, dict[str, Any]],
    full_queue: Sequence[Mapping[str, Any]],
    processing_items: Sequence[Mapping[str, Any]],
    base_meta: Mapping[str, Any],
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
    counters_init: Mapping[str, Any] | None = None,
    start_index: int = 0,
) -> dict[str, int]:
    resolved_context = build_context(context)
    adapter = get_adapter(resolved_context)
    resolved_runtime_context = adapter.build_runtime_context(
        resolved_context,
        runtime_context=dict(runtime_context or {}),
    )

    queue_total = len(full_queue)
    local_total = len(processing_items)
    save_every_items = max(1, to_int(base_meta.get("save_every_items", _get_default_save_every_items()), _get_default_save_every_items()))
    save_every_minutes = max(1, to_int(base_meta.get("save_every_minutes", _get_default_save_every_minutes()), _get_default_save_every_minutes()))

    counters = {
        "itens_novos_adicionados": max(0, to_int(dict(counters_init or {}).get("itens_novos_adicionados", 0), 0)),
        "itens_atualizados": max(0, to_int(dict(counters_init or {}).get("itens_atualizados", 0), 0)),
        "itens_sem_mudanca": max(0, to_int(dict(counters_init or {}).get("itens_sem_mudanca", 0), 0)),
    }

    last_save_monotonic = time.monotonic()
    items_since_last_save = 0
    cleaned_full_queue = clean_queue_items(full_queue, default_item_type=resolved_context.item_type_key)
    shared_detail_http_session = requests.Session()

    try:
        for offset, item in enumerate(processing_items, start=1):
            await browser_check_pause_stop(control, app)

            queue_index = start_index + offset
            item_dict = adapter.normalize_list_item(
                item,
                category_name=_normalize_spaces(dict(item).get("categoria_nome", "")),
                category_url=ensure_trailing_slash(dict(item).get("categoria_url", "")),
            )

            _state_update(
                app,
                status="Rodando",
                current_phase="Extraindo detalhes",
                current_category=item_dict.get("categoria_nome", "") or "-",
                current_item=item_dict.get("nome_lista") or item_dict.get("link_produto") or "-",
                saved_count=len(products_dict),
                pending_count=max(0, local_total - offset),
                resume_queue_index=queue_index,
                resume_queue_total=queue_total,
                new_items_added=counters["itens_novos_adicionados"],
                items_updated=counters["itens_atualizados"],
                items_unchanged=counters["itens_sem_mudanca"],
            )

            details = await extract_item_details(
                detail_page,
                item_dict,
                control,
                app,
                context=resolved_context,
                runtime_context=resolved_runtime_context,
                adapter=adapter,
                shared_session=shared_detail_http_session,
            )

            link = details["link_produto"]
            existing = products_dict.get(link)
            final_product = dict(
                merge_existing_product(
                    existing,
                    details,
                    default_item_type=resolved_context.item_type_key,
                )
            )

            if final_product.get("tipo") == "template":
                final_product = ensure_template_image_saved(
                    final_product,
                    context=resolved_context,
                )
            else:
                final_product["imagem_url"] = ""
                final_product["imagem_path"] = ""

            if existing:
                changes = describe_product_changes(
                    existing,
                    final_product,
                    default_item_type=resolved_context.item_type_key,
                )
                if changes:
                    counters["itens_atualizados"] += 1
                    _log(
                        app,
                        f"♻️ Atualizado: {final_product.get('nome_produto', link)} | "
                        f"{', '.join(changes)}",
                    )
                else:
                    counters["itens_sem_mudanca"] += 1
                    _log(app, f"✓ Sem mudança: {final_product.get('nome_produto', link)}")
            else:
                counters["itens_novos_adicionados"] += 1
                _log(app, f"🆕 Novo item: {final_product.get('nome_produto', link)}")

            detail_observation = _normalize_spaces(details.get("observacao", ""))
            final_observation = _normalize_spaces(final_product.get("observacao", ""))

            if detail_observation:
                _log(
                    app,
                    f"🧾 Observação capturada | {final_product.get('nome_produto', link)} | {_truncate_log_value(detail_observation)}",
                )

            if detail_observation and not final_observation:
                _log(app, f"⚠️ Observação sumiu após merge | {link}")

            products_dict[link] = dict(final_product)
            items_since_last_save += 1

            should_save_by_items = items_since_last_save >= save_every_items
            should_save_by_time = (time.monotonic() - last_save_monotonic) >= (save_every_minutes * 60)

            if should_save_by_items or should_save_by_time:
                _persist_catalog_snapshot(
                    app,
                    resolved_context,
                    products_dict,
                    {
                        **dict(base_meta),
                        "status": "em_andamento",
                        "current_phase": "Extraindo detalhes",
                        "ultima_categoria": final_product.get("categoria_nome", item_dict.get("categoria_nome", "-")),
                        "ultimo_item_nome": final_product.get("nome_produto", link),
                        "resume_full_queue_items": cleaned_full_queue,
                        "resume_queue_index": queue_index,
                        "resume_queue_total": queue_total,
                        "itens_novos_adicionados": counters["itens_novos_adicionados"],
                        "itens_atualizados": counters["itens_atualizados"],
                        "itens_sem_mudanca": counters["itens_sem_mudanca"],
                        "run_started_at": _state_snapshot_data(app).get("run_started_at", dict(base_meta).get("run_started_at", "")),
                        "run_finished_at": "",
                    },
                    log_paths=False,
                )
                items_since_last_save = 0
                last_save_monotonic = time.monotonic()

        return counters
    finally:
        if resolved_context.site_key in {"ultrapackv2", "plugintheme"}:
            # Mantém a mesma sessão/cookies para a preparação local de updates no painel.
            session_attribute = "ultrapack_http_session" if resolved_context.site_key == "ultrapackv2" else "plugintheme_http_session"
            previous = getattr(app, session_attribute, None)
            if previous is not None and previous is not shared_detail_http_session:
                with suppress(Exception):
                    previous.close()
            setattr(app, session_attribute, shared_detail_http_session)
            try:
                from app.updates.source_auth import register_source_session
                register_source_session(
                    resolved_context.site_key,
                    shared_detail_http_session,
                    resolved_context.account_key,
                )
            except Exception:
                pass
        else:
            with suppress(Exception):
                shared_detail_http_session.close()


async def execute_continuation(
    app: Any,
    control: Any,
    detail_page: Any,
    products_dict: dict[str, dict[str, Any]],
    run_payload: Mapping[str, Any] | None = None,
    *,
    context: Any = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    resolved_context = build_context(context)
    progress = load_progress_data(resolved_context)
    meta = progress.get("meta", {}) if isinstance(progress, Mapping) else {}
    if not isinstance(meta, Mapping):
        meta = {}

    resume_info = _resolve_resume_info(meta)
    if not resume_info["can_continue"]:
        return None

    full_queue = clean_queue_items(
        resume_info.get("full_queue", []) or meta.get("resume_full_queue_items", []),
        default_item_type=resolved_context.item_type_key,
    )
    queue_total = len(full_queue)
    queue_index = max(0, to_int(resume_info.get("queue_index", 0), 0))

    if not full_queue or queue_index >= queue_total:
        return None

    processing_items = full_queue[queue_index:]
    if not processing_items:
        return None

    resumed_run_mode = _normalize_run_mode(resume_info.get("run_mode", _get_run_mode_full()))
    verify_mode = str(meta.get("verify_mode", _get_default_verify_mode()) or _get_default_verify_mode()).strip().lower()
    scope_mode = str(meta.get("scope_mode", _get_default_scope_mode()) or _get_default_scope_mode()).strip().lower()
    save_every_items = max(1, to_int(meta.get("save_every_items", _get_default_save_every_items()), _get_default_save_every_items()))
    save_every_minutes = max(1, to_int(meta.get("save_every_minutes", _get_default_save_every_minutes()), _get_default_save_every_minutes()))

    _log(
        app,
        f"⏯️ Retomando fila salva | índice: {queue_index}/{queue_total} | fluxo: {_get_run_mode_label(resumed_run_mode)}",
    )

    _state_update(
        app,
        current_phase="Retomando",
        status="Rodando",
        can_continue=True,
        resume_run_mode=resumed_run_mode,
        resume_run_mode_label=_get_run_mode_label(resumed_run_mode),
        resume_queue_index=queue_index,
        resume_queue_total=queue_total,
    )

    details_info = await process_queue_details(
        app=app,
        control=control,
        detail_page=detail_page,
        products_dict=products_dict,
        full_queue=full_queue,
        processing_items=processing_items,
        base_meta={
            "run_mode": resumed_run_mode,
            "modo_teste": _get_test_mode(),
            "verify_mode": verify_mode,
            "scope_mode": scope_mode,
            "save_every_items": save_every_items,
            "save_every_minutes": save_every_minutes,
            "categorias_reutilizadas": meta.get("categorias_reutilizadas", 0),
            "categorias_refeitas": meta.get("categorias_refeitas", 0),
            "queue_detected_count": meta.get("queue_detected_count", queue_total),
            "new_links_detected": meta.get("new_links_detected", 0),
            "existing_links_detected": meta.get("existing_links_detected", queue_total),
            "run_started_at": meta.get("run_started_at", _state_snapshot_data(app).get("run_started_at", "")),
        },
        context=resolved_context,
        runtime_context=runtime_context,
        counters_init={
            "itens_novos_adicionados": meta.get("itens_novos_adicionados", 0),
            "itens_atualizados": meta.get("itens_atualizados", 0),
            "itens_sem_mudanca": meta.get("itens_sem_mudanca", 0),
        },
        start_index=queue_index,
    )

    _persist_catalog_snapshot(
        app,
        resolved_context,
        products_dict,
        {
            "status": "concluido",
            "run_mode": resumed_run_mode,
            "current_phase": "Retomada concluída",
            "modo_teste": _get_test_mode(),
            "verify_mode": verify_mode,
            "scope_mode": scope_mode,
            "save_every_items": save_every_items,
            "save_every_minutes": save_every_minutes,
            "categorias_reutilizadas": meta.get("categorias_reutilizadas", 0),
            "categorias_refeitas": meta.get("categorias_refeitas", 0),
            "queue_detected_count": meta.get("queue_detected_count", queue_total),
            "new_links_detected": meta.get("new_links_detected", 0),
            "existing_links_detected": meta.get("existing_links_detected", queue_total),
            "resume_full_queue_items": [],
            "resume_queue_index": 0,
            "resume_queue_total": 0,
            "itens_novos_adicionados": details_info["itens_novos_adicionados"],
            "itens_atualizados": details_info["itens_atualizados"],
            "itens_sem_mudanca": details_info["itens_sem_mudanca"],
            "run_started_at": meta.get("run_started_at", _state_snapshot_data(app).get("run_started_at", "")),
            "run_finished_at": now_iso(),
        },
        log_paths=True,
    )

    _log(
        app,
        f"🏁 Continuação finalizada | novos adicionados: {details_info['itens_novos_adicionados']} | "
        f"itens atualizados: {details_info['itens_atualizados']} | "
        f"sem mudança: {details_info['itens_sem_mudanca']}",
    )

    return list(products_dict.values())





# ============================================================
# FLUXO PRINCIPAL
# ============================================================


async def execute_flow_async(
    app: Any,
    run_options: Mapping[str, Any] | RunOptions | None,
    run_mode: str | None,
    run_payload: Mapping[str, Any] | None = None,
    *,
    context: Any = None,
) -> list[dict[str, Any]]:
    resolved_context = build_context(
        context or getattr(app, "get_current_context", lambda: None)()
    )
    options = build_run_options(run_options)
    resolved_run_mode = _normalize_run_mode(run_mode)
    payload = dict(run_payload or {})

    if resolved_run_mode == _get_run_mode_primary():
        resolved_run_mode = _get_run_mode_full()

    verify_mode = str(options.verify_mode or _get_default_verify_mode()).strip().lower()
    scope_mode = str(options.scope_mode or _get_default_scope_mode()).strip().lower()
    save_every_items = max(1, int(options.save_every_items or _get_default_save_every_items()))
    save_every_minutes = max(1, int(options.save_every_minutes or _get_default_save_every_minutes()))

    control = getattr(app, "control", None)
    products_dict = dict(load_existing_products_dict(resolved_context))
    total_existing = len(products_dict)

    if total_existing:
        _log(app, f"↺ Catálogo carregado: {total_existing} itens já salvos.")

    _state_update(
        app,
        summary=f"Itens já salvos ao iniciar: {total_existing}",
        saved_count=total_existing,
        pending_count=0,
        running=True,
        status="Rodando",
        run_mode=resolved_run_mode,
        run_mode_label=_get_run_mode_label(resolved_run_mode),
        reused_categories=0,
        refetched_categories=0,
        queue_detected_count=0,
        new_links_detected=0,
        existing_links_detected=0,
        new_items_added=0,
        items_updated=0,
        items_unchanged=0,
        current_phase="Preparando",
        current_run_payload=dict(payload),
    )

    session: BrowserSession | None = None
    latest_base_meta: dict[str, Any] = {
        "run_mode": resolved_run_mode,
        "modo_teste": _get_test_mode(),
        "verify_mode": verify_mode,
        "scope_mode": scope_mode,
        "save_every_items": save_every_items,
        "save_every_minutes": save_every_minutes,
        "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
    }

    try:
        if resolved_context.site_key == "plugintheme":
            _log(app, "PluginTheme: verificando disponibilidade pública via HTTPS")
            operation_page = None
            runtime_context = get_adapter(resolved_context).build_runtime_context(
                resolved_context,
            )
            _log(app, "PluginTheme: catálogo público acessível; login não necessário")
        else:
            _log(app, "Abrindo navegador Playwright")
            session = await open_authenticated_browser_session(
                app,
                control,
                resolved_context,
                create_detail_page=False,
            )
            _log(app, "Navegador Playwright aberto")
            _log(app, "Iniciando autenticação/navegação")
            operation_page = session.page
            runtime_context = get_adapter(resolved_context).build_runtime_context(
                resolved_context,
                runtime_context=session.runtime_context,
            )

        if resolved_context.site_key == "ultrapackv2":
            # Publica a autenticacao logo apos o login; Parar durante a fila nao a perde.
            http_session = requests.Session()
            http_session.trust_env = False
            current_url = _normalize_spaces(getattr(session.page, "url", "") or "")
            cookies = await _get_browser_cookies_from_page(session.page)
            document_cookie = await _get_browser_document_cookie_header(session.page)
            _prepare_authenticated_http_session(
                http_session,
                target_url=current_url or str(session.runtime_context.get("base_url", "")),
                current_url=current_url,
                referer=current_url,
                browser_cookies=cookies,
                document_cookie_header=document_cookie,
                preserve_existing_state=False,
            )
            previous = getattr(app, "ultrapack_http_session", None)
            if previous is not None and previous is not http_session:
                with suppress(Exception):
                    previous.close()
            setattr(app, session_attribute, http_session)
            try:
                from app.updates.source_auth import register_source_session
                register_source_session(
                    resolved_context.site_key,
                    http_session,
                    resolved_context.account_key,
                )
            except Exception:
                pass
            if resolved_context.site_key == "plugintheme":
                _log(
                    app,
                    "🌐 Sessão HTTPS autenticada preparada com os cookies do navegador.",
                )

        if payload.get("resume"):
            resumed = await execute_continuation(
                app,
                control,
                operation_page,
                products_dict,
                payload,
                context=resolved_context,
                runtime_context=runtime_context,
            )
            if resumed is not None:
                return resumed
            _log(app, "↳ Continuação não disponível. Seguindo com novo fluxo.")

        if resolved_run_mode == _get_run_mode_categories_only():
            categories = await collect_categories(
                operation_page,
                control,
                app,
                context=resolved_context,
                runtime_context=runtime_context,
            )
            available_categories = _build_available_categories(categories)
            available_categories = save_available_categories(available_categories, resolved_context)
            _sync_available_categories_state(app, available_categories)
            _state_update(app, current_phase="Categorias atualizadas")

            _persist_catalog_snapshot(
                app,
                resolved_context,
                products_dict,
                {
                    "status": "concluido",
                    "run_mode": _get_run_mode_categories_only(),
                    "current_phase": "Categorias atualizadas",
                    "modo_teste": _get_test_mode(),
                    "verify_mode": verify_mode,
                    "scope_mode": scope_mode,
                    "save_every_items": save_every_items,
                    "save_every_minutes": save_every_minutes,
                    "resume_full_queue_items": [],
                    "resume_queue_index": 0,
                    "resume_queue_total": 0,
                    "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                    "run_finished_at": now_iso(),
                },
                log_paths=True,
            )
            _log(app, f"🏁 Atualização de categorias finalizada | total: {len(available_categories)}")
            return list(products_dict.values())

        force_selected = scope_mode == "selected"
        all_categories, filtered_categories = await load_filtered_categories_online(
            app,
            control,
            operation_page,
            options,
            context=resolved_context,
            runtime_context=runtime_context,
            force_selected=force_selected,
        )

        if not all_categories:
            _persist_catalog_snapshot(
                app,
                resolved_context,
                products_dict,
                {
                    "status": "concluido",
                    "run_mode": resolved_run_mode,
                    "current_phase": "Sem categorias",
                    "modo_teste": _get_test_mode(),
                    "verify_mode": verify_mode,
                    "scope_mode": "selected" if force_selected else scope_mode,
                    "save_every_items": save_every_items,
                    "save_every_minutes": save_every_minutes,
                    "resume_full_queue_items": [],
                    "resume_queue_index": 0,
                    "resume_queue_total": 0,
                    "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                    "run_finished_at": now_iso(),
                },
                log_paths=True,
            )
            return list(products_dict.values())

        if resolved_run_mode in {
            _get_run_mode_full(),
            _get_run_mode_links_only(),
        }:
            _log(
                app,
                f"✅ Categorias após filtro de escopo: {len(filtered_categories)} | "
                f"validação: {verify_mode} | escopo: {'selected' if force_selected else scope_mode}",
            )

            if not filtered_categories:
                _log(app, "⚠️ Nenhuma categoria ficou disponível após aplicar o escopo selecionado.")
                _persist_catalog_snapshot(
                    app,
                    resolved_context,
                    products_dict,
                    {
                        "status": "concluido",
                        "run_mode": resolved_run_mode,
                        "current_phase": "Sem categorias no escopo",
                        "modo_teste": _get_test_mode(),
                        "verify_mode": verify_mode,
                        "scope_mode": "selected" if force_selected else scope_mode,
                        "save_every_items": save_every_items,
                        "save_every_minutes": save_every_minutes,
                        "resume_full_queue_items": [],
                        "resume_queue_index": 0,
                        "resume_queue_total": 0,
                        "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                        "run_finished_at": now_iso(),
                    },
                    log_paths=True,
                )
                return list(products_dict.values())

            if _get_test_mode() and _get_test_max_categories():
                filtered_categories = filtered_categories[:_get_test_max_categories()]
                _log(app, f"🧪 Modo teste ativo: usando só {len(filtered_categories)} categorias")

            queue_info = await build_processing_queue_by_categories(
                app,
                control,
                operation_page,
                filtered_categories,
                products_dict,
                verify_mode,
                context=resolved_context,
                runtime_context=runtime_context,
            )
            queue = queue_info["items"]

            latest_base_meta = {
                "run_mode": resolved_run_mode,
                "modo_teste": _get_test_mode(),
                "verify_mode": verify_mode,
                "scope_mode": "selected" if force_selected else scope_mode,
                "save_every_items": save_every_items,
                "save_every_minutes": save_every_minutes,
                "categorias_reutilizadas": queue_info["categorias_reutilizadas"],
                "categorias_refeitas": queue_info["categorias_refeitas"],
                "queue_detected_count": len(queue),
                "new_links_detected": queue_info["itens_novos_detectados"],
                "existing_links_detected": queue_info["itens_existentes_detectados"],
                "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                "run_finished_at": "",
            }

            if resolved_run_mode == _get_run_mode_links_only():
                _persist_catalog_snapshot(
                    app,
                    resolved_context,
                    products_dict,
                    {
                        **latest_base_meta,
                        "status": "concluido",
                        "current_phase": "Detecção finalizada",
                        "resume_full_queue_items": [],
                        "resume_queue_index": 0,
                        "resume_queue_total": 0,
                        "itens_novos_adicionados": 0,
                        "itens_atualizados": 0,
                        "itens_sem_mudanca": 0,
                        "run_finished_at": now_iso(),
                    },
                    log_paths=True,
                )
                _log(
                    app,
                    f"🏁 Detecção de links finalizada | novos: {queue_info['itens_novos_detectados']} | "
                    f"existentes: {queue_info['itens_existentes_detectados']}"
                )
                return list(products_dict.values())

            details_info = await process_queue_details(
                app=app,
                control=control,
                detail_page=operation_page,
                products_dict=products_dict,
                full_queue=queue,
                processing_items=queue,
                base_meta=latest_base_meta,
                context=resolved_context,
                runtime_context=runtime_context,
                counters_init={
                    "itens_novos_adicionados": 0,
                    "itens_atualizados": 0,
                    "itens_sem_mudanca": 0,
                },
                start_index=0,
            )

            _persist_catalog_snapshot(
                app,
                resolved_context,
                products_dict,
                {
                    **latest_base_meta,
                    "status": "concluido",
                    "current_phase": "Sincronização concluída",
                    "resume_full_queue_items": [],
                    "resume_queue_index": 0,
                    "resume_queue_total": 0,
                    "itens_novos_adicionados": details_info["itens_novos_adicionados"],
                    "itens_atualizados": details_info["itens_atualizados"],
                    "itens_sem_mudanca": details_info["itens_sem_mudanca"],
                    "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                    "run_finished_at": now_iso(),
                },
                log_paths=True,
            )
            _log(
                app,
                f"🏁 Sincronização finalizada | novos: {details_info['itens_novos_adicionados']} | "
                f"atualizados: {details_info['itens_atualizados']} | "
                f"sem mudança: {details_info['itens_sem_mudanca']}",
            )
            return list(products_dict.values())

        if resolved_run_mode == _get_run_mode_existing_review():
            review_items_raw = filter_existing_products_by_scope(products_dict, options.to_dict(), resolved_context)
            review_queue = clean_queue_items(
                [
                    {
                        "tipo": _normalize_spaces(dict(item).get("tipo", resolved_context.item_type_key)) or resolved_context.item_type_key,
                        "categoria_nome": _normalize_spaces(dict(item).get("categoria_nome", "")),
                        "categoria_url": ensure_trailing_slash(dict(item).get("categoria_url", "")),
                        "link_produto": _normalize_spaces(dict(item).get("link_produto", "")),
                        "nome_lista": _normalize_spaces(dict(item).get("nome_produto", "")),
                        "versao_lista": _normalize_spaces(dict(item).get("versao_produto", "")),
                    }
                    for item in review_items_raw
                ],
                default_item_type=resolved_context.item_type_key,
            )

            _log(app, f"🔎 Itens para revisão: {len(review_queue)}")

            latest_base_meta = {
                "run_mode": resolved_run_mode,
                "modo_teste": _get_test_mode(),
                "verify_mode": verify_mode,
                "scope_mode": scope_mode,
                "save_every_items": save_every_items,
                "save_every_minutes": save_every_minutes,
                "categorias_reutilizadas": 0,
                "categorias_refeitas": 0,
                "queue_detected_count": len(review_queue),
                "new_links_detected": 0,
                "existing_links_detected": len(review_queue),
                "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                "run_finished_at": "",
            }

            if not review_queue:
                _persist_catalog_snapshot(
                    app,
                    resolved_context,
                    products_dict,
                    {
                        **latest_base_meta,
                        "status": "concluido",
                        "current_phase": "Sem itens para revisão",
                        "resume_full_queue_items": [],
                        "resume_queue_index": 0,
                        "resume_queue_total": 0,
                        "itens_novos_adicionados": 0,
                        "itens_atualizados": 0,
                        "itens_sem_mudanca": 0,
                        "run_finished_at": now_iso(),
                    },
                    log_paths=True,
                )
                return list(products_dict.values())

            details_info = await process_queue_details(
                app=app,
                control=control,
                detail_page=operation_page,
                products_dict=products_dict,
                full_queue=review_queue,
                processing_items=review_queue,
                base_meta=latest_base_meta,
                context=resolved_context,
                runtime_context=runtime_context,
                counters_init={
                    "itens_novos_adicionados": 0,
                    "itens_atualizados": 0,
                    "itens_sem_mudanca": 0,
                },
                start_index=0,
            )

            _persist_catalog_snapshot(
                app,
                resolved_context,
                products_dict,
                {
                    **latest_base_meta,
                    "status": "concluido",
                    "current_phase": "Revisão concluída",
                    "resume_full_queue_items": [],
                    "resume_queue_index": 0,
                    "resume_queue_total": 0,
                    "itens_novos_adicionados": details_info["itens_novos_adicionados"],
                    "itens_atualizados": details_info["itens_atualizados"],
                    "itens_sem_mudanca": details_info["itens_sem_mudanca"],
                    "run_started_at": _state_snapshot_data(app).get("run_started_at", ""),
                    "run_finished_at": now_iso(),
                },
                log_paths=True,
            )
            _log(
                app,
                f"🏁 Revisão finalizada | atualizados: {details_info['itens_atualizados']} | "
                f"sem mudança: {details_info['itens_sem_mudanca']}",
            )
            return list(products_dict.values())

        _log(app, f"⚠️ Modo de execução sem tratamento específico: {resolved_run_mode}")
        return list(products_dict.values())

    except StopScraper:
        _log(app, "⏹ Processo interrompido pelo usuário.")
        _persist_catalog_snapshot(
            app,
            resolved_context,
            products_dict,
            {
                **latest_base_meta,
                "status": "interrompido",
                "current_phase": _state_snapshot_data(app).get("current_phase", "Interrompido"),
                "run_started_at": _state_snapshot_data(app).get("run_started_at", latest_base_meta.get("run_started_at", "")),
                "run_finished_at": now_iso(),
            },
            log_paths=False,
        )
        _persist_full_logs(app, resolved_context)
        return list(products_dict.values())

    except Exception as error:
        _persist_catalog_snapshot(
            app,
            resolved_context,
            products_dict,
            {
                **latest_base_meta,
                "status": "erro",
                "current_phase": "Erro",
                "run_started_at": _state_snapshot_data(app).get("run_started_at", latest_base_meta.get("run_started_at", "")),
                "run_finished_at": now_iso(),
            },
            log_paths=False,
        )
        _persist_full_logs(app, resolved_context)
        error_message = str(error).strip() or error.__class__.__name__
        raise EngineError(f"Falha no engine: {error_message}") from error

    finally:
        await close_browser_session(session)
        _persist_full_logs(app, resolved_context)


def execute_flow(
    app: Any,
    run_options: Mapping[str, Any] | RunOptions | None,
    run_mode: str | None,
    run_payload: Mapping[str, Any] | None = None,
    *,
    context: Any = None,
) -> list[dict[str, Any]]:
    return asyncio.run(
        execute_flow_async(
            app,
            run_options,
            run_mode,
            run_payload,
            context=context,
        )
    )


# ============================================================
# ALIASES EM PT-BR
# ============================================================

extrair_links_categorias_da_pagina = extract_category_links_from_page
avisar_possivel_categoria_agrupadora = warn_possible_grouped_category
coletar_categorias = collect_categories

coletar_total_itens_na_categoria = collect_total_items_in_category
scroll_fim = scroll_to_page_end
extrair_cards_da_pagina = extract_cards_from_page
coletar_cards_da_pagina = extract_cards_from_page
construir_candidatos_paginas = build_page_candidates
coletar_itens_da_categoria = collect_items_from_category

extrair_detalhes_brutos = extract_raw_details
escolher_nome_final = choose_final_name
extrair_detalhes_do_item = extract_item_details

carregar_categorias_filtradas_online = load_filtered_categories_online
montar_fila_por_categorias = build_processing_queue_by_categories
processar_detalhes_fila = process_queue_details
executar_continuacao = execute_continuation
executar_fluxo_async = execute_flow_async
executar_fluxo = execute_flow


__all__ = [
    "EngineError",
    "extract_category_links_from_page",
    "warn_possible_grouped_category",
    "collect_categories",
    "collect_total_items_in_category",
    "scroll_to_page_end",
    "extract_cards_from_page",
    "build_page_candidates",
    "collect_items_from_category",
    "extract_raw_details",
    "choose_final_name",
    "extract_item_details",
    "load_filtered_categories_online",
    "build_processing_queue_by_categories",
    "process_queue_details",
    "execute_continuation",
    "execute_flow_async",
    "execute_flow",
    "extrair_links_categorias_da_pagina",
    "avisar_possivel_categoria_agrupadora",
    "coletar_categorias",
    "coletar_total_itens_na_categoria",
    "scroll_fim",
    "extrair_cards_da_pagina",
    "coletar_cards_da_pagina",
    "construir_candidatos_paginas",
    "coletar_itens_da_categoria",
    "extrair_detalhes_brutos",
    "escolher_nome_final",
    "extrair_detalhes_do_item",
    "carregar_categorias_filtradas_online",
    "montar_fila_por_categorias",
    "processar_detalhes_fila",
    "executar_continuacao",
    "executar_fluxo_async",
    "executar_fluxo",
]
