from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Mapping

import app.addition_one_click_policy as one_click
import app.new_product_workflow_policy as additions

_INSTALLED = False
_BASE_PROMPT: Callable[[Mapping[str, Any]], str] | None = None
_BASE_SEND_MESSAGE: Callable[[Any, str, str], tuple[int, set[str]]] | None = None
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_REFERENCE_FILES = {
    "plugin": _STATIC_DIR / "exemplo plugin.webp",
    "theme": _STATIC_DIR / "exemplo tema.webp",
}

_SHORT_DESCRIPTION_EXAMPLE = (
    "Crie páginas profissionais com total liberdade visual O Elementor Pro ajuda a montar páginas, "
    "lojas e áreas do site com visual avançado, melhorando apresentação, conversão e flexibilidade "
    "para criar projetos WordPress mais modernos e profissionais. Ele funciona com edição de arrastar "
    "e soltar, widgets premium, templates e construtores para tema, formulários e pop-ups, deixando a "
    "criação mais prática e reduzindo dependência de código no projeto."
)


def _kind(job: Mapping[str, Any]) -> str:
    return "theme" if str(job.get("kind") or "").strip().lower() == "theme" else "plugin"


def _reference_path(job: Mapping[str, Any]) -> Path:
    return _REFERENCE_FILES[_kind(job)]


def _short_description_guidance() -> str:
    return (
        "REGRA PRIORITÁRIA PARA A BREVE DESCRIÇÃO\n"
        "A breve descrição deve ter aproximadamente a mesma estrutura e extensão do exemplo abaixo: "
        "idealmente entre 400 e 500 caracteres, com alvo próximo de 450 caracteres. "
        "Comece com uma frase curta orientada ao principal benefício do produto e, em seguida, explique "
        "em 2 frases fluidas o que ele ajuda a fazer, para quem é útil e como entrega esse benefício. "
        "Use texto corrido, natural, comercial e informativo; não use tópicos, não inclua a versão e não "
        "encha o texto com recursos desconexos. Esta regra substitui qualquer orientação anterior de tamanho.\n\n"
        "EXEMPLO DE ESTRUTURA E TAMANHO — use como referência, sem copiar:\n"
        f'"{_SHORT_DESCRIPTION_EXAMPLE}"'
    )


def _strip_image_instructions(base: str) -> str:
    text = str(base or "")
    text = re.sub(
        r"\n7\.\s*Gere também uma imagem quadrada 1:1, limpa, profissional, "
        r"sem selos de preço, sem texto pequeno ilegível e sem copiar identidade visual protegida de terceiros\. "
        r"A imagem deve funcionar como capa de produto em uma loja de plugins e temas WordPress\.\n",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace(
        "Depois do conteúdo textual, gere também a imagem principal quadrada 1:1 solicitada para o produto.",
        "Nesta etapa, NÃO gere imagem. Entregue somente o conteúdo textual estruturado.",
    )
    return text.rstrip()


def _image_guidance(job: Mapping[str, Any], *, reference_attached: bool) -> str:
    if _kind(job) == "theme":
        reference_intro = (
            "REFERÊNCIA VISUAL — TEMA\n"
            "Use o arquivo anexado 'exemplo tema.webp' como referência visual principal. "
            "Mantenha a composição, acabamento, proporções, iluminação e apresentação do mockup. "
            if reference_attached
            else "COMPOSIÇÃO VISUAL — TEMA\n"
            "Não há mockup local anexado nesta execução. Siga diretamente a composição descrita a seguir. "
        )
        return (
            reference_intro
            + "A imagem final deve ser quadrada 1:1, com FUNDO TRANSPARENTE. "
            "Mostre explicitamente o tema nas telas de um computador e de um celular; a posição do celular pode "
            "mudar, mas as duas telas precisam ficar claramente visíveis. O computador deve usar um monitor Apple. "
            "Nas telas, represente visualmente o tema real deste produto com base nas informações/páginas fornecidas, "
            "sem inventar uma identidade diferente. Não use cenário ou fundo sólido e não corte os dispositivos."
        )

    reference_intro = (
        "REFERÊNCIA VISUAL — PLUGIN\n"
        "Use o arquivo anexado 'exemplo plugin.webp' como referência visual principal. "
        "Mantenha a proporção e a linguagem visual do mockup anexado. "
        if reference_attached
        else "COMPOSIÇÃO VISUAL — PLUGIN\n"
        "Não há mockup local anexado nesta execução. Siga diretamente a composição descrita a seguir. "
    )
    return (
        reference_intro
        + "Crie uma caixa tridimensional profissional em imagem quadrada 1:1 e com FUNDO TRANSPARENTE. "
        "A caixa deve ser bem construída e mostrar pelo menos 3 lados/faces visíveis; o ângulo pode variar, desde "
        "que preserve a sensação tridimensional e a qualidade do mockup. Use a logo real do plugin e cores "
        "associadas à identidade do produto, sem inventar outra marca. Use a fonte Quicksand nas informações da "
        "embalagem e deixe claramente visível exatamente o texto 'Vitalício | Ilimitado | Atualizado'. Evite textos "
        "adicionais pequenos ou ilegíveis, não use cenário e não corte a caixa."
    )


def _patched_prompt(job: Mapping[str, Any]) -> str:
    if _BASE_PROMPT is None:
        raise RuntimeError("Política criativa ainda não foi instalada.")
    base = _strip_image_instructions(_BASE_PROMPT(job))
    return (
        base
        + "\n\n"
        + _short_description_guidance()
        + "\n\nETAPA ATUAL: SOMENTE CONTEÚDO\n"
        + "Não gere imagem, não descreva um prompt de imagem e não espere por nenhuma referência visual nesta etapa. "
        + "Responda somente com o conteúdo editorial e o bloco final estruturado solicitado."
    )


def _is_image_request(prompt: str) -> bool:
    normalized = str(prompt or "").lower()
    return (
        "referência visual obrigatória" in normalized
        or "agora gere somente a imagem" in normalized
        or "gere somente uma imagem" in normalized
        or "imagem final do produto" in normalized
    )


def _image_only_prompt(job: Mapping[str, Any], *, reference_attached: bool) -> str:
    title = str(job.get("title") or job.get("source_name") or "produto WordPress").strip()
    source_url = str(job.get("source_product_url") or "").strip()
    official_url = str(job.get("source_official_url") or "").strip()
    context_lines = [
        f"Produto: {title}",
        f"Tipo: {'tema WordPress' if _kind(job) == 'theme' else 'plugin WordPress'}",
    ]
    if source_url:
        context_lines.append(f"Página da fonte: {source_url}")
    if official_url:
        context_lines.append(f"Página oficial: {official_url}")

    reference_requirement = (
        "- Use o anexo apenas como referência de composição; adapte o conteúdo visual para o produto atual."
        if reference_attached
        else "- Como não há mockup local anexado, siga rigorosamente a composição descrita acima."
    )
    return (
        "Agora gere SOMENTE a imagem principal do produto. Não responda com texto fora da geração da imagem.\n\n"
        + "\n".join(context_lines)
        + "\n\n"
        + _image_guidance(job, reference_attached=reference_attached)
        + "\n\nREQUISITOS FINAIS\n"
        "- Formato quadrado 1:1.\n"
        "- Fundo totalmente transparente, inclusive nas bordas e áreas vazias.\n"
        "- Alta qualidade para uso como capa de produto em e-commerce.\n"
        "- Use a identidade visual verdadeira do produto atual; não invente logotipo ou marca.\n"
        + reference_requirement
    )


def _set_existing_file_input(page: Any, reference_path: Path) -> bool:
    try:
        inputs = page.locator("input[type='file']")
        count = inputs.count()
    except Exception:
        return False

    for index in range(count - 1, -1, -1):
        try:
            inputs.nth(index).set_input_files(str(reference_path))
            return True
        except Exception:
            continue
    return False


def _attach_reference(page: Any, reference_path: Path, job_id: str) -> bool:
    if not reference_path.exists() or not reference_path.is_file():
        one_click._emit(
            job_id,
            f"Referência visual local não encontrada ({reference_path.name}); continuando a geração sem o mockup de referência.",
            step="chatgpt_image",
        )
        return False

    one_click._emit(
        job_id,
        f"Referência visual localizada: {reference_path.name}. Preparando anexo no ChatGPT…",
        step="chatgpt_image",
    )

    if _set_existing_file_input(page, reference_path):
        page.wait_for_timeout(1200)
        one_click._emit(
            job_id,
            f"Referência visual anexada com sucesso: {reference_path.name}.",
            step="chatgpt_image",
        )
        return True

    button_selectors = (
        "button[data-testid='composer-plus-btn']",
        "button[data-testid*='composer-add' i]",
        "button[data-testid*='attach' i]",
        "button[aria-label*='Add files' i]",
        "button[aria-label*='Attach' i]",
        "button[aria-label*='Adicionar arquivos' i]",
        "button[aria-label*='Anexar' i]",
        "button[aria-label*='Upload' i]",
    )

    for selector in button_selectors:
        try:
            button = page.locator(selector).first
            if not (button.count() and button.is_visible() and button.is_enabled()):
                continue
            try:
                with page.expect_file_chooser(timeout=2500) as chooser_info:
                    button.click()
                chooser_info.value.set_files(str(reference_path))
                page.wait_for_timeout(1200)
                one_click._emit(
                    job_id,
                    f"Referência visual anexada com sucesso: {reference_path.name}.",
                    step="chatgpt_image",
                )
                return True
            except Exception:
                page.wait_for_timeout(300)
                if _set_existing_file_input(page, reference_path):
                    page.wait_for_timeout(1200)
                    one_click._emit(
                        job_id,
                        f"Referência visual anexada com sucesso: {reference_path.name}.",
                        step="chatgpt_image",
                    )
                    return True
                break
        except Exception:
            continue

    menu_selectors = (
        "[role='menuitem']:has-text('Upload from computer')",
        "[role='menuitem']:has-text('Upload files')",
        "[role='menuitem']:has-text('Carregar do computador')",
        "[role='menuitem']:has-text('Fazer upload')",
        "[role='menuitem']:has-text('Adicionar fotos e arquivos')",
    )
    for selector in menu_selectors:
        try:
            item = page.locator(selector).first
            if not (item.count() and item.is_visible()):
                continue
            try:
                with page.expect_file_chooser(timeout=2500) as chooser_info:
                    item.click()
                chooser_info.value.set_files(str(reference_path))
                page.wait_for_timeout(1200)
                one_click._emit(
                    job_id,
                    f"Referência visual anexada com sucesso: {reference_path.name}.",
                    step="chatgpt_image",
                )
                return True
            except Exception:
                page.wait_for_timeout(300)
                if _set_existing_file_input(page, reference_path):
                    page.wait_for_timeout(1200)
                    one_click._emit(
                        job_id,
                        f"Referência visual anexada com sucesso: {reference_path.name}.",
                        step="chatgpt_image",
                    )
                    return True
        except Exception:
            continue

    one_click._emit(
        job_id,
        f"Não foi possível anexar {reference_path.name}; continuando a geração sem o mockup de referência.",
        step="chatgpt_image",
    )
    return False


def _patched_send_message(page: Any, prompt: str, job_id: str) -> tuple[int, set[str]]:
    if _BASE_SEND_MESSAGE is None:
        raise RuntimeError("Política criativa ainda não foi instalada.")

    final_prompt = str(prompt or "")
    try:
        job = additions._row(job_id)
    except Exception:
        job = {"kind": "plugin", "source_name": "produto WordPress"}

    if _is_image_request(final_prompt):
        reference = _reference_path(job)
        reference_attached = _attach_reference(page, reference, job_id)
        final_prompt = _image_only_prompt(job, reference_attached=reference_attached)

    return _BASE_SEND_MESSAGE(page, final_prompt, job_id)


def install_addition_product_creative_policy() -> None:
    global _INSTALLED, _BASE_PROMPT, _BASE_SEND_MESSAGE
    if _INSTALLED:
        return

    _BASE_PROMPT = additions._prompt
    _BASE_SEND_MESSAGE = one_click._send_message
    additions._prompt = _patched_prompt
    one_click._send_message = _patched_send_message
    _INSTALLED = True

    from app.addition_two_stage_creation_policy import install_addition_two_stage_creation_policy

    install_addition_two_stage_creation_policy()
