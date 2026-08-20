from __future__ import annotations

import os
import re
import threading
import time
from typing import Any

import app.addition_chat_binding_policy as binding
import app.addition_chat_title_policy as title_policy
import app.addition_chatgpt_cdp_reconnect_policy as reconnect
import app.addition_one_click_policy as one_click
import app.addition_real_chat_url_policy as real_url
import app.new_product_workflow_policy as additions


_INSTALLED = False
_BASE_BIND_CHAT_PAGE = None
_BASE_SEND_MESSAGE = None
_BASE_WAIT_COMPOSER = None

_RATE_LOCK = threading.RLock()
_RATE_COOLDOWN_UNTIL = 0.0
_RATE_LAST_LOG = 0.0
_RATE_LIMIT_COOLDOWN_SECONDS = max(
    30,
    int(os.environ.get("SCRAPER_CHATGPT_RATE_LIMIT_COOLDOWN_SECONDS", "120") or 120),
)

_RATE_LIMIT_MARKERS = (
    "excesso de solicitações",
    "excesso de solicitacoes",
    "solicitações rápido demais",
    "solicitacoes rapido demais",
    "limitamos temporariamente o acesso às suas conversas",
    "limitamos temporariamente o acesso as suas conversas",
    "too many requests",
    "requests too quickly",
    "temporarily limited access to your conversations",
)


def _body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=1200) or "")
    except Exception:
        try:
            return str(page.evaluate("() => String(document.body?.innerText || '')") or "")
        except Exception:
            return ""


def _rate_limit_visible(page: Any) -> bool:
    text = " ".join(_body_text(page).lower().split())
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


def _set_cooldown() -> None:
    global _RATE_COOLDOWN_UNTIL
    with _RATE_LOCK:
        _RATE_COOLDOWN_UNTIL = max(
            _RATE_COOLDOWN_UNTIL,
            time.time() + _RATE_LIMIT_COOLDOWN_SECONDS,
        )


def _dismiss_rate_limit(page: Any, job_id: str = "") -> bool:
    global _RATE_LAST_LOG
    if page is None or not _rate_limit_visible(page):
        return False

    try:
        page.bring_to_front()
    except Exception:
        pass

    dismissed = False
    # O modal atualmente aceita Enter; tente isso primeiro para não depender do texto do botão.
    try:
        page.keyboard.press("Enter")
        dismissed = True
        page.wait_for_timeout(250)
    except Exception:
        pass

    if _rate_limit_visible(page):
        patterns = re.compile(r"^(OK|Okay|Entendi|Continuar|Fechar|Close|Dismiss|Confirmar)$", re.I)
        for selector in ("[role='dialog'] button:visible", "button:visible"):
            try:
                buttons = page.locator(selector)
                for index in range(buttons.count() - 1, -1, -1):
                    button = buttons.nth(index)
                    text = " ".join(
                        str(button.inner_text(timeout=300) or button.get_attribute("aria-label") or "").split()
                    )
                    if text and patterns.match(text):
                        button.click(timeout=1000)
                        dismissed = True
                        page.wait_for_timeout(250)
                        break
            except Exception:
                continue
            if not _rate_limit_visible(page):
                break

    _set_cooldown()
    now = time.time()
    if job_id and now - _RATE_LAST_LOG >= 10:
        _RATE_LAST_LOG = now
        one_click._emit(
            job_id,
            "Aviso de excesso de solicitações detectado no ChatGPT. O aviso foi confirmado automaticamente; "
            f"novos envios aguardarão {_RATE_LIMIT_COOLDOWN_SECONDS}s antes de continuar.",
            step="chatgpt_rate_limit",
        )
    return dismissed


def _wait_rate_cooldown(job_id: str) -> None:
    announced = False
    while True:
        with _RATE_LOCK:
            remaining = _RATE_COOLDOWN_UNTIL - time.time()
        if remaining <= 0:
            return
        if job_id and not announced:
            one_click._emit(
                job_id,
                f"ChatGPT pediu redução do ritmo. Aguardando {max(1, int(remaining))}s antes do próximo envio…",
                step="chatgpt_rate_limit",
            )
            announced = True
        time.sleep(min(1.0, max(0.1, remaining)))


def _wait_composer_guarded(page: Any, job_id: str, timeout_seconds: int = 300) -> Any:
    deadline = time.time() + max(1, int(timeout_seconds))
    warned = False
    while time.time() < deadline:
        _dismiss_rate_limit(page, job_id)
        try:
            composer = one_click._composer(page)
        except Exception:
            composer = None
        if composer is not None:
            return composer
        if not warned:
            one_click._emit(
                job_id,
                "Aguardando o ChatGPT ficar disponível. Avisos de excesso de solicitações serão tratados automaticamente.",
                step="chatgpt_login",
            )
            warned = True
        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Tempo esgotado aguardando a caixa de mensagem do ChatGPT.")


def _send_message_guarded(context: Any, page: Any, prompt: str, job_id: str, project_url: str):
    _dismiss_rate_limit(page, job_id)
    _wait_rate_cooldown(job_id)
    result = _BASE_SEND_MESSAGE(context, page, prompt, job_id, project_url)
    current = result[0]
    _dismiss_rate_limit(current, job_id)
    return result


def _conversation_id(page: Any) -> str:
    url = real_url._page_url(page)
    match = re.search(r"/c/([A-Za-z0-9-]+)", str(url or ""), re.I)
    return match.group(1) if match else ""


def _desired_title(job_id: str, label: str) -> str:
    try:
        job = additions._row(job_id)
    except Exception:
        job = {}
    name = " ".join(str(job.get("source_name") or job.get("title") or "Produto WordPress").split()).strip()
    prefix = "Descrição" if "chat 1" in str(label).lower() else "Imagem" if "chat 2" in str(label).lower() else "Chat"
    return f"{prefix}: {name}"


def _rename_via_backend(page: Any, desired: str) -> bool:
    conversation_id = _conversation_id(page)
    if not conversation_id or not desired:
        return False
    try:
        status = page.evaluate(
            """
            async ({id, title}) => {
              const response = await fetch(`/backend-api/conversation/${encodeURIComponent(id)}`, {
                method: 'PATCH',
                credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({title}),
              });
              return Number(response.status || 0);
            }
            """,
            {"id": conversation_id, "title": desired},
        )
        return int(status or 0) in {200, 204}
    except Exception:
        return False


def _rename_chat_reliably(page: Any, desired: str) -> bool:
    if not desired or not real_url._is_real_conversation_url(real_url._page_url(page)):
        return False
    if _rename_via_backend(page, desired):
        return True
    try:
        return bool(title_policy._rename_chat(page, desired))
    except Exception:
        return False


def _bind_chat_with_reliability(
    context: Any,
    current: Any,
    chat_url: str,
    project_url: str,
    job_id: str,
    label: str,
) -> Any:
    page = _BASE_BIND_CHAT_PAGE(context, current, chat_url, project_url, job_id, label)
    _dismiss_rate_limit(page, job_id)

    if real_url._is_real_conversation_url(real_url._page_url(page)):
        desired = _desired_title(job_id, label)
        kind = "description" if "chat 1" in str(label).lower() else "image" if "chat 2" in str(label).lower() else "chat"
        success_key = f"_cs_title_success_{kind}"
        attempt_key = f"_cs_title_attempt_{kind}"
        try:
            succeeded = bool(getattr(page, success_key, False))
            last_attempt = float(getattr(page, attempt_key, 0.0) or 0.0)
        except Exception:
            succeeded = False
            last_attempt = 0.0

        # Só encerra as tentativas depois de sucesso confirmado. Em falha, tenta de novo
        # durante o monitoramento da conversa, sem atrapalhar descrição/imagem.
        if not succeeded and time.time() - last_attempt >= 5.0:
            try:
                setattr(page, attempt_key, time.time())
            except Exception:
                pass
            if _rename_chat_reliably(page, desired):
                try:
                    setattr(page, success_key, True)
                except Exception:
                    pass
                one_click._emit(job_id, f"{label}: conversa padronizada como {desired}.", step="chatgpt")
    return page


def install_addition_chat_reliability_policy() -> None:
    global _INSTALLED, _BASE_BIND_CHAT_PAGE, _BASE_SEND_MESSAGE, _BASE_WAIT_COMPOSER
    if _INSTALLED:
        return

    _BASE_BIND_CHAT_PAGE = binding._bind_chat_page
    _BASE_SEND_MESSAGE = reconnect._send_message_resilient
    _BASE_WAIT_COMPOSER = one_click._wait_composer

    binding._bind_chat_page = _bind_chat_with_reliability
    reconnect._send_message_resilient = _send_message_guarded
    one_click._wait_composer = _wait_composer_guarded
    _INSTALLED = True
