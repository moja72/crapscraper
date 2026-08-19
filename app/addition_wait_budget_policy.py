from __future__ import annotations

import hashlib
import time
from typing import Any

import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_conversation_capture_policy as capture
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple


_INSTALLED = False


def _bounded_description_timeout(value: int | None) -> int:
    try:
        parsed = int(value or 120)
    except Exception:
        parsed = 120
    return min(max(parsed, 1), 120)


def _bounded_image_timeout(value: int | None) -> int:
    try:
        parsed = int(value or 240)
    except Exception:
        parsed = 240
    return min(max(parsed, 1), 240)


def _wait_generated_image_budget(
    context: Any,
    page: Any,
    before: set[str],
    job_id: str,
    url: str,
    *,
    timeout_seconds: int,
) -> tuple[Any, str]:
    timeout_seconds = _bounded_image_timeout(timeout_seconds)
    started = time.time()
    deadline = started + timeout_seconds
    next_status_at = 30.0
    current = page
    _reference, reference_sha = final_validation._reference_hash(job_id)
    announced_candidate = False
    announced_read = False
    retry_used = False

    while time.time() < deadline:
        if not reconnect._page_is_alive(current):
            current = reconnect._pick_page(context)
            current = reconnect._ensure_project_page_resilient(
                context, current, job_id, url, timeout_seconds=60
            )

        elapsed = time.time() - started
        busy = simple._assistant_busy(current)
        candidates = [
            item
            for item in capture._image_candidates(current)
            if str(item.get("src") or "") not in before
            and capture._image_candidate_score(item) >= 0
        ]
        candidates.sort(key=capture._image_candidate_score, reverse=True)

        if candidates and elapsed >= 8:
            if not announced_candidate:
                one_click._emit(
                    job_id,
                    "Imagem do turno do assistente detectada no Chat 2; aguardando o término da geração para capturar os bytes finais…",
                    step="chatgpt_image",
                    progress=68,
                )
                announced_candidate = True

            if not busy:
                for candidate in candidates[:4]:
                    source = str(candidate.get("src") or "")
                    data_url = capture._extract_image_data_url(current, source)
                    raw = capture._decode_data_url(data_url)
                    if not raw:
                        continue
                    current_sha = hashlib.sha256(raw).hexdigest()
                    if reference_sha and current_sha == reference_sha:
                        continue
                    if len(raw) < 20_000:
                        continue
                    one_click._emit(
                        job_id,
                        f"Imagem final do Chat 2 capturada e validada em memória ({len(raw):,} bytes).",
                        step="chatgpt_image",
                        progress=74,
                    )
                    return current, data_url

                if not announced_read:
                    one_click._emit(
                        job_id,
                        "A imagem final está visível, mas ainda não pôde ser lida em bytes; mantendo a captura autenticada ativa…",
                        step="chatgpt_image",
                        progress=70,
                    )
                    announced_read = True

        if (
            not retry_used
            and elapsed >= 20
            and not busy
            and final_validation._is_generation_error_visible(current)
            and final_validation._click_retry(current)
        ):
            retry_used = True
            before.update(
                str(item.get("src") or "") for item in capture._image_candidates(current)
            )
            one_click._emit(
                job_id,
                "O ChatGPT exibiu erro de geração; Repetir foi acionado automaticamente e o Chat 2 continua sendo monitorado.",
                step="chatgpt_image",
                progress=66,
            )
            announced_candidate = False
            announced_read = False

        if elapsed >= next_status_at:
            one_click._emit(
                job_id,
                f"Chat 2 ainda gerando/processando a imagem; nova conferência automática em andamento ({int(elapsed)}s/{timeout_seconds}s).",
                step="chatgpt_image",
                progress=66,
            )
            next_status_at += 30.0

        time.sleep(1.0)

    raise RuntimeError(
        "A imagem foi solicitada no Chat 2, mas o CrapScraper não conseguiu capturar a geração final dentro de 4 minutos."
    )


def install_addition_wait_budget_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    capture._wait_generated_image = _wait_generated_image_budget
    reconnect._wait_new_image_resilient = _wait_generated_image_budget
    _INSTALLED = True
