from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from app import settings
import app.web as web
import app.chatgpt_browser_assist as chatgpt
import app.addition_one_click_policy as one_click

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_AUTOMATIC_CHATGPT: Callable[[str], None] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "addition_chatgpt_assist.js"
_CHATGPT_AUTOMATION_LOCK = threading.RLock()
_CHATGPT_PROJECT_URL = "https://chatgpt.com/g/g-p-6a852af976708191937e4a92648e2095/project"
_CHATGPT_AUTOMATION_PROFILE_DIR = Path(settings.DATA_DIR) / "browser_profiles" / "chatgpt_automatic"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return html
    block = f"\n<script data-addition-chatgpt-assist>\n{script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _clear_stale_automation_profile_locks() -> None:
    _CHATGPT_AUTOMATION_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = _CHATGPT_AUTOMATION_PROFILE_DIR / name
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
        except OSError:
            pass


def _patched_automatic_chatgpt(job_id: str) -> None:
    base = _BASE_AUTOMATIC_CHATGPT or one_click._automatic_chatgpt
    with _CHATGPT_AUTOMATION_LOCK:
        original_profile = chatgpt._PROFILE_DIR
        original_default_url = chatgpt._DEFAULT_URL
        _CHATGPT_AUTOMATION_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # O modo automático usa um perfil exclusivo. Assim uma janela deixada aberta
        # pelo modo assistido não bloqueia launch_persistent_context do Playwright.
        chatgpt._PROFILE_DIR = _CHATGPT_AUTOMATION_PROFILE_DIR
        chatgpt._DEFAULT_URL = _CHATGPT_PROJECT_URL
        try:
            chatgpt._save_config({"conversation_url": _CHATGPT_PROJECT_URL})
        except Exception:
            pass

        try:
            try:
                return base(job_id)
            except Exception as error:
                message = str(error or "")
                retryable = (
                    "target page, context or browser has been closed" in message.lower()
                    or "processsingleton" in message.lower()
                    or "user data directory is already in use" in message.lower()
                )
                if not retryable:
                    raise

                one_click._emit(
                    job_id,
                    "O perfil automático do ChatGPT estava preso por uma sessão anterior. Limpando o bloqueio e tentando novamente…",
                    step="chatgpt",
                    progress=9,
                )
                _clear_stale_automation_profile_locks()
                return base(job_id)
        finally:
            # O fallback assistido continua usando seu perfil próprio, evitando
            # concorrência com o perfil controlado pelo Playwright.
            chatgpt._PROFILE_DIR = original_profile
            chatgpt._DEFAULT_URL = original_default_url


def install_addition_chatgpt_assist_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_AUTOMATIC_CHATGPT
    if _INSTALLED:
        return
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _BASE_AUTOMATIC_CHATGPT = one_click._automatic_chatgpt
    one_click._automatic_chatgpt = _patched_automatic_chatgpt
    _INSTALLED = True
