from __future__ import annotations

import re
import time
import uuid
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_real_chat_url_policy as real_url
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_DESCRIPTION_PROMPT = None
_ORIGINAL_IMAGE_PROMPT = None
_ORIGINAL_BIND_CHAT_PAGE = None
_ORIGINAL_IMAGE_CANDIDATES = None

_DESC_MARKER_RE = re.compile(r"CSADD-[A-Z0-9-]+-DESC-END", re.I)
_IMG_MARKER_RE = re.compile(r"CSADD-[A-Z0-9-]+-IMG-END", re.I)


def _run_token(job: Mapping[str, Any], kind: str) -> str:
    job_id = re.sub(r"[^A-Za-z0-9]", "", str(job.get("job_id") or "ADD"))[-8:] or "ADD"
    stamp = time.strftime("%H%M%S")
    nonce = uuid.uuid4().hex[:6].upper()
    return f"CSADD-{job_id.upper()}-{stamp}-{nonce}-{kind.upper()}"


def _description_prompt_named(job: Mapping[str, Any]) -> str:
    token = _run_token(job, "DESC")
    base = _ORIGINAL_DESCRIPTION_PROMPT(job).rstrip()
    return (
        f"NOME INTERNO DESTA CONVERSA: {token}\n"
        "Use esse identificador apenas para distinguir esta conversa. Não o repita na resposta final.\n\n"
        f"{base}\n\n"
        f"{token}-END"
    )


def _image_prompt_named(job: Mapping[str, Any]) -> str:
    token = _run_token(job, "IMG")
    base = _ORIGINAL_IMAGE_PROMPT(job).rstrip()
    return (
        f"NOME INTERNO DESTA CONVERSA: {token}\n"
        "Use esse identificador apenas para distinguir esta conversa. Não o reproduza na imagem.\n\n"
        f"{base}\n\n"
        f"{token}-END"
    )


def _main_text(page: Any) -> str:
    try:
        return str(page.locator("main").inner_text(timeout=3000) or "")
    except Exception:
        try:
            return str(page.evaluate("() => String(document.querySelector('main')?.innerText || '')") or "")
        except Exception:
            return ""


def _text_after_last_marker(text: str, marker_re: re.Pattern[str]) -> str:
    matches = list(marker_re.finditer(str(text or "")))
    if not matches:
        return ""
    return str(text or "")[matches[-1].end():].strip()


def _clean_visible_tail(value: str) -> str:
    lines = []
    for raw in str(value or "").splitlines():
        line = " ".join(raw.split()).strip()
        if not line:
            lines.append("")
            continue
        lowered = line.lower()
        if re.match(r"^(pensou por|worked for)\b", lowered):
            continue
        if lowered in {
            "editar", "edit", "copiar", "copy", "repetir", "retry", "compartilhar", "share",
            "boa resposta", "bad response", "regenerar", "regenerate",
        }:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _visible_description_candidates(page: Any) -> list[str]:
    tail = _clean_visible_tail(_text_after_last_marker(_main_text(page), _DESC_MARKER_RE))
    if not tail:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    blocks = [" ".join(block.split()) for block in re.split(r"\n\s*\n", tail) if block.strip()]
    for block in blocks:
        value = final_validation._validated_description(block)
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    merged = " ".join(line.strip() for line in tail.splitlines() if line.strip())
    value = final_validation._validated_description(merged)
    if value and value not in seen:
        candidates.append(value)

    candidates.sort(key=lambda item: abs(len(item) - 450))
    return candidates


def _description_candidates_resilient(page: Any) -> list[str]:
    values = _visible_description_candidates(page)
    if values:
        return values
    return binding._description_candidates_legacy(page) if hasattr(binding, "_description_candidates_legacy") else []


def _images_after_image_marker(page: Any, before: set[str]) -> list[dict[str, Any]]:
    before_list = list(before)
    try:
        result = page.evaluate(
            """
            ({before, markerPattern}) => {
              const main = document.querySelector('main');
              if (!main) return [];
              const rx = new RegExp(markerPattern, 'i');
              const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
              let markerTextNode = null;
              let node;
              while ((node = walker.nextNode())) {
                if (rx.test(String(node.nodeValue || ''))) markerTextNode = node;
              }
              if (!markerTextNode) return [];
              const markerElement = markerTextNode.parentElement;
              if (!markerElement) return [];
              const seenBefore = new Set(before || []);
              return [...main.querySelectorAll('img')]
                .map(img => ({
                  src: String(img.currentSrc || img.src || ''),
                  width: Number(img.naturalWidth || 0),
                  height: Number(img.naturalHeight || 0),
                  alt: String(img.alt || ''),
                  visible: !!(img.getClientRects().length && img.offsetWidth && img.offsetHeight),
                  after: !!(markerElement.compareDocumentPosition(img) & Node.DOCUMENT_POSITION_FOLLOWING),
                }))
                .filter(item => item.src && item.after && item.visible &&
                  item.width >= 256 && item.height >= 256 && !seenBefore.has(item.src) &&
                  !item.src.includes('avatar') && !item.src.includes('icon'));
            }
            """,
            {"before": before_list, "markerPattern": _IMG_MARKER_RE.pattern},
        )
    except Exception:
        return []
    rows = [dict(item) for item in (result or []) if isinstance(item, Mapping)]
    rows.sort(key=lambda item: (int(item.get("width") or 0) * int(item.get("height") or 0)), reverse=True)
    return rows


def _assistant_image_candidates_resilient(page: Any, before: set[str]) -> list[dict[str, Any]]:
    rows = _images_after_image_marker(page, before)
    if rows:
        return rows
    return _ORIGINAL_IMAGE_CANDIDATES(page, before)


def _best_effort_name_chat(page: Any, desired: str) -> bool:
    if not desired or not real_url._is_real_conversation_url(real_url._page_url(page)):
        return False
    try:
        # Primeiro tente um botão de renomear exposto diretamente no cabeçalho.
        buttons = page.locator("button")
        for i in range(min(buttons.count(), 80)):
            button = buttons.nth(i)
            label = " ".join([
                str(button.get_attribute("aria-label") or ""),
                str(button.get_attribute("title") or ""),
            ]).lower()
            if not any(word in label for word in ("renome", "rename")):
                continue
            try:
                button.click(timeout=1000)
                field = page.locator("input").last
                field.fill(desired, timeout=1500)
                field.press("Enter")
                return True
            except Exception:
                continue

        # Fallback: use o item da conversa no sidebar e o menu contextual correspondente.
        current = real_url._page_url(page)
        path = re.sub(r"^https?://[^/]+", "", current)
        link = page.locator(f'a[href="{path}"]').first
        if link.count():
            container = link.locator("xpath=ancestor-or-self::*[self::li or self::div][1]")
            menu = container.locator("button").last
            if menu.count():
                menu.click(timeout=1200)
                rename_item = page.get_by_text(re.compile(r"^(Renomear|Rename)$", re.I)).last
                if rename_item.count():
                    rename_item.click(timeout=1200)
                    field = page.locator("input").last
                    field.fill(desired, timeout=1500)
                    field.press("Enter")
                    return True
    except Exception:
        return False
    return False


def _bind_chat_page_named(context: Any, current: Any, chat_url: str, project_url: str, job_id: str, label: str) -> Any:
    page = _ORIGINAL_BIND_CHAT_PAGE(context, current, chat_url, project_url, job_id, label)
    marker_kind = "DESC" if "chat 1" in label.lower() else "IMG" if "chat 2" in label.lower() else ""
    if marker_kind and real_url._is_real_conversation_url(real_url._page_url(page)):
        desired = f"CSADD {str(job_id)[-8:]} {marker_kind}"
        key = f"_cs_named_{marker_kind.lower()}"
        try:
            if not getattr(page, key, False):
                if _best_effort_name_chat(page, desired):
                    one_click._emit(job_id, f"{label}: conversa renomeada para {desired}.", step="chatgpt")
                setattr(page, key, True)
        except Exception:
            pass
    return page


def install_addition_unique_chat_marker_policy() -> None:
    global _INSTALLED, _ORIGINAL_DESCRIPTION_PROMPT, _ORIGINAL_IMAGE_PROMPT
    global _ORIGINAL_BIND_CHAT_PAGE, _ORIGINAL_IMAGE_CANDIDATES
    if _INSTALLED:
        return

    _ORIGINAL_DESCRIPTION_PROMPT = binding._description_only_prompt
    _ORIGINAL_IMAGE_PROMPT = binding.parallel._parallel_image_prompt
    _ORIGINAL_BIND_CHAT_PAGE = binding._bind_chat_page
    _ORIGINAL_IMAGE_CANDIDATES = binding._assistant_image_candidates

    binding._description_candidates_legacy = binding._description_candidates
    binding._description_only_prompt = _description_prompt_named
    binding.parallel._parallel_image_prompt = _image_prompt_named
    binding._description_candidates = _description_candidates_resilient
    binding._assistant_image_candidates = _assistant_image_candidates_resilient
    binding._bind_chat_page = _bind_chat_page_named

    _INSTALLED = True
