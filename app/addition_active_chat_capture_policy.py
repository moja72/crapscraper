from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_parallel_generation_policy as parallel
import app.addition_product_creative_policy as creative


_INSTALLED = False
_ORIGINAL_BIND_CHAT_PAGE = None
_ORIGINAL_DESCRIPTION_CANDIDATES = None
_ORIGINAL_IMAGE_CANDIDATES = None
_ORIGINAL_ATTACH_REFERENCE = None
_ORIGINAL_REFUSAL_TEXT = None

_PROMPT_MARKERS = (
    "identificador interno:",
    "pesquise e escreva somente a breve descrição comercial",
    "use apenas estrutura, ritmo e extensão",
    "regra de saída",
    "marketplace/fonte oficial esperada",
    "gere somente a imagem principal",
)

_UI_LINES = {
    "mostrar mais",
    "editar",
    "copiar",
    "repetir",
    "retry",
    "compartilhar",
    "share",
}

_IMAGE_ERROR_MARKERS = (
    "algo deu errado. tente novamente",
    "something went wrong. try again",
)


def _focus_page(page: Any) -> None:
    try:
        page.bring_to_front()
    except Exception:
        pass
    try:
        page.wait_for_timeout(250)
    except Exception:
        pass


def _clean_dom_text(value: str) -> str:
    lines: list[str] = []
    for raw in str(value or "").splitlines():
        line = " ".join(raw.split()).strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in _UI_LINES:
            continue
        if re.match(r"^(pensou por|worked for)\b", lowered):
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _looks_like_prompt(value: str) -> bool:
    lowered = " ".join(str(value or "").lower().split())
    if any(marker in lowered for marker in _PROMPT_MARKERS):
        return True
    # Exact example embedded in the prompt; never treat it as the product answer.
    if (
        "crie páginas profissionais com total liberdade visual" in lowered
        and "elementor pro ajuda a montar páginas" in lowered
    ):
        return True
    return False


def _direct_description_candidates(page: Any) -> list[str]:
    """Read the answer from the active mapped conversation without relying on role attributes."""
    _focus_page(page)
    try:
        payload = page.evaluate(
            """
            () => {
              const main = document.querySelector('main');
              if (!main) return {blocks: [], mainText: ''};
              const selectors = [
                '[data-message-author-role="assistant"]',
                '[data-testid^="conversation-turn-"] p',
                '[data-testid*="conversation-turn"] p',
                'article p',
                '.markdown p',
                '[class*="markdown"] p',
                '[class*="prose"] p',
                'main p',
                '.markdown',
                '[class*="prose"]'
              ];
              const nodes = [...main.querySelectorAll(selectors.join(','))];
              const seen = new Set();
              const blocks = [];
              nodes.forEach((node, order) => {
                const text = String(node.innerText || node.textContent || '').trim();
                if (!text || seen.has(text)) return;
                seen.add(text);
                blocks.push({text, order});
              });
              return {blocks, mainText: String(main.innerText || main.textContent || '')};
            }
            """
        )
    except Exception:
        return []

    values: list[str] = []
    seen_values: set[str] = set()
    blocks = list(payload.get("blocks") or []) if isinstance(payload, Mapping) else []
    for item in reversed(blocks):
        raw = str(item.get("text") if isinstance(item, Mapping) else item or "")
        cleaned = _clean_dom_text(raw)
        if not cleaned or _looks_like_prompt(cleaned):
            continue
        candidate = final_validation._validated_description(cleaned)
        if candidate and candidate not in seen_values:
            seen_values.add(candidate)
            values.append(candidate)

    if values:
        values.sort(key=lambda text: abs(len(text) - 450))
        return values

    main_text = str(payload.get("mainText") or "") if isinstance(payload, Mapping) else ""
    lines = []
    for raw in main_text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in _UI_LINES or re.match(r"^(pensou por|worked for)\b", lowered):
            continue
        lines.append(line)

    # Search from the bottom because the final assistant response is after the prompt.
    for end in range(len(lines), 0, -1):
        for width in range(1, 8):
            start = max(0, end - width)
            cleaned = " ".join(lines[start:end]).strip()
            if not cleaned or _looks_like_prompt(cleaned):
                continue
            candidate = final_validation._validated_description(cleaned)
            if candidate and candidate not in seen_values:
                seen_values.add(candidate)
                values.append(candidate)
        if values:
            break

    values.sort(key=lambda text: abs(len(text) - 450))
    return values


def _description_candidates_active(page: Any) -> list[str]:
    direct = _direct_description_candidates(page)
    if direct:
        return direct
    if callable(_ORIGINAL_DESCRIPTION_CANDIDATES):
        return list(_ORIGINAL_DESCRIPTION_CANDIDATES(page) or [])
    return []


def _direct_new_images(page: Any, before: set[str]) -> list[dict[str, Any]]:
    _focus_page(page)
    try:
        rows = page.evaluate(
            """
            (before) => {
              const main = document.querySelector('main') || document.body;
              const old = new Set(before || []);
              return [...main.querySelectorAll('img')]
                .map((img, index) => ({
                  index,
                  src: String(img.currentSrc || img.src || ''),
                  width: Number(img.naturalWidth || 0),
                  height: Number(img.naturalHeight || 0),
                  visible: !!(img.getClientRects().length && img.offsetWidth && img.offsetHeight),
                  alt: String(img.alt || '')
                }))
                .filter(item => item.src && !old.has(item.src) && item.visible &&
                  item.width >= 256 && item.height >= 256 &&
                  !item.src.includes('avatar') && !item.src.includes('icon'));
            }
            """,
            list(before),
        )
    except Exception:
        return []
    result = [dict(item) for item in (rows or []) if isinstance(item, Mapping)]
    result.sort(key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0), reverse=True)
    return result


def _image_candidates_active(page: Any, before: set[str]) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in (
        _direct_new_images(page, before),
        list(_ORIGINAL_IMAGE_CANDIDATES(page, before) or []) if callable(_ORIGINAL_IMAGE_CANDIDATES) else [],
    ):
        for item in source:
            row = dict(item)
            src = str(row.get("src") or "")
            if not src or src in seen:
                continue
            seen.add(src)
            combined.append(row)
    combined.sort(key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0), reverse=True)
    return combined


def _attachment_snapshot(page: Any) -> set[str]:
    try:
        return set(
            str(value)
            for value in (
                page.evaluate(
                    """
                    () => [...document.images]
                      .filter(img => img.naturalWidth >= 96 && img.naturalHeight >= 96)
                      .map(img => String(img.currentSrc || img.src || ''))
                      .filter(Boolean)
                    """
                )
                or []
            )
        )
    except Exception:
        return set()


def _attachment_confirmed(page: Any, reference_path: Path, before: set[str], timeout_seconds: float = 8.0) -> bool:
    filename = reference_path.name.lower()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        _focus_page(page)
        try:
            evidence = page.evaluate(
                """
                ({filename, before}) => {
                  const old = new Set(before || []);
                  const bodyText = String(document.body?.innerText || '').toLowerCase();
                  const named = [...document.querySelectorAll('[aria-label], [title], [alt]')].some(el =>
                    [el.getAttribute('aria-label'), el.getAttribute('title'), el.getAttribute('alt')]
                      .some(v => String(v || '').toLowerCase().includes(filename))
                  );
                  const newPreview = [...document.images].some(img => {
                    const src = String(img.currentSrc || img.src || '');
                    return src && !old.has(src) && img.naturalWidth >= 96 && img.naturalHeight >= 96 &&
                      !!(img.getClientRects().length && img.offsetWidth && img.offsetHeight);
                  });
                  const composer = document.querySelector('#prompt-textarea, [data-testid="composer-text-input"], [contenteditable="true"][role="textbox"]');
                  const form = composer?.closest('form');
                  const scopedFile = form ? [...form.querySelectorAll('input[type="file"]')].some(input =>
                    [...(input.files || [])].some(file => String(file.name || '').toLowerCase() === filename)
                  ) : false;
                  const attachmentUi = [...document.querySelectorAll('[data-testid*="attach" i], [data-testid*="file" i], [class*="attachment" i]')].some(el =>
                    String(el.innerText || el.textContent || '').toLowerCase().includes(filename)
                  );
                  return {bodyName: bodyText.includes(filename), named, newPreview, scopedFile, attachmentUi};
                }
                """,
                {"filename": filename, "before": list(before)},
            )
        except Exception:
            evidence = {}
        if isinstance(evidence, Mapping) and any(bool(value) for value in evidence.values()):
            return True
        try:
            page.wait_for_timeout(350)
        except Exception:
            time.sleep(0.35)
    return False


def _attach_reference_verified(page: Any, reference_path: Path, job_id: str) -> bool:
    _focus_page(page)
    before = _attachment_snapshot(page)
    for attempt in range(1, 3):
        ok = bool(_ORIGINAL_ATTACH_REFERENCE(page, reference_path, job_id)) if callable(_ORIGINAL_ATTACH_REFERENCE) else False
        if ok and _attachment_confirmed(page, reference_path, before):
            one_click._emit(
                job_id,
                f"Referência visual confirmada no compositor: {reference_path.name}.",
                step="chatgpt_image",
            )
            return True
        if attempt == 1:
            one_click._emit(
                job_id,
                f"O upload de {reference_path.name} não apareceu no compositor; tentando anexar novamente antes de enviar o prompt.",
                step="chatgpt_image",
            )
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass
    one_click._emit(
        job_id,
        f"A referência {reference_path.name} não pôde ser confirmada visualmente no ChatGPT; o prompt de imagem não será enviado sem o anexo.",
        step="chatgpt_image",
    )
    return False


def _bind_and_focus(context: Any, current: Any, chat_url: str, project_url: str, job_id: str, label: str) -> Any:
    page = _ORIGINAL_BIND_CHAT_PAGE(context, current, chat_url, project_url, job_id, label)
    _focus_page(page)
    return page


def _refusal_with_image_retry(page: Any) -> str:
    _focus_page(page)
    try:
        main_text = str(page.locator("main").inner_text(timeout=2500) or "").lower()
    except Exception:
        main_text = ""
    if any(marker in main_text for marker in _IMAGE_ERROR_MARKERS):
        already = bool(getattr(page, "_cs_generic_image_retry_clicked", False))
        if not already:
            try:
                button = page.get_by_role("button", name=re.compile(r"^(Repetir|Retry|Try again)$", re.I)).last
                if button.count() and button.is_visible() and button.is_enabled():
                    button.click(timeout=1500)
                    setattr(page, "_cs_generic_image_retry_clicked", True)
                    try:
                        page.wait_for_timeout(700)
                    except Exception:
                        pass
                    return ""
            except Exception:
                pass
        # On a second generic failure, let the existing fallback path take over.
        if already:
            return main_text
    if callable(_ORIGINAL_REFUSAL_TEXT):
        return str(_ORIGINAL_REFUSAL_TEXT(page) or "")
    return ""


def install_addition_active_chat_capture_policy() -> None:
    global _INSTALLED, _ORIGINAL_BIND_CHAT_PAGE, _ORIGINAL_DESCRIPTION_CANDIDATES
    global _ORIGINAL_IMAGE_CANDIDATES, _ORIGINAL_ATTACH_REFERENCE, _ORIGINAL_REFUSAL_TEXT
    if _INSTALLED:
        return

    _ORIGINAL_BIND_CHAT_PAGE = binding._bind_chat_page
    _ORIGINAL_DESCRIPTION_CANDIDATES = binding._description_candidates
    _ORIGINAL_IMAGE_CANDIDATES = binding._assistant_image_candidates
    _ORIGINAL_ATTACH_REFERENCE = creative._attach_reference
    _ORIGINAL_REFUSAL_TEXT = parallel._assistant_refusal_text

    binding._bind_chat_page = _bind_and_focus
    binding._description_candidates = _description_candidates_active
    binding._assistant_image_candidates = _image_candidates_active
    creative._attach_reference = _attach_reference_verified
    parallel._assistant_refusal_text = _refusal_with_image_retry

    _INSTALLED = True
