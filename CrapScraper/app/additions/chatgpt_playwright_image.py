from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.additions.creative import image_prompt
from app.additions.chatgpt_image_detection_runtime import _image_candidate_key
from app.additions.chatgpt_playwright import (
    ChatGPTPlaywrightError,
    _LOCK,
    _browser,
    _candidate_images,
    _composer,
    _ensure_authenticated,
    _looks_like_auth_wall,
    _normalize_image_bytes,
    _open_job_conversation,
    _read_image_from_locator,
    _timeout_seconds,
    _update_job_state,
    image_valid,
    project_name,
)


def _submit_image_prompt(page: Any, prompt: str) -> None:
    composer = _composer(page, 7000)
    if composer is None:
        _ensure_authenticated(page)
        composer = _composer(page, 3000)
    if composer is None:
        raise ChatGPTPlaywrightError("Campo de mensagem do ChatGPT não encontrado.")
    composer.click()
    composer.fill(prompt)
    try:
        composer.press("Enter")
    except Exception:
        send = page.locator(
            "button[data-testid='send-button'], button[aria-label*='Enviar' i], button[aria-label*='Send' i]"
        ).first
        if not send.count():
            raise
        send.click()


def _diagnostic(page: Any, reason: str) -> str:
    try:
        from app.additions import chatgpt_playwright_compat as compat

        return str(compat._diagnostic(page, reason) or "")
    except Exception:
        return ""


def generate_image(job: dict[str, Any], root: Path) -> Path:
    """Generate and persist the product image without depending on one ChatGPT DOM role.

    The current ChatGPT image turn can render a perfectly valid image without
    data-message-author-role='assistant'. The resilient collector installed by
    chatgpt_image_detection_runtime scans large images in the conversation
    <main>, and this function compares stable occurrence keys instead of only
    raw src URLs.
    """
    with _LOCK, _browser() as page:
        _open_job_conversation(page, str(job["job_id"]))
        before_candidates = _candidate_images(page)
        before_keys = {_image_candidate_key(item) for item in before_candidates}
        before_count = len(before_candidates)

        prompt = (
            f"Continuando o cadastro de {job['product_name']} no projeto {project_name()}, gere AGORA a imagem principal.\n\n"
            + image_prompt(job)
            + "\n\nUse a ferramenta de geração de imagens do ChatGPT. Não responda apenas com uma descrição da imagem; produza a imagem de fato."
        )
        _submit_image_prompt(page, prompt)

        deadline = time.monotonic() + _timeout_seconds()
        selected: dict[str, Any] | None = None
        last_candidates: list[dict[str, Any]] = []
        stable_fresh_key = ""
        stable_cycles = 0

        while time.monotonic() < deadline:
            if _looks_like_auth_wall(page) and _composer(page, 1000) is None:
                raise ChatGPTPlaywrightError(
                    "Sessão ChatGPT expirou durante a geração da imagem. Execute o bootstrap novamente."
                )

            candidates = _candidate_images(page)
            last_candidates = candidates
            fresh = [item for item in candidates if _image_candidate_key(item) not in before_keys]

            # Fallback adicional: se a UI duplicou/reutilizou a mesma src, um
            # aumento da quantidade de imagens grandes ainda prova que surgiu
            # uma nova imagem no turno atual.
            if not fresh and len(candidates) > before_count:
                fresh = candidates[before_count:]

            if fresh:
                candidate = fresh[-1]
                key = _image_candidate_key(candidate)
                if key == stable_fresh_key:
                    stable_cycles += 1
                else:
                    stable_fresh_key = key
                    stable_cycles = 0
                # Um ciclo de estabilidade evita capturar placeholder/transição,
                # mas não espera o botão Stop desaparecer, que pode ficar obsoleto.
                if stable_cycles >= 1:
                    selected = candidate
                    break
            time.sleep(0.8)

        if selected is None:
            diagnostic = _diagnostic(page, "image_response_timeout")
            suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
            visible = len(last_candidates)
            raise ChatGPTPlaywrightError(
                "ChatGPT respondeu, mas o CrapScraper não conseguiu identificar a nova imagem gerada na conversa. "
                f"Imagens grandes detectadas no fim: {visible}." + suffix
            )

        raw = _read_image_from_locator(page, selected)
        target = _normalize_image_bytes(raw, Path(root), str(job["job_id"]))
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            image_ready=True,
            image_path=str(target),
            image_generated_at=int(time.time()),
            image_candidate_src=str(selected.get("src") or "")[:1000],
        )
        return target


__all__ = ["generate_image", "image_valid"]
