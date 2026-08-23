from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.addition_conversation_capture_policy as capture
import app.addition_one_click_policy as one_click
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_RUN_TWO_CHATS: Callable[[str], dict[str, Any]] | None = None
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
    global _INSTALLED, _BASE_RUN_TWO_CHATS
    if _INSTALLED:
        return

    _BASE_RUN_TWO_CHATS = simple._run_two_chats
    simple._run_two_chats = _run_with_optional_reference
    _INSTALLED = True
