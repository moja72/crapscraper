from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.additions import chatgpt_playwright as legacy

_INSTALLED = False

_COMPOSER_SELECTORS = (
    "#prompt-textarea",
    "div#prompt-textarea[contenteditable='true']",
    "textarea[data-testid='prompt-textarea']",
    "div[data-testid='prompt-textarea'][contenteditable='true']",
    "div.ProseMirror[contenteditable='true']",
    "div[data-lexical-editor='true'][contenteditable='true']",
    "main form div[contenteditable='true'][role='textbox']",
    "main form div[contenteditable='true']",
    "main form textarea",
    "textarea[placeholder*='Message' i]",
    "textarea[placeholder*='Ask' i]",
    "textarea[placeholder*='Pergunte' i]",
    "div[contenteditable='true'][aria-label*='Message' i]",
    "div[contenteditable='true'][aria-label*='Pergunte' i]",
    "div[contenteditable='true'][role='textbox']",
)

_SIGNED_IN_SELECTORS = (
    "button[data-testid*='profile']",
    "button[data-testid*='account']",
    "button[aria-label*='Profile' i]",
    "button[aria-label*='Conta' i]",
    "a[href^='/c/']",
    "a[href*='/g/']",
    "nav",
)

_AUTH_WALL_TOKENS = (
    "log in",
    "sign up",
    "entrar",
    "criar conta",
    "verifying you are human",
    "just a moment",
    "verify you are human",
    "cloudflare",
)


def _truthy(value: str | None, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "sim"}


def _profile_score(path: Path) -> tuple[int, float]:
    score = 0
    newest = 0.0
    candidates = (
        path / "Default" / "Network" / "Cookies",
        path / "Default" / "Cookies",
        path / "Default" / "Preferences",
        path / "Local State",
    )
    for item in candidates:
        try:
            if item.is_file() and item.stat().st_size > 0:
                score += 1
                newest = max(newest, item.stat().st_mtime)
        except OSError:
            pass
    return score, newest


def profile_dir() -> Path:
    explicit = os.getenv("SCRAPER_CHATGPT_PROFILE_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    root = legacy._data_dir() / "browser_profiles"
    old_profile = root / "chatgpt"
    new_profile = root / "chatgpt_automation"
    old_score = _profile_score(old_profile)
    new_score = _profile_score(new_profile)

    # A implementação legada já utilizava browser_profiles/chatgpt. Reaproveitar
    # esse perfil evita perder a sessão autenticada ao migrar para Playwright.
    if old_score[0] > 0 and old_score >= new_score:
        return old_profile.resolve()
    if new_score[0] > 0:
        return new_profile.resolve()
    return old_profile.resolve()


def _browser_candidates() -> list[str]:
    values: list[str] = []
    explicit = os.getenv("SCRAPER_CHATGPT_BROWSER_PATH", "").strip()
    if explicit:
        values.append(explicit)
    if sys.platform == "win32":
        local = os.getenv("LOCALAPPDATA", "")
        pf = os.getenv("ProgramFiles", r"C:\Program Files")
        pfx86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
        values.extend(
            [
                str(Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                str(Path(pfx86) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                str(Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe") if local else "",
                str(Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                str(Path(pfx86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                str(Path(local) / "Programs" / "Opera" / "opera.exe") if local else "",
                str(Path(local) / "Programs" / "Opera GX" / "opera.exe") if local else "",
            ]
        )
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser", "msedge", "opera"):
        found = shutil.which(name)
        if found:
            values.append(found)
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if not item or item in seen:
            continue
        seen.add(item)
        if Path(item).exists() or shutil.which(item):
            result.append(item)
    return result


@contextmanager
def browser(headless: bool | None = None):
    sync_playwright = legacy._load_playwright()
    profile = profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    use_headless = _truthy(os.getenv("SCRAPER_CHATGPT_HEADLESS"), True) if headless is None else bool(headless)
    playwright = sync_playwright().start()
    context = None
    try:
        kwargs: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": use_headless,
            "viewport": {"width": 1600, "height": 1000},
            "device_scale_factor": 1.5,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "accept_downloads": True,
            "args": ["--disable-blink-features=AutomationControlled"],
            "ignore_default_args": ["--enable-automation"],
        }
        candidates = _browser_candidates()
        if candidates:
            kwargs["executable_path"] = candidates[0]
        context = playwright.chromium.launch_persistent_context(**kwargs)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(15000)
        yield page
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass


def _roots(page):
    yield page
    for frame in list(getattr(page, "frames", []) or []):
        if frame is getattr(page, "main_frame", None):
            continue
        yield frame


def composer(page, timeout_ms: int = 5000):
    deadline = time.monotonic() + max(0.5, timeout_ms / 1000)
    while time.monotonic() < deadline:
        for root in _roots(page):
            for selector in _COMPOSER_SELECTORS:
                try:
                    locator = root.locator(selector)
                    count = min(locator.count(), 8)
                except Exception:
                    continue
                for index in range(count):
                    item = locator.nth(index)
                    try:
                        if not item.is_visible():
                            continue
                        box = item.bounding_box()
                        if box and box.get("width", 0) >= 180 and box.get("height", 0) >= 20:
                            return item
                    except Exception:
                        continue
        time.sleep(0.2)
    return None


def _body_text(page) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=3000) or "")
    except Exception:
        return ""


def _looks_like_auth_wall(page) -> bool:
    text = _body_text(page).casefold()
    return any(token in text for token in _AUTH_WALL_TOKENS)


def _signed_in_evidence(page) -> bool:
    if composer(page, 1200) is not None:
        return True
    for root in _roots(page):
        for selector in _SIGNED_IN_SELECTORS:
            try:
                item = root.locator(selector).first
                if item.count() and item.is_visible():
                    return True
            except Exception:
                continue
    try:
        cookies = page.context.cookies("https://chatgpt.com/")
    except Exception:
        cookies = []
    for cookie in cookies or []:
        name = str(cookie.get("name") or "").casefold()
        if any(token in name for token in ("session", "auth", "puid")):
            return True
    return False


def _diagnostic(page, reason: str) -> str:
    root = legacy._data_dir() / "chatgpt_diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = root / f"chatgpt-{stamp}"
    try:
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True, timeout=15000)
    except Exception:
        pass
    payload = {
        "reason": reason,
        "url": str(getattr(page, "url", "") or ""),
        "title": "",
        "profile_dir": str(profile_dir()),
        "project": legacy.project_name(),
        "body_excerpt": _body_text(page)[:6000],
        "composer_selectors": list(_COMPOSER_SELECTORS),
    }
    try:
        payload["title"] = page.title()
    except Exception:
        pass
    json_path = base.with_suffix(".json")
    try:
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return str(root)
    return str(json_path)


def ensure_authenticated(page) -> None:
    if _signed_in_evidence(page):
        return
    diagnostic = _diagnostic(page, "authentication_not_confirmed")
    if _looks_like_auth_wall(page):
        raise legacy.ChatGPTPlaywrightError(
            "Sessão ChatGPT não autenticada. Execute: python -m app.additions.chatgpt_playwright_compat bootstrap "
            f"(diagnóstico: {diagnostic})"
        )
    raise legacy.ChatGPTPlaywrightError(
        "A sessão do ChatGPT não pôde ser confirmada. Faça o bootstrap do perfil persistente. "
        f"Diagnóstico salvo em {diagnostic}."
    )


def _open_sidebar(page) -> None:
    selectors = (
        "button[aria-label*='sidebar' i]",
        "button[aria-label*='barra lateral' i]",
        "button[data-testid*='sidebar']",
        "button[aria-label*='Open sidebar' i]",
    )
    for selector in selectors:
        try:
            item = page.locator(selector).first
            if item.count() and item.is_visible():
                item.click()
                page.wait_for_timeout(600)
                return
        except Exception:
            continue


def _project_locator(page):
    name = legacy.project_name().strip()
    candidates = (
        page.get_by_text(name, exact=True),
        page.locator("a[href]").filter(has_text=name),
        page.locator("button").filter(has_text=name),
        page.locator("[role='link']").filter(has_text=name),
    )
    for candidate in candidates:
        try:
            count = min(candidate.count(), 20)
        except Exception:
            continue
        for index in range(count):
            item = candidate.nth(index)
            try:
                if item.is_visible():
                    return item
            except Exception:
                continue
    return None


def _dismiss_common_dialogs(page) -> None:
    patterns = (
        re.compile(r"^(aceitar|accept|continue|continuar)$", re.I),
        re.compile(r"^(agora não|not now)$", re.I),
    )
    for pattern in patterns:
        for role in ("button", "link"):
            try:
                item = page.get_by_role(role, name=pattern).first
                if item.count() and item.is_visible():
                    item.click(timeout=1500)
                    page.wait_for_timeout(300)
            except Exception:
                pass


def _try_new_chat(page) -> bool:
    patterns = (
        re.compile(r"novo chat", re.I),
        re.compile(r"new chat", re.I),
        re.compile(r"iniciar.*chat", re.I),
        re.compile(r"start.*chat", re.I),
    )
    for role in ("button", "link"):
        for pattern in patterns:
            try:
                item = page.get_by_role(role, name=pattern).first
                if item.count() and item.is_visible():
                    item.click()
                    page.wait_for_timeout(900)
                    if composer(page, 5000) is not None:
                        return True
            except Exception:
                continue
    return False


def open_project(page) -> None:
    state = legacy._read_state()
    saved = str(state.get("project_url") or "").strip()
    if saved.startswith("https://chatgpt.com/"):
        try:
            page.goto(saved, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            _dismiss_common_dialogs(page)
            ensure_authenticated(page)
            if composer(page, 6000) is not None or _try_new_chat(page):
                return
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass

    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    _dismiss_common_dialogs(page)
    ensure_authenticated(page)
    _open_sidebar(page)
    locator = _project_locator(page)
    if locator is None:
        diagnostic = _diagnostic(page, "project_not_found")
        raise legacy.ChatGPTPlaywrightError(
            f"Projeto {legacy.project_name()} não encontrado no ChatGPT. Diagnóstico salvo em {diagnostic}."
        )
    locator.click()
    page.wait_for_timeout(1200)
    _dismiss_common_dialogs(page)
    if composer(page, 7000) is None and not _try_new_chat(page):
        diagnostic = _diagnostic(page, "project_composer_not_found")
        raise legacy.ChatGPTPlaywrightError(
            f"Projeto {legacy.project_name()} abriu, mas o campo de mensagem não foi localizado. Diagnóstico salvo em {diagnostic}."
        )
    if str(page.url).startswith("https://chatgpt.com/"):
        legacy._update_state(
            project_url=page.url,
            project_name=legacy.project_name(),
            profile_dir=str(profile_dir()),
            bootstrap_ok=True,
            bootstrap_at=int(time.time()),
        )


def open_job_conversation(page, job_id: str) -> None:
    item = legacy._job_state(job_id)
    conversation = str(item.get("conversation_url") or "").strip()
    if conversation.startswith("https://chatgpt.com/"):
        try:
            page.goto(conversation, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1000)
            _dismiss_common_dialogs(page)
            ensure_authenticated(page)
            if composer(page, 6000) is not None:
                return
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass
    open_project(page)


def bootstrap() -> dict[str, Any]:
    with legacy._LOCK, browser(headless=False) as page:
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        print("\nChatGPT aberto no perfil persistente do CrapScraper:")
        print(str(profile_dir()))
        print("Faça login, se necessário, e pressione ENTER neste CMD.\n")
        input()
        _dismiss_common_dialogs(page)
        ensure_authenticated(page)
        try:
            open_project(page)
        except legacy.ChatGPTPlaywrightError as error:
            print(f"\n{error}\n")
            print(f"Abra manualmente o projeto {legacy.project_name()} na janela e pressione ENTER aqui.")
            input()
            if composer(page, 7000) is None and not _try_new_chat(page):
                diagnostic = _diagnostic(page, "manual_project_composer_not_found")
                raise legacy.ChatGPTPlaywrightError(
                    f"Campo de mensagem ainda não localizado. Diagnóstico salvo em {diagnostic}."
                )
            legacy._update_state(
                project_url=page.url,
                project_name=legacy.project_name(),
                profile_dir=str(profile_dir()),
                bootstrap_ok=True,
                bootstrap_at=int(time.time()),
            )
        result = {
            "ok": True,
            "project": legacy.project_name(),
            "project_url": page.url,
            "profile_dir": str(profile_dir()),
            "composer_found": composer(page, 2000) is not None,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def doctor() -> dict[str, Any]:
    with legacy._LOCK, browser(headless=True) as page:
        try:
            open_project(page)
            result = {
                "ok": True,
                "project": legacy.project_name(),
                "project_url": page.url,
                "profile_dir": str(profile_dir()),
                "composer_found": composer(page, 2000) is not None,
                "headless": True,
            }
        except Exception as error:
            diagnostic = _diagnostic(page, "doctor_failed")
            result = {
                "ok": False,
                "error": str(error),
                "url": str(getattr(page, "url", "") or ""),
                "profile_dir": str(profile_dir()),
                "diagnostic": diagnostic,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    legacy.profile_dir = profile_dir
    legacy._browser = browser
    legacy._composer = composer
    legacy._looks_like_auth_wall = _looks_like_auth_wall
    legacy._ensure_authenticated = ensure_authenticated
    legacy._open_sidebar = _open_sidebar
    legacy._find_project_locator = _project_locator
    legacy._open_project = open_project
    legacy._open_job_conversation = open_job_conversation
    legacy.bootstrap = bootstrap
    _INSTALLED = True


def main() -> None:
    import sys

    install()
    command = (sys.argv[1] if len(sys.argv) > 1 else "doctor").strip().lower()
    if command == "bootstrap":
        bootstrap()
        return
    if command in {"doctor", "diagnose", "diagnostico"}:
        doctor()
        return
    if command == "status":
        payload = legacy.status()
        payload["profile_dir"] = str(profile_dir())
        payload["legacy_profile_score"] = _profile_score(legacy._data_dir() / "browser_profiles" / "chatgpt")
        payload["automation_profile_score"] = _profile_score(legacy._data_dir() / "browser_profiles" / "chatgpt_automation")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    raise SystemExit("Use: python -m app.additions.chatgpt_playwright_compat [bootstrap|doctor|status]")


if __name__ == "__main__":
    main()
