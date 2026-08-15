from __future__ import annotations

import os
from typing import Any, Callable

import app.web as web

_INSTALLED = False
_BASE_UPDATE_PREREQUISITES: Callable[..., dict[str, Any]] | None = None

# Produto público e estável usado somente para confirmar que a sessão autenticada
# realmente recebe autorização da API de downloads. Nenhum arquivo é baixado.
_DEFAULT_PROBE_URL = "https://plugintheme.net/product/memberpress-downloads"


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _live_plugintheme_access_probe(app: Any) -> dict[str, Any]:
    """Valida a sessão pelo backend real de acesso, não apenas pela presença de cookies."""
    probe_url = os.getenv("SCRAPER_PLUGINTHEME_SESSION_PROBE_URL", _DEFAULT_PROBE_URL).strip() or _DEFAULT_PROBE_URL

    try:
        # Este módulo já é usado pelo fluxo real de preparação. Em instalações antigas
        # ele pode existir apenas localmente; falhar aqui deve significar "não validado",
        # nunca um falso positivo baseado em contagem de cookies.
        from app.integrations.ultrapack_session import get_authenticated_plugintheme_session
        from app.integrations.plugintheme_download import PluginThemeDownloader

        auth = get_authenticated_plugintheme_session(app, probe_url)
        if not bool(getattr(auth, "authenticated", False)):
            return {
                "ok": False,
                "authenticated": False,
                "access_allowed": False,
                "status": "SESSÃO INVÁLIDA",
                "message": "Cookies encontrados, mas a sessão PluginTheme não está autenticada.",
            }

        session = getattr(auth, "session", None)
        if session is None:
            return {
                "ok": False,
                "authenticated": False,
                "access_allowed": False,
                "status": "SESSÃO INVÁLIDA",
                "message": "A sessão PluginTheme não está disponível para validação.",
            }

        product_response = session.get(probe_url, timeout=20)
        product_response.raise_for_status()
        product = PluginThemeDownloader.product_data(probe_url, product_response.text)
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            raise RuntimeError("Produto de prova sem identificador")

        check = session.get(
            f"{PluginThemeDownloader.API_BASE}/downloads/{product_id}/check-access",
            timeout=20,
        )
        check.raise_for_status()
        payload = check.json()
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            payload = payload["data"]

        allowed = PluginThemeDownloader.access_allowed(payload)
        if not allowed:
            return {
                "ok": False,
                "authenticated": True,
                "access_allowed": False,
                "status": "SEM ACESSO",
                "message": "A sessão existe, mas a API de downloads não autorizou o acesso.",
            }

        return {
            "ok": True,
            "authenticated": True,
            "access_allowed": True,
            "status": "VÁLIDOS",
            "message": "Sessão autenticada e acesso de download confirmado pela API PluginTheme.",
        }
    except Exception as error:
        return {
            "ok": False,
            "authenticated": False,
            "access_allowed": False,
            "status": "NÃO VALIDADA",
            "message": f"Não foi possível confirmar a sessão PluginTheme: {type(error).__name__}.",
        }


def _patched_update_prerequisites(*, check_ssh_connection: bool = False, app: Any = None) -> dict[str, Any]:
    base = _BASE_UPDATE_PREREQUISITES
    if base is None:
        result = web.prerequisite_status()
    else:
        try:
            result = base(check_ssh_connection=check_ssh_connection, app=app)
        except ModuleNotFoundError:
            # Evita que um módulo local/legado ausente derrube todo o diagnóstico.
            result = web.prerequisite_status()

    result = dict(result or {})
    if app is None:
        return result

    previous = result.get("plugintheme_cookies")
    previous = dict(previous) if isinstance(previous, dict) else {}
    live = _live_plugintheme_access_probe(app)

    # Preserva a contagem exibida pela integração existente, mas o campo `ok` passa
    # a refletir exclusivamente a prova real de autenticação + autorização da API.
    result["plugintheme_cookies"] = {
        **previous,
        **live,
        "count": _safe_count(previous.get("count", 0)),
    }
    return result


def install_session_validation_policy() -> None:
    global _INSTALLED, _BASE_UPDATE_PREREQUISITES
    if _INSTALLED:
        return
    _BASE_UPDATE_PREREQUISITES = web._update_prerequisites
    web._update_prerequisites = _patched_update_prerequisites
    _INSTALLED = True
