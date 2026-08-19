from __future__ import annotations

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


def _image_guidance(job: Mapping[str, Any]) -> str:
    if _kind(job) == "theme":
        return (
            "REFERÊNCIA VISUAL OBRIGATÓRIA — TEMA\n"
            "Quando gerar a imagem, use o arquivo anexado 'exemplo tema.webp' como referência visual principal. "
            "A imagem final deve ser quadrada 1:1, com FUNDO TRANSPARENTE e o mais parecida possível com a "
            "referência em composição, acabamento, proporções, iluminação e apresentação do mockup. "
            "Mostre explicitamente o tema nas telas de um computador e de um celular; a posição do celular pode "
            "mudar, mas as duas telas precisam ficar claramente visíveis. O computador deve usar um monitor Apple. "
            "Nas telas, represente visualmente o tema real deste produto com base nas informações/páginas fornecidas, "
            "sem inventar uma identidade diferente. Não use cenário ou fundo sólido e não corte os dispositivos."
        )

    return (
        "REFERÊNCIA VISUAL OBRIGATÓRIA — PLUGIN\n"
        "Quando gerar a imagem, use o arquivo anexado 'exemplo plugin.webp' como referência visual principal. "
        "Refaça a caixa mantendo proporção e linguagem visual o mais próximas possível da referência, em imagem "
        "quadrada 1:1 e com FUNDO TRANSPARENTE. A caixa deve ser profissional, bem construída e mostrar pelo menos "
        "3 lados/faces visíveis; o ângulo pode variar, desde que preserve a sensação tridimensional e a qualidade do "
        "mockup original. Use a logo real do plugin e cores associadas à identidade do produto, sem inventar outra "
        "marca. Use a fonte Quicksand nas informações da embalagem e deixe claramente visível exatamente o texto "
        "'Vitalício | Ilimitado | Atualizado'. Evite textos adicionais pequenos ou ilegíveis, não use cenário e "
        "não corte a caixa."
    )


def _patched_prompt(job: Mapping[str, Any]) -> str:
    if _BASE_PROMPT is None:
        raise RuntimeError("Política criativa ainda não foi instalada.")
    base = _BASE_PROMPT(job)
    return (
        base
        + "\n\n"
        + _short_description_guidance()
        + "\n\n"
        + _image_guidance(job)
        + "\n\nA imagem de referência anexada serve como modelo visual de composição e acabamento; "
        "adapte apenas a identidade, logo, cores e conteúdo visual para o produto atual."
    )


def _is_image_request(prompt: str) -> bool:
    normalized = str(prompt or "").lower()
    return (
        "referência visual obrigatória" in normalized
        or "agora gere somente uma imagem" in normalized
        or "gere também uma imagem quadrada" in normalized
        or "imagem de capa quadrada 1:1" in normalized
    )


def _image_only_prompt(job: Mapping[str, Any]) -> str:
    title = str(job.get("title") or job.get("source_name") or "produto WordPress").strip()
    return (
        f"Agora gere SOMENTE a imagem final do produto {title}. Não responda com texto fora da geração da imagem.\n\n"
        + _image_guidance(job)
        + "\n\nREQUISITOS FINAIS\n"
        "- Formato quadrado 1:1.\n"
        "- Fundo totalmente transparente, inclusive nas bordas e áreas vazias.\n"
        "- Alta qualidade para uso como capa de produto em e-commerce.\n"
        "- Preserve a aparência geral, o nível de acabamento e a lógica de composição da imagem de referência.\n"
        "- Use a identidade visual verdadeira do produto atual; não invente logotipo ou marca."
    )


def _attach_reference(page: Any, reference_path: Path, job_id: str) -> bool:
    if not reference_path.exists() or not reference_path.is_file():
        one_click._emit(
            job_id,
            f"Referência visual não encontrada em {reference_path}. A geração seguirá sem o anexo.",
            step="chatgpt_image",
        )
        return False

    try:
        inputs = page.locator("input[type='file']")
        count = inputs.count()

        if count <= 0:
            for selector in (
                "button[aria-label*='Attach' i]",
                "button[aria-label*='Anexar' i]",
                "button[data-testid*='attach' i]",
                "button[data-testid*='composer-add' i]",
            ):
                button = page.locator(selector).first
                try:
                    if button.count() and button.is_visible() and button.is_enabled():
                        button.click()
                        page.wait_for_timeout(250)
                        break
                except Exception:
                    continue
            inputs = page.locator("input[type='file']")
            count = inputs.count()

        if count <= 0:
            raise RuntimeError("campo de upload de arquivo não encontrado")

        inputs.nth(count - 1).set_input_files(str(reference_path))
        page.wait_for_timeout(1400)
        one_click._emit(
            job_id,
            f"Referência visual anexada: {reference_path.name}.",
            step="chatgpt_image",
        )
        return True
    except Exception as error:
        one_click._emit(
            job_id,
            f"Não foi possível anexar {reference_path.name}: {type(error).__name__}. A geração seguirá sem o anexo.",
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

    if "agora gere somente uma imagem" in final_prompt.lower():
        final_prompt = _image_only_prompt(job)

    if _is_image_request(final_prompt):
        _attach_reference(page, _reference_path(job), job_id)

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
