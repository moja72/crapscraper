from __future__ import annotations

from typing import Any

_INSTALLED = False


def _image_candidate_key(item: dict[str, Any]) -> str:
    """Stable-enough key for comparing conversation images before/after generation.

    ChatGPT sometimes reuses blob/src URLs while appending another rendered image.
    occurrence is preferred when supplied by the collector; index is a fallback
    used by tests and older callers.
    """
    src = str(item.get("src") or "").strip()
    occurrence = item.get("occurrence")
    if occurrence is None:
        occurrence = item.get("index", 0)
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    return f"{src}|{occurrence}|{width}x{height}"


def _is_probable_generated_image(item: dict[str, Any]) -> bool:
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    if width < 256 or height < 256:
        return False

    src = str(item.get("src") or "").strip()
    if not src or src.startswith("data:image/svg"):
        return False

    text = f"{src} {item.get('alt') or ''} {item.get('aria') or ''}".casefold()
    # Evita elementos grandes de conta/UI sem bloquear imagens do produto que
    # naturalmente possam conter a palavra 'logo' em algum atributo.
    blocked = (
        "avatar",
        "profile picture",
        "foto do perfil",
        "user profile",
        "favicon",
        "chatgpt logo",
        "openai logo",
    )
    return not any(token in text for token in blocked)


def candidate_render_area(item: dict[str, Any]) -> float:
    width = float(item.get("display_width") or 0)
    height = float(item.get("display_height") or 0)
    if width > 0 and height > 0:
        return width * height
    return float(item.get("width") or 0) * float(item.get("height") or 0)


def candidate_images(page: Any) -> list[dict[str, Any]]:
    """Find large images in the conversation without depending on assistant role DOM.

    The current ChatGPT UI does not consistently expose
    data-message-author-role='assistant' on generated-image turns. Prefer every
    large IMG inside <main>; only fall back to the whole document if <main>
    contains no usable image.
    """

    def collect(selector: str, scope: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        occurrences: dict[str, int] = {}
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            return []

        for index in range(count):
            image = locator.nth(index)
            try:
                info = image.evaluate(
                    """img => {
                      const rect = img.getBoundingClientRect();
                      return {
                        src: img.currentSrc || img.src || '',
                        width: img.naturalWidth || img.width || 0,
                        height: img.naturalHeight || img.height || 0,
                        display_width: Math.max(0, rect.width || 0),
                        display_height: Math.max(0, rect.height || 0),
                        alt: img.alt || '',
                        aria: img.getAttribute('aria-label') || '',
                        complete: Boolean(img.complete)
                      };
                    }"""
                )
            except Exception:
                continue
            if not isinstance(info, dict):
                continue
            info["scope"] = scope
            info["index"] = index
            if not _is_probable_generated_image(info):
                continue
            src = str(info.get("src") or "").strip()
            occurrences[src] = occurrences.get(src, 0) + 1
            info["occurrence"] = occurrences[src]
            info["locator"] = image
            items.append(info)
        return items

    main = collect("main img", "main")
    if main:
        return main
    return collect("img", "document")


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from app.additions import chatgpt_playwright as legacy

    legacy._candidate_images = candidate_images
    # Exponha também no módulo legado para compatibilidade com diagnósticos e
    # testes externos já existentes.
    legacy._image_candidate_key = _image_candidate_key
    legacy._is_probable_generated_image = _is_probable_generated_image
    _INSTALLED = True


__all__ = [
    "candidate_images",
    "candidate_render_area",
    "install",
    "_image_candidate_key",
    "_is_probable_generated_image",
]
