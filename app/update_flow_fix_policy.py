from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_RENDER: Callable[..., str] | None = None
_BASE_PREPARATION_FACTORY: Callable[..., Any] | None = None
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_queue_fix.js"


def _fresh_plugintheme_profile_session(app: Any, logger: Any = None) -> Any | None:
    """Recria a sessão HTTP a partir do perfil renovado antes de preparar updates.

    O fluxo de Adicionar já possui recuperação forte de cookies/token do perfil
    persistente. Atualizar precisa usar a mesma fonte de verdade; do contrário,
    um ``plugintheme_http_session`` antigo pode continuar existindo em memória e
    a preparação falha mesmo depois de o usuário renovar o login no Chrome.
    """
    try:
        from app.addition_plugintheme_profile_recovery_policy import _profile_http_session
    except Exception:
        return None

    try:
        session, detail = _profile_http_session(app)
    except Exception as error:
        if callable(logger):
            logger(
                "ℹ Não foi possível reler o perfil PluginTheme para a atualização: "
                f"{type(error).__name__}. Tentando a sessão já carregada."
            )
        return None

    if session is None:
        if callable(logger) and detail:
            logger(f"ℹ Perfil PluginTheme não reutilizado na atualização: {detail}")
        return None

    # Mantém a sessão renovada disponível também para os demais helpers do app.
    try:
        app.plugintheme_http_session = session
    except Exception:
        pass

    if callable(logger):
        suffix = f" {detail}" if detail else ""
        logger(
            "✅ Sessão PluginTheme relida do perfil renovado para preparar a atualização."
            + suffix
        )
    return session


def _patched_build_update_preparation_service(app: Any, logger: Any = None) -> Any:
    """Usa o perfil renovado no update e mantém fallback para a sessão existente.

    Para PluginTheme, reler o perfil primeiro evita dois falsos negativos que
    impediam a ação ``Preparar e gerar plano``:

    * sessão HTTP antiga permanecendo em memória após ``Renovar sessão``;
    * bearer token/entitlement de bundles reconhecido pelo fluxo de Adicionar,
      mas não reaproveitado pelo fluxo de Atualizar.

    A autorização real continua sendo verificada pelo downloader logo depois;
    esta policy apenas escolhe a sessão correta, sem presumir acesso.
    """
    base = _BASE_PREPARATION_FACTORY
    if base is None:
        raise RuntimeError("Factory de preparação indisponível")
    service = base(app, logger)
    original_provider = getattr(service, "session_provider", None)
    if not callable(original_provider):
        return service

    def resilient_provider(job: Any) -> Any:
        from app.integrations.plugintheme_download import SourceDownloader

        source_url = str(getattr(job, "ultrapack_url", "") or "").strip()
        if not SourceDownloader.is_plugintheme(source_url):
            return original_provider(job)

        # O perfil persistente é a fonte mais nova depois do botão Renovar
        # sessão. A função é substituída em runtime pela recuperação robusta de
        # entitlement, portanto raw bearer tokens e bundles também são cobertos.
        fresh = _fresh_plugintheme_profile_session(app, logger)
        if fresh is not None:
            return fresh

        try:
            return original_provider(job)
        except Exception:
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
