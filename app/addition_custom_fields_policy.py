from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import app.addition_one_click_policy as one_click
import app.new_product_workflow_policy as additions
from app.integrations.woocommerce import metadata_value


_INSTALLED = False
_BASE_CREATE_DRAFT = None

_BLOCKED_OFFICIAL_HOSTS = {
    "ultrapackv2.com",
    "www.ultrapackv2.com",
    "plugintema.com.br",
    "www.plugintema.com.br",
}
_GENERIC_DEVELOPERS = {
    "envato",
    "themeforest",
    "codecanyon",
    "wordpress",
    "wordpress.org",
    "woocommerce",
}


def _clean(value: Any) -> str:
    return " ".join(html_lib.unescape(str(value or "")).split()).strip()


def _host(url: str) -> str:
    try:
        return str(urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def _valid_external_url(url: str) -> bool:
    value = str(url or "").strip()
    if not value.startswith(("https://", "http://")):
        return False
    host = _host(value)
    return bool(host and host not in _BLOCKED_OFFICIAL_HOSTS)


def _fetch_html(url: str, timeout: int = 12) -> str:
    if not str(url or "").startswith(("http://", "https://")):
        return ""
    request = Request(
        str(url),
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(3_000_000)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _official_from_source_html(raw_html: str) -> str:
    text = html_lib.unescape(str(raw_html or "")).replace("\\/", "/")
    patterns = (
        r'https?://(?:www\.)?themeforest\.net/item/[^"\'\s<>]+',
        r'https?://(?:www\.)?codecanyon\.net/item/[^"\'\s<>]+',
        r'https?://wordpress\.org/plugins/[^"\'\s<>]+',
        r'https?://(?:www\.)?woocommerce\.com/products/[^"\'\s<>]+',
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(0).rstrip(".,;)>]")
    return ""


def _official_url(job: Mapping[str, Any]) -> str:
    for key in ("source_official_url", "official_url", "site_oficial"):
        value = str(job.get(key) or "").strip()
        if _valid_external_url(value):
            return value

    source_url = str(job.get("source_product_url") or "").strip()
    if source_url:
        discovered = _official_from_source_html(_fetch_html(source_url))
        if _valid_external_url(discovered):
            return discovered
    return ""


def _strip_tags(value: str) -> str:
    return _clean(re.sub(r"<[^>]+>", " ", str(value or "")))


def _developer_ok(value: str) -> bool:
    cleaned = _clean(value)
    if len(cleaned) < 2 or len(cleaned) > 120:
        return False
    return cleaned.lower() not in _GENERIC_DEVELOPERS


def _json_developer(value: Any) -> str:
    interesting = {"author", "creator", "brand", "seller", "publisher", "manufacturer", "vendor"}
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in interesting:
                if isinstance(nested, Mapping):
                    name = _clean(nested.get("name") or nested.get("legalName"))
                    if _developer_ok(name):
                        return name
                elif isinstance(nested, list):
                    for item in nested:
                        name = _json_developer({"author": item})
                        if name:
                            return name
                else:
                    name = _clean(nested)
                    if _developer_ok(name):
                        return name
        for nested in value.values():
            found = _json_developer(nested)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _json_developer(item)
            if found:
                return found
    return ""


def _developer_from_html(raw_html: str) -> str:
    html = str(raw_html or "")
    if not html:
        return ""

    for script in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        try:
            payload = json.loads(html_lib.unescape(script).strip())
        except Exception:
            continue
        found = _json_developer(payload)
        if found:
            return found

    meta_patterns = (
        r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']author["\']',
    )
    for pattern in meta_patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            value = _clean(match.group(1))
            if _developer_ok(value):
                return value

    # Envato/ThemeForest/CodeCanyon author links and WordPress profile links.
    link_patterns = (
        r'<a[^>]+href=["\'][^"\']*/user/([^/"\'?&#]+)[^"\']*["\'][^>]*>(.*?)</a>',
        r'<a[^>]+href=["\'][^"\']*/profiles/([^/"\'?&#]+)[^"\']*["\'][^>]*>(.*?)</a>',
    )
    for pattern in link_patterns:
        for match in re.finditer(pattern, html, flags=re.I | re.S):
            visible = _strip_tags(match.group(2))
            slug = _clean(match.group(1))
            candidate = visible if _developer_ok(visible) else slug
            if _developer_ok(candidate):
                return candidate

    by_match = re.search(
        r'\bby\s*</?[^>]*>\s*<a[^>]*>(.*?)</a>|\bby\s+<a[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    )
    if by_match:
        candidate = _strip_tags(by_match.group(1) or by_match.group(2) or "")
        if _developer_ok(candidate):
            return candidate
    return ""


def _domain_developer(official_url: str) -> str:
    host = _host(official_url)
    if not host or host in {
        "themeforest.net", "www.themeforest.net",
        "codecanyon.net", "www.codecanyon.net",
        "wordpress.org", "www.wordpress.org",
        "woocommerce.com", "www.woocommerce.com",
    }:
        return ""
    root = host.split(".")[-2] if len(host.split(".")) >= 2 else host
    value = re.sub(r"[-_]", " ", root).strip().title()
    return value if _developer_ok(value) else ""


def _developer(job: Mapping[str, Any], official_url: str) -> str:
    for key in ("desenvolvedor", "developer", "author", "vendor"):
        value = _clean(job.get(key))
        if _developer_ok(value):
            return value

    documents: list[str] = []
    if official_url:
        documents.append(_fetch_html(official_url))
    source_url = str(job.get("source_product_url") or "").strip()
    if source_url and source_url != official_url:
        documents.append(_fetch_html(source_url))

    for document in documents:
        found = _developer_from_html(document)
        if found:
            return found
    return _domain_developer(official_url)


def _apply_custom_fields(job_id: str) -> None:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        return

    official = _official_url(job)
    developer = _developer(job, official)
    meta_data: list[dict[str, str]] = []
    if official:
        meta_data.append({"key": "site_oficial", "value": official})
    if developer:
        meta_data.append({"key": "desenvolvedor", "value": developer})
    if not meta_data:
        one_click._emit(
            job_id,
            "Campos adicionais: não foi possível resolver site oficial/desenvolvedor com segurança; produto mantido sem inventar dados.",
            step="store_fields",
        )
        return

    woo = additions.web._build_store_woocommerce_client()
    additions._wc_request(
        woo,
        "PUT",
        f"/wp-json/wc/v3/products/{product_id}",
        {"meta_data": meta_data},
    )
    fresh = woo.get_product_fresh(product_id)

    if official and str(metadata_value(fresh, "site_oficial") or "").strip() != official:
        raise RuntimeError("WooCommerce não confirmou o campo personalizado site_oficial.")
    if developer and str(metadata_value(fresh, "desenvolvedor") or "").strip() != developer:
        raise RuntimeError("WooCommerce não confirmou o campo personalizado desenvolvedor.")

    fields = []
    if official:
        fields.append(f"site_oficial={official}")
    if developer:
        fields.append(f"desenvolvedor={developer}")
    one_click._emit(
        job_id,
        "Campos personalizados confirmados: " + "; ".join(fields) + ".",
        step="store_fields",
    )


def _create_draft_with_custom_fields(job_id: str, confirmation: str) -> dict[str, Any]:
    result = _BASE_CREATE_DRAFT(job_id, confirmation)
    _apply_custom_fields(job_id)
    result = dict(result or {})
    result["job"] = additions._row(job_id)
    return result


def install_addition_custom_fields_policy() -> None:
    global _INSTALLED, _BASE_CREATE_DRAFT
    if _INSTALLED:
        return
    _BASE_CREATE_DRAFT = additions._create_or_resume_draft
    additions._create_or_resume_draft = _create_draft_with_custom_fields
    _INSTALLED = True
