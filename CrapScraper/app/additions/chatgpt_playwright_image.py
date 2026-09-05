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


def image_fingerprint(job: dict[str, Any]) -> str:
    payload = {
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
    return image_valid(str(job.get("image_path") or item.get("image_path") or ""))


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


def generate_image(job: dict[str, Any], root: Path) -> Path:
    """Generate a product-specific image and prove it is new before persisting it.

    DOM/src changes are not enough: ChatGPT can re-render an older image and make
    it look like a fresh candidate. We hash the actual bytes visible before the
    prompt and reject any post-prompt candidate with the same content hash.
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
        for item in before_candidates:
            digest, _ = _candidate_hash(page, item)
            if digest:
                before_hashes.add(digest)

        prompt = (
            f"Continuando o cadastro de {job['product_name']} no projeto {project_name()}, gere AGORA a imagem principal.\n\n"
            + image_prompt(job)
            + "\n\nIMPORTANTE: esta imagem é EXCLUSIVA deste produto. Não reutilize imagem de outro item ou de uma resposta anterior. "
            + "Use a ferramenta de geração de imagens do ChatGPT. Não responda apenas com uma descrição; produza a imagem de fato."
        )
        _submit_image_prompt(page, prompt)

        deadline = time.monotonic() + _timeout_seconds()
        last_candidates: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        selected_raw = b""
        stable_hash = ""
        stable_cycles = 0
        first_new_at: float | None = None

        while time.monotonic() < deadline:
            if _looks_like_auth_wall(page) and _composer(page, 1000) is None:
                raise ChatGPTPlaywrightError(
                    "Sessão ChatGPT expirou durante a geração da imagem. Execute o bootstrap novamente."
                )

            candidates = _candidate_images(page)
            last_candidates = candidates
            fresh = [item for item in candidates if _image_candidate_key(item) not in before_keys]
            if not fresh and len(candidates) > before_count:
                fresh = candidates[before_count:]

            # Prefer larger candidates, but accept only bytes that did not exist
            # before this prompt. This blocks the exact stale-image failure seen
            # when the next product inherited the previous product's artwork.
            fresh = sorted(fresh, key=candidate_render_area, reverse=True)
            current_hash = ""
            current_raw = b""
            current_candidate = None
            for candidate in fresh:
                if candidate.get("complete") is False:
                    continue
                digest, raw = _candidate_hash(page, candidate)
                if not digest or digest in before_hashes:
                    continue
                current_hash = digest
                current_raw = raw
                current_candidate = candidate
                break

            if current_candidate is not None:
                if first_new_at is None:
                    first_new_at = time.monotonic()
                if current_hash == stable_hash:
                    stable_cycles += 1
                else:
                    stable_hash = current_hash
                    stable_cycles = 0

                grace = time.monotonic() - first_new_at
                # Require repeated identical bytes. Prefer generation fully idle,
                # but never wait forever on a stale Stop button.
                if stable_cycles >= 2 and (not _stop_visible(page) or grace >= 10):
                    selected = current_candidate
                    selected_raw = current_raw
                    break

            time.sleep(0.8)

        if selected is None or not selected_raw:
            diagnostic = _diagnostic(page, "image_response_timeout")
            suffix = f" Diagnóstico salvo em {diagnostic}." if diagnostic else ""
            raise ChatGPTPlaywrightError(
                "ChatGPT não entregou uma imagem NOVA confirmada para este produto. "
                f"Imagens grandes detectadas no fim: {len(last_candidates)}; imagens anteriores protegidas: {len(before_hashes)}."
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
            image_candidate_src=str(selected.get("src") or "")[:1000],
            cache_until=now + _CACHE_SECONDS,
        )
        return target


__all__ = ["generate_image", "image_fingerprint", "image_reusable", "image_valid"]
