from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Mapping

import app.addition_conversation_capture_policy as capture
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_RUN_TWO_CHATS: Callable[[str], dict[str, Any]] | None = None
_BASE_IMAGE_PROMPT: Callable[..., str] | None = None
_REFERENCE_FAILURE_MARKERS = (
    "Referência visual obrigatória não encontrada",
    "Não foi possível anexar a referência visual obrigatória",
)


def _sequential_fallback() -> Callable[[str], dict[str, Any]]:
    runner = getattr(capture, "_ORIGINAL_RUN_TWO_CHATS", None)
    if not callable(runner):
        raise RuntimeError("Fluxo de fallback sem referência visual não está disponível.")
    return runner


def _reference_for_job(job_id: str) -> Path:
    return creative._reference_path(additions._row(job_id))


def _accepts_reference_attached(prompt: Callable[..., str]) -> bool:
    """Detecta wrappers novos e antigos sem usar TypeError como controle de fluxo."""
    try:
        signature = inspect.signature(prompt)
    except (TypeError, ValueError):
        return False
    if "reference_attached" in signature.parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _without_attachment_claims(prompt: str) -> str:
    """Evita dizer ao ChatGPT que há um mockup anexado quando a execução seguiu sem arquivo local."""
    text = str(prompt or "")
    replacements = (
        (
            "Use o arquivo anexado apenas como referência de mockup. ",
            "Não há mockup local anexado nesta execução. ",
        ),
        (
            "Use o arquivo anexado apenas como referência da caixa 3D. ",
            "Não há mockup local anexado nesta execução. ",
        ),
        (
            "Use o arquivo anexado 'exemplo tema.webp' SOMENTE como referência de composição, proporção, mockup e acabamento. ",
            "Não há mockup local anexado nesta execução; siga a composição, proporção e acabamento descritos no pedido. ",
        ),
        (
            "Use o arquivo anexado 'exemplo plugin.webp' SOMENTE como referência de composição, proporção da caixa 3D e acabamento. ",
            "Não há mockup local anexado nesta execução; siga a composição, proporção da caixa 3D e acabamento descritos no pedido. ",
        ),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _image_prompt_with_optional_reference(
    job: Mapping[str, Any],
    *,
    reference_attached: bool = True,
) -> str:
    """Normaliza o contrato final de prompt após todas as policies de entrega/validação."""
    if _BASE_IMAGE_PROMPT is None:
        raise RuntimeError("Prompt visual base ainda não foi capturado.")

    if _accepts_reference_attached(_BASE_IMAGE_PROMPT):
        prompt = _BASE_IMAGE_PROMPT(job, reference_attached=reference_attached)
    else:
        prompt = _BASE_IMAGE_PROMPT(job)

    if not reference_attached:
        prompt = _without_attachment_claims(prompt)
    return str(prompt or "")


def _run_with_optional_reference(job_id: str) -> dict[str, Any]:
    """Mantém a geração paralela quando há mockup e usa o fluxo seguro quando não há."""
    if _BASE_RUN_TWO_CHATS is None:
        raise RuntimeError("Fluxo paralelo de geração ainda não foi capturado.")

    reference = _reference_for_job(job_id)
    if not reference.exists() or not reference.is_file():
        one_click._emit(
            job_id,
            f"Referência visual local não encontrada ({reference.name}); continuando sem mockup local.",
            step="chatgpt_image",
            progress=7,
        )
        return _sequential_fallback()(job_id)

    try:
        return _BASE_RUN_TWO_CHATS(job_id)
    except RuntimeError as error:
        message = str(error or "")
        if not any(marker in message for marker in _REFERENCE_FAILURE_MARKERS):
            raise

        one_click._emit(
            job_id,
            f"A referência {reference.name} não pôde ser usada no fluxo paralelo; continuando sem mockup local.",
            step="chatgpt_image",
            progress=7,
        )
        return _sequential_fallback()(job_id)


def install_addition_parallel_reference_fallback_policy() -> None:
    global _INSTALLED, _BASE_RUN_TWO_CHATS, _BASE_IMAGE_PROMPT
    if _INSTALLED:
        return

    # Esta policy é instalada após product_contract + image_delivery. Capturamos o
    # prompt realmente ativo nesse ponto e expomos uma assinatura estável para o
    # fluxo simples/two-stage: (job, *, reference_attached=bool).
    _BASE_IMAGE_PROMPT = creative._image_only_prompt
    creative._image_only_prompt = _image_prompt_with_optional_reference

    _BASE_RUN_TWO_CHATS = simple._run_two_chats
    simple._run_two_chats = _run_with_optional_reference
    _INSTALLED = True
