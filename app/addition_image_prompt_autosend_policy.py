from __future__ import annotations

import time
from typing import Any, Callable, Mapping

import app.addition_capture_pipeline_resilience_policy as resilience
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_parallel_generation_policy as parallel
import app.addition_product_contract_policy as product_contract
import app.addition_product_creative_policy as creative
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_simple_creation_policy as simple


_INSTALLED = False
_BASE_SEND_MESSAGE: Callable[..., tuple[Any, int, set[str]]] | None = None
_SUBMISSION_VERIFY_SECONDS = 4.0
_MAPPED_CHAT_REPROMPT_SECONDS = 2


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if _clean(job.get("kind")).lower() == "theme" else "plugin"


def _project_reference_image_prompt(
    job: Mapping[str, Any],
    *,
    reference_attached: bool | None = None,
) -> str:
    """Prompt final: usa a referência que já existe nos arquivos do Projeto ChatGPT."""
    name = _clean(job.get("source_name") or job.get("title") or "produto WordPress")
    try:
        marketplace = _clean(parallel._expected_marketplace(job))
    except Exception:
        marketplace = "site oficial do desenvolvedor ou marketplace oficial"

    if _kind(job) == "theme":
        kind_label = "tema WordPress"
        project_reference = "Exemplo Tema.webp"
        visual = (
            "Gere uma NOVA imagem quadrada 1:1 com fundo transparente, monitor Apple e celular inteiros. "
            "Mostre nas telas a aparência real do tema pesquisado; não reutilize as telas, cores, textos ou marca "
            "da imagem de referência. A referência serve somente para composição, proporção, posição dos dispositivos "
            "e acabamento do mockup. Não corte o monitor nem o celular."
        )
    else:
        kind_label = "plugin WordPress"
        project_reference = "Exemplo Plugin.webp"
        visual = (
            "Gere uma NOVA imagem quadrada 1:1 com fundo transparente e uma caixa 3D profissional com pelo menos "
            "3 faces visíveis. Use a identidade visual real do plugin pesquisado. A referência serve somente para "
            "composição, proporção e acabamento da caixa; não reutilize a marca, cores ou arte da referência. "
            "Use a fonte Quicksand e deixe claramente visível exatamente o texto "
            "'Vitalício | Ilimitado | Atualizado'. Não corte a caixa."
        )

    return f"""Gere SOMENTE a imagem principal deste produto para a PluginTema.

Produto: {name}
Tipo: {kind_label}
Fonte oficial esperada: {marketplace or 'site oficial do desenvolvedor ou marketplace oficial'}

REFERÊNCIA VISUAL DO PROJETO
Use obrigatoriamente como referência de mockup a imagem "{project_reference}", que já está disponível nos arquivos deste Projeto do ChatGPT. Não peça para o usuário anexar essa imagem novamente e não dependa de um novo upload na conversa. Localize e use a referência do próprio Projeto antes de gerar a imagem.

Pesquise o produto exato e use previews, screenshots e imagens públicas confiáveis para confirmar sua identidade visual. Se a página oficial não abrir, continue pela pesquisa pública; não peça arquivos e não responda com explicações.

{visual}

REQUISITOS FINAIS
- Entregue uma única imagem final, nova, profissional e pronta para e-commerce.
- Formato 1:1.
- Fundo totalmente transparente, inclusive nas bordas e áreas vazias.
- Use a identidade visual verdadeira do produto atual; não invente logotipo ou marca.
- A imagem "{project_reference}" do Projeto deve orientar somente o mockup/composição, nunca a identidade do produto.

Responda SOMENTE com a geração da imagem, sem texto adicional."""


def _is_image_prompt(prompt: str) -> bool:
    text = _clean(prompt).lower()
    return "gere somente a imagem principal" in text or "imagem principal deste produto" in text


def _user_turn_count(page: Any) -> int:
    selectors = (
        "[data-message-author-role='user']",
        "[data-testid*='conversation-turn'][data-message-author-role='user']",
    )
    best = 0
    for selector in selectors:
        try:
            best = max(best, int(page.locator(selector).count()))
        except Exception:
            continue
    return best


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "")
    except Exception:
        return ""


def _composer_text(page: Any) -> str:
    try:
        composer = one_click._composer(page)
    except Exception:
        composer = None
    if composer is None:
        return ""
    try:
        value = composer.input_value(timeout=500)
        if value is not None:
            return str(value or "").strip()
    except Exception:
        pass
    for reader in ("inner_text", "text_content"):
        try:
            value = getattr(composer, reader)(timeout=500)
            if value is not None:
                return str(value or "").strip()
        except Exception:
            continue
    return ""


def _submission_confirmed(
    page: Any,
    *,
    before_user_count: int,
    before_url: str,
    prompt: str,
) -> bool:
    try:
        if _user_turn_count(page) > before_user_count:
            return True
    except Exception:
        pass
    try:
        if simple._assistant_busy(page):
            return True
    except Exception:
        pass

    current_text = _composer_text(page)
    if not current_text:
        return True

    current_url = _page_url(page)
    if before_url and current_url and current_url != before_url and prompt[:80] not in current_text:
        return True
    return False


def _wait_submission(
    page: Any,
    *,
    before_user_count: int,
    before_url: str,
    prompt: str,
    timeout_seconds: float = _SUBMISSION_VERIFY_SECONDS,
) -> bool:
    deadline = time.time() + max(0.5, float(timeout_seconds))
    while time.time() < deadline:
        if _submission_confirmed(
            page,
            before_user_count=before_user_count,
            before_url=before_url,
            prompt=prompt,
        ):
            return True
        try:
            page.wait_for_timeout(200)
        except Exception:
            time.sleep(0.2)
    return _submission_confirmed(
        page,
        before_user_count=before_user_count,
        before_url=before_url,
        prompt=prompt,
    )


def _force_submit(page: Any, prompt: str) -> None:
    composer = one_click._composer(page)
    if composer is None:
        raise RuntimeError("A caixa de mensagem do ChatGPT desapareceu antes do envio confirmado.")

    current_text = _composer_text(page)
    if not current_text or prompt[:80] not in current_text:
        reconnect._fill_composer_without_pointer_click(page, composer, prompt)
        try:
            page.wait_for_timeout(180)
        except Exception:
            pass

    for selector in (
        "button[data-testid='send-button']",
        "button[aria-label*='Send' i]",
        "button[aria-label*='Enviar' i]",
    ):
        try:
            button = page.locator(selector).first
            if not (button.count() and button.is_visible() and button.is_enabled()):
                continue
            # DOM click evita o bloqueio de hit-test/pointer que já ocorreu no compositor do projeto.
            button.evaluate("el => el.click()")
            return
        except Exception:
            continue

    try:
        composer.focus(timeout=2_000)
        composer.press("Enter", timeout=2_000)
        return
    except Exception:
        pass
    page.keyboard.press("Enter")


def _send_message_confirmed(
    context: Any,
    page: Any,
    prompt: str,
    job_id: str,
    url: str,
) -> tuple[Any, int, set[str]]:
    """Só considera o prompt enviado depois de observar confirmação real na conversa/UI."""
    if _BASE_SEND_MESSAGE is None:
        raise RuntimeError("Envio base do ChatGPT não foi inicializado.")

    before_user_count = _user_turn_count(page)
    before_url = _page_url(page)
    current, before_count, before_images = _BASE_SEND_MESSAGE(
        context, page, prompt, job_id, url
    )

    if _wait_submission(
        current,
        before_user_count=before_user_count,
        before_url=before_url,
        prompt=prompt,
    ):
        if _is_image_prompt(prompt):
            one_click._emit(
                job_id,
                "Chat 2: prompt de imagem enviado automaticamente e confirmado.",
                step="chatgpt_image",
            )
        return current, before_count, before_images

    one_click._emit(
        job_id,
        "O primeiro acionamento do envio não foi confirmado; reenviando automaticamente pelo compositor do ChatGPT.",
        step="chatgpt_image" if _is_image_prompt(prompt) else "chatgpt_description",
    )
    _force_submit(current, prompt)

    if not _wait_submission(
        current,
        before_user_count=before_user_count,
        before_url=before_url,
        prompt=prompt,
        timeout_seconds=5.0,
    ):
        raise RuntimeError(
            "O prompt foi preenchido no ChatGPT, mas o CrapScraper não conseguiu confirmar o envio automático."
        )

    if _is_image_prompt(prompt):
        one_click._emit(
            job_id,
            "Chat 2: prompt de imagem reenviado automaticamente e confirmado.",
            step="chatgpt_image",
        )
    return current, before_count, before_images


def install_addition_image_prompt_autosend_policy() -> None:
    global _INSTALLED, _BASE_SEND_MESSAGE
    if _INSTALLED:
        return

    # O prompt final não depende de upload local: ele aponta explicitamente para
    # a referência de Plugin/Tema que já está nos arquivos do Projeto ChatGPT.
    product_contract._short_image_prompt = _project_reference_image_prompt
    creative._image_only_prompt = _project_reference_image_prompt
    parallel._parallel_image_prompt = _project_reference_image_prompt
    final_validation._image_prompt = _project_reference_image_prompt

    # Chats mapeados recebem o prompt automaticamente quase de imediato quando
    # não há imagem capturável e o assistente está ocioso.
    resilience._EXISTING_CHAT_REPROMPT_SECONDS = _MAPPED_CHAT_REPROMPT_SECONDS

    # A camada final verifica se o envio realmente ocorreu. Se o botão falhar,
    # tenta DOM click/Enter e falha cedo em vez de aguardar 16 minutos sem prompt.
    _BASE_SEND_MESSAGE = reconnect._send_message_resilient
    reconnect._send_message_resilient = _send_message_confirmed
    _INSTALLED = True
