from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from app import settings
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_one_click_policy as one_click
import app.chatgpt_browser_assist as chatgpt
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_PROMPT = None

_PROJECT_SLUG = "g-p-6a85a9a911888191a2cc491671a4056d-cs-automacao"
_PROJECT_URL = f"https://chatgpt.com/g/{_PROJECT_SLUG}/project"
_PROFILE_DIR = Path(settings.DATA_DIR) / "browser_profiles" / "chatgpt-coproducaolancamentos"
_DEBUG_PORT = 9444

_LOGIN_MARKERS = (
    "auth.openai.com",
    "/auth/",
    "/login",
    "oauth",
    "signin",
    "sign-in",
)


def _project_url() -> str:
    configured = str(os.getenv("SCRAPER_CHATGPT_PROJECT_URL", "") or "").strip()
    if configured and _PROJECT_SLUG in configured:
        return configured
    return _PROJECT_URL


def _project_debug_port() -> int:
    raw = str(os.getenv("SCRAPER_CHATGPT_COPRODUCAO_DEBUG_PORT", _DEBUG_PORT) or "").strip()
    try:
        value = int(raw)
    except Exception:
        value = _DEBUG_PORT
    return max(1024, min(65535, value))


def _project_debug_endpoint() -> str:
    return f"http://127.0.0.1:{_project_debug_port()}"


def _profile_candidates() -> list[Path]:
    # A conta Coproducaolancamentos usa um perfil isolado para não herdar a
    # sessão da conta utilizada anteriormente no outro projeto do ChatGPT.
    return [_PROFILE_DIR]


def _cdp_targets(endpoint: str) -> list[dict[str, Any]]:
    request = Request(endpoint.rstrip("/") + "/json", method="GET")
    with urlopen(request, timeout=2.5) as response:
        payload = json.loads(response.read() or b"[]")
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, Mapping)]


def _target_urls(endpoint: str) -> list[str]:
    try:
        return [str(item.get("url") or "") for item in _cdp_targets(endpoint)]
    except Exception:
        return []


def _is_login_url(url: str) -> bool:
    text = str(url or "").lower()
    return any(marker in text for marker in _LOGIN_MARKERS)


def _has_project_url(urls: list[str]) -> bool:
    return any(_PROJECT_SLUG in str(url or "") for url in urls)


def _has_chatgpt_url(urls: list[str]) -> bool:
    return any(
        "chatgpt.com" in str(url or "").lower()
        or "chat.openai.com" in str(url or "").lower()
        for url in urls
    )


def _wait_login_then_project(
    job_id: str,
    endpoint: str,
    url: str,
    *,
    timeout_seconds: int = 10 * 60,
) -> None:
    """Wait outside Playwright while authentication redirects settle.

    Authentication can replace/close Chromium targets. Polling CDP's HTTP
    endpoint avoids holding a stale Playwright Page during that transition.
    """
    deadline = time.time() + timeout_seconds
    announced_login = False
    announced_success = False
    last_project_open = 0.0

    while time.time() < deadline:
        if not cdp._browser_ready(endpoint):
            time.sleep(0.8)
            continue

        urls = _target_urls(endpoint)
        login_visible = any(_is_login_url(item) for item in urls)

        if login_visible:
            if not announced_login:
                one_click._emit(
                    job_id,
                    "Login necessário na conta Coproducaolancamentos. Conclua o login na janela aberta; não feche o Chrome.",
                    step="chatgpt_login",
                    progress=11,
                )
                announced_login = True
            time.sleep(1.0)
            continue

        if _has_project_url(urls):
            if announced_login and not announced_success:
                one_click._emit(
                    job_id,
                    "Login concluído. Projeto CS Automação localizado; iniciando o prompt automaticamente…",
                    step="chatgpt_project",
                    progress=14,
                )
            return

        # After authentication ChatGPT commonly lands on the home screen. Open
        # the configured project again without relying on the old login target.
        if _has_chatgpt_url(urls) or not urls:
            now = time.time()
            if now - last_project_open >= 4.0:
                cdp._open_project_tab(endpoint, url)
                last_project_open = now
                if announced_login and not announced_success:
                    one_click._emit(
                        job_id,
                        "Sessão do ChatGPT detectada. Abrindo o projeto CS Automação…",
                        step="chatgpt_project",
                        progress=13,
                    )
                    announced_success = True

        time.sleep(1.0)

    raise RuntimeError(
        "Tempo esgotado aguardando o login e a abertura do projeto CS Automação. "
        "Mantenha a janela do Chrome aberta durante o login."
    )


def _patched_prompt(job: Mapping[str, Any]) -> str:
    base = str(_BASE_PROMPT(job) or "").rstrip()
    return (
        base
        + "\n\nEXECUÇÃO AUTOMÁTICA\n"
        + "Comece imediatamente e NÃO peça confirmação nem faça perguntas ao usuário. "
        + "Use as informações do produto fornecidas acima para produzir o cadastro. "
        + "Entregue obrigatoriamente o bloco final estruturado com TÍTULO, BREVE DESCRIÇÃO, "
        + "DESCRIÇÃO, TÍTULO SEO, META DESCRIPTION, TAGS e CATEGORIA. "
        + "Depois do conteúdo textual, gere também a imagem principal quadrada 1:1 solicitada para o produto."
    )


def _run_project_automation(job_id: str, url: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

    endpoint, profile_dir = cdp._ensure_debug_browser(url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=9,
    )

    # Critical difference from the old flow: login is observed through the CDP
    # HTTP endpoint first. No Playwright Page is held while OAuth/login replaces
    # tabs or browser targets.
    _wait_login_then_project(job_id, endpoint, url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError("Chrome autenticado, mas nenhum contexto de navegação foi encontrado.")
        context = contexts[0]

        page = reconnect._pick_page(context)
        page = reconnect._ensure_project_page_resilient(
            context,
            page,
            job_id,
            url,
            timeout_seconds=120,
        )

        one_click._emit(
            job_id,
            "Projeto CS Automação confirmado. Enviando prompt para gerar descrição e imagem…",
            step="chatgpt_content",
            progress=16,
        )

        prompt = str(additions._public_job(additions._row(job_id)).get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError("Não foi possível montar o prompt do produto.")

        page, before_count, before_images = reconnect._send_message_resilient(
            context,
            page,
            prompt,
            job_id,
            url,
        )
        one_click._emit(
            job_id,
            "Prompt enviado. Aguardando descrição, SEO, tags e categoria…",
            step="chatgpt_content",
            progress=20,
        )

        page, answer = reconnect._wait_complete_answer_resilient(
            context,
            page,
            before_count,
            job_id,
            url,
            timeout_seconds=420,
        )
        one_click._save_text(job_id, answer)
        one_click._emit(
            job_id,
            "Descrição, SEO, tags e categoria recebidos e salvos.",
            step="chatgpt_content",
            progress=30,
        )

        page, image_source = reconnect._wait_new_image_resilient(
            context,
            page,
            before_images,
            job_id,
            url,
            timeout_seconds=50,
        )

        if not image_source:
            current = additions._row(job_id)
            title = str(current.get("title") or current.get("source_name") or "produto WordPress")
            image_prompt = (
                f"Agora gere a imagem principal do produto {title}. "
                "Gere SOMENTE uma imagem quadrada 1:1, profissional, apropriada para a capa de um produto "
                "de e-commerce WordPress, sem preço, sem marca d'água, sem texto pequeno ilegível e sem copiar "
                "identidade visual protegida de terceiros. Não responda apenas com um prompt: gere a imagem."
            )
            one_click._emit(
                job_id,
                "Descrição pronta. Solicitando agora a geração da imagem 1:1…",
                step="chatgpt_image",
                progress=34,
            )
            page, _count, before_second = reconnect._send_message_resilient(
                context,
                page,
                image_prompt,
                job_id,
                url,
            )
            page, image_source = reconnect._wait_new_image_resilient(
                context,
                page,
                before_second,
                job_id,
                url,
                timeout_seconds=360,
            )

        if not image_source:
            raise RuntimeError("O ChatGPT gerou o conteúdo, mas nenhuma imagem utilizável apareceu no projeto.")

        data_url = one_click._image_data_url(page, image_source)
        image_path = one_click._persist_image(job_id, data_url)
        one_click._emit(
            job_id,
            f"Imagem gerada e salva: {Path(image_path).name}.",
            step="content_ready",
            progress=42,
        )


def _automatic_chatgpt(job_id: str) -> None:
    job = additions._row(job_id)
    if additions._content_complete(job) and str(job.get("image_path") or "").strip():
        one_click._emit(
            job_id,
            "Conteúdo e imagem já estão prontos; etapa do ChatGPT reaproveitada.",
            step="content_ready",
            progress=42,
        )
        return

    one_click._emit(
        job_id,
        "Abrindo o projeto CS Automação na conta Coproducaolancamentos…",
        step="chatgpt",
        progress=7,
    )

    url = _project_url()
    last_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            _run_project_automation(job_id, url)
            return
        except Exception as error:
            last_error = error
            if attempt >= 3 or not reconnect._is_retryable_browser_error(error):
                raise
            one_click._emit(
                job_id,
                f"O alvo do Chrome mudou durante a autenticação. Reconectando automaticamente ({attempt + 1}/3)…",
                step="chatgpt_reconnect",
                progress=12,
            )
            time.sleep(1.5)

    if last_error is not None:
        raise last_error


def _public_config() -> dict[str, Any]:
    return {
        "ok": True,
        "conversation_url": _project_url(),
        "profile_dir": str(_PROFILE_DIR),
        "mode": "browser_automatic_coproducaolancamentos",
        "automatic_extraction": True,
        "debug_endpoint": _project_debug_endpoint(),
        "account_profile": "Coproducaolancamentos",
    }


def install_addition_chatgpt_coproducao_policy() -> None:
    global _INSTALLED, _BASE_PROMPT
    if _INSTALLED:
        return

    _BASE_PROMPT = additions._prompt
    additions._prompt = _patched_prompt

    # Isolate this account/project from the profile previously used by the
    # automation. Credentials are never stored in code; Chrome persists only
    # the authenticated browser session after the user's first manual login.
    chatgpt._PROFILE_DIR = _PROFILE_DIR
    chatgpt._DEFAULT_URL = _PROJECT_URL
    chatgpt.public_config = _public_config

    cdp._PROJECT_ID = _PROJECT_SLUG
    cdp._PROJECT_URL = _PROJECT_URL
    cdp._CDP_PROFILE_DIR = _PROFILE_DIR
    cdp._DEFAULT_DEBUG_PORT = _DEBUG_PORT
    cdp._debug_port = _project_debug_port
    cdp._debug_endpoint = _project_debug_endpoint
    cdp._conversation_url = _project_url
    cdp._profile_candidates = _profile_candidates

    one_click._automatic_chatgpt = _automatic_chatgpt
    _INSTALLED = True
