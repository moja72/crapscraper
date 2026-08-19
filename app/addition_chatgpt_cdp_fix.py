from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from app import settings
import app.addition_one_click_policy as one_click
import app.chatgpt_browser_assist as chatgpt
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_PUBLIC_CONFIG = None
_ORIGINAL_CREATE_DRAFT = None
_PROJECT_ID = "g-p-6a852af976708191937e4a92648e2095"
_PROJECT_URL = f"https://chatgpt.com/g/{_PROJECT_ID}/project"
_CDP_PROFILE_DIR = Path(settings.DATA_DIR) / "browser_profiles" / "chatgpt-cdp"
_DEFAULT_DEBUG_PORT = 9333


def _debug_port() -> int:
    raw = str(os.getenv("SCRAPER_CHATGPT_DEBUG_PORT", _DEFAULT_DEBUG_PORT) or "").strip()
    try:
        port = int(raw)
    except Exception:
        port = _DEFAULT_DEBUG_PORT
    return max(1024, min(65535, port))


def _debug_endpoint() -> str:
    return f"http://127.0.0.1:{_debug_port()}"


def _conversation_url() -> str:
    explicit = str(os.getenv("SCRAPER_CHATGPT_PROJECT_URL", "") or "").strip()
    if explicit and _PROJECT_ID in explicit:
        return explicit

    try:
        configured = str(chatgpt._load_config().get("conversation_url") or "").strip()
    except Exception:
        configured = ""

    if configured and _PROJECT_ID in configured:
        return configured

    return _PROJECT_URL


def _browser_version(endpoint: str) -> dict[str, Any]:
    request = Request(endpoint.rstrip("/") + "/json/version", method="GET")
    with urlopen(request, timeout=1.5) as response:
        payload = json.loads(response.read() or b"{}")
    if not isinstance(payload, dict) or not payload.get("webSocketDebuggerUrl"):
        raise RuntimeError("endpoint CDP respondeu sem webSocketDebuggerUrl")
    return payload


def _browser_ready(endpoint: str) -> bool:
    try:
        _browser_version(endpoint)
        return True
    except Exception:
        return False


def _profile_candidates() -> list[Path]:
    candidates: list[Path] = []
    try:
        current = Path(chatgpt._PROFILE_DIR)
        candidates.append(current)
    except Exception:
        pass
    if _CDP_PROFILE_DIR not in candidates:
        candidates.append(_CDP_PROFILE_DIR)
    return candidates


def _browser_args(browser: str, profile_dir: Path, url: str, port: int) -> list[str]:
    return [
        browser,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--start-maximized",
        url,
    ]


def _launch_profile(profile_dir: Path, url: str, endpoint: str) -> tuple[bool, str]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    browser = chatgpt._find_browser()
    args = _browser_args(browser, profile_dir, url, _debug_port())
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as error:
        return False, f"{profile_dir.name}: falha ao iniciar Chrome ({type(error).__name__}: {error})"

    deadline = time.time() + 14
    while time.time() < deadline:
        if _browser_ready(endpoint):
            return True, ""
        code = process.poll()
        if code is not None:
            return False, f"{profile_dir.name}: Chrome encerrou durante a inicialização (código {code})"
        time.sleep(0.25)

    return False, f"{profile_dir.name}: porta de depuração não ficou disponível"


def _ensure_debug_browser(url: str | None = None) -> tuple[str, Path]:
    endpoint = _debug_endpoint()
    target_url = str(url or _conversation_url()).strip() or _PROJECT_URL

    if _browser_ready(endpoint):
        active = Path(str(chatgpt._load_config().get("cdp_profile_dir") or _CDP_PROFILE_DIR))
        return endpoint, active

    failures: list[str] = []
    for profile_dir in _profile_candidates():
        ok, failure = _launch_profile(profile_dir, target_url, endpoint)
        if ok:
            chatgpt._PROFILE_DIR = profile_dir
            try:
                chatgpt._save_config(
                    {
                        "conversation_url": target_url,
                        "cdp_profile_dir": str(profile_dir),
                        "cdp_debug_port": _debug_port(),
                        "mode": "browser_automatic_cdp",
                    }
                )
            except Exception:
                pass
            return endpoint, profile_dir
        if failure:
            failures.append(failure)

    details = " | ".join(failures[-2:])
    raise RuntimeError(
        "Não foi possível iniciar um Chrome controlável pelo CrapScraper. "
        + (details or "Feche janelas antigas do perfil ChatGPT e tente novamente.")
    )


def _open_project_tab(endpoint: str, url: str) -> None:
    try:
        request = Request(
            endpoint.rstrip("/") + "/json/new?" + quote(url, safe=""),
            method="PUT",
        )
        with urlopen(request, timeout=3):
            return
    except Exception:
        return


def _public_config() -> dict[str, Any]:
    base: dict[str, Any] = {}
    if callable(_ORIGINAL_PUBLIC_CONFIG):
        try:
            base = dict(_ORIGINAL_PUBLIC_CONFIG())
        except Exception:
            base = {}
    base.update(
        {
            "ok": True,
            "conversation_url": _conversation_url(),
            "profile_dir": str(chatgpt._PROFILE_DIR),
            "mode": "browser_automatic_cdp",
            "automatic_extraction": True,
            "debug_endpoint": _debug_endpoint(),
        }
    )
    return base


def _open_for_job(job_id: str) -> dict[str, Any]:
    job = additions._row(additions._normalize(job_id))
    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Não foi possível gerar o prompt deste produto.")
    chatgpt._copy_to_clipboard(prompt)
    url = _conversation_url()
    endpoint, profile_dir = _ensure_debug_browser(url)
    _open_project_tab(endpoint, url)
    return {
        "ok": True,
        "message": (
            "Projeto do ChatGPT aberto no navegador controlado pelo CrapScraper. "
            "Se este perfil ainda não estiver autenticado, faça login uma única vez; a sessão será reutilizada."
        ),
        "conversation_url": url,
        "profile_dir": str(profile_dir),
        "debug_endpoint": endpoint,
    }


def _ensure_project_page(page: Any, job_id: str, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    one_click._wait_composer(page, job_id)

    if _PROJECT_ID not in str(page.url or ""):
        one_click._emit(
            job_id,
            "Login detectado. Reabrindo o projeto correto do ChatGPT…",
            step="chatgpt_project",
            progress=13,
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        one_click._wait_composer(page, job_id)

    if _PROJECT_ID not in str(page.url or ""):
        raise RuntimeError("O ChatGPT abriu, mas não confirmou a navegação dentro do projeto configurado.")


def _wait_complete_answer(page: Any, before_count: int, job_id: str, timeout_seconds: int = 360) -> str:
    deadline = time.time() + timeout_seconds
    latest = ""
    required = (
        "TÍTULO",
        "BREVE DESCRIÇÃO",
        "DESCRIÇÃO",
        "TAGS",
        "CATEGORIA",
    )

    while time.time() < deadline:
        messages = one_click._assistant_messages(page)
        try:
            count = messages.count()
        except Exception:
            count = 0

        if count > before_count:
            try:
                latest = str(messages.nth(count - 1).inner_text() or "").strip()
            except Exception:
                latest = ""

            normalized = latest.upper()
            if all(label in normalized for label in required):
                parsed = chatgpt.parse_chatgpt_text(latest)
                if str(parsed.get("category_name") or "").strip():
                    return latest

        page.wait_for_timeout(1200)

    if latest:
        raise RuntimeError(
            "O ChatGPT respondeu, mas o bloco final ainda não trouxe todos os campos, incluindo CATEGORIA."
        )
    raise RuntimeError("Tempo esgotado aguardando a resposta do ChatGPT.")


def _automatic_chatgpt(job_id: str) -> None:
    job = additions._row(job_id)
    if additions._content_complete(job) and str(job.get("image_path") or "").strip():
        one_click._emit(
            job_id,
            "Conteúdo e imagem já estão prontos; etapa de IA reaproveitada.",
            step="content_ready",
            progress=42,
        )
        return

    prompt = str(additions._public_job(job).get("prompt") or "").strip()
    if not prompt:
        raise RuntimeError("Não foi possível montar o prompt do produto.")

    one_click._emit(
        job_id,
        "Abrindo o projeto do ChatGPT no navegador controlado…",
        step="chatgpt",
        progress=8,
    )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

    url = _conversation_url()
    endpoint, profile_dir = _ensure_debug_browser(url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=10,
    )

    page = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError("Chrome conectado, mas nenhum contexto de navegação foi encontrado.")
        context = contexts[0]

        try:
            page = context.new_page()
            _ensure_project_page(page, job_id, url)
            one_click._emit(
                job_id,
                "Projeto ChatGPT confirmado. Enviando instruções do produto…",
                step="chatgpt_content",
                progress=16,
            )

            before_count, before_images = one_click._send_message(page, prompt, job_id)
            answer = _wait_complete_answer(page, before_count, job_id)
            one_click._save_text(job_id, answer)
            one_click._emit(
                job_id,
                "Descrição, SEO, tags e categoria recebidos.",
                step="chatgpt_content",
                progress=30,
            )

            image_source = one_click._wait_new_image(page, before_images, timeout_seconds=45)
            if not image_source:
                current = additions._row(job_id)
                title = str(current.get("title") or current.get("source_name") or "produto WordPress")
                image_prompt = (
                    f"Gere agora SOMENTE uma imagem de capa quadrada 1:1 para o produto {title}. "
                    "Visual profissional para e-commerce de plugins/temas WordPress, composição limpa, "
                    "sem preço, sem marca d'água, sem texto pequeno e sem copiar identidade visual protegida."
                )
                one_click._emit(
                    job_id,
                    "Gerando a imagem 1:1 no mesmo chat do projeto…",
                    step="chatgpt_image",
                    progress=34,
                )
                _count, before_second = one_click._send_message(page, image_prompt, job_id)
                image_source = one_click._wait_new_image(page, before_second, timeout_seconds=300)

            if not image_source:
                raise RuntimeError("O ChatGPT concluiu o texto, mas não retornou uma imagem utilizável.")

            data_url = one_click._image_data_url(page, image_source)
            image_path = one_click._persist_image(job_id, data_url)
            one_click._emit(
                job_id,
                f"Imagem recebida e salva localmente: {Path(image_path).name}.",
                step="content_ready",
                progress=42,
            )
        finally:
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass


def _create_draft_with_required_media(job_id: str, confirmation: str) -> dict[str, Any]:
    job = additions._row(job_id)
    image_path = Path(str(job.get("image_path") or ""))
    if not image_path.exists():
        raise ValueError("A imagem do produto ainda não foi gerada/salva; o cadastro não será criado sem capa.")

    category_name = str(job.get("category_name") or "").strip()
    if not category_name:
        raise ValueError("A categoria do produto não foi definida pelo conteúdo gerado; gere o conteúdo novamente.")

    media_id = int(job.get("media_id") or 0)
    if not media_id:
        media_id = int(
            additions._wp_media_upload(
                str(image_path),
                str(job.get("title") or job.get("source_name") or "Produto"),
            )
            or 0
        )
        if not media_id:
            raise RuntimeError(
                "A imagem foi gerada, mas o WordPress não confirmou o upload para a Biblioteca de Mídia. "
                "Confira SCRAPER_WP_BASE_URL, SCRAPER_WP_USERNAME e SCRAPER_WP_APPLICATION_PASSWORD."
            )
        additions._update(job_id, media_id=media_id, error="")

    return _ORIGINAL_CREATE_DRAFT(job_id, confirmation)


def install_addition_chatgpt_cdp_fix() -> None:
    global _INSTALLED, _ORIGINAL_PUBLIC_CONFIG, _ORIGINAL_CREATE_DRAFT
    if _INSTALLED:
        return

    _ORIGINAL_PUBLIC_CONFIG = chatgpt.public_config
    _ORIGINAL_CREATE_DRAFT = additions._create_or_resume_draft
    chatgpt._DEFAULT_URL = _PROJECT_URL
    chatgpt.public_config = _public_config
    chatgpt.open_for_job = _open_for_job
    one_click._automatic_chatgpt = _automatic_chatgpt
    additions._create_or_resume_draft = _create_draft_with_required_media
    _INSTALLED = True
