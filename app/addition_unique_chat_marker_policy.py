from __future__ import annotations

import base64
import hashlib
import re
import time
import uuid
from typing import Any, Mapping

import app.addition_chat_binding_policy as binding
import app.addition_chatgpt_response_reader_policy as response_reader
import app.addition_real_chat_url_policy as real_url
import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_DESCRIPTION_PROMPT = None
_ORIGINAL_IMAGE_PROMPT = None
_ORIGINAL_BIND_CHAT_PAGE = None
_ORIGINAL_IMAGE_CANDIDATES = None
_ORIGINAL_ELEMENT_IMAGE_DATA_URL = None

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
        f"IDENTIFICADOR INTERNO: {token}\n"
        "Use esse identificador apenas para o CrapScraper localizar esta execução. Não o repita na resposta final.\n\n"
        f"{base}\n\n"
        f"{token}-END"
    )


def _image_prompt_named(job: Mapping[str, Any]) -> str:
    token = _run_token(job, "IMG")
    base = _ORIGINAL_IMAGE_PROMPT(job).rstrip()
    return (
        f"IDENTIFICADOR INTERNO: {token}\n"
        "Use esse identificador apenas para o CrapScraper localizar esta execução. Não o reproduza na imagem.\n\n"
        f"{base}\n\n"
        f"{token}-END"
    )


def _main_text(page: Any) -> str:
    try:
        node = page.locator("main")
        raw = str(node.text_content(timeout=3000) or "")
        if raw:
            return raw
    except Exception:
        pass
    try:
        return str(page.evaluate("() => String(document.querySelector('main')?.textContent || '')") or "")
    except Exception:
        try:
            return str(page.locator("main").inner_text(timeout=3000) or "")
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


def _latest_conversation_description_candidates(page: Any) -> list[str]:
    """Read the actual answer turn without depending on ChatGPT's internal role selectors."""
    try:
        rows = response_reader._conversation_candidates(page)
    except Exception:
        rows = []

    values: list[str] = []
    seen: set[str] = set()
    for item in reversed(list(rows or [])):
        raw = str(item.get("text") if isinstance(item, Mapping) else item or "").strip()
        if not raw:
            continue
        lowered = " ".join(raw.lower().split())
        if (
            "pesquise e escreva somente a breve descrição comercial" in lowered
            or "identificador interno:" in lowered
            or "gere somente a imagem principal" in lowered
        ):
            continue
        value = final_validation._validated_description(raw)
        if value and value not in seen:
            seen.add(value)
            values.append(value)

    try:
        selected = response_reader._select_description_candidate(rows)
    except Exception:
        selected = ""
    if selected and selected not in seen:
        values.insert(0, selected)

    return values


def _last_turn_text_candidates(page: Any) -> list[str]:
    """Fallback for layouts where role/data-testid attributes disappear.

    It inspects the final conversation/article/prose blocks in DOM order and ignores
    the outgoing prompt by its own signatures.
    """
    try:
        result = page.evaluate(
            """
            () => {
              const main = document.querySelector('main');
              if (!main) return [];
              const selectors = [
                '[data-testid^="conversation-turn-"]',
                '[data-testid*="conversation-turn"]',
                'article',
                '.markdown',
                '[class*="markdown"]',
                '[class*="prose"]'
              ];
              const nodes = [...main.querySelectorAll(selectors.join(','))];
              const seen = new Set();
              const out = [];
              for (const node of nodes) {
                const text = String(node.innerText || node.textContent || '').trim();
                if (!text || seen.has(text)) continue;
                seen.add(text);
                out.push(text);
              }
              return out.slice(-30);
            }
            """
        )
    except Exception:
        return []

    values: list[str] = []
    seen: set[str] = set()
    for raw in reversed(list(result or [])):
        text = str(raw or "").strip()
        normalized = " ".join(text.lower().split())
        if (
            not text
            or "pesquise e escreva somente a breve descrição comercial" in normalized
            or "identificador interno:" in normalized
            or "gere somente a imagem principal" in normalized
        ):
            continue
        candidate = final_validation._validated_description(text)
        if candidate and candidate not in seen:
            seen.add(candidate)
            values.append(candidate)
    return values


def _description_candidates_resilient(page: Any) -> list[str]:
    values = _visible_description_candidates(page)
    if values:
        return values

    values = _latest_conversation_description_candidates(page)
    if values:
        return values

    values = _last_turn_text_candidates(page)
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
                .map((img, index) => ({
                  index,
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


def _new_large_images_anywhere(page: Any, before: set[str]) -> list[dict[str, Any]]:
    """Fallback independent of assistant-role classification."""
    try:
        result = page.evaluate(
            """
            (before) => {
              const seenBefore = new Set(before || []);
              const main = document.querySelector('main') || document.body;
              return [...main.querySelectorAll('img')]
                .map((img, index) => ({
                  index,
                  src: String(img.currentSrc || img.src || ''),
                  width: Number(img.naturalWidth || 0),
                  height: Number(img.naturalHeight || 0),
                  alt: String(img.alt || ''),
                  visible: !!(img.getClientRects().length && img.offsetWidth && img.offsetHeight),
                }))
                .filter(item => item.src && item.visible && item.width >= 256 && item.height >= 256 &&
                  !seenBefore.has(item.src) && !item.src.includes('avatar') && !item.src.includes('icon'));
            }
            """,
            list(before),
        )
    except Exception:
        return []
    rows = [dict(item) for item in (result or []) if isinstance(item, Mapping)]
    rows.sort(key=lambda item: (int(item.get("width") or 0) * int(item.get("height") or 0)), reverse=True)
    return rows


def _assistant_image_candidates_resilient(page: Any, before: set[str]) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = (
        _images_after_image_marker(page, before),
        _ORIGINAL_IMAGE_CANDIDATES(page, before),
        _new_large_images_anywhere(page, before),
    )
    for rows in sources:
        for item in rows or []:
            row = dict(item)
            src = str(row.get("src") or "")
            if not src or src in seen:
                continue
            seen.add(src)
            combined.append(row)
    combined.sort(
        key=lambda item: (int(item.get("width") or 0) * int(item.get("height") or 0)),
        reverse=True,
    )
    return combined


def _element_image_data_url_resilient(page: Any, candidate: Mapping[str, Any], reference_sha: str) -> str:
    source = str(candidate.get("src") or "").strip()
    if source:
        try:
            images = page.locator("img")
            count = images.count()
            for index in range(max(0, count - 80), count):
                locator = images.nth(index)
                try:
                    current = str(locator.evaluate("img => String(img.currentSrc || img.src || '')") or "")
                    if current != source or not locator.is_visible():
                        continue
                    raw = locator.screenshot(type="png")
                    if not raw or len(raw) < 20_000:
                        continue
                    current_sha = hashlib.sha256(raw).hexdigest()
                    if reference_sha and current_sha == reference_sha:
                        continue
                    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
                except Exception:
                    continue
        except Exception:
            pass
    if callable(_ORIGINAL_ELEMENT_IMAGE_DATA_URL):
        return _ORIGINAL_ELEMENT_IMAGE_DATA_URL(page, candidate, reference_sha)
    return ""


def _desired_chat_name(job_id: str, label: str) -> str:
    try:
        job = additions._row(job_id)
    except Exception:
        job = {}
    name = " ".join(str(job.get("source_name") or job.get("title") or "Produto WordPress").split()).strip()
    if len(name) > 92:
        name = name[:89].rstrip() + "..."
    prefix = "Descrição" if "chat 1" in str(label).lower() else "Imagem" if "chat 2" in str(label).lower() else "Chat"
    return f"{prefix} [{name}]".strip()


def _best_effort_name_chat(page: Any, desired: str) -> bool:
    if not desired or not real_url._is_real_conversation_url(real_url._page_url(page)):
        return False
    current = real_url._page_url(page)
    path = re.sub(r"^https?://[^/]+", "", current)
    try:
        link = page.locator(f'a[href="{path}"], a[href$="{path}"]').first
        if link.count():
            containers = [
                link.locator("xpath=ancestor::li[1]"),
                link.locator("xpath=ancestor::div[.//button][1]"),
                link.locator("xpath=.."),
            ]
            for container in containers:
                try:
                    if not container.count():
                        continue
                    buttons = container.locator("button")
                    for idx in range(buttons.count() - 1, -1, -1):
                        button = buttons.nth(idx)
                        label = " ".join([
                            str(button.get_attribute("aria-label") or ""),
                            str(button.get_attribute("title") or ""),
                            str(button.get_attribute("data-testid") or ""),
                        ]).lower()
                        if label and not any(word in label for word in ("menu", "option", "opç", "more", "mais")):
                            continue
                        try:
                            button.click(timeout=1200)
                        except Exception:
                            continue
                        rename_item = page.get_by_text(re.compile(r"^(Renomear|Rename)$", re.I)).last
                        try:
                            if not rename_item.count():
                                continue
                            rename_item.click(timeout=1200)
                            visible_inputs = page.locator("input:visible")
                            if not visible_inputs.count():
                                continue
                            field = visible_inputs.last
                            field.fill(desired, timeout=1500)
                            field.press("Enter")
                            return True
                        except Exception:
                            continue
                except Exception:
                    continue

        buttons = page.locator("button")
        for i in range(min(buttons.count(), 100)):
            button = buttons.nth(i)
            label = " ".join([
                str(button.get_attribute("aria-label") or ""),
                str(button.get_attribute("title") or ""),
            ]).lower()
            if not any(word in label for word in ("renome", "rename")):
                continue
            try:
                button.click(timeout=1000)
                field = page.locator("input:visible").last
                field.fill(desired, timeout=1500)
                field.press("Enter")
                return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _bind_chat_page_named(context: Any, current: Any, chat_url: str, project_url: str, job_id: str, label: str) -> Any:
    page = _ORIGINAL_BIND_CHAT_PAGE(context, current, chat_url, project_url, job_id, label)
    if real_url._is_real_conversation_url(real_url._page_url(page)):
        desired = _desired_chat_name(job_id, label)
        marker_kind = "DESC" if "chat 1" in label.lower() else "IMG" if "chat 2" in label.lower() else "CHAT"
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
    global _ORIGINAL_BIND_CHAT_PAGE, _ORIGINAL_IMAGE_CANDIDATES, _ORIGINAL_ELEMENT_IMAGE_DATA_URL
    if _INSTALLED:
        return

    _ORIGINAL_DESCRIPTION_PROMPT = binding._description_only_prompt
    _ORIGINAL_IMAGE_PROMPT = binding.parallel._parallel_image_prompt
    _ORIGINAL_BIND_CHAT_PAGE = binding._bind_chat_page
    _ORIGINAL_IMAGE_CANDIDATES = binding._assistant_image_candidates
    _ORIGINAL_ELEMENT_IMAGE_DATA_URL = binding._element_image_data_url

    binding._description_candidates_legacy = binding._description_candidates
    binding._description_only_prompt = _description_prompt_named
    binding.parallel._parallel_image_prompt = _image_prompt_named
    binding._description_candidates = _description_candidates_resilient
    binding._assistant_image_candidates = _assistant_image_candidates_resilient
    binding._element_image_data_url = _element_image_data_url_resilient
    binding._bind_chat_page = _bind_chat_page_named

    _INSTALLED = True
