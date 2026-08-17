from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_PREPARATION_FACTORY: Callable[..., Any] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_queue_fix.js"


def _patched_build_update_preparation_service(app: Any, logger: Any = None) -> Any:
    """Reaproveita a sessão HTTP existente quando a confirmação auxiliar falha.

    A validação real continua acontecendo logo depois, via inspect_product/download.
    Portanto este fallback evita falso negativo do helper sem transformar cookies
    presentes em autenticação presumida.
    """
    base = _BASE_PREPARATION_FACTORY
    if base is None:
        raise RuntimeError("Factory de preparação indisponível")
    service = base(app, logger)
    original_provider = getattr(service, "session_provider", None)
    if not callable(original_provider):
        return service

    def resilient_provider(job: Any) -> Any:
        try:
            return original_provider(job)
        except Exception as error:
            from app.integrations.plugintheme_download import SourceDownloader

            source_url = str(getattr(job, "ultrapack_url", "") or "").strip()
            if not SourceDownloader.is_plugintheme(source_url):
                raise

            existing = getattr(app, "plugintheme_http_session", None)
            if existing is None:
                raise

            if callable(logger):
                logger(
                    "ℹ A confirmação auxiliar da sessão PluginTheme falhou; "
                    "reutilizando a sessão HTTP carregada e validando diretamente na fonte."
                )
            return existing

    service.session_provider = resilient_provider
    return service


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return html
    script = script.replace("</script>", "<\\/script>")
    block = f"\n<script data-update-queue-fix>\n{script}\n</script>\n"
    marker = "</body>"
    return html.replace(marker, block + marker, 1) if marker in html else html + block


def install_update_flow_fix_policy() -> None:
    global _INSTALLED, _BASE_RENDER, _BASE_PREPARATION_FACTORY
    if _INSTALLED:
        return
    _BASE_PREPARATION_FACTORY = web._build_update_preparation_service
    web._build_update_preparation_service = _patched_build_update_preparation_service
    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
