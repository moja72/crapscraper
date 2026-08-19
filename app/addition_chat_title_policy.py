from __future__ import annotations

import re
from typing import Any

import app.addition_real_chat_url_policy as real_url
import app.addition_unique_chat_marker_policy as unique


_INSTALLED = False
_ORIGINAL_RENAME = None


def _click_rename_menu(page: Any, desired: str) -> bool:
    try:
        page.bring_to_front()
        page.wait_for_timeout(200)
    except Exception:
        pass

    selectors = (
        "header button[data-testid*='conversation' i]",
        "header button[aria-label*='conversation' i]",
        "header button[aria-label*='more' i]",
        "header button[aria-label*='mais' i]",
        "button[data-testid*='conversation-options' i]",
        "button[aria-label*='conversation options' i]",
        "button[aria-label*='opções da conversa' i]",
    )
    for selector in selectors:
        try:
            buttons = page.locator(selector)
            for index in range(buttons.count() - 1, -1, -1):
                button = buttons.nth(index)
                if not (button.is_visible() and button.is_enabled()):
                    continue
                button.click(timeout=1200)
                page.wait_for_timeout(150)
                rename_item = page.get_by_text(re.compile(r"^(Renomear|Rename)$", re.I)).last
                if not rename_item.count() or not rename_item.is_visible():
                    continue
                rename_item.click(timeout=1200)
                page.wait_for_timeout(150)
                fields = page.locator("input:visible")
                if not fields.count():
                    continue
                field = fields.last
                field.fill(desired, timeout=1500)
                field.press("Enter")
                page.wait_for_timeout(250)
                return True
        except Exception:
            continue
    return False


def _rename_chat(page: Any, desired: str) -> bool:
    if not desired or not real_url._is_real_conversation_url(real_url._page_url(page)):
        return False
    if callable(_ORIGINAL_RENAME):
        try:
            if _ORIGINAL_RENAME(page, desired):
                return True
        except Exception:
            pass
    return _click_rename_menu(page, desired)


def install_addition_chat_title_policy() -> None:
    global _INSTALLED, _ORIGINAL_RENAME
    if _INSTALLED:
        return
    _ORIGINAL_RENAME = unique._best_effort_name_chat
    unique._best_effort_name_chat = _rename_chat
    _INSTALLED = True
