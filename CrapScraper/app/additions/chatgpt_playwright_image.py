from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.additions.creative import image_prompt
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
        send = page.locator("button[data-testid='send-button'], button[aria-label*='Enviar' i], button[aria-label*='Send' i]").first
        if not send.count():
            raise
        send.click()


def generate_image(job: dict[str, Any], root: Path) -> Path:
    """Gera a imagem no mesmo chat do produto sem exigir texto do assistente.

    Em algumas respostas de geração de imagem o ChatGPT não produz texto estável;
    por isso aguardamos diretamente um novo elemento de imagem renderizado.
    """
    with _LOCK, _browser() as page:
        _open_job_conversation(page, str(job["job_id"]))
        before = {str(item.get("src") or "") for item in _candidate_images(page)}
        prompt = (
            f"Continuando o cadastro de {job['product_name']} no projeto {project_name()}, gere AGORA a imagem principal.\n\n"
            + image_prompt(job)
            + "\n\nUse a ferramenta de geração de imagens do ChatGPT. Não responda apenas com uma descrição da imagem; produza a imagem de fato."
        )
        _submit_image_prompt(page, prompt)

        deadline = time.monotonic() + _timeout_seconds()
        selected = None
        while time.monotonic() < deadline:
            if _looks_like_auth_wall(page) and _composer(page, 1000) is None:
                raise ChatGPTPlaywrightError("Sessão ChatGPT expirou durante a geração da imagem. Execute o bootstrap novamente.")
            candidates = _candidate_images(page)
            fresh = [item for item in candidates if str(item.get("src") or "") not in before]
            if fresh:
                selected = fresh[-1]
                break
            time.sleep(1.0)
        if selected is None:
            raise ChatGPTPlaywrightError("ChatGPT respondeu, mas nenhuma imagem gerada apareceu na conversa.")

        raw = _read_image_from_locator(page, selected)
        target = _normalize_image_bytes(raw, Path(root), str(job["job_id"]))
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            image_ready=True,
            image_path=str(target),
            image_generated_at=int(time.time()),
        )
        return target


__all__ = ["generate_image", "image_valid"]
