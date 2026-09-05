from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_INSTALLED = False


def _mode() -> str:
    return (os.getenv("SCRAPER_CHATGPT_AUTOMATION_MODE") or "playwright").strip().lower()


def install_addition_chatgpt_playwright() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    # Corrige descoberta do compositor, reaproveita o perfil persistente legado,
    # persiste a URL concreta do projeto, usa navegador real minimizado no
    # Windows e torna a captura da resposta textual independente do DOM instável
    # do ChatGPT.
    from app.additions.chatgpt_playwright_compat import install as install_compat
    from app.additions.chatgpt_project_url_recovery import install as install_project_url_recovery
    from app.additions.chatgpt_background_project_runtime import install as install_background_project_runtime
    from app.additions.chatgpt_content_response_runtime import install as install_content_response_runtime

    install_compat()
    install_project_url_recovery()
    install_background_project_runtime()
    install_content_response_runtime()

    from app.additions.chatgpt import ChatGPTContentService
    from app.additions.images import ImageService
    import app.additions.executor as executor_module
    from app.additions.chatgpt_content_response_runtime import generate_content
    from app.additions.chatgpt_playwright import content_reusable
    from app.additions.chatgpt_playwright_image import generate_image, image_valid

    original_content_generate = ChatGPTContentService.generate
    original_image_generate = ImageService.generate
    original_image_valid = ImageService.valid
    original_valid_content = executor_module.valid_content

    def content_generate(self: Any, job: dict[str, Any]) -> dict[str, Any]:
        if _mode() != "playwright":
            return original_content_generate(self, job)
        return generate_content(job)

    def image_generate(self: Any, job: dict[str, Any]) -> Path:
        if _mode() != "playwright":
            return original_image_generate(self, job)
        return generate_image(job, Path(self.root))

    def valid_image(self: Any, path: str) -> bool:
        if _mode() != "playwright":
            return original_image_valid(self, path)
        return image_valid(path)

    def valid_browser_content(value: dict[str, Any]) -> bool:
        if _mode() != "playwright":
            return original_valid_content(value)
        return bool(original_valid_content(value) and content_reusable(value))

    ChatGPTContentService.generate = content_generate
    ImageService.generate = image_generate
    ImageService.valid = valid_image
    executor_module.valid_content = valid_browser_content
    ChatGPTContentService._crapscraper_playwright_generation = True
    ImageService._crapscraper_playwright_generation = True
    _INSTALLED = True


__all__ = ["install_addition_chatgpt_playwright"]