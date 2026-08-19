from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_conversation_capture_policy as capture
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_parallel_generation_policy as parallel
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False

# These are hard ceilings, not waits. The loop checks the mapped chats continuously.
_DESCRIPTION_TIMEOUT_SECONDS = 300  # 5 minutes
_IMAGE_TIMEOUT_SECONDS = 600        # 10 minutes
_IMAGE_RECOVERY_SECONDS = 300       # extra recovery window after fallback/retry when needed
_DESCRIPTION_STATUS_SECONDS = 10
_IMAGE_STATUS_SECONDS = 15
_LOOP_SLEEP_SECONDS = 0.65


def _duration_label(seconds: float) -> str:
    value = max(0, int(seconds))
    minutes, remainder = divmod(value, 60)
    if minutes and remainder:
        return f"{minutes}m {remainder}s"
    if minutes:
        return f"{minutes}m"
    return f"{remainder}s"


def _focus(page: Any) -> None:
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        page.wait_for_timeout(120)
    except Exception:
        pass


def _rendered_image_data_url(page: Any, candidate: Mapping[str, Any], reference_sha: str) -> str:
    """Capture the exact rendered image by currentSrc/src, avoiding fragile DOM indexes."""
    source = str(candidate.get("src") or "").strip()
    if not source:
        return ""
    try:
        images = page.locator("img")
        count = images.count()
    except Exception:
        return ""

    for index in range(count - 1, -1, -1):
        try:
            locator = images.nth(index)
            if not locator.count() or not locator.is_visible():
                continue
            current = str(
                locator.evaluate("img => String(img.currentSrc || img.src || '')") or ""
            ).strip()
            if current != source:
                continue
            raw = locator.screenshot(type="png")
        except Exception:
            continue
        if not raw or len(raw) < 20_000:
            continue
        current_sha = hashlib.sha256(raw).hexdigest()
        if reference_sha and current_sha == reference_sha:
            continue
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    return ""


def _adaptive_image_data_url(page: Any, before: set[str], reference_sha: str) -> str:
    """Prefer final image bytes immediately; use rendered screenshot once generation is no longer busy."""
    _focus(page)
    busy = simple._assistant_busy(page)
    try:
        candidates = list(binding._assistant_image_candidates(page, before) or [])
    except Exception:
        candidates = []

    for candidate in candidates[:10]:
        source = str(candidate.get("src") or "").strip()
        if not source or source in before:
            continue

        # Do not block byte capture just because ChatGPT still exposes a stop/progress control.
        # If the full asset is already retrievable, it is safer and faster than waiting for UI state.
        try:
            data_url = capture._extract_image_data_url(page, source)
            raw = capture._decode_data_url(data_url)
        except Exception:
            data_url = ""
            raw = b""
        if len(raw) >= 20_000:
            current_sha = hashlib.sha256(raw).hexdigest()
            if not reference_sha or current_sha != reference_sha:
                return data_url

        # A screenshot may freeze a progressive frame, so only use it after the assistant is idle.
        if not busy:
            rendered = _rendered_image_data_url(page, candidate, reference_sha)
            if rendered:
                return rendered
    return ""


def _extend_image_deadline(current_deadline: float, hard_deadline: float) -> float:
    return min(hard_deadline, max(current_deadline, time.time() + _IMAGE_RECOVERY_SECONDS))


def _run_adaptive_parallel_chats(job_id: str) -> dict[str, Any]:
    capture._ensure_tracking_schema()
    job = additions._row(job_id)
    reference = creative._reference_path(job)
    if not reference.exists():
        raise RuntimeError(
            f"Referência visual obrigatória não encontrada em {reference}. "
            "Confirme Exemplo Plugin.webp e Exemplo Tema.webp em app/static."
        )

    description_ready = bool(binding._valid_existing_description(job))
    image_ready = bool(parallel._valid_existing_image(job_id, job))
    if description_ready:
        one_click._emit(
            job_id,
            "A descrição validada já existe; o Chat 1 será reaproveitado.",
            step="description_ready",
            progress=40,
        )
    if image_ready:
        one_click._emit(
            job_id,
            "A imagem final validada já existe; o Chat 2 será reaproveitado.",
            step="image_ready",
            progress=78,
        )
    if description_ready and image_ready:
        return additions._row(job_id)

    project_url = coproducao._project_url()
    endpoint, profile_dir = cdp._ensure_debug_browser(project_url)
    one_click._emit(
        job_id,
        f"Chrome conectado via CDP. Perfil: {profile_dir.name}.",
        step="chatgpt",
        progress=8,
    )
    coproducao._wait_login_then_project(job_id, endpoint, project_url)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        raise RuntimeError(
            f"Playwright indisponível para automação do ChatGPT: {type(error).__name__}"
        ) from None

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=30_000)
        contexts = list(browser.contexts)
        if not contexts:
            raise RuntimeError("Chrome autenticado, mas nenhum contexto de navegação foi encontrado.")
        context = contexts[0]
        base_page = reconnect._pick_page(context)
        description_page = None
        image_page = None
        description_started = 0.0
        image_started = 0.0
        description_deadline = 0.0
        image_deadline = 0.0
        image_hard_deadline = 0.0
        next_description_log = float(_DESCRIPTION_STATUS_SECONDS)
        next_image_log = float(_IMAGE_STATUS_SECONDS)
        image_before: set[str] = set()
        fallback_sent = False
        retry_logged = False
        official_capture: Path | None = None
        last_description = ""
        description_stable_since = 0.0

        one_click._emit(
            job_id,
            "Abrindo os dois chats em paralelo com monitoramento contínuo e limites ampliados.",
            step="chatgpt",
            progress=10,
        )

        if not description_ready:
            description_page = simple._fresh_project_chat(
                context, base_page, job_id, project_url, "Chat 1/2 — descrição"
            )
            one_click._emit(
                job_id,
                "Chat 1/2: enviando somente o pedido da breve descrição.",
                step="chatgpt_description",
                progress=15,
            )
            description_page, _before_count, _before_images = reconnect._send_message_resilient(
                context,
                description_page,
                binding._description_only_prompt(additions._row(job_id)),
                job_id,
                project_url,
            )
            description_started = time.time()
            description_deadline = description_started + _DESCRIPTION_TIMEOUT_SECONDS

        if not image_ready:
            image_page = context.new_page()
            image_page = simple._fresh_project_chat(
                context, image_page, job_id, project_url, "Chat 2/2 — imagem"
            )
            one_click._emit(
                job_id,
                f"Chat 2/2: anexando {reference.name} e iniciando a geração sem esperar o Chat 1 terminar.",
                step="chatgpt_image",
                progress=50,
            )
            if not creative._attach_reference(image_page, reference, job_id):
                raise RuntimeError(
                    f"Não foi possível anexar a referência visual obrigatória {reference.name}."
                )
            image_page, _image_count, image_before = reconnect._send_message_resilient(
                context,
                image_page,
                parallel._parallel_image_prompt(additions._row(job_id)),
                job_id,
                project_url,
            )
            image_started = time.time()
            image_deadline = image_started + _IMAGE_TIMEOUT_SECONDS
            image_hard_deadline = image_started + _IMAGE_TIMEOUT_SECONDS + _IMAGE_RECOVERY_SECONDS

        one_click._emit(
            job_id,
            "Chats enviados. Captura contínua ativa: descrição até 5 min e imagem até 10 min; "
            "os limites são máximos e o fluxo avança imediatamente quando cada resultado fica pronto.",
            step="chatgpt",
            progress=22,
        )
        _reference, reference_sha = final_validation._reference_hash(job_id)

        while not (description_ready and image_ready):
            now = time.time()
            job = additions._row(job_id)

            if not description_ready and description_page is not None:
                chat_url = str(job.get("description_chat_url") or "")
                description_page = binding._bind_chat_page(
                    context,
                    description_page,
                    chat_url,
                    project_url,
                    job_id,
                    "Chat 1",
                )
                _focus(description_page)
                candidates = list(binding._description_candidates(description_page) or [])
                candidate = candidates[0] if candidates else ""
                busy = simple._assistant_busy(description_page)
                if candidate:
                    if candidate != last_description:
                        last_description = candidate
                        description_stable_since = now
                    stable_for = now - description_stable_since
                    if not busy or stable_for >= 1.5:
                        binding._persist_description(job_id, candidate)
                        description_ready = True
                        job = additions._row(job_id)
                if not description_ready:
                    elapsed = now - description_started
                    if now >= description_deadline:
                        raise RuntimeError(
                            "O Chat 1 não entregou uma descrição final capturável dentro do limite máximo de 5 minutos."
                        )
                    if elapsed >= next_description_log:
                        one_click._emit(
                            job_id,
                            f"Chat 1 em monitoramento contínuo: {chat_url or 'conversa mapeada'} "
                            f"({_duration_label(elapsed)}/{_duration_label(_DESCRIPTION_TIMEOUT_SECONDS)}).",
                            step="chatgpt_description",
                            progress=24,
                        )
                        next_description_log += _DESCRIPTION_STATUS_SECONDS

            if not image_ready and image_page is not None:
                chat_url = str(job.get("image_chat_url") or "")
                image_page = binding._bind_chat_page(
                    context,
                    image_page,
                    chat_url,
                    project_url,
                    job_id,
                    "Chat 2",
                )
                _focus(image_page)
                data_url = _adaptive_image_data_url(image_page, image_before, reference_sha)
                if data_url:
                    binding._persist_image(job_id, data_url)
                    image_ready = True
                else:
                    refusal = parallel._assistant_refusal_text(image_page)
                    retried = bool(getattr(image_page, "_cs_generic_image_retry_clicked", False))
                    if retried and not retry_logged:
                        retry_logged = True
                        image_deadline = _extend_image_deadline(image_deadline, image_hard_deadline)
                        one_click._emit(
                            job_id,
                            "Chat 2 acionou Repetir automaticamente; a janela de recuperação da imagem foi preservada.",
                            step="chatgpt_image",
                            progress=66,
                        )

                    if refusal and not fallback_sent and not simple._assistant_busy(image_page):
                        fallback_sent = True
                        current_job = additions._row(job_id)
                        official_url = str(current_job.get("source_official_url") or "")
                        if official_url:
                            official_capture = parallel._capture_official_visual(
                                context, job_id, official_url
                            )
                            if official_capture is not None:
                                one_click._emit(
                                    job_id,
                                    "Chat 2 entrou no fallback; anexando captura local da fonte e reenviando sem depender da URL.",
                                    step="chatgpt_image",
                                    progress=66,
                                )
                                creative._attach_reference(image_page, official_capture, job_id)
                        try:
                            image_before.update(
                                str(item.get("src") or "")
                                for item in binding._assistant_image_candidates(image_page, image_before)
                            )
                        except Exception:
                            pass
                        image_page, _fallback_count, fallback_before = reconnect._send_message_resilient(
                            context,
                            image_page,
                            parallel._fallback_image_prompt(
                                current_job,
                                has_official_capture=official_capture is not None,
                            ),
                            job_id,
                            project_url,
                        )
                        image_before.update(fallback_before)
                        image_deadline = _extend_image_deadline(image_deadline, image_hard_deadline)
                        one_click._emit(
                            job_id,
                            "Fallback do Chat 2 enviado; nova geração continua sendo monitorada sem reiniciar o fluxo.",
                            step="chatgpt_image",
                            progress=67,
                        )

                    elapsed = now - image_started
                    if now >= image_deadline:
                        raise RuntimeError(
                            "O Chat 2 não entregou uma imagem final capturável dentro do limite máximo de "
                            f"{_duration_label(image_deadline - image_started)}."
                        )
                    if elapsed >= next_image_log:
                        try:
                            candidate_count = len(binding._assistant_image_candidates(image_page, image_before) or [])
                        except Exception:
                            candidate_count = 0
                        suffix = (
                            f" {candidate_count} candidato(s) visual(is) novo(s) detectado(s); tentando extrair os bytes finais."
                            if candidate_count
                            else " Aguardando a imagem final aparecer na conversa."
                        )
                        one_click._emit(
                            job_id,
                            f"Chat 2 em monitoramento contínuo: {chat_url or 'conversa mapeada'} "
                            f"({_duration_label(elapsed)}/{_duration_label(image_deadline - image_started)}).{suffix}",
                            step="chatgpt_image",
                            progress=68,
                        )
                        next_image_log += _IMAGE_STATUS_SECONDS

            time.sleep(_LOOP_SLEEP_SECONDS)

    return additions._row(job_id)


def install_addition_adaptive_chat_monitor_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Keep legacy constants aligned for any helper/fallback path that still reads them.
    binding._DESCRIPTION_TIMEOUT_SECONDS = _DESCRIPTION_TIMEOUT_SECONDS
    binding._IMAGE_TIMEOUT_SECONDS = _IMAGE_TIMEOUT_SECONDS
    binding._DESCRIPTION_POLL_SECONDS = _DESCRIPTION_STATUS_SECONDS
    binding._IMAGE_POLL_SECONDS = _IMAGE_STATUS_SECONDS
    parallel._DESCRIPTION_TIMEOUT_SECONDS = _DESCRIPTION_TIMEOUT_SECONDS
    parallel._IMAGE_TIMEOUT_SECONDS = _IMAGE_TIMEOUT_SECONDS
    parallel._DESCRIPTION_POLL_SECONDS = _DESCRIPTION_STATUS_SECONDS
    parallel._IMAGE_POLL_SECONDS = _IMAGE_STATUS_SECONDS

    simple._run_two_chats = _run_adaptive_parallel_chats
    _INSTALLED = True
