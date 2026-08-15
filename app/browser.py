from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import time
from typing import Any

from app import settings
from app.models import (
    BrowserSessionData,
    ScraperContext,
    build_context,
    build_runtime_context_dict,
)

try:
    from app.core.exceptions import AuthenticationError, BrowserError, StopScraper
except Exception:  # pragma: no cover
    class StopScraper(Exception):
        pass

    class BrowserError(Exception):
        pass

    class AuthenticationError(BrowserError):
        pass


# ============================================================
# SELECTORS DE AUTENTICAÇÃO
# ============================================================

EMAIL_FIELD_SELECTORS = (
    "input[type='email']",
    "input[name='email']",
    "input[name='log']",
    "input[name='username']",
    "input[name='user_login']",
    "#user_login",
    "#email",
)

PASSWORD_FIELD_SELECTORS = (
    "input[type='password']",
    "input[name='password']",
    "input[name='pwd']",
    "#user_pass",
    "#password",
)

SUBMIT_BUTTON_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    ".login-button",
    ".woocommerce-Button",
    "button.button",
    "input.button",
)

AUTHENTICATED_INDICATOR_SELECTORS = (
    "body.logged-in",
    ".woocommerce-MyAccount-navigation",
    ".woocommerce-MyAccount-content",
    ".woocommerce-account",
    ".dashboard-links",
    ".account-dashboard",
    "a[href*='customer-logout']",
    "a[href*='wp-login.php?action=logout']",
    "a[href*='logout']",
    "a[href*='/account/orders']",
    "a[href*='/account/downloads']",
    "a[href*='/account/edit-account']",
)

PLUGINTHEME_LANGUAGE_POPUP_TEXT = (
    "plugintheme.net Has Been Renewed!",
    "Pick yours below!",
    "Now you can browse our site in your language",
)


class AuthenticationState(str, Enum):
    AUTHENTICATED = "authenticated"
    NOT_AUTHENTICATED = "not_authenticated"
    UNKNOWN = "unknown"


def get_plugintheme_profile_dir(account_key: str) -> Path:
    """Retorna um perfil exclusivo do CrapScraper, sem aceitar travessia de path."""
    safe_account = re.sub(r"[^a-z0-9_-]+", "-", str(account_key or "default").lower()).strip("-")
    return Path(settings.PLUGINTHEME_BROWSER_PROFILES_DIR) / (safe_account or "default")


# ============================================================
# HELPERS INTERNOS
# ============================================================


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _normalize_url_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        url = _normalize_spaces(value)
        if not url or url in seen:
            continue
        seen.add(url)
        result.append(url)

    return result


def _get_default_headless() -> bool:
    return bool(getattr(settings, "HEADLESS", False))


def _get_default_delay() -> float:
    try:
        return max(0.0, float(getattr(settings, "DELAY", 1.4)))
    except Exception:
        return 1.4


def _get_default_timeout() -> int:
    return max(1, _to_int(getattr(settings, "TIMEOUT", 30_000), 30_000))


def _get_default_viewport() -> dict[str, int]:
    raw = getattr(settings, "PLAYWRIGHT_VIEWPORT", None)
    if isinstance(raw, Mapping):
        return {
            "width": max(320, _to_int(raw.get("width", 1440), 1440)),
            "height": max(240, _to_int(raw.get("height", 900), 900)),
        }
    return {"width": 1440, "height": 900}


def _get_default_user_agent() -> str:
    raw = getattr(settings, "PLAYWRIGHT_USER_AGENT", None)
    if raw:
        return str(raw)

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )


def _get_default_launch_args() -> list[str]:
    raw = getattr(settings, "PLAYWRIGHT_LAUNCH_ARGS", None)
    if isinstance(raw, (list, tuple)):
        values = [str(item).strip() for item in raw if str(item).strip()]
        if values:
            return values
    return ["--disable-blink-features=AutomationControlled"]


def _get_default_locale() -> str | None:
    value = getattr(settings, "PLAYWRIGHT_LOCALE", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_default_timezone_id() -> str | None:
    value = getattr(settings, "PLAYWRIGHT_TIMEZONE_ID", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_default_color_scheme() -> str | None:
    value = getattr(settings, "PLAYWRIGHT_COLOR_SCHEME", None)
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"light", "dark", "no-preference"}:
        return text
    return None


def _resolve_context(
    context: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
) -> ScraperContext:
    return build_context(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )


def _resolve_runtime_context(
    context: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = build_runtime_context_dict(
        _resolve_context(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
    )

    if isinstance(runtime_context, Mapping):
        resolved.update(dict(runtime_context))

    return resolved


def _log(app: Any, message: str) -> None:
    if app is None:
        return

    logger = getattr(app, "log", None)
    if callable(logger):
        try:
            logger(str(message))
        except Exception:
            pass


def _state_update(app: Any, **kwargs: Any) -> None:
    if app is None:
        return

    state = getattr(app, "state", None)
    if state is None:
        return

    updater = getattr(state, "update", None)
    if callable(updater):
        try:
            updater(**kwargs)
        except Exception:
            pass


def _control_should_stop(control: Any) -> bool:
    checker = getattr(control, "should_stop", None)
    return bool(checker()) if callable(checker) else False


def _control_is_paused(control: Any) -> bool:
    checker = getattr(control, "is_paused", None)
    return bool(checker()) if callable(checker) else False


def _control_is_running(control: Any) -> bool:
    checker = getattr(control, "is_running", None)
    return bool(checker()) if callable(checker) else False


def _control_pause(control: Any) -> None:
    action = getattr(control, "pause", None)
    if callable(action):
        with suppress(Exception):
            action()


# ============================================================
# WRAPPER OPERACIONAL DA SESSÃO
# ============================================================


@dataclass(slots=True)
class BrowserSession:
    data: BrowserSessionData
    detail_page: Any | None = None
    closed: bool = False

    @property
    def context(self) -> ScraperContext | None:
        return self.data.context

    @property
    def runtime_context(self) -> dict[str, Any]:
        return self.data.runtime_context

    @property
    def playwright(self) -> Any:
        return self.data.playwright

    @playwright.setter
    def playwright(self, value: Any) -> None:
        self.data.playwright = value

    @property
    def browser(self) -> Any:
        return self.data.browser

    @browser.setter
    def browser(self, value: Any) -> None:
        self.data.browser = value

    @property
    def browser_context(self) -> Any:
        return self.data.browser_context

    @browser_context.setter
    def browser_context(self, value: Any) -> None:
        self.data.browser_context = value

    @property
    def page(self) -> Any:
        return self.data.page

    @page.setter
    def page(self, value: Any) -> None:
        self.data.page = value

    @property
    def headless(self) -> bool:
        return self.data.headless

    @headless.setter
    def headless(self, value: bool) -> None:
        self.data.headless = bool(value)

    @property
    def default_timeout(self) -> int:
        return self.data.timeout_ms

    @default_timeout.setter
    def default_timeout(self, value: int) -> None:
        self.data.timeout_ms = max(1, _to_int(value, self.data.timeout_ms))

    @property
    def default_delay(self) -> float:
        return max(0.0, float(getattr(self.data, "default_delay_seconds", _get_default_delay())))

    @default_delay.setter
    def default_delay(self, value: float) -> None:
        self.data.default_delay_seconds = max(0.0, float(value))

    @property
    def started_at(self) -> str:
        return self.data.started_at

    def is_open(self) -> bool:
        return not self.closed and self.browser is not None and self.page is not None

    def get_page(self, *, detail: bool = False) -> Any:
        if detail and self.detail_page is not None:
            return self.detail_page
        return self.page

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.data.to_public_dict()
        payload["has_detail_page"] = self.detail_page is not None
        payload["closed"] = self.closed
        return payload

    def set_default_timeout_all(self, timeout: int | None = None) -> int:
        resolved_timeout = max(1, _to_int(timeout, self.default_timeout))
        self.default_timeout = resolved_timeout

        with suppress(Exception):
            self.browser_context.set_default_timeout(resolved_timeout)
        with suppress(Exception):
            self.browser_context.set_default_navigation_timeout(resolved_timeout)
        with suppress(Exception):
            self.page.set_default_timeout(resolved_timeout)
        with suppress(Exception):
            self.page.set_default_navigation_timeout(resolved_timeout)

        if self.detail_page is not None:
            with suppress(Exception):
                self.detail_page.set_default_timeout(resolved_timeout)
            with suppress(Exception):
                self.detail_page.set_default_navigation_timeout(resolved_timeout)

        return resolved_timeout

    async def wait(
        self,
        seconds: float | None = None,
        *,
        control: Any = None,
        app: Any = None,
    ) -> None:
        await controlled_sleep(
            self.default_delay if seconds is None else seconds,
            control=control,
            app=app,
        )

    async def new_page(self, *, as_detail_page: bool = False) -> Any:
        page = await self.browser_context.new_page()

        with suppress(Exception):
            page.set_default_timeout(self.default_timeout)
        with suppress(Exception):
            page.set_default_navigation_timeout(self.default_timeout)

        if as_detail_page:
            self.detail_page = page

        return page

    async def goto(
        self,
        url: str,
        *,
        control: Any = None,
        app: Any = None,
        timeout: int | None = None,
        wait_until: str = "domcontentloaded",
        delay_seconds: float | None = None,
        detail: bool = False,
    ) -> Any:
        target_page = self.get_page(detail=detail)
        return await safe_goto(
            target_page,
            url,
            control=control,
            app=app,
            timeout=timeout if timeout is not None else self.default_timeout,
            wait_until=wait_until,
            delay_seconds=self.default_delay if delay_seconds is None else delay_seconds,
        )

    async def close(self) -> None:
        if self.closed:
            return

        self.closed = True

        with suppress(Exception):
            if self.detail_page is not None:
                await self.detail_page.close()

        with suppress(Exception):
            if self.page is not None:
                await self.page.close()

        with suppress(Exception):
            if self.browser_context is not None:
                await self.browser_context.close()

        with suppress(Exception):
            if self.browser is not None:
                await self.browser.close()

        with suppress(Exception):
            if self.playwright is not None:
                await self.playwright.stop()

        self.detail_page = None
        self.page = None
        self.browser_context = None
        self.browser = None
        self.playwright = None


# ============================================================
# HELPERS DE PAGE / SELECTOR
# ============================================================


async def query_first(page: Any, selectors: Iterable[str]) -> Any | None:
    for selector in selectors:
        normalized = _normalize_spaces(selector)
        if not normalized:
            continue

        try:
            element = await page.query_selector(normalized)
            if element is not None:
                return element
        except Exception:
            continue

    return None


async def query_first_visible(page: Any, selectors: Iterable[str]) -> Any | None:
    for selector in selectors:
        normalized = _normalize_spaces(selector)
        if not normalized:
            continue

        try:
            element = await page.query_selector(normalized)
            if element is None:
                continue

            with suppress(Exception):
                if not await element.is_visible():
                    continue

            return element
        except Exception:
            continue

    return None


async def has_any_selector(page: Any, selectors: Iterable[str], *, visible_only: bool = False) -> bool:
    for selector in selectors:
        normalized = _normalize_spaces(selector)
        if not normalized:
            continue

        try:
            element = await page.query_selector(normalized)
            if element is None:
                continue

            if visible_only:
                with suppress(Exception):
                    if await element.is_visible():
                        return True
                continue

            return True
        except Exception:
            continue

    return False


async def wait_for_any_selector(
    page: Any,
    selectors: Iterable[str],
    *,
    timeout: int | None = None,
    state: str = "visible",
) -> str | None:
    resolved_timeout = max(1, _to_int(timeout, _get_default_timeout()))

    for selector in selectors:
        normalized = _normalize_spaces(selector)
        if not normalized:
            continue

        try:
            await page.wait_for_selector(
                normalized,
                timeout=resolved_timeout,
                state=state,
            )
            return normalized
        except Exception:
            continue

    return None


async def get_visible_text(page: Any, selector: str, default: str = "") -> str:
    normalized = _normalize_spaces(selector)
    if not normalized:
        return default

    try:
        element = await query_first_visible(page, (normalized,))
        if element is None:
            return default

        text = await element.inner_text()
        return _normalize_spaces(text) or default
    except Exception:
        return default


async def get_attribute(page: Any, selector: str, attribute_name: str, default: str = "") -> str:
    normalized = _normalize_spaces(selector)
    attr_name = _normalize_spaces(attribute_name)

    if not normalized or not attr_name:
        return default

    try:
        element = await query_first(page, (normalized,))
        if element is None:
            return default

        value = await element.get_attribute(attr_name)
        return _normalize_spaces(value) or default
    except Exception:
        return default


# ============================================================
# CONTROLE / ESPERA / NAVEGAÇÃO
# ============================================================


async def check_pause_stop(
    control: Any = None,
    app: Any = None,
    *,
    poll_interval: float = 0.4,
) -> None:
    if _control_should_stop(control):
        raise StopScraper()

    while _control_is_paused(control):
        _state_update(app, status="Pausado")
        await asyncio.sleep(max(0.05, float(poll_interval)))
        if _control_should_stop(control):
            raise StopScraper()

    if _control_is_running(control):
        _state_update(app, status="Rodando")


async def controlled_sleep(
    seconds: float | None = None,
    control: Any = None,
    app: Any = None,
    *,
    check_interval: float = 0.2,
) -> None:
    remaining = max(0.0, float(_get_default_delay() if seconds is None else seconds))
    step = max(0.05, float(check_interval))

    while remaining > 0:
        await check_pause_stop(control, app, poll_interval=step)
        current_step = min(step, remaining)
        await asyncio.sleep(current_step)
        remaining -= current_step


async def safe_goto(
    page: Any,
    url: str,
    *,
    control: Any = None,
    app: Any = None,
    timeout: int | None = None,
    wait_until: str = "domcontentloaded",
    delay_seconds: float | None = None,
) -> Any:
    if page is None:
        raise BrowserError("Page inválida para navegação.")

    target_url = _normalize_spaces(url)
    if not target_url:
        raise BrowserError("URL vazia para navegação.")

    await check_pause_stop(control, app)

    resolved_timeout = max(1, _to_int(timeout, _get_default_timeout()))

    try:
        response = await page.goto(
            target_url,
            wait_until=str(wait_until or "domcontentloaded"),
            timeout=resolved_timeout,
        )
    except StopScraper:
        raise
    except Exception as error:
        raise BrowserError(f"Falha ao navegar para: {target_url}") from error

    await controlled_sleep(
        _get_default_delay() if delay_seconds is None else delay_seconds,
        control=control,
        app=app,
    )

    return response


# ============================================================
# LOGIN
# ============================================================


def _resolve_login_urls(runtime_context: Mapping[str, Any]) -> list[str]:
    return _normalize_url_list(runtime_context.get("login_urls", []))


def _resolve_login_credentials(runtime_context: Mapping[str, Any]) -> tuple[str, str]:
    email = str(runtime_context.get("login_email", "") or "").strip()
    password = str(runtime_context.get("login_password", "") or "").strip()
    return email, password


async def _plugintheme_popup_visible(page: Any) -> bool:
    for text in PLUGINTHEME_LANGUAGE_POPUP_TEXT:
        with suppress(Exception):
            locator = page.get_by_text(text, exact=False).first
            if await locator.count() > 0 and await locator.is_visible():
                return True

    with suppress(Exception):
        dialog = page.locator("[role='dialog'], [aria-modal='true']").first
        if await dialog.count() > 0 and await dialog.is_visible():
            text = _normalize_spaces(await dialog.inner_text()).lower()
            if (
                "renewed" in text
                or "pick yours below" in text
                or "português" in text
                or "english" in text
            ):
                return True

    return False


async def _plugintheme_click_popup_close(page: Any) -> bool:
    """Fecha somente o modal de idioma; não confunde botões Close da página."""
    selectors = (
        "button[aria-label='Close']",
        "div:has(h2:has-text('plugintheme.net Has Been Renewed!')) > button[aria-label='Close']",
        "div.relative.rounded-2xl button[aria-label='Close']",
        "[role='dialog'] button[aria-label='Close']",
        "[aria-modal='true'] button[aria-label='Close']",
        "[role='dialog'] button:has-text('Close')",
        "[aria-modal='true'] button:has-text('Close')",
    )
    for selector in selectors:
        with suppress(Exception):
            button = page.locator(selector).first
            if await button.count() > 0 and await button.is_visible():
                try:
                    await button.click(timeout=2_000, force=True)
                except Exception:
                    await page.evaluate("el => el.click()", button)
                return True
    # Fallback estrutural: sobe do título conhecido até o primeiro contêiner
    # que possua o botão de fechar. Evita depender das classes Tailwind.
    with suppress(Exception):
        title = page.get_by_text("plugintheme.net Has Been Renewed!", exact=True).first
        if await title.count() > 0 and await title.is_visible():
            button = title.locator(
                "xpath=ancestor::div[.//button[@aria-label='Close']][1]//button[@aria-label='Close']"
            ).first
            if await button.count() > 0 and await button.is_visible():
                await button.click(timeout=2_000)
                return True
    # Último fallback independente da árvore/classe: o site fornece um botão
    # de fechamento acessível e único nesse popup.
    with suppress(Exception):
        clicked = await page.evaluate("""
            () => {
              const title = [...document.querySelectorAll('h1,h2,h3,p')]
                .find(el => (el.textContent || '').includes('plugintheme.net Has Been Renewed!'));
              const scope = title?.parentElement?.parentElement || document;
              const button = scope.querySelector('button[aria-label="Close"]')
                || document.querySelector('button[aria-label="Close"]');
              if (!button) return false;
              button.click();
              return true;
            }
        """)
        if clicked:
            return True
    return False


async def _plugintheme_close_popup_with_escape(
    page: Any,
    *,
    control: Any = None,
    app: Any = None,
    max_attempts: int = 20,
) -> bool:
    await controlled_sleep(0.5, control=control, app=app)

    for attempt in range(1, max_attempts + 1):
        visible = await _plugintheme_popup_visible(page)
        if not visible:
            _log(app, f"✓ Popup não está visível na tentativa {attempt}.")
            return True

        _log(app, f"→ Popup visível. Fechamento tentativa {attempt}/{max_attempts}")

        if await _plugintheme_click_popup_close(page):
            await controlled_sleep(0.4, control=control, app=app)
            continue

        with suppress(Exception):
            body = await page.query_selector("body")
            if body is not None:
                await body.click(timeout=1000, position={"x": 30, "y": 30})

        with suppress(Exception):
            await page.keyboard.press("Escape")

        await controlled_sleep(0.4, control=control, app=app)

    hidden = not await _plugintheme_popup_visible(page)
    if hidden:
        _log(app, "✓ Popup sumiu após sequência de ESC.")
    else:
        _log(app, "✗ Popup ainda visível após todas as tentativas de ESC.")
    return hidden


async def _plugintheme_fill_login_form_like_user(
    page: Any,
    *,
    email: str,
    password: str,
) -> bool:
    email_field = await query_first_visible(page, EMAIL_FIELD_SELECTORS)
    if email_field is None:
        return False

    password_field = await query_first_visible(page, PASSWORD_FIELD_SELECTORS)
    if password_field is None:
        return False

    with suppress(Exception):
        await email_field.click()
    with suppress(Exception):
        await email_field.fill("")
    try:
        await email_field.type(email, delay=35)
    except Exception:
        with suppress(Exception):
            await email_field.fill(email)

    with suppress(Exception):
        await password_field.click()
    with suppress(Exception):
        await password_field.fill("")
    try:
        await password_field.type(password, delay=35)
    except Exception:
        with suppress(Exception):
            await password_field.fill(password)

    return True


async def _plugintheme_human_verification_state(page: Any) -> tuple[bool, bool]:
    """Retorna (desafio_presente, token_liberado) sem tentar resolver CAPTCHA."""
    token_ready = False
    with suppress(Exception):
        token_ready = bool(await page.evaluate("""
            () => [...document.querySelectorAll(
              'input[name="cf-turnstile-response"], textarea[name="cf-turnstile-response"],'
              + 'input[name="g-recaptcha-response"], textarea[name="g-recaptcha-response"]'
            )].some(el => (el.value || '').trim().length > 10)
        """))

    selectors = (
        "iframe[src*='challenges.cloudflare.com']",
        "iframe[title*='challenge' i]",
        "iframe[title*='human' i]",
        ".cf-turnstile",
        "[data-sitekey]",
        "input[name='cf-turnstile-response']",
        "textarea[name='g-recaptcha-response']",
    )
    for selector in selectors:
        with suppress(Exception):
            locator = page.locator(selector).first
            if await locator.count() > 0:
                return True, token_ready

    for text in ("Sou humano", "Verify you are human", "I'm human", "I am human"):
        with suppress(Exception):
            locator = page.get_by_text(text, exact=False).first
            if await locator.count() > 0 and await locator.is_visible():
                return True, token_ready
    return False, token_ready


async def _plugintheme_wait_for_human_verification(
    page: Any, *, control: Any = None, app: Any = None,
) -> bool:
    present, ready = await _plugintheme_human_verification_state(page)
    if not present or ready:
        return True

    _log(app, "🛡️ PluginTheme exige verificação humana.")
    _log(app, "Resolva 'Sou humano' no navegador e depois clique em Continuar no painel.")
    _control_pause(control)
    while _control_is_paused(control):
        await asyncio.sleep(0.5)
        if _control_should_stop(control):
            raise StopScraper()

    # O token pode ser preenchido alguns instantes após o clique visual.
    for _attempt in range(20):
        present, ready = await _plugintheme_human_verification_state(page)
        if ready or not present:
            _log(app, "✓ Verificação humana confirmada; enviando login.")
            return True
        await asyncio.sleep(0.5)

    _log(app, "✗ A verificação humana não liberou um token válido.")
    return False


async def _plugintheme_tab_and_enter_submit(
    page: Any,
    *,
    control: Any = None,
    app: Any = None,
) -> bool:
    await controlled_sleep(0.3, control=control, app=app)

    _log(app, "→ TAB 1")
    with suppress(Exception):
        await page.keyboard.press("Tab")
    await controlled_sleep(0.25, control=control, app=app)

    _log(app, "→ TAB 2")
    with suppress(Exception):
        await page.keyboard.press("Tab")
    await controlled_sleep(0.25, control=control, app=app)

    _log(app, "→ TAB 3")
    with suppress(Exception):
        await page.keyboard.press("Tab")
    await controlled_sleep(0.25, control=control, app=app)

    _log(app, "→ ENTER")

    submitted = False

    try:
        async with page.expect_navigation(wait_until="domcontentloaded", timeout=12_000):
            await page.keyboard.press("Enter")
        submitted = True
    except Exception:
        with suppress(Exception):
            await page.keyboard.press("Enter")
            submitted = True

    with suppress(Exception):
        await page.wait_for_load_state("domcontentloaded", timeout=8_000)

    with suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=8_000)

    await controlled_sleep(1.2, control=control, app=app)
    return submitted


async def _plugintheme_wait_login_success(
    page: Any,
    *,
    control: Any = None,
    app: Any = None,
    attempted_url: str = "",
    timeout_ms: int = 20_000,
) -> bool:
    end = asyncio.get_running_loop().time() + (timeout_ms / 1000)

    while asyncio.get_running_loop().time() < end:
        await check_pause_stop(control, app)

        if await is_authenticated(page):
            return True

        await asyncio.sleep(0.5)

    return False


async def _plugintheme_attempt_login_patch(
    page: Any,
    *,
    email: str,
    password: str,
    control: Any = None,
    app: Any = None,
    attempted_url: str = "",
) -> bool:
    _log(app, "↳ PluginTheme: autenticando pelo formulário visível")

    await controlled_sleep(3.0, control=control, app=app)

    popup_closed = await _plugintheme_close_popup_with_escape(
        page,
        control=control,
        app=app,
        max_attempts=4,
    )
    if not popup_closed:
        _log(app, "↳ Popup do PluginTheme ainda visível após ESC.")

    form_filled = await _plugintheme_fill_login_form_like_user(
        page,
        email=email,
        password=password,
    )
    if not form_filled:
        _log(app, "↳ Formulário do PluginTheme não foi encontrado para o patch.")
        return False

    if not await _plugintheme_wait_for_human_verification(
        page, control=control, app=app,
    ):
        return False

    submitted = await submit_login_form(page)
    if not submitted:
        _log(app, "↳ Botão de login não respondeu; tentando Enter no campo de senha.")
        password_field = await query_first_visible(page, PASSWORD_FIELD_SELECTORS)
        if password_field is not None:
            with suppress(Exception):
                await password_field.press("Enter")
                submitted = True
    if not submitted:
        _log(app, "↳ Não foi possível submeter o formulário do PluginTheme.")
        return False

    success = await _plugintheme_wait_login_success(
        page,
        control=control,
        app=app,
        attempted_url=attempted_url,
        timeout_ms=20_000,
    )

    if not success:
        _log(app, "↳ Patch do PluginTheme executou, mas o login não confirmou.")

    return success


async def has_login_form(page: Any) -> bool:
    email_field = await query_first_visible(page, EMAIL_FIELD_SELECTORS)
    if email_field is None:
        return False

    password_field = await query_first_visible(page, PASSWORD_FIELD_SELECTORS)
    return password_field is not None


async def is_authenticated(page: Any) -> bool:
    return (await determine_authentication_state(page)) is AuthenticationState.AUTHENTICATED


async def determine_authentication_state(page: Any) -> AuthenticationState:
    """Classifica a sessão usando sinais do DOM; URL sozinha nunca confirma login."""
    if page is None:
        return AuthenticationState.UNKNOWN
    if await has_any_selector(page, AUTHENTICATED_INDICATOR_SELECTORS, visible_only=False):
        return AuthenticationState.AUTHENTICATED
    if await has_login_form(page):
        return AuthenticationState.NOT_AUTHENTICATED
    current_url = str(getattr(page, "url", "") or "").lower()
    if "/auth/login" in current_url:
        return AuthenticationState.NOT_AUTHENTICATED
    return AuthenticationState.UNKNOWN


async def dismiss_login_popup_if_needed(
    page: Any,
    *,
    control: Any = None,
    app: Any = None,
) -> bool:
    with suppress(Exception):
        await page.keyboard.press("Escape")

    await controlled_sleep(0.4, control=control, app=app)

    selectors = (
        "button[aria-label='Fechar']",
        "button[aria-label*='Fechar']",
        "button[aria-label='Close']",
        "button[aria-label*='Close']",
        "button[title='Fechar']",
        "button[title*='Fechar']",
        ".modal button",
        ".popup button",
        ".wd-popup button",
        ".mfp-container button",
        ".mfp-close",
        ".popup-close",
        ".modal-close",
        "[role='dialog'] button",
        "[aria-modal='true'] button",
    )

    for selector in selectors:
        buttons = []
        with suppress(Exception):
            buttons = await page.query_selector_all(selector)

        for button in buttons or []:
            text = ""
            aria_label = ""
            title_text = ""
            class_name = ""

            with suppress(Exception):
                text = _normalize_spaces(await button.inner_text()).lower()

            with suppress(Exception):
                aria_label = _normalize_spaces(await button.get_attribute("aria-label")).lower()

            with suppress(Exception):
                title_text = _normalize_spaces(await button.get_attribute("title")).lower()

            with suppress(Exception):
                class_name = _normalize_spaces(await button.get_attribute("class")).lower()

            combined = " ".join(
                part for part in (text, aria_label, title_text, class_name) if part
            ).strip()

            is_close_button = (
                combined in {"×", "x"}
                or any(token in combined for token in ("close", "fechar", "dismiss"))
                or "lucide-x" in combined
            )

            if not is_close_button:
                continue

            clicked = False

            with suppress(Exception):
                await button.scroll_into_view_if_needed()

            with suppress(Exception):
                await button.click(timeout=2000, force=True)
                clicked = True

            if not clicked:
                with suppress(Exception):
                    await page.evaluate("(el) => el.click()", button)
                    clicked = True

            if clicked:
                await controlled_sleep(0.6, control=control, app=app)
                return True

    return False


async def fill_login_form(
    page: Any,
    *,
    email: str,
    password: str,
) -> bool:
    email_field = await query_first_visible(page, EMAIL_FIELD_SELECTORS)
    if email_field is None:
        return False

    password_field = await query_first_visible(page, PASSWORD_FIELD_SELECTORS)
    if password_field is None:
        return False

    await email_field.fill(email)
    await password_field.fill(password)
    return True


async def submit_login_form(page: Any) -> bool:
    button = await query_first_visible(page, SUBMIT_BUTTON_SELECTORS)
    if button is not None:
        with suppress(Exception):
            await button.scroll_into_view_if_needed()

        with suppress(Exception):
            await button.click(timeout=3000, force=True)
            return True

        with suppress(Exception):
            await page.evaluate("(el) => el.click()", button)
            return True

    password_field = await query_first_visible(page, PASSWORD_FIELD_SELECTORS)
    if password_field is not None:
        with suppress(Exception):
            await password_field.press("Enter")
            return True

    return False


async def wait_login_settle(
    page: Any,
    *,
    control: Any = None,
    app: Any = None,
) -> None:
    with suppress(Exception):
        await page.wait_for_load_state("domcontentloaded", timeout=8_000)

    with suppress(Exception):
        await page.wait_for_load_state("networkidle", timeout=5_000)

    await controlled_sleep(2.0, control=control, app=app)


async def did_login_succeed(page: Any, *, attempted_url: str = "") -> bool:
    del attempted_url  # mantido por compatibilidade com chamadas existentes
    return (await determine_authentication_state(page)) is AuthenticationState.AUTHENTICATED


async def attempt_login(
    page: Any = None,
    control: Any = None,
    app: Any = None,
    *,
    session: BrowserSession | None = None,
    context: ScraperContext | Mapping[str, Any] | None = None,
    runtime_context: Mapping[str, Any] | None = None,
    timeout: int | None = None,
    delay_seconds: float | None = None,
) -> bool:
    target_page = page
    if target_page is None and session is not None:
        target_page = session.page

    if target_page is None:
        _log(app, "⚠️ Não foi possível tentar login: page não foi informada.")
        return False

    session_context = session.context if session is not None else None
    session_runtime_context = session.runtime_context if session is not None else None

    resolved_context = _resolve_context(context or session_context)
    resolved_runtime_context = _resolve_runtime_context(
        context=resolved_context,
        runtime_context=runtime_context or session_runtime_context,
    )

    login_urls = _resolve_login_urls(resolved_runtime_context)
    login_email, login_password = _resolve_login_credentials(resolved_runtime_context)
    site_key = str(getattr(resolved_context, "site_key", "") or "").strip().lower()

    env_email_var = str(resolved_runtime_context.get("env_email_var", "") or "").strip()
    env_password_var = str(resolved_runtime_context.get("env_password_var", "") or "").strip()
    resolved_timeout = max(1, _to_int(timeout, _get_default_timeout()))
    resolved_delay = _get_default_delay() if delay_seconds is None else max(0.0, float(delay_seconds))

    if not login_urls:
        _log(app, "⚠️ Nenhuma URL de login foi definida para o contexto atual.")
        return False

    if not login_email or not login_password:
        # Mesmo sem credenciais automáticas, deixe o navegador pronto para o
        # login manual. No PluginTheme isso também remove o seletor de idioma
        # que bloqueia todos os controles da página.
        if site_key == "plugintheme" and login_urls:
            with suppress(Exception):
                await safe_goto(
                    target_page, login_urls[0], control=control, app=app,
                    timeout=resolved_timeout, delay_seconds=resolved_delay,
                )
                await _plugintheme_close_popup_with_escape(
                    target_page, control=control, app=app, max_attempts=4,
                )
        details = []
        if env_email_var:
            details.append(f"email: {env_email_var}")
        if env_password_var:
            details.append(f"senha: {env_password_var}")

        suffix = f" Variáveis esperadas: {', '.join(details)}." if details else ""
        _log(app, f"⚠️ Credenciais não configuradas para o contexto atual.{suffix}")
        return False

    for login_url in login_urls:
        try:
            await safe_goto(
                target_page,
                login_url,
                control=control,
                app=app,
                timeout=resolved_timeout,
                delay_seconds=resolved_delay,
            )

            if await is_authenticated(target_page):
                _log(app, f"✅ Sessão já autenticada em: {login_url}")
                return True

            if site_key == "plugintheme":
                patched = await _plugintheme_attempt_login_patch(
                    target_page,
                    email=login_email,
                    password=login_password,
                    control=control,
                    app=app,
                    attempted_url=login_url,
                )
                if patched:
                    _log(app, f"✅ Login concluído em: {login_url}")
                    return True

                challenge_present, challenge_ready = (
                    await _plugintheme_human_verification_state(target_page)
                )
                if challenge_present and not challenge_ready:
                    _log(
                        app,
                        "↳ Verificação humana ainda pendente; o formulário não será reenviado.",
                    )
                    return False

                # Uma tentativa sem desafio foi suficiente. Não cai no fluxo
                # genérico, não repete submit e não percorre outras URLs.
                _log(app, "PluginTheme: autenticação não confirmada; aguardando renovação manual")
                return False

                _log(
                    app,
                    f"↳ Patch do PluginTheme não confirmou em: {login_url}; tentando fluxo padrão."
                )

            await dismiss_login_popup_if_needed(
                target_page,
                control=control,
                app=app,
            )
            await controlled_sleep(0.6, control=control, app=app)

            if await is_authenticated(target_page):
                _log(app, f"✅ Sessão já autenticada em: {login_url}")
                return True

            if not await has_login_form(target_page):
                await dismiss_login_popup_if_needed(
                    target_page,
                    control=control,
                    app=app,
                )
                await controlled_sleep(0.4, control=control, app=app)

            if not await has_login_form(target_page):
                _log(app, f"↳ Formulário não encontrado em: {login_url}")
                continue

            _log(app, f"✅ Formulário encontrado em: {login_url}")

            form_filled = await fill_login_form(
                target_page,
                email=login_email,
                password=login_password,
            )
            if not form_filled:
                continue

            await dismiss_login_popup_if_needed(
                target_page,
                control=control,
                app=app,
            )
            await controlled_sleep(0.4, control=control, app=app)

            submitted = await submit_login_form(target_page)
            if not submitted:
                _log(app, f"↳ Não foi possível submeter o formulário em: {login_url}")
                continue

            await wait_login_settle(target_page, control=control, app=app)

            current_url = str(getattr(target_page, "url", "") or "").strip().lower()

            if site_key == "plugintheme":
                if "/auth/login" not in current_url and "/account" in current_url:
                    _log(app, f"✅ Login concluído em: {login_url}")
                    return True

            if await did_login_succeed(target_page, attempted_url=login_url):
                _log(app, f"✅ Login concluído em: {login_url}")
                return True

        except StopScraper:
            raise
        except Exception as error:
            _log(app, f"↳ Falhou em {login_url}: {str(error)[:120]}")

    return False


# ============================================================
# SESSÃO PLAYWRIGHT
# ============================================================


async def create_browser_session(
    context: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    headless: bool | None = None,
    create_detail_page: bool = True,
    app: Any = None,
) -> BrowserSession:
    from playwright.async_api import async_playwright

    resolved_context = _resolve_context(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
    )
    runtime_context = _resolve_runtime_context(resolved_context)

    resolved_headless = _get_default_headless() if headless is None else bool(headless)
    resolved_timeout = _get_default_timeout()
    resolved_delay = _get_default_delay()
    resolved_viewport = _get_default_viewport()
    resolved_user_agent = _get_default_user_agent()
    resolved_launch_args = _get_default_launch_args()
    resolved_locale = _get_default_locale()
    resolved_timezone_id = _get_default_timezone_id()
    resolved_color_scheme = _get_default_color_scheme()

    playwright = browser = browser_context = page = detail_page = None

    try:
        playwright = await async_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "headless": resolved_headless,
            "args": resolved_launch_args,
        }

        context_kwargs: dict[str, Any] = {
            "user_agent": resolved_user_agent,
            "viewport": resolved_viewport,
        }

        if resolved_locale:
            context_kwargs["locale"] = resolved_locale
        if resolved_timezone_id:
            context_kwargs["timezone_id"] = resolved_timezone_id
        if resolved_color_scheme:
            context_kwargs["color_scheme"] = resolved_color_scheme

        if resolved_context.site_key == "plugintheme":
            # Cloudflare deve ser concluído legitimamente no perfil dedicado.
            # Não aplicamos flags de ocultação/alteração de automação neste site.
            resolved_launch_args = tuple(
                arg for arg in resolved_launch_args
                if "AutomationControlled" not in str(arg)
            )
            launch_kwargs["args"] = resolved_launch_args
            with suppress(Exception):
                from app.integrations.plugintheme_manual_session import find_chrome_executable
                launch_kwargs["executable_path"] = str(find_chrome_executable())
            profile_dir = get_plugintheme_profile_dir(resolved_context.account_key)
            profile_dir.mkdir(parents=True, exist_ok=True)
            _log(app, f"PluginTheme: abrindo perfil persistente da conta {resolved_context.account_key}")
            browser_context = await playwright.chromium.launch_persistent_context(
                str(profile_dir),
                **launch_kwargs,
                **context_kwargs,
            )
            browser = browser_context.browser
            pages = list(browser_context.pages)
            page = pages[0] if pages else await browser_context.new_page()
        else:
            browser = await playwright.chromium.launch(**launch_kwargs)
            browser_context = await browser.new_context(**context_kwargs)
            page = await browser_context.new_page()

        if create_detail_page:
            detail_page = await browser_context.new_page()

        session_data = BrowserSessionData.build(
            resolved_context,
            headless=resolved_headless,
            timeout_ms=resolved_timeout,
            runtime_context=runtime_context,
        )
        session_data.viewport = dict(resolved_viewport)
        session_data.user_agent = resolved_user_agent
        session_data.launch_args = tuple(resolved_launch_args)
        session_data.locale = resolved_locale
        session_data.timezone_id = resolved_timezone_id
        session_data.color_scheme = resolved_color_scheme
        session_data.playwright = playwright
        session_data.browser = browser
        session_data.browser_context = browser_context
        session_data.page = page

        session = BrowserSession(
            data=session_data,
            detail_page=detail_page,
        )
        session.default_delay = resolved_delay
        session.set_default_timeout_all(resolved_timeout)

        _log(
            app,
            "🌐 Sessão Playwright aberta | "
            f"{resolved_context.site_key} | "
            f"{resolved_context.item_type_key} | "
            f"{resolved_context.account_key} | "
            f"slot={resolved_context.slot_name}",
        )

        return session

    except Exception:
        with suppress(Exception):
            if detail_page is not None:
                await detail_page.close()
        with suppress(Exception):
            if page is not None:
                await page.close()
        with suppress(Exception):
            if browser_context is not None:
                await browser_context.close()
        with suppress(Exception):
            if browser is not None:
                await browser.close()
        with suppress(Exception):
            if playwright is not None:
                await playwright.stop()
        raise


async def close_browser_session(session: BrowserSession | None) -> None:
    if session is None:
        return
    await session.close()


async def open_authenticated_browser_session(
    app: Any,
    control: Any,
    context: ScraperContext | Mapping[str, Any] | None = None,
    *,
    site_key: str | None = None,
    item_type_key: str | None = None,
    account_key: str | None = None,
    slot_name: str | None = None,
    headless: bool | None = None,
    allow_manual_login: bool = True,
    create_detail_page: bool = True,
) -> BrowserSession:
    session = await create_browser_session(
        context,
        site_key=site_key,
        item_type_key=item_type_key,
        account_key=account_key,
        slot_name=slot_name,
        headless=headless,
        create_detail_page=create_detail_page,
        app=app,
    )

    base_url = str(session.runtime_context.get("base_url", "") or "").strip()
    if base_url:
        _log(app, f"🔑 Acessando {base_url}...")
        await session.goto(base_url, control=control, app=app)

    if session.context.site_key == "plugintheme":
        _log(app, "PluginTheme: verificando sessão existente")
        auth_state = await determine_authentication_state(session.page)
        if auth_state is AuthenticationState.AUTHENTICATED:
            _log(app, "PluginTheme: sessão autenticada reutilizada")
            _log(app, "PluginTheme: login não necessário")
            return session
        _log(app, "PluginTheme: autenticação necessária")
        _log(app, "↳ PluginTheme: removendo seletor de idioma antes do login")
        await _plugintheme_close_popup_with_escape(
            session.page, control=control, app=app, max_attempts=6,
        )

    _log(app, "🔑 Tentando login...")

    logged_in = await attempt_login(
        page=session.page,
        control=control,
        app=app,
        session=session,
        context=session.context,
        runtime_context=session.runtime_context,
        timeout=session.default_timeout,
        delay_seconds=session.default_delay,
    )

    if not logged_in and allow_manual_login:
        _log(
            app,
            "⚠️ Autenticação manual necessária. Conclua o login na janela do PluginTheme; a confirmação será detectada automaticamente.",
        )
        _control_pause(control)
        deadline = time.monotonic() + 300
        manual_confirmed = False
        while time.monotonic() < deadline:
            if _control_should_stop(control):
                raise StopScraper()
            if session.page.is_closed():
                raise AuthenticationError(
                    "A janela de autenticação do PluginTheme foi fechada antes da confirmação."
                )
            if await did_login_succeed(
                session.page,
                attempted_url=str((session.runtime_context.get("login_urls") or [""])[0]),
            ):
                manual_confirmed = True
                break
            await asyncio.sleep(1.0)
        pause_event = getattr(control, "pause_event", None)
        if pause_event is not None:
            pause_event.clear()
        if not manual_confirmed:
            await session.close()
            raise AuthenticationError(
                "Tempo esgotado aguardando a autenticação manual do PluginTheme."
            )

    elif not logged_in:
        raise AuthenticationError("Falha no login automático.")

    await session.wait(2.0, control=control, app=app)

    try:
        current_url = str(session.page.url or "")
    except Exception:
        current_url = ""

    if current_url:
        _log(app, f"🌍 URL após login: {current_url}")

    return session


# ============================================================
# ALIASES EM PT-BR
# ============================================================

SessaoNavegador = BrowserSession

checar_pause_stop = check_pause_stop
aguardar = controlled_sleep

consultar_primeiro = query_first
consultar_primeiro_visivel = query_first_visible
existe_algum_seletor = has_any_selector
aguardar_algum_seletor = wait_for_any_selector
obter_texto_visivel = get_visible_text
obter_atributo = get_attribute

tentar_login = attempt_login
navegar_seguro = safe_goto

criar_sessao_navegador = create_browser_session
fechar_sessao_navegador = close_browser_session
abrir_contexto_logado = open_authenticated_browser_session


__all__ = [
    "EMAIL_FIELD_SELECTORS",
    "PASSWORD_FIELD_SELECTORS",
    "SUBMIT_BUTTON_SELECTORS",
    "AUTHENTICATED_INDICATOR_SELECTORS",
    "AuthenticationState",
    "determine_authentication_state",
    "get_plugintheme_profile_dir",
    "BrowserSession",
    "SessaoNavegador",
    "query_first",
    "query_first_visible",
    "has_any_selector",
    "wait_for_any_selector",
    "get_visible_text",
    "get_attribute",
    "check_pause_stop",
    "controlled_sleep",
    "safe_goto",
    "has_login_form",
    "is_authenticated",
    "fill_login_form",
    "submit_login_form",
    "wait_login_settle",
    "did_login_succeed",
    "attempt_login",
    "create_browser_session",
    "close_browser_session",
    "open_authenticated_browser_session",
    "checar_pause_stop",
    "aguardar",
    "consultar_primeiro",
    "consultar_primeiro_visivel",
    "existe_algum_seletor",
    "aguardar_algum_seletor",
    "obter_texto_visivel",
    "obter_atributo",
    "tentar_login",
    "navegar_seguro",
    "criar_sessao_navegador",
    "fechar_sessao_navegador",
    "abrir_contexto_logado",
]
