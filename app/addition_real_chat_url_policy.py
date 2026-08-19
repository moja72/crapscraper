from __future__ import annotations

import base64
import hashlib
import re
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

import app.addition_chat_binding_policy as binding
import app.addition_conversation_capture_policy as capture
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_BIND_CHAT_PAGE = None
_ORIGINAL_RAW_SEND = None
_CONVERSATION_RE = re.compile(r"/c/[A-Za-z0-9-]+(?:/|$)", re.I)


def _is_real_conversation_url(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        parsed = urlsplit(raw)
        host = str(parsed.hostname or "").lower()
        path = str(parsed.path or "")
    except Exception:
        return False
    if host not in {"chatgpt.com", "www.chatgpt.com"}:
        return False
    return bool(_CONVERSATION_RE.search(path))


def _page_url(page: Any) -> str:
    try:
        return str(page.url or "").strip()
    except Exception:
        return ""


def _field_for_prompt(prompt: str) -> tuple[str, str, str]:
    lowered = str(prompt or "").lower()
    if "breve descrição comercial" in lowered or "breve descricao comercial" in lowered:
        return "description_chat_url", "Chat 1", "chatgpt_description"
    if "imagem principal" in lowered:
        return "image_chat_url", "Chat 2", "chatgpt_image"
    return "", "", "chatgpt"


def _field_for_label(label: str) -> tuple[str, str]:
    lowered = str(label or "").lower()
    if "chat 1" in lowered:
        return "description_chat_url", "image_chat_url"
    if "chat 2" in lowered:
        return "image_chat_url", "description_chat_url"
    return "", ""


def _save_real_chat_url(job_id: str, field: str, value: str, label: str, step: str) -> bool:
    url = str(value or "").strip()
    if not field or not _is_real_conversation_url(url):
        return False
    job = additions._row(job_id)
    current = str(job.get(field) or "").strip()
    if current == url:
        return True
    additions._update(job_id, **{field: url})
    one_click._emit(
        job_id,
        f"{label}: URL real da conversa confirmada e persistida: {url}",
        step=step,
    )
    return True


def _clear_invalid_mapping(job_id: str, field: str) -> None:
    if not field:
        return
    job = additions._row(job_id)
    current = str(job.get(field) or "").strip()
    if current and not _is_real_conversation_url(current):
        additions._update(job_id, **{field: ""})


def _wait_short_for_real_url(page: Any, timeout_seconds: float = 2.0) -> str:
    deadline = time.time() + max(0.0, timeout_seconds)
    while time.time() < deadline:
        value = _page_url(page)
        if _is_real_conversation_url(value):
            return value
        time.sleep(0.2)
    value = _page_url(page)
    return value if _is_real_conversation_url(value) else ""


def _send_message_real_chat_tracked(
    context: Any,
    page: Any,
    prompt: str,
    job_id: str,
    project_url: str,
) -> tuple[Any, int, set[str]]:
    result = _ORIGINAL_RAW_SEND(context, page, prompt, job_id, project_url)
    current = result[0]
    field, label, step = _field_for_prompt(prompt)
    if not field:
        return result

    # Nunca deixe a raiz /project sobreviver como se fosse uma conversa.
    _clear_invalid_mapping(job_id, field)
    chat_url = _wait_short_for_real_url(current, timeout_seconds=2.0)
    if chat_url:
        _save_real_chat_url(job_id, field, chat_url, label, step)
    else:
        one_click._emit(
            job_id,
            f"{label}: prompt enviado; aguardando a navegação real para /c/<id> antes de vincular a conversa.",
            step=step,
        )
    return result


def _late_bound_chat_page(
    context: Any,
    current: Any,
    chat_url: str,
    project_url: str,
    job_id: str,
    label: str,
) -> Any:
    field, other_field = _field_for_label(label)
    target = str(chat_url or "").strip()

    # Bancos/jobs de tentativas anteriores podem conter a raiz /project. Ignore-a.
    if target and not _is_real_conversation_url(target):
        _clear_invalid_mapping(job_id, field)
        target = ""

    current_url = _page_url(current) if reconnect._page_is_alive(current) else ""
    if _is_real_conversation_url(current_url):
        _save_real_chat_url(
            job_id,
            field,
            current_url,
            label,
            "chatgpt_description" if field == "description_chat_url" else "chatgpt_image",
        )
        return current

    # Se já temos uma URL /c/ confirmada, use a lógica estrita da policy anterior.
    if _is_real_conversation_url(target):
        return _ORIGINAL_BIND_CHAT_PAGE(context, current, target, project_url, job_id, label)

    # Enquanto a SPA ainda está em /project, mantenha o objeto Page original. Quando ele
    # migrar para /c/<id>, a próxima rodada acima fará o late binding automaticamente.
    if reconnect._page_is_alive(current):
        return current

    # Caso raro: a aba fechou antes do /c/ ser persistido. Recupere somente uma conversa
    # real que não pertença ao outro chat; nunca escolha /project aleatoriamente.
    job = additions._row(job_id)
    other_url = str(job.get(other_field) or "").strip() if other_field else ""
    choices: list[Any] = []
    for candidate in list(getattr(context, "pages", []) or []):
        if not reconnect._page_is_alive(candidate):
            continue
        candidate_url = _page_url(candidate)
        if not _is_real_conversation_url(candidate_url):
            continue
        if other_url and binding._same_chat_url(candidate_url, other_url):
            continue
        choices.append(candidate)
    if len(choices) == 1:
        recovered = choices[0]
        recovered_url = _page_url(recovered)
        _save_real_chat_url(
            job_id,
            field,
            recovered_url,
            label,
            "chatgpt_description" if field == "description_chat_url" else "chatgpt_image",
        )
        return recovered

    raise RuntimeError(
        f"{label}: a aba original foi fechada antes de a URL real /c/<id> ser confirmada e não foi possível identificar a conversa com segurança."
    )


def _exact_element_image_data_url(page: Any, candidate: Mapping[str, Any], reference_sha: str) -> str:
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
            actual = str(locator.evaluate("img => String(img.currentSrc || img.src || '')") or "")
            if actual != source or not locator.is_visible():
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


def install_addition_real_chat_url_policy() -> None:
    global _INSTALLED, _ORIGINAL_BIND_CHAT_PAGE, _ORIGINAL_RAW_SEND
    if _INSTALLED:
        return

    _ORIGINAL_BIND_CHAT_PAGE = binding._bind_chat_page
    # A conversation-capture policy guardou aqui a função resiliente anterior ao wrapper
    # que persistia /project cedo demais. Chame-a diretamente e faça tracking corretamente.
    _ORIGINAL_RAW_SEND = capture._ORIGINAL_SEND_MESSAGE or reconnect._send_message_resilient

    reconnect._send_message_resilient = _send_message_real_chat_tracked
    binding._bind_chat_page = _late_bound_chat_page
    binding._element_image_data_url = _exact_element_image_data_url
    capture._conversation_url = lambda page, timeout_seconds=10: (
        _wait_short_for_real_url(page, timeout_seconds=min(float(timeout_seconds), 2.0))
    )

    _INSTALLED = True
