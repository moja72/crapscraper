from __future__ import annotations

import time
from typing import Any

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat

_INSTALLED = False


def _editable(locator: Any) -> bool:
    """Return True only for a composer that can actually receive a prompt.

    ChatGPT can keep a visible disabled textarea in the DOM while the previous
    turn is finishing/hydrating. Treating that node as the composer makes
    Playwright wait 15 seconds on a click that can never succeed.
    """
    try:
        if not locator.is_visible():
            return False
    except Exception:
        return False
    try:
        disabled = locator.get_attribute("disabled")
        aria_disabled = str(locator.get_attribute("aria-disabled") or "").strip().lower()
        readonly = locator.get_attribute("readonly")
        contenteditable = str(locator.get_attribute("contenteditable") or "").strip().lower()
        tag = str(locator.evaluate("el => el.tagName.toLowerCase()") or "").strip().lower()
        if disabled is not None or readonly is not None or aria_disabled == "true":
            return False
        if tag in {"textarea", "input"}:
            return bool(locator.is_enabled() and locator.is_editable())
        if contenteditable == "true":
            return True
        return bool(locator.is_enabled() and locator.is_editable())
    except Exception:
        return False


def writable_composer(page: Any, timeout_ms: int = 30000):
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000)
    while time.monotonic() < deadline:
        for root in compat._roots(page):
            for selector in compat._COMPOSER_SELECTORS:
                try:
                    locator = root.locator(selector)
                    count = min(locator.count(), 8)
                except Exception:
                    continue
                for index in range(count):
                    item = locator.nth(index)
                    try:
                        if not _editable(item):
                            continue
                        box = item.bounding_box()
                        if box and box.get("width", 0) >= 180 and box.get("height", 0) >= 20:
                            return item
                    except Exception:
                        continue
        time.sleep(0.25)
    return None


def wait_until_chat_ready(page: Any, timeout_ms: int = 45000):
    """Wait until ChatGPT exposes a visible, enabled and editable composer."""
    composer = writable_composer(page, timeout_ms)
    if composer is not None:
        return composer
    diagnostic = ""
    try:
        diagnostic = compat._diagnostic(page, "composer_remained_disabled")
    except Exception:
        pass
    suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
    raise legacy.ChatGPTPlaywrightError(
        "O ChatGPT manteve o campo de mensagem desabilitado após a resposta anterior. "
        "A execução foi interrompida antes de enviar o próximo prompt." + suffix
    )


def fill_and_submit(page: Any, prompt: str, timeout_ms: int = 45000) -> None:
    """Resolve a fresh writable composer, fill it and submit exactly once."""
    composer = wait_until_chat_ready(page, timeout_ms)
    try:
        composer.click(timeout=5000)
    except Exception:
        try:
            composer.focus(timeout=5000)
        except Exception:
            pass

    try:
        composer.fill(prompt, timeout=10000)
    except Exception:
        # React can replace the composer node between discovery and fill. Resolve
        # a fresh writable node once instead of retrying a stale disabled locator.
        composer = wait_until_chat_ready(page, 15000)
        try:
            composer.click(timeout=5000)
        except Exception:
            composer.focus(timeout=5000)
        composer.fill(prompt, timeout=10000)

    try:
        composer.press("Enter", timeout=5000)
        return
    except Exception:
        pass

    for selector in (
        "button[data-testid='send-button']",
        "button[aria-label*='Enviar' i]",
        "button[aria-label*='Send' i]",
    ):
        try:
            button = page.locator(selector).first
            if button.count() and button.is_visible() and button.is_enabled():
                button.click(timeout=5000)
                return
        except Exception:
            continue
    raise legacy.ChatGPTPlaywrightError("Não foi possível enviar o prompt ao ChatGPT após preencher o compositor.")


def _submit_content(page: Any, prompt: str) -> None:
    fill_and_submit(page, prompt, 45000)


def _submit_image(page: Any, prompt: str) -> None:
    # Image starts immediately after description in the same conversation. Give
    # ChatGPT enough time to release the composer from the previous response.
    fill_and_submit(page, prompt, 60000)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    compat.composer = writable_composer
    legacy._composer = writable_composer

    # Patch both prompt entry points. chatgpt_playwright_image imported _composer
    # by value, so changing legacy._composer alone would not fix that module.
    from app.additions import chatgpt_content_response_runtime as content_runtime
    from app.additions import chatgpt_playwright_image as image_runtime

    content_runtime._submit = _submit_content
    image_runtime._composer = writable_composer
    image_runtime._submit_image_prompt = _submit_image
    _INSTALLED = True


__all__ = [
    "fill_and_submit",
    "install",
    "wait_until_chat_ready",
    "writable_composer",
]
