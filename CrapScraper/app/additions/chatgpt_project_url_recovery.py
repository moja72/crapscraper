from __future__ import annotations

import json
import time
from urllib.parse import urlparse
from typing import Any

from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat

_INSTALLED = False
_ORIGINAL_OPEN_PROJECT = compat.open_project


def is_project_candidate_url(value: str) -> bool:
    """Return True only for a concrete ChatGPT page, never the site root."""
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    if parsed.scheme != "https" or parsed.netloc.casefold() not in {"chatgpt.com", "www.chatgpt.com"}:
        return False
    return bool((parsed.path or "").strip("/"))


def saved_project_url(state: dict[str, Any] | None = None) -> str:
    """Return the last concrete project/chat URL without destroying it on failures.

    project_url used to be cleared by doctor/open_project when a transient browser
    navigation failed.  Keep a second durable copy so a diagnostic run can never
    erase a bootstrap that the user already completed successfully.
    """
    payload = state if isinstance(state, dict) else legacy._read_state()
    current = str(payload.get("project_url") or "").strip()
    if is_project_candidate_url(current):
        return current
    backup = str(payload.get("last_good_project_url") or "").strip()
    if is_project_candidate_url(backup):
        return backup
    return ""


def _remember_current_page(page: Any) -> str:
    compat._dismiss_common_dialogs(page)
    compat.ensure_authenticated(page)
    if compat.composer(page, 7000) is None and not compat._try_new_chat(page):
        diagnostic = compat._diagnostic(page, "manual_project_composer_not_found")
        raise legacy.ChatGPTPlaywrightError(
            f"Campo de mensagem ainda não localizado. Diagnóstico salvo em {diagnostic}."
        )

    current = str(getattr(page, "url", "") or "").strip()
    if not is_project_candidate_url(current):
        diagnostic = compat._diagnostic(page, "manual_project_url_is_root")
        raise legacy.ChatGPTPlaywrightError(
            "O ChatGPT está autenticado, mas a URL ainda é a página inicial. "
            f"Abra um chat dentro do projeto {legacy.project_name()} antes de continuar. "
            f"Diagnóstico salvo em {diagnostic}."
        )

    legacy._update_state(
        project_url=current,
        last_good_project_url=current,
        project_name=legacy.project_name(),
        profile_dir=str(compat.profile_dir()),
        bootstrap_ok=True,
        bootstrap_at=int(time.time()),
    )
    return current


def open_project(page: Any) -> None:
    state = legacy._read_state()
    raw_saved = str(state.get("project_url") or "").strip()
    saved = saved_project_url(state)

    # Direct navigation is preferred, but a transient failure must never erase a
    # URL that was captured from a successful visible bootstrap.
    if saved:
        try:
            page.goto(saved, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1200)
            compat._dismiss_common_dialogs(page)
            compat.ensure_authenticated(page)
            if compat.composer(page, 7000) is not None or compat._try_new_chat(page):
                current = str(getattr(page, "url", "") or saved).strip()
                if is_project_candidate_url(current):
                    legacy._update_state(project_url=current, last_good_project_url=current)
                return
        except legacy.ChatGPTPlaywrightError:
            raise
        except Exception:
            pass

    # Only clear an explicitly invalid root URL left by very old versions. Never
    # clear a concrete saved URL merely because browser navigation failed.
    if raw_saved and not is_project_candidate_url(raw_saved):
        legacy._update_state(project_url="")

    _ORIGINAL_OPEN_PROJECT(page)
    current = str(getattr(page, "url", "") or "").strip()
    if is_project_candidate_url(current):
        legacy._update_state(project_url=current, last_good_project_url=current)


def bootstrap() -> dict[str, Any]:
    with legacy._LOCK, compat.browser(headless=False) as page:
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        print("\nChatGPT aberto no perfil persistente do CrapScraper:")
        print(str(compat.profile_dir()))
        print(f"Faça login e abra um chat dentro do projeto {legacy.project_name()}.")
        print("Somente depois que esse chat estiver aberto, volte ao CMD e pressione ENTER.\n")
        input()

        compat._dismiss_common_dialogs(page)
        compat.ensure_authenticated(page)

        current = str(getattr(page, "url", "") or "").strip()
        if is_project_candidate_url(current) and (compat.composer(page, 5000) is not None or compat._try_new_chat(page)):
            project_url = _remember_current_page(page)
        else:
            try:
                open_project(page)
                project_url = _remember_current_page(page)
            except legacy.ChatGPTPlaywrightError as error:
                print(f"\n{error}\n")
                print(f"Abra manualmente um chat dentro do projeto {legacy.project_name()} e pressione ENTER aqui.")
                input()
                project_url = _remember_current_page(page)

        result = {
            "ok": True,
            "project": legacy.project_name(),
            "project_url": project_url,
            "profile_dir": str(compat.profile_dir()),
            "composer_found": compat.composer(page, 2000) is not None,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def doctor() -> dict[str, Any]:
    with legacy._LOCK, compat.browser(headless=True) as page:
        try:
            open_project(page)
            result = {
                "ok": True,
                "project": legacy.project_name(),
                "project_url": str(getattr(page, "url", "") or ""),
                "profile_dir": str(compat.profile_dir()),
                "composer_found": compat.composer(page, 2000) is not None,
                "headless": True,
            }
        except Exception as error:
            diagnostic = compat._diagnostic(page, "doctor_failed")
            result = {
                "ok": False,
                "error": str(error),
                "url": str(getattr(page, "url", "") or ""),
                "saved_project_url": saved_project_url(),
                "profile_dir": str(compat.profile_dir()),
                "diagnostic": diagnostic,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    compat.open_project = open_project
    compat.bootstrap = bootstrap
    compat.doctor = doctor
    legacy._open_project = open_project
    legacy.bootstrap = bootstrap
    _INSTALLED = True


def main() -> None:
    import sys

    compat.install()
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
        durable = saved_project_url(payload)
        if durable and not is_project_candidate_url(str(payload.get("project_url") or "")):
            payload["project_url"] = durable
            payload["project_url_recovered_from_backup"] = True
        payload["profile_dir"] = str(compat.profile_dir())
        payload["project_url_valid"] = bool(durable)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    raise SystemExit("Use: python -m app.additions.chatgpt_project_url_recovery [bootstrap|doctor|status]")


if __name__ == "__main__":
    main()
