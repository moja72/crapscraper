from __future__ import annotations

from pathlib import Path
from typing import Any

import app.web as web
from app.update_credit_diagnostics_policy import install_update_credit_diagnostics_policy

_INSTALLED = False
_ORIGINAL_RENDER_PANEL_PAGE = web.render_panel_page
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_recovery.js"


def _script_block(path: Path, attribute: str) -> str:
    try:
        script = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    script = script.replace("</script>", "<\\/script>")
    return f"\n<script {attribute}>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    html = _ORIGINAL_RENDER_PANEL_PAGE(*args, **kwargs)
    block = _script_block(_SCRIPT_PATH, "data-update-recovery-ui")
    if not block:
        return html

    marker = "</body>"
    if marker in html:
        return html.replace(marker, block + marker, 1)
    return html + block


def install_update_recovery_policy() -> None:
    """Ativa as estratégias reais de recuperação usadas pelos retries."""
    global _INSTALLED
    if _INSTALLED:
        return

    install_update_credit_diagnostics_policy()
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True

    from app.update_recoverability_policy import install_update_recoverability_policy
    from app.update_metadata_preflight_policy import install_update_metadata_preflight_policy

    install_update_recoverability_policy()
    install_update_metadata_preflight_policy()
