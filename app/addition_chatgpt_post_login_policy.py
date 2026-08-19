from __future__ import annotations

import time
from typing import Any

import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_one_click_policy as one_click


_INSTALLED = False


def _wait_login_then_project_fixed(
    job_id: str,
    endpoint: str,
    url: str,
    *,
    timeout_seconds: int = 10 * 60,
) -> None:
    """Wait for authentication without letting stale login targets block progress.

    Chrome/OpenAI can leave an auth target alive after a successful login. The
    configured project is authoritative: once its target exists, authentication
    is complete enough for Playwright to attach and send the product prompt.
    """
    deadline = time.time() + timeout_seconds
    announced_login = False
    announced_project_open = False
    last_project_open = 0.0

    while time.time() < deadline:
        if not cdp._browser_ready(endpoint):
            time.sleep(0.8)
            continue

        urls = coproducao._target_urls(endpoint)

        # IMPORTANT: project wins over stale auth/login targets. A completed
        # OAuth flow may leave an old login page/target behind for several
        # minutes, which previously kept the job stuck at 12% forever.
        if coproducao._has_project_url(urls):
            one_click._emit(
                job_id,
                "Sessão autenticada. Projeto CS Automação confirmado; preparando um novo chat…",
                step="chatgpt_project",
                progress=14,
            )
            return

        login_visible = any(coproducao._is_login_url(item) for item in urls)
        if login_visible:
            if not announced_login:
                one_click._emit(
                    job_id,
                    "Login necessário na conta Coproducaolancamentos. Conclua o login na janela aberta; o processo continuará sozinho.",
                    step="chatgpt_login",
                    progress=11,
                )
                announced_login = True
            time.sleep(1.0)
            continue

        # Successful login often lands on ChatGPT home. Reopen the project root;
        # that root is the project's 'Novo chat' screen, so the next stage sends
        # the product prompt into a fresh project conversation.
        if coproducao._has_chatgpt_url(urls) or not urls:
            now = time.time()
            if now - last_project_open >= 3.0:
                cdp._open_project_tab(endpoint, url)
                last_project_open = now
                if not announced_project_open:
                    one_click._emit(
                        job_id,
                        "Login detectado. Abrindo a tela de novo chat do projeto CS Automação…",
                        step="chatgpt_project",
                        progress=13,
                    )
                    announced_project_open = True

        time.sleep(0.8)

    raise RuntimeError(
        "Tempo esgotado aguardando a autenticação e o novo chat do projeto CS Automação. "
        "Mantenha a janela controlada do Chrome aberta."
    )


def install_addition_chatgpt_post_login_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    coproducao._wait_login_then_project = _wait_login_then_project_fixed
    _INSTALLED = True
