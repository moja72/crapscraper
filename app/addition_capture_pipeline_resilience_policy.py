from __future__ import annotations

import hashlib
import inspect
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import app.addition_adaptive_chat_monitor_policy as adaptive
import app.addition_chat_binding_policy as binding
import app.addition_chatgpt_cdp_fix as cdp
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_chatgpt_coproducao_policy as coproducao
import app.addition_conversation_capture_policy as capture
import app.addition_one_click_policy as one_click
import app.addition_operational_ui_policy as additions_ui
import app.addition_product_creative_policy as creative
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_REQUEST_ADD: Callable[..., dict[str, Any]] | None = None
_BASE_START_QUEUE: Callable[[], dict[str, Any]] | None = None

# Limites máximos. O monitor continua verificando continuamente e avança assim
# que o conteúdo estiver disponível; estes valores não criam uma espera fixa.
_DESCRIPTION_TIMEOUT_SECONDS = 600  # 10 minutos
_IMAGE_TIMEOUT_SECONDS = 960        # 16 minutos
_DESCRIPTION_STATUS_SECONDS = 10
_IMAGE_STATUS_SECONDS = 15
_LOOP_SLEEP_SECONDS = 0.65
_EXISTING_CHAT_REPROMPT_SECONDS = 30


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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
        page.wait_for_timeout(100)
    except Exception:
        pass


def _prompt_accepts_reference_attached(builder: Callable[..., str]) -> bool:
    try:
        signature = inspect.signature(builder)
    except (TypeError, ValueError):
        return False
    if "reference_attached" in signature.parameters:
        return True
    return any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _strip_attachment_claims(prompt: str) -> str:
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


def _image_prompt(job: Mapping[str, Any], *, reference_attached: bool) -> str:
    """Usa o prompt visual ativo sem afirmar que existe anexo quando não existe."""
    builder = creative._image_only_prompt
    if _prompt_accepts_reference_attached(builder):
        prompt = builder(job, reference_attached=reference_attached)
    else:
        prompt = builder(job)
    return str(prompt or "") if reference_attached else _strip_attachment_claims(str(prompt or ""))


def _reference_info(job: Mapping[str, Any]) -> tuple[Path, bool, str]:
    reference = creative._reference_path(job)
    exists = bool(reference.exists() and reference.is_file())
    reference_sha = ""
    if exists:
        try:
            reference_sha = hashlib.sha256(reference.read_bytes()).hexdigest()
        except OSError:
            reference_sha = ""
    return reference, exists, reference_sha


def _bind_or_open_chat(
    context: Any,
    current: Any,
    chat_url: str,
    project_url: str,
    job_id: str,
    label: str,
) -> tuple[Any, bool]:
    mapped = _clean(chat_url)
    if mapped:
        page = binding._bind_chat_page(
            context, current, mapped, project_url, job_id, label
        )
        one_click._emit(
            job_id,
            f"{label}: conversa já mapeada encontrada; tentando reaproveitar o resultado existente antes de gerar novamente.",
            step="chatgpt",
        )
        return page, True
    page = simple._fresh_project_chat(context, current, job_id, project_url, label)
    return page, False


def _run_resilient_two_chats(job_id: str) -> dict[str, Any]:
    """Retoma chats mapeados, aceita mockup opcional e captura a imagem mesmo com UI busy."""
    capture._ensure_tracking_schema()
    job = additions._row(job_id)
    reference, reference_exists, reference_sha = _reference_info(job)

    description_ready = bool(binding._valid_existing_description(job))
    image_ready = bool(__import__("app.addition_parallel_generation_policy", fromlist=["x"])._valid_existing_image(job_id, job))

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

    if not reference_exists:
        one_click._emit(
            job_id,
            f"Referência visual local {reference.name} ausente; a geração continuará sem mockup local.",
            step="chatgpt_image",
            progress=7,
        )

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
        description_started = time.time()
        image_started = time.time()
        description_sent = False
        image_sent = False
        description_was_mapped = False
        image_was_mapped = False
        next_description_log = float(_DESCRIPTION_STATUS_SECONDS)
        next_image_log = float(_IMAGE_STATUS_SECONDS)
        last_description = ""
        description_stable_since = 0.0
        image_before: set[str] = set()

        if not description_ready:
            current_job = additions._row(job_id)
            description_page, description_was_mapped = _bind_or_open_chat(
                context,
                base_page,
                _clean(current_job.get("description_chat_url")),
                project_url,
                job_id,
                "Chat 1/2 — descrição",
            )
            if not description_was_mapped:
                one_click._emit(
                    job_id,
                    "Chat 1/2: enviando somente o pedido da breve descrição.",
                    step="chatgpt_description",
                    progress=15,
                )
                description_page, _count, _images = reconnect._send_message_resilient(
                    context,
                    description_page,
                    binding._description_only_prompt(additions._row(job_id)),
                    job_id,
                    project_url,
                )
                description_sent = True
            description_started = time.time()

        if not image_ready:
            current_job = additions._row(job_id)
            image_page, image_was_mapped = _bind_or_open_chat(
                context,
                context.new_page(),
                _clean(current_job.get("image_chat_url")),
                project_url,
                job_id,
                "Chat 2/2 — imagem",
            )
            if not image_was_mapped:
                reference_attached = False
                if reference_exists:
                    try:
                        reference_attached = bool(
                            creative._attach_reference(image_page, reference, job_id)
                        )
                    except Exception:
                        reference_attached = False
                    if not reference_attached:
                        one_click._emit(
                            job_id,
                            f"Não foi possível anexar {reference.name}; continuando sem mockup local.",
                            step="chatgpt_image",
                            progress=50,
                        )
                prompt = _image_prompt(
                    additions._row(job_id), reference_attached=reference_attached
                )
                one_click._emit(
                    job_id,
                    "Chat 2/2: enviando o pedido da imagem; a captura começará assim que os bytes finais aparecerem.",
                    step="chatgpt_image",
                    progress=50,
                )
                image_page, _count, image_before = reconnect._send_message_resilient(
                    context, image_page, prompt, job_id, project_url
                )
                image_sent = True
            else:
                # No retry, a imagem já pode estar pronta na conversa. Não a marque
                # como "before": precisamos tentar capturá-la imediatamente.
                image_before = set()
            image_started = time.time()

        one_click._emit(
            job_id,
            "Monitoramento resiliente ativo: descrição até 10 min e imagem até 16 min. "
            "Os limites são máximos; o fluxo avança imediatamente quando o resultado fica capturável.",
            step="chatgpt",
            progress=22,
        )

        while not (description_ready and image_ready):
            now = time.time()
            job = additions._row(job_id)

            if not description_ready and description_page is not None:
                chat_url = _clean(job.get("description_chat_url"))
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

                elapsed = now - description_started
                if (
                    not description_ready
                    and description_was_mapped
                    and not description_sent
                    and elapsed >= _EXISTING_CHAT_REPROMPT_SECONDS
                    and not busy
                ):
                    one_click._emit(
                        job_id,
                        "Chat 1 mapeado ainda não contém uma descrição capturável; reenviando o pedido na mesma conversa.",
                        step="chatgpt_description",
                        progress=23,
                    )
                    description_page, _count, _images = reconnect._send_message_resilient(
                        context,
                        description_page,
                        binding._description_only_prompt(additions._row(job_id)),
                        job_id,
                        project_url,
                    )
                    description_sent = True

                if not description_ready:
                    if elapsed >= _DESCRIPTION_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 1 não entregou uma descrição final capturável dentro do limite máximo de "
                            f"{_duration_label(_DESCRIPTION_TIMEOUT_SECONDS)}."
                        )
                    if elapsed >= next_description_log:
                        one_click._emit(
                            job_id,
                            f"Chat 1 em monitoramento: {chat_url or 'conversa atual'} "
                            f"({_duration_label(elapsed)}/{_duration_label(_DESCRIPTION_TIMEOUT_SECONDS)}).",
                            step="chatgpt_description",
                            progress=24,
                        )
                        next_description_log += _DESCRIPTION_STATUS_SECONDS

            if not image_ready and image_page is not None:
                chat_url = _clean(job.get("image_chat_url"))
                image_page = binding._bind_chat_page(
                    context,
                    image_page,
                    chat_url,
                    project_url,
                    job_id,
                    "Chat 2",
                )
                _focus(image_page)

                # adaptive._adaptive_image_data_url tenta primeiro baixar os bytes
                # da imagem mesmo quando o ChatGPT ainda exibe stop/progresso.
                data_url = adaptive._adaptive_image_data_url(
                    image_page, image_before, reference_sha
                )
                if data_url:
                    binding._persist_image(job_id, data_url)
                    image_ready = True
                else:
                    busy = simple._assistant_busy(image_page)
                    elapsed = now - image_started
                    if (
                        image_was_mapped
                        and not image_sent
                        and elapsed >= _EXISTING_CHAT_REPROMPT_SECONDS
                        and not busy
                    ):
                        reference_attached = False
                        if reference_exists:
                            try:
                                reference_attached = bool(
                                    creative._attach_reference(image_page, reference, job_id)
                                )
                            except Exception:
                                reference_attached = False
                        prompt = _image_prompt(
                            additions._row(job_id),
                            reference_attached=reference_attached,
                        )
                        one_click._emit(
                            job_id,
                            "Chat 2 mapeado ainda não contém imagem capturável; reenviando o pedido na mesma conversa.",
                            step="chatgpt_image",
                            progress=66,
                        )
                        image_page, _count, before = reconnect._send_message_resilient(
                            context, image_page, prompt, job_id, project_url
                        )
                        image_before.update(before)
                        image_sent = True

                    if elapsed >= _IMAGE_TIMEOUT_SECONDS:
                        raise RuntimeError(
                            "O Chat 2 não entregou uma imagem final capturável dentro do limite máximo de "
                            f"{_duration_label(_IMAGE_TIMEOUT_SECONDS)}."
                        )
                    if elapsed >= next_image_log:
                        try:
                            candidate_count = len(
                                binding._assistant_image_candidates(image_page, image_before) or []
                            )
                        except Exception:
                            candidate_count = 0
                        suffix = (
                            f" {candidate_count} candidato(s) visual(is) detectado(s); tentando extrair os bytes finais agora."
                            if candidate_count
                            else " Aguardando a imagem final aparecer na conversa."
                        )
                        one_click._emit(
                            job_id,
                            f"Chat 2 em monitoramento: {chat_url or 'conversa atual'} "
                            f"({_duration_label(elapsed)}/{_duration_label(_IMAGE_TIMEOUT_SECONDS)}).{suffix}",
                            step="chatgpt_image",
                            progress=68,
                        )
                        next_image_log += _IMAGE_STATUS_SECONDS

            time.sleep(_LOOP_SLEEP_SECONDS)

    return additions._row(job_id)


def _image_file_ready(row: Mapping[str, Any]) -> bool:
    raw = _clean(row.get("image_path"))
    if not raw:
        return False
    try:
        return Path(raw).is_file()
    except OSError:
        return False


def _recoverable_capture_pending(row: Mapping[str, Any]) -> bool:
    """Reconhece um item que pode terminar a captura antes de entrar na fila."""
    if not bool(_safe_int(row.get("approval_active"), 1)):
        return False
    if _clean(row.get("queue_state")) not in {"error", "interrupted", "waiting", "ready"}:
        return False
    if additions_ui._prepared_local(row) or _image_file_ready(row):
        return False
    description_available = bool(
        _clean(row.get("short_description"))
        or _clean(row.get("description"))
        or _clean(row.get("description_chat_url"))
    )
    image_chat_available = bool(_clean(row.get("image_chat_url")))
    return description_available and image_chat_available


def _request_add_resilient(
    payload: Mapping[str, Any], manager: Any, *, retry: bool = False
) -> dict[str, Any]:
    """Aceita intenção de fila mesmo quando só falta recuperar captura persistida."""
    if _BASE_REQUEST_ADD is None:
        raise RuntimeError("Fluxo base da fila de adições indisponível.")

    # Retry já é end-to-end no gate atual; ele só precisa do runner resiliente.
    if retry:
        return _BASE_REQUEST_ADD(payload, manager, retry=True)

    job_ids = additions_ui._normalize_job_ids(payload)
    recoverable: list[str] = []
    regular: list[str] = []

    for job_id in job_ids:
        row = additions_ui._job_snapshot(job_id)
        if _recoverable_capture_pending(row) and not _safe_int(row.get("active_attempt_id")):
            recoverable.append(job_id)
        else:
            regular.append(job_id)

    recovery_started = 0
    for job_id in recoverable:
        additions_ui._create_attempt(job_id)
        try:
            additions._update(job_id, error="")
        except Exception:
            pass
        additions_ui._update_operation(
            job_id,
            queue_state="preparing",
            queue_position=0,
            enqueue_after_prepare=1,
            current_step="chatgpt_image",
            progress=max(40, _safe_int(additions_ui._job_snapshot(job_id).get("progress"))),
            status_message="Captura pendente aceita para a fila; concluindo a Preparação antes de enfileirar",
            operation_error="",
            hidden_from_queue=0,
            finished_at="",
        )
        recovery_started += 1

    if recovery_started:
        additions_ui._start_preparation_worker(manager)

    if regular:
        forwarded = dict(payload)
        forwarded["job_ids"] = regular
        forwarded.pop("job_id", None)
        result = dict(_BASE_REQUEST_ADD(forwarded, manager, retry=False))
    else:
        result = {
            "ok": True,
            "accepted": 0,
            "queued": 0,
            "preparing": 0,
            "not_ready": 0,
            "skipped": 0,
            "queue": additions_ui._queue_runtime(),
        }

    result["accepted"] = _safe_int(result.get("accepted")) + recovery_started
    result["preparing"] = _safe_int(result.get("preparing")) + recovery_started
    result["recovering_capture"] = recovery_started
    if recovery_started:
        prefix = (
            f"{recovery_started} produto(s) com captura pendente aceito(s) para a fila; "
            "eles entrarão em 'Na fila' automaticamente assim que a Preparação terminar."
        )
        existing = _clean(result.get("message"))
        result["message"] = f"{prefix} {existing}".strip()
    return result


def _start_queue_resilient() -> dict[str, Any]:
    """Permite iniciar a fila enquanto itens aceitos ainda terminam a captura."""
    if _BASE_START_QUEUE is None:
        raise RuntimeError("Inicializador base da fila de adições indisponível.")

    with additions_ui.additions._db() as connection:
        pending = _safe_int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM addition_jobs "
                "WHERE approval_active=1 AND queue_state='preparing' AND enqueue_after_prepare=1"
            ).fetchone()["total"]
        )
        queued = _safe_int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM addition_jobs "
                "WHERE approval_active=1 AND queue_state='queued'"
            ).fetchone()["total"]
        )
        executing = _safe_int(
            connection.execute(
                "SELECT COUNT(*) AS total FROM addition_jobs "
                "WHERE approval_active=1 AND queue_state='executing'"
            ).fetchone()["total"]
        )

    if pending > 0 and queued <= 0 and executing <= 0:
        additions_ui._set_queue_runtime("running")
        started = additions_ui._start_queue_worker()
        return {
            "ok": True,
            "message": (
                f"Fila iniciada aguardando {pending} produto(s) concluir(em) a captura/Preparação. "
                "Eles serão executados automaticamente assim que entrarem em 'Na fila'."
            ),
            "started": started,
            "queue": additions_ui._queue_runtime(),
        }
    return _BASE_START_QUEUE()


def install_addition_capture_pipeline_resilience_policy() -> None:
    global _INSTALLED, _BASE_REQUEST_ADD, _BASE_START_QUEUE
    if _INSTALLED:
        return

    # Alinha também os limites lidos por helpers legados, sem criar polling novo.
    adaptive._DESCRIPTION_TIMEOUT_SECONDS = _DESCRIPTION_TIMEOUT_SECONDS
    adaptive._IMAGE_TIMEOUT_SECONDS = _IMAGE_TIMEOUT_SECONDS
    binding._DESCRIPTION_TIMEOUT_SECONDS = _DESCRIPTION_TIMEOUT_SECONDS
    binding._IMAGE_TIMEOUT_SECONDS = _IMAGE_TIMEOUT_SECONDS

    # Último runner instalado: evita o fallback antigo de 4 minutos e reaproveita
    # conversas persistidas antes de criar uma nova geração.
    simple._run_two_chats = _run_resilient_two_chats

    # O servidor operacional resolve estes globals em tempo de requisição; manter
    # os IDs/listeners do frontend intactos e trocar somente a semântica do backend.
    _BASE_REQUEST_ADD = additions_ui._request_add
    _BASE_START_QUEUE = additions_ui._start_queue
    additions_ui._request_add = _request_add_resilient
    additions_ui._start_queue = _start_queue_resilient
    _INSTALLED = True
