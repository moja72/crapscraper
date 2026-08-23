from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import app.addition_chatgpt_cdp_fix as cdp
import app.addition_one_click_policy as one_click
import app.chatgpt_browser_assist as chatgpt
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_BROWSER_ARGS = None

_RETRYABLE_MARKERS = (
    "target page, context or browser has been closed",
    "page has been closed",
    "browser has been closed",
    "context has been closed",
    "connection closed",
    "websocket error",
    "browser disconnected",
    "target closed",
)

_LOGIN_MARKERS = (
    "auth.openai.com",
    "/auth/",
    "/login",
    "oauth",
    "signin",
    "sign-in",
)


def _is_retryable_browser_error(error: BaseException) -> bool:
    text = str(error or "").lower()
    return any(marker in text for marker in _RETRYABLE_MARKERS)


def _is_login_url(url: str) -> bool:
    text = str(url or "").lower()
    return any(marker in text for marker in _LOGIN_MARKERS)


def _stable_browser_args(browser: str, profile_dir: Path, url: str, port: int) -> list[str]:
    base = list(_ORIGINAL_BROWSER_ARGS(browser, profile_dir, url, port))
    target = base[-1] if base else url
    prefix = base[:-1] if base else [browser]
    extras = (
        "--new-window",
        "--disable-background-mode",
        "--disable-session-crashed-bubble",
        "--disable-search-engine-choice-screen",
        "--disable-features=AutoDeElevate",
    )
    for value in extras:
        if value not in prefix:
            prefix.append(value)
    return prefix + [target]


def _page_is_alive(page: Any) -> bool:
    try:
        return not bool(page.is_closed())
    except Exception:
        return False


def _live_pages(context: Any) -> list[Any]:
    try:
        return [page for page in list(context.pages) if _page_is_alive(page)]
    except Exception:
        return []


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:
        return ""


def _pick_page(context: Any) -> Any:
    pages = _live_pages(context)

    project_pages = [page for page in pages if cdp._PROJECT_ID in _page_url(page)]
    if project_pages:
        return project_pages[-1]

    chatgpt_pages = [
        page
        for page in pages
        if "chatgpt.com" in _page_url(page).lower()
        or "chat.openai.com" in _page_url(page).lower()
        or "openai.com" in _page_url(page).lower()
    ]
    if chatgpt_pages:
        return chatgpt_pages[-1]

    if pages:
        return pages[-1]

    return context.new_page()


def _ensure_project_page_resilient(
    context: Any,
    page: Any,
    job_id: str,
    url: str,
    *,
    timeout_seconds: int = 300,
) -> Any:
    deadline = time.time() + timeout_seconds
    warned = False
    navigated_once = False
    current = page

    while time.time() < deadline:
        if not _page_is_alive(current):
            current = _pick_page(context)

        current_url = _page_url(current)

        # Never steal the page while the user is authenticating. Once login
        # finishes, ChatGPT returns to a regular page and the loop continues.
        if _is_login_url(current_url):
            if not warned:
                one_click._emit(
                    job_id,
                    "Login do ChatGPT necessário neste perfil. Conclua o login na janela aberta; o processo continuará sozinho.",
                    step="chatgpt_login",
                    progress=12,
                )
                warned = True
            time.sleep(1.0)
            continue

        if cdp._PROJECT_ID not in current_url and not navigated_once:
            try:
                current.goto(url, wait_until="domcontentloaded", timeout=60_000)
                navigated_once = True
                current_url = _page_url(current)
            except Exception as error:
                if _is_retryable_browser_error(error):
                    current = _pick_page(context)
                    time.sleep(0.8)
                    continue
                raise

        try:
            composer = one_click._composer(current)
        except Exception as error:
            if _is_retryable_browser_error(error):
                current = _pick_page(context)
                time.sleep(0.8)
                continue
            raise

        if composer is not None:
            current_url = _page_url(current)
            if cdp._PROJECT_ID in current_url:
                return current

            # Login may land on the ChatGPT home page. At this point there is a
            # composer, so it is safe to move into the configured project.
            try:
                current.goto(url, wait_until="domcontentloaded", timeout=60_000)
                navigated_once = True
            except Exception as error:
                if _is_retryable_browser_error(error):
                    current = _pick_page(context)
                    time.sleep(0.8)
                    continue
                raise
            time.sleep(0.8)
            continue

        if not warned:
            one_click._emit(
                job_id,
                "Aguardando o ChatGPT ficar disponível. Se este perfil ainda não estiver autenticado, faça login na janela aberta; o fluxo continuará sozinho.",
                step="chatgpt_login",
                progress=12,
            )
            warned = True

        # If ChatGPT redirected away from the project without entering a login
        # URL, allow one fresh navigation after the page settles.
        if navigated_once and current_url and cdp._PROJECT_ID not in current_url:
            navigated_once = False

        time.sleep(1.0)

    raise RuntimeError("Tempo esgotado aguardando a caixa de mensagem do projeto ChatGPT.")


def _fill_composer_without_pointer_click(page: Any, composer: Any, prompt: str) -> None:
    """Preenche o editor do projeto sem depender de um clique físico no ProseMirror."""
    first_error: BaseException | None = None
    try:
        composer.fill(prompt, timeout=10_000)
        return
    except Exception as error:
        first_error = error

    try:
        composer.focus(timeout=5_000)
        page.keyboard.press("Control+A")
        page.keyboard.insert_text(prompt)
        return
    except Exception:
        pass

    try:
        composer.evaluate(
            """
            (el, text) => {
              el.focus();
              if (el.isContentEditable) {
                el.textContent = '';
                el.textContent = String(text || '');
              } else {
                el.value = String(text || '');
              }
              el.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                inputType: 'insertText',
                data: String(text || '')
              }));
              el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            prompt,
        )
        return
    except Exception as error:
        raise RuntimeError(
            "A caixa de mensagem do novo chat foi encontrada, mas não pôde receber o prompt."
        ) from (first_error or error)


def _send_message_resilient(
    context: Any,
    page: Any,
    prompt: str,
    job_id: str,
    url: str,
) -> tuple[Any, int, set[str]]:
    current = _ensure_project_page_resilient(context, page, job_id, url)
    messages = one_click._assistant_messages(current)
    before_count = messages.count()
    before_images = set(one_click._large_image_sources(current))
    composer = one_click._composer(current)
    if composer is None:
        raise RuntimeError("A caixa de mensagem do ChatGPT desapareceu antes do envio.")

    # Na raiz do projeto o compositor já representa "Novo chat em [Projeto]".
    # Evite locator.click(): no layout atual o ProseMirror pode estar visível,
    # habilitado e estável e mesmo assim manter a ação de ponteiro bloqueada até
    # o timeout. fill/focus usam o editor diretamente e o primeiro envio cria a
    # conversa dentro do projeto.
    _fill_composer_without_pointer_click(current, composer, prompt)
    time.sleep(0.25)

    sent = False
    for selector in (
        "button[data-testid='send-button']",
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
    ):
        try:
            button = current.locator(selector).first
            if button.count() and button.is_visible() and button.is_enabled():
                button.click(timeout=5_000)
                sent = True
                break
        except Exception:
            continue

    if not sent:
        # O editor permanece focado após fill/focus. Enter é um fallback mais
        # estável que insistir em um clique de ponteiro bloqueado pelo layout.
        current.keyboard.press("Enter")

    return current, before_count, before_images


def _wait_complete_answer_resilient(
    context: Any,
    page: Any,
    before_count: int,
    job_id: str,
    url: str,
    *,
    timeout_seconds: int = 360,
) -> tuple[Any, str]:
    deadline = time.time() + timeout_seconds
    current = page
    latest = ""
    required = ("TÍTULO", "BREVE DESCRIÇÃO", "DESCRIÇÃO", "TAGS", "CATEGORIA")

    while time.time() < deadline:
        if not _page_is_alive(current):
            current = _pick_page(context)
            current = _ensure_project_page_resilient(
                context,
                current,
                job_id,
                url,
                timeout_seconds=60,
            )

        try:
            messages = one_click._assistant_messages(current)
            count = messages.count()
        except Exception as error:
            if _is_retryable_browser_error(error):
                current = _pick_page(context)
                time.sleep(0.8)
                continue
            raise

        if count > before_count:
            try:
                latest = str(messages.nth(count - 1).inner_text() or "").strip()
            except Exception as error:
                if _is_retryable_browser_error(error):
                    current = _pick_page(context)
                    time.sleep(0.8)
                    continue
                latest = ""

            normalized = latest.upper()
            if all(label in normalized for label in required):
                parsed = chatgpt.parse_chatgpt_text(latest)
                if str(parsed.get("category_name") or "").strip():
                    return current, latest

        time.sleep(1.2)

    if latest:
        raise RuntimeError(
            "O ChatGPT respondeu, mas o bloco final ainda não trouxe todos os campos, incluindo CATEGORIA."
        )
    raise RuntimeError("Tempo esgotado aguardando a resposta do ChatGPT.")


def _wait_new_image_resilient(
    context: Any,
    page: Any,
    before: set[str],
    job_id: str,
    url: str,
    *,
    timeout_seconds: int,
) -> tuple[Any, str]:
    deadline = time.time() + timeout_seconds
    current = page

    while time.time() < deadline:
        if not _page_is_alive(current):
            current = _pick_page(context)
            current = _ensure_project_page_resilient(
                context,
                current,
                job_id,
                url,
                timeout_seconds=60,
            )

        try:
            sources = one_click._large_image_sources(current)
        except Exception as error:
            if _is_retryable_browser_error(error):
                current = _pick_page(context)
                time.sleep(0.8)
                continue
            sources = []

        for source in reversed(sources):
            if source not in before:
                return current, source

        time.sleep(1.2)

    return current, ""


def _run_once(job_id: str, url: str) -> None:
    from playwright.sync_api import sync_playwright

    endpoint, profile_dir = cdp._ensure_debug_browser(url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=10,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
        contexts = list(browser.contexts)
        if not contexts:
            cdp._open_project_tab(endpoint, url)
            time.sleep(0.8)
            contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError("Chrome conectado, mas nenhum contexto de navegação foi encontrado.")

        context = contexts[0]

        # Reuse the tab Chrome opened at startup. Creating a second page here
        # was the source of the transient TargetClosed failures seen on Windows.
        page = _pick_page(context)
        page = _ensure_project_page_resilient(context, page, job_id, url)

        one_click._emit(
            job_id,
            "Projeto ChatGPT confirmado. Enviando instruções do produto…",
            step="chatgpt_content",
            progress=16,
        )

        prompt = str(additions._public_job(additions._row(job_id)).get("prompt") or "").strip()
        page, before_count, before_images = _send_message_resilient(
            context,
            page,
            prompt,
            job_id,
            url,
        )

        page, answer = _wait_complete_answer_resilient(
            context,
            page,
            before_count,
            job_id,
            url,
        )
        one_click._save_text(job_id, answer)
        one_click._emit(
            job_id,
            "Descrição, SEO, tags e categoria recebidos.",
            step="chatgpt_content",
            progress=30,
        )

        page, image_source = _wait_new_image_resilient(
            context,
            page,
            before_images,
            job_id,
            url,
            timeout_seconds=45,
        )

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
            page, _count, before_second = _send_message_resilient(
                context,
                page,
                image_prompt,
                job_id,
                url,
            )
            page, image_source = _wait_new_image_resilient(
                context,
                page,
                before_second,
                job_id,
                url,
                timeout_seconds=300,
            )

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


def _automatic_chatgpt_resilient(job_id: str) -> None:
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
        import playwright.sync_api  # noqa: F401
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

    url = cdp._conversation_url()
    last_error: BaseException | None = None

    for attempt in range(1, 4):
        try:
            _run_once(job_id, url)
            return
        except Exception as error:
            last_error = error
            if attempt >= 3 or not _is_retryable_browser_error(error):
                raise

            one_click._emit(
                job_id,
                f"A guia ou o contexto do ChatGPT foi encerrado. Reconectando automaticamente (tentativa {attempt + 1}/3)…",
                step="chatgpt_reconnect",
                progress=12,
            )
            time.sleep(1.5)

    if last_error is not None:
        raise last_error


def install_addition_chatgpt_cdp_reconnect_policy() -> None:
    global _INSTALLED, _ORIGINAL_BROWSER_ARGS
    if _INSTALLED:
        return

    _ORIGINAL_BROWSER_ARGS = cdp._browser_args
    cdp._browser_args = _stable_browser_args
    one_click._automatic_chatgpt = _automatic_chatgpt_resilient
    _INSTALLED = True
