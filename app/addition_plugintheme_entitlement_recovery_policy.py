from __future__ import annotations

import re
from contextlib import suppress
from typing import Any, Callable, Mapping

import app.addition_plugintheme_profile_recovery_policy as profile_recovery
import app.integrations.plugintheme_download as plugintheme_download


_INSTALLED = False
_BASE_FIND_ACCESS_TOKEN: Callable[[Any], str] | None = None
_BASE_PROFILE_HTTP_SESSION: Callable[[Any], tuple[Any | None, str]] | None = None
_BASE_ACCESS_ALLOWED: Callable[[object], bool] | None = None

_TOKEN_RE = re.compile(r"^[A-Za-z0-9._~+/=-]{40,}$")
_POSITIVE_VALUES = {"1", "true", "yes", "allowed", "active", "granted", "purchased", "entitled"}
_ENTITLEMENT_KEYS = (
    "canAccess",
    "can_access",
    "hasPurchased",
    "has_purchased",
    "isPurchased",
    "is_purchased",
    "purchased",
    "entitled",
    "isEntitled",
    "is_entitled",
    "hasEntitlement",
    "has_entitlement",
    "bundleAccess",
    "bundle_access",
    "premiumAccess",
    "premium_access",
    "subscriptionAccess",
    "subscription_access",
)
_CONTAINER_KEYS = ("data", "result", "access", "entitlement", "purchase", "subscription", "bundle")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _positive(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return _clean(value).lower() in _POSITIVE_VALUES


def _find_access_token_robust(value: Any) -> str:
    """Accept raw bearer/JWT tokens in addition to JSON-wrapped tokens."""
    if isinstance(value, str):
        raw = value.strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if len(raw) >= 40 and _TOKEN_RE.fullmatch(raw):
            return raw
    if _BASE_FIND_ACCESS_TOKEN is None:
        return ""
    return _BASE_FIND_ACCESS_TOKEN(value)


def _storage_token_from_profile(primary: Any) -> str:
    """Read localStorage and sessionStorage from the renewed PluginTheme profile."""
    try:
        from playwright.sync_api import sync_playwright
        from app.browser import get_plugintheme_profile_dir
    except Exception:
        return ""

    profile_dir = get_plugintheme_profile_dir(profile_recovery._account_key(primary))
    if not profile_dir.exists():
        return ""

    try:
        with sync_playwright() as playwright:
            context = None
            for kwargs in ({"channel": "chrome", "headless": True}, {"headless": True}):
                try:
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        args=["--disable-blink-features=AutomationControlled"],
                        **kwargs,
                    )
                    break
                except Exception:
                    continue
            if context is None:
                return ""
            try:
                page = context.pages[0] if context.pages else context.new_page()
                with suppress(Exception):
                    page.goto(
                        "https://plugintheme.net/pt-BR/account",
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                rows: list[Mapping[str, Any]] = []
                with suppress(Exception):
                    rows = list(
                        page.evaluate(
                            """() => {
                              const out = [];
                              for (const store of [window.localStorage, window.sessionStorage]) {
                                for (let i = 0; i < store.length; i += 1) {
                                  const key = store.key(i);
                                  out.push({key, value: store.getItem(key) || ''});
                                }
                              }
                              return out;
                            }"""
                        )
                        or []
                    )
                for row in rows:
                    if not isinstance(row, Mapping):
                        continue
                    token = _find_access_token_robust(row.get("value"))
                    if token:
                        return token
                return ""
            finally:
                context.close()
    except Exception:
        return ""


def _profile_http_session_robust(primary: Any) -> tuple[Any | None, str]:
    if _BASE_PROFILE_HTTP_SESSION is None:
        return None, "Leitor do perfil PluginTheme indisponível."

    session, detail = _BASE_PROFILE_HTTP_SESSION(primary)
    if session is None:
        return session, detail

    authorization = _clean(getattr(session, "headers", {}).get("Authorization"))
    if authorization:
        return session, detail

    token = _storage_token_from_profile(primary)
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
        detail = (
            f"{_clean(detail)} Token de acesso recuperado do armazenamento autenticado do perfil."
        ).strip()
    return session, detail


def _access_allowed_robust(payload: object) -> bool:
    """Accept only explicit positive purchase/entitlement signals for bundles."""
    if _BASE_ACCESS_ALLOWED is not None and _BASE_ACCESS_ALLOWED(payload):
        return True
    if not isinstance(payload, Mapping):
        return False

    for key in _ENTITLEMENT_KEYS:
        if key in payload and _positive(payload.get(key)):
            return True

    for key in _CONTAINER_KEYS:
        nested = payload.get(key)
        if isinstance(nested, Mapping) and _access_allowed_robust(nested):
            return True
        if key == "access" and _positive(nested):
            return True
    return False


def install_addition_plugintheme_entitlement_recovery_policy() -> None:
    global _INSTALLED, _BASE_FIND_ACCESS_TOKEN, _BASE_PROFILE_HTTP_SESSION, _BASE_ACCESS_ALLOWED
    if _INSTALLED:
        return

    _BASE_FIND_ACCESS_TOKEN = profile_recovery._find_access_token
    _BASE_PROFILE_HTTP_SESSION = profile_recovery._profile_http_session
    _BASE_ACCESS_ALLOWED = plugintheme_download.PluginThemeDownloader.access_allowed

    # The existing profile-recovery downloader resolves these globals at retry
    # time, so this upgrades authentication without replacing queue behavior.
    profile_recovery._find_access_token = _find_access_token_robust
    profile_recovery._profile_http_session = _profile_http_session_robust
    plugintheme_download.PluginThemeDownloader.access_allowed = staticmethod(_access_allowed_robust)

    _INSTALLED = True
