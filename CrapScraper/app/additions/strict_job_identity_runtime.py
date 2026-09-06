from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.additions import chatgpt_background_project_runtime as background
from app.additions import chatgpt_background_route_recovery as route_recovery
from app.additions import chatgpt_playwright as legacy
from app.additions import chatgpt_playwright_compat as compat
from app.additions import chatgpt_playwright_image as image_runtime
from app.additions import chatgpt_product_isolation_runtime as isolation
from app.additions import chatgpt_project_url_recovery as project_recovery
from app.additions import chatgpt_content_response_runtime as content_runtime
from app.additions import product_content_contract_runtime as product_contract

_INSTALLED = False
_IDENTITY_VERSION = 1
_ISOLATION_VERSION = 2
_IMAGE_BINDING_VERSION = 4
_CONTENT_CONTRACT_VERSION = 3


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def job_identity_payload(job: dict[str, Any]) -> dict[str, str]:
    return {
        "job_id": str(job.get("job_id") or "").strip(),
        "comparison_item_id": str(job.get("comparison_item_id") or "").strip(),
        "product_name": " ".join(str(job.get("product_name") or "").split()).strip(),
        "kind": str(job.get("kind") or "").strip().casefold(),
        "source_url": str(job.get("source_url") or "").strip(),
        "source_version": str(job.get("source_version") or "").strip(),
    }


def job_identity_fingerprint(job: dict[str, Any]) -> str:
    raw = json.dumps(job_identity_payload(job), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"addition-product-v{_IDENTITY_VERSION}|{raw}".encode("utf-8")).hexdigest()


def bind_job_identity(job: dict[str, Any]) -> str:
    """Bind Playwright state to the exact addition row before any ChatGPT action.

    If a job id ever points at different product/source data, every cached chat,
    description and image is invalidated instead of leaking the previous product.
    """
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise legacy.ChatGPTPlaywrightError("Job de adição sem job_id; identidade do produto não pode ser validada.")
    payload = job_identity_payload(job)
    fingerprint = job_identity_fingerprint(job)
    current = legacy._job_state(job_id)
    previous = str(current.get("product_identity_fingerprint") or "")
    values: dict[str, Any] = {
        "product_identity_version": _IDENTITY_VERSION,
        "product_identity_fingerprint": fingerprint,
        "product_identity_product_name": payload["product_name"],
        "product_identity_comparison_item_id": payload["comparison_item_id"],
        "product_identity_kind": payload["kind"],
        "product_identity_source_url": payload["source_url"],
        "product_identity_source_version": payload["source_version"],
    }
    if previous and previous != fingerprint:
        values.update(
            conversation_url="",
            isolated_chat_version=0,
            isolated_chat_fingerprint="",
            isolated_chat_created_at=0,
            content_ready=False,
            content_fingerprint="",
            content_generated_at=0,
            image_ready=False,
            image_fingerprint="",
            image_sha256="",
            image_path="",
            image_prompt_marker="",
            image_candidate_src="",
        )
    legacy._update_job_state(job_id, **values)
    return fingerprint


def strict_job_conversation_fingerprint(job_id: str) -> str:
    state = legacy._job_state(str(job_id))
    identity = str(state.get("product_identity_fingerprint") or "")
    raw = f"addition-chat-v{_ISOLATION_VERSION}|{job_id}|{identity}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def strict_conversation_reusable(item: dict[str, Any], job_id: str) -> bool:
    state = legacy._job_state(str(job_id))
    identity = str(state.get("product_identity_fingerprint") or "")
    url = str(item.get("conversation_url") or "").strip()
    return bool(
        identity
        and int(item.get("isolated_chat_version") or 0) == _ISOLATION_VERSION
        and str(item.get("isolated_chat_fingerprint") or "") == strict_job_conversation_fingerprint(job_id)
        and project_recovery.is_project_candidate_url(url)
    )


def _user_turn_count(page: Any) -> int:
    try:
        return int(
            page.evaluate(
                """
                () => {
                  const main = document.querySelector('main');
                  if (!main) return 0;
                  const explicit = main.querySelectorAll('[data-message-author-role="user"]');
                  if (explicit.length) return explicit.length;
                  return [...main.querySelectorAll('[data-testid^="conversation-turn-"], article')]
                    .filter(turn => {
                      const roleNode = turn.matches?.('[data-message-author-role]')
                        ? turn : turn.querySelector?.('[data-message-author-role]');
                      return String(roleNode?.getAttribute('data-message-author-role') || '').toLowerCase() === 'user';
                    }).length;
                }
                """
            )
        )
    except Exception:
        return -1


def _is_blank_project_chat(page: Any, expected: str) -> bool:
    current = str(getattr(page, "url", "") or "").strip()
    if not current or not background._same_project_route(expected, current):
        return False
    if compat.composer(page, 5000) is None:
        return False
    return _user_turn_count(page) == 0


def strict_click_project_new(page: Any, expected: str) -> bool:
    """Create a provably empty chat inside the project.

    The previous implementation accepted a click merely because it stayed in the
    same project. That could leave the browser inside the Admin Columns chat and
    make the next product inherit its context. Here a successful click must leave
    us with zero user turns; an unchanged /c/ conversation is never accepted.
    """
    before_url = str(getattr(page, "url", "") or "").strip()
    patterns = (re.compile(r"^Novo$", re.I), re.compile(r"^New$", re.I))
    for role in ("button", "link"):
        for pattern in patterns:
            try:
                nodes = page.get_by_role(role, name=pattern)
                count = nodes.count()
            except Exception:
                continue
            for index in range(max(0, count - 1), -1, -1):
                try:
                    item = nodes.nth(index)
                    if not item.is_visible():
                        continue
                    try:
                        item.evaluate("el => el.click()")
                    except Exception:
                        item.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)
                    current = str(getattr(page, "url", "") or "").strip()
                    if not _is_blank_project_chat(page, expected):
                        continue
                    # Remaining on the exact same concrete conversation is not a
                    # new chat even if the DOM briefly reports no turns.
                    if "/c/" in before_url and current.rstrip("/") == before_url.rstrip("/"):
                        continue
                    return True
                except Exception:
                    continue
    return False


def strict_create_project_local_chat(page: Any, job_id: str) -> None:
    route_recovery.open_project(page)
    saved = project_recovery.saved_project_url() or str(getattr(page, "url", "") or "").strip()
    token = background._project_token(saved)
    if not token:
        raise legacy.ChatGPTPlaywrightError("Projeto [CS] Automação sem identificador g-p-*; não é seguro reutilizar chat anterior.")

    project_root = f"https://chatgpt.com/g/{token}"
    created = False
    try:
        page.goto(project_root, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1000)
        route_recovery._wait_signed_in(page, 10000)
        if _is_blank_project_chat(page, project_root):
            created = True
        else:
            created = strict_click_project_new(page, project_root)
    except Exception:
        created = False

    if not created:
        try:
            route_recovery.open_project(page)
            created = strict_click_project_new(page, project_root)
        except Exception:
            created = False

    # One final UI fallback is allowed only if the resulting page is proven blank.
    if not created:
        try:
            before = str(getattr(page, "url", "") or "").strip()
            route_recovery._try_project_new_button(page, project_root)
            page.wait_for_timeout(900)
            current = str(getattr(page, "url", "") or "").strip()
            created = _is_blank_project_chat(page, project_root) and not (
                "/c/" in before and current.rstrip("/") == before.rstrip("/")
            )
        except Exception:
            created = False

    if not created:
        diagnostic = compat._diagnostic(page, "strict_job_chat_creation_failed")
        raise legacy.ChatGPTPlaywrightError(
            "Não foi possível criar um chat NOVO e vazio para este produto no projeto [CS] Automação. "
            "A execução foi interrompida para impedir que descrição/imagem do Admin Columns ou de outro item seja reutilizada. "
            f"Diagnóstico: {diagnostic}."
        )

    now = int(__import__("time").time())
    legacy._update_job_state(
        str(job_id),
        conversation_url=str(getattr(page, "url", "") or "").strip(),
        isolated_chat_version=_ISOLATION_VERSION,
        isolated_chat_fingerprint=strict_job_conversation_fingerprint(job_id),
        isolated_chat_created_at=now,
        cache_until=now + 30 * 24 * 60 * 60,
        content_ready=False,
        content_fingerprint="",
        image_ready=False,
        image_fingerprint="",
        image_sha256="",
        image_prompt_marker="",
    )


def strict_open_job_conversation(page: Any, job_id: str) -> None:
    item = legacy._job_state(str(job_id))
    if strict_conversation_reusable(item, str(job_id)):
        url = str(item.get("conversation_url") or "").strip()
        expected = project_recovery.saved_project_url() or url
        try:
            if route_recovery._goto_project_candidate(page, url, expected, 16000):
                return
        except Exception:
            pass
    strict_create_project_local_chat(page, str(job_id))


def strict_parse_content_response(text: str, job: dict[str, Any]) -> dict[str, Any]:
    """Reject content if ChatGPT answered for another product.

    Do not silently rename an Admin Columns response to Aagan/911/etc. The model's
    returned product_name must match the queue row before the result is normalized.
    """
    raw = product_contract._ORIGINAL_PARSE(text, job)
    expected = _normalized(job.get("product_name"))
    actual = _normalized(raw.get("product_name"))
    if not expected or actual != expected:
        raise legacy.ChatGPTPlaywrightError(
            "O ChatGPT respondeu para outro produto. "
            f"Esperado: {job.get('product_name') or ''}; recebido: {raw.get('product_name') or '(ausente)'}. "
            "O conteúdo foi descartado e não será aplicado ao WooCommerce."
        )
    return product_contract.normalize_catalog_result(job, raw)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions.chatgpt import ChatGPTContentService
    from app.additions.images import ImageService

    # Invalidate all pre-fix conversations/images/content and strengthen cache
    # identity from job-id-only to the complete approved product identity.
    isolation._ISOLATION_VERSION = _ISOLATION_VERSION
    isolation.job_conversation_fingerprint = strict_job_conversation_fingerprint
    isolation.conversation_reusable = strict_conversation_reusable
    isolation._click_project_new = strict_click_project_new
    isolation._create_project_local_chat = strict_create_project_local_chat
    isolation.open_job_conversation = strict_open_job_conversation

    legacy._open_job_conversation = strict_open_job_conversation
    compat.open_job_conversation = strict_open_job_conversation
    route_recovery.open_job_conversation = strict_open_job_conversation
    image_runtime._open_job_conversation = strict_open_job_conversation
    image_runtime._IMAGE_BINDING_VERSION = _IMAGE_BINDING_VERSION

    product_contract._CONTENT_CONTRACT_VERSION = _CONTENT_CONTRACT_VERSION
    content_runtime.parse_content_response = strict_parse_content_response
    legacy.parse_content_response = strict_parse_content_response

    original_content_generate = ChatGPTContentService.generate
    original_image_generate = ImageService.generate

    def content_generate(self: Any, job: dict[str, Any]) -> dict[str, Any]:
        bind_job_identity(job)
        result = original_content_generate(self, job)
        if _normalized(result.get("product_name")) != _normalized(job.get("product_name")):
            raise legacy.ChatGPTPlaywrightError("Descrição retornou identidade diferente do item atual; resultado descartado.")
        return result

    def image_generate(self: Any, job: dict[str, Any]):
        bind_job_identity(job)
        return original_image_generate(self, job)

    ChatGPTContentService.generate = content_generate
    ImageService.generate = image_generate
    _INSTALLED = True


__all__ = [
    "bind_job_identity",
    "install",
    "job_identity_fingerprint",
    "job_identity_payload",
    "strict_conversation_reusable",
    "strict_create_project_local_chat",
    "strict_open_job_conversation",
    "strict_parse_content_response",
]
