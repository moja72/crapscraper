from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.additions.creative import image_prompt
from app.additions.chatgpt_image_detection_runtime import (
    _image_candidate_key,
    candidate_render_area,
)
from app.additions.chatgpt_playwright import (
    ChatGPTPlaywrightError,
    _LOCK,
    _browser,
    _candidate_images,
    _composer,
    _ensure_authenticated,
    _job_state,
    _looks_like_auth_wall,
    _normalize_image_bytes,
    _open_job_conversation,
    _read_image_from_locator,
    _stop_visible,
    _timeout_seconds,
    _update_job_state,
    image_valid,
    project_name,
)

_CACHE_SECONDS = 30 * 24 * 60 * 60
_IMAGE_BINDING_VERSION = 2


def image_fingerprint(job: dict[str, Any]) -> str:
    payload = {
        "binding_version": _IMAGE_BINDING_VERSION,
        "job_id": str(job.get("job_id") or ""),
        "product_name": str(job.get("product_name") or ""),
        "source_version": str(job.get("source_version") or ""),
        "source_url": str(job.get("source_url") or ""),
        "official_url": str(job.get("official_url") or ""),
        "kind": str(job.get("kind") or ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def image_reusable(job: dict[str, Any]) -> bool:
    """Only reuse an image when it was generated for this exact addition job/product."""
    item = _job_state(str(job.get("job_id") or ""))
    if not bool(item.get("image_ready")):
        return False
    if str(item.get("image_fingerprint") or "") != image_fingerprint(job):
        return False
    cache_until = int(item.get("cache_until") or 0)
    if cache_until and cache_until < int(time.time()):
        return False
    path = Path(str(job.get("image_path") or item.get("image_path") or ""))
    if not item.get("image_prompt_marker") or not item.get("image_sha256") or not image_valid(str(path)):
        return False
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == item["image_sha256"]
    except OSError:
        return False


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


def _candidate_bytes(page: Any, candidate: dict[str, Any]) -> bytes:
    try:
        return bytes(_read_image_from_locator(page, candidate) or b"")
    except Exception:
        return b""


def _candidate_hash(page: Any, candidate: dict[str, Any]) -> tuple[str, bytes]:
    raw = _candidate_bytes(page, candidate)
    if len(raw) <= 1024:
        return "", raw
    return hashlib.sha256(raw).hexdigest(), raw


def _candidate_is_after_marker(candidate: dict[str, Any], marker: str) -> bool:
    """Prove that an image belongs to the assistant turn after this image request."""
    locator = candidate.get("locator")
    if locator is None:
        return False
    try:
        return bool(
            locator.evaluate(
                """
                (img, marker) => {
                  const textOf = node => String(node?.innerText || node?.textContent || '');
                  const scopes = [
                    ...document.querySelectorAll('main [data-message-author-role]'),
                    ...document.querySelectorAll('main [data-testid^="conversation-turn-"]'),
                    ...document.querySelectorAll('main article')
                  ];
                  const turns = [...new Set(scopes)].filter(node =>
                    !scopes.some(parent => parent !== node && parent.contains(node)));
                  const roleOf = node => {
                    const explicit = node.matches('[data-message-author-role]') ? node : node.querySelector('[data-message-author-role]');
                    if (explicit) return explicit.getAttribute('data-message-author-role');
                    const label = String(node.getAttribute('aria-label') || '').toLowerCase();
                    if (/you said|você disse/.test(label)) return 'user';
                    if (/chatgpt said|chatgpt disse/.test(label)) return 'assistant';
                    return '';
                  };
                  turns.sort((a,b) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1);
                  const index = turns.findIndex(node => node.contains(img));
                  if (index < 0 || roleOf(turns[index]) !== 'assistant') return false;
                  for (let i = index - 1; i >= 0; i--) {
                    if (roleOf(turns[i]) === 'user') return textOf(turns[i]).includes(marker);
                    if (!roleOf(turns[i])) return false;
                  }
                  return false;
                }
                """,
                marker,
            )
        )
    except Exception:
        return False


def _marker_visible(page: Any, marker: str) -> bool:
    try:
        node = page.get_by_text(marker, exact=False).last
        return bool(node.count() and node.is_visible())
    except Exception:
        try:
            body = page.locator("main").inner_text(timeout=1500) or ""
            return marker in body
        except Exception:
            return False


def _candidate_generation_complete(candidate: dict[str, Any]) -> bool:
    """Check the candidate's own response turn for loading/generation UI."""
    locator = candidate.get("locator")
    if locator is None:
        return False
    try:
        return bool(
            locator.evaluate(
                """
                img => {
                  const turn = img.closest(
                    '[data-testid^="conversation-turn-"], article, [data-message-author-role="assistant"]'
                  ) || img.parentElement;
                  if (!turn) return false;
                  const selectors = [
                    'button[data-testid*="stop"]',
                    'button[aria-label*="Stop" i]',
                    'button[aria-label*="Parar" i]',
                    '[aria-busy="true"]',
                    '[data-loading="true"]',
                    '[class*="animate-spin"]',
                    '[class*="loading"]'
                  ];
                  if (selectors.some(selector => turn.querySelector(selector))) return false;
                  const rect = img.getBoundingClientRect();
                  return Boolean(img.complete && (img.naturalWidth || 0) >= 256 && (img.naturalHeight || 0) >= 256 && rect.width > 0 && rect.height > 0);
                }
                """
            )
        )
    except Exception:
        return False


def generate_image(job: dict[str, Any], root: Path) -> Path:
    """Generate a product-specific image and prove it belongs to this exact prompt.

    Acceptance requires all of the following:
    - bytes were not present before the request;
    - DOM position is after the unique marker of the current user prompt;
    - bytes stay identical for multiple polling cycles;
    - the image's own assistant turn is no longer loading;
    - ChatGPT's global Stop control is gone.

    A timeout is preferable to assigning the previous product's image.
    """
    with _LOCK, _browser() as page:
        _open_job_conversation(page, str(job["job_id"]))
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            cache_until=int(time.time()) + _CACHE_SECONDS,
        )

        before_candidates = _candidate_images(page)
        before_keys = {_image_candidate_key(item) for item in before_candidates}
        before_count = len(before_candidates)
        before_hashes: set[str] = set()
        # A different conversation need not render the preceding product's image.
        # Protect hashes recorded for every completed job, not just this page.
        from app.additions.chatgpt_playwright import _read_state
        for previous in (_read_state().get("jobs") or {}).values():
            if isinstance(previous, dict):
                before_hashes.update(str(previous[key]) for key in ("image_sha256", "image_raw_sha256") if previous.get(key))
        for item in before_candidates:
            digest, _ = _candidate_hash(page, item)
            if digest:
                before_hashes.add(digest)

        marker_seed = f"{job.get('job_id')}|{job.get('product_name')}|{job.get('source_version')}|{time.time_ns()}"
        marker = "CSIMG-" + hashlib.sha256(marker_seed.encode("utf-8")).hexdigest()[:16].upper()
        prompt = (
            f"Continuando o cadastro de {job['product_name']} no projeto {project_name()}, gere AGORA a imagem principal.\n\n"
            + image_prompt(job)
            + "\n\nIMPORTANTE: esta imagem é EXCLUSIVA deste produto. Não reutilize imagem de outro item ou de uma resposta anterior. "
            + "Use a ferramenta de geração de imagens do ChatGPT. Não responda apenas com uma descrição; produza a imagem de fato.\n"
            + f"Identificador interno desta solicitação: {marker}. Não repita esse identificador na resposta."
        )
        _submit_image_prompt(page, prompt)

        deadline = time.monotonic() + _timeout_seconds()
        last_candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        selected_raw = b""
        stable_hash = ""
        stable_cycles = 0
        marker_seen = False

        while time.monotonic() < deadline:
            if _looks_like_auth_wall(page) and _composer(page, 1000) is None:
                raise ChatGPTPlaywrightError(
                    "Sessão ChatGPT expirou durante a geração da imagem. Execute o bootstrap novamente."
                )

            marker_seen = marker_seen or _marker_visible(page, marker)
            candidates = _candidate_images(page)
            last_candidates = candidates
            fresh = [item for item in candidates if _image_candidate_key(item) not in before_keys]
            if not fresh and len(candidates) > before_count:
                fresh = candidates[before_count:]

            fresh = sorted(fresh, key=candidate_render_area, reverse=True)
            current_hash = ""
            current_raw = b""
            current_candidate = None
            for candidate in fresh:
                if candidate.get("complete") is False:
                    continue
                if not marker_seen or not _candidate_is_after_marker(candidate, marker):
                    continue
                digest, raw = _candidate_hash(page, candidate)
                if not digest or digest in before_hashes:
                    continue
                current_hash = digest
                current_raw = raw
                current_candidate = candidate
                break

            if current_candidate is not None:
                if current_hash == stable_hash:
                    stable_cycles += 1
                else:
                    stable_hash = current_hash
                    stable_cycles = 0

                if (
                    stable_cycles >= 4
                    and _candidate_generation_complete(current_candidate)
                    and not _stop_visible(page)
                ):
                    selected = current_candidate
                    selected_raw = current_raw
                    break

            time.sleep(0.9)

        if selected is None or not selected_raw:
            diagnostic = _diagnostic(page, "image_response_timeout")
            suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
            raise ChatGPTPlaywrightError(
                "ChatGPT não entregou uma imagem NOVA concluída e vinculada ao prompt deste produto. "
                f"Marcador do prompt localizado: {'sim' if marker_seen else 'não'}; "
                f"imagens grandes detectadas no fim: {len(last_candidates)}; imagens anteriores protegidas: {len(before_hashes)}."
                + suffix
            )

        target = _normalize_image_bytes(selected_raw, Path(root), str(job["job_id"]))
        now = int(time.time())
        _update_job_state(
            str(job["job_id"]),
            conversation_url=page.url,
            image_ready=True,
            image_path=str(target),
            image_generated_at=now,
            image_fingerprint=image_fingerprint(job),
            image_sha256=hashlib.sha256(Path(target).read_bytes()).hexdigest(),
            image_raw_sha256=hashlib.sha256(selected_raw).hexdigest(),
            image_candidate_src=str(selected.get("src") or "")[:1000],
            image_prompt_marker=marker,
            cache_until=now + _CACHE_SECONDS,
        )
        return target


__all__ = [
    "generate_image",
    "image_fingerprint",
    "image_reusable",
    "image_valid",
    "_candidate_is_after_marker",
    "_candidate_generation_complete",
]
