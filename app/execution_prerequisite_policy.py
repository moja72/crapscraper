from __future__ import annotations

from typing import Any, Callable

from app import settings
import app.web as web

_INSTALLED = False
_BASE_PREREQUISITE_STATUS: Callable[..., dict[str, Any]] | None = None
_BASE_RENDER_PANEL_PAGE: Callable[..., str] | None = None


def _patched_prerequisite_status() -> dict[str, Any]:
    if _BASE_PREREQUISITE_STATUS is None:
        return {}
    result = dict(_BASE_PREREQUISITE_STATUS())
    enabled = bool(settings.UPDATE_EXECUTION_ENABLED)
    allowed = sorted(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS)

    result["woocommerce_write"] = {
        "ok": enabled,
        "status": "HABILITADA" if enabled else "BLOQUEADA",
        "mode": "pt_versao_controlada",
    }
    result["remote_execution"] = {
        "ok": enabled,
        "status": "HABILITADA" if enabled else "BLOQUEADA",
    }
    update_execution = dict(result.get("update_execution") or {})
    update_execution.update(
        enabled=enabled,
        status="HABILITADA" if enabled else "BLOQUEADA",
        allowed_product_ids=allowed,
        allow_all_products=not bool(allowed),
    )
    result["update_execution"] = update_execution
    return result


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    if _BASE_RENDER_PANEL_PAGE is None:
        return ""
    html = _BASE_RENDER_PANEL_PAGE(*args, **kwargs)
    enabled = "true" if settings.UPDATE_EXECUTION_ENABLED else "false"
    allow_all = "true" if not settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS else "false"
    allowed = ",".join(str(item) for item in sorted(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS))
    script = f"""
<script data-execution-status-fix>
(() => {{
  'use strict';
  const EXECUTION_ENABLED = {enabled};
  const ALLOW_ALL = {allow_all};
  const ALLOWED_IDS = {allowed!r};

  function syncExecutionStatus() {{
    const lock = document.getElementById('updates_execution_lock');
    if (lock) {{
      if (EXECUTION_ENABLED) {{
        lock.textContent = ALLOW_ALL
          ? 'Execução real habilitada · produtos com plano válido podem ser executados'
          : `Execução real habilitada · produtos permitidos: ${{ALLOWED_IDS || 'nenhum'}}`;
        lock.style.borderColor = '#166534';
        lock.style.background = 'rgba(22, 101, 52, .18)';
        lock.style.color = '#86efac';
      }} else {{
        lock.textContent = 'Execução real bloqueada para homologação';
        lock.style.borderColor = '';
        lock.style.background = '';
        lock.style.color = '';
      }}
    }}

    const summary = document.getElementById('updates_environment_summary');
    const chips = Array.from(document.querySelectorAll('#updates_environment_chips .environment-chip strong'));
    if (summary && chips.length) {{
      const blocked = chips.filter(node => !['OK', 'HABILITADA'].includes((node.textContent || '').trim().toUpperCase()));
      summary.textContent = blocked.length
        ? `${{blocked.length}} requisito(s) exigem atenção`
        : 'Todos os pré-requisitos estão OK';
    }}
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', syncExecutionStatus, {{ once: true }});
  }} else {{
    syncExecutionStatus();
  }}
  [150, 500, 1200].forEach(delay => setTimeout(syncExecutionStatus, delay));
  setInterval(syncExecutionStatus, 1500);
  document.addEventListener('click', event => {{
    if (event.target && event.target.id === 'updates_check_prerequisites') {{
      setTimeout(syncExecutionStatus, 400);
      setTimeout(syncExecutionStatus, 1200);
    }}
  }});
}})();
</script>
"""
    return html.replace("</body>", script + "</body>", 1) if "</body>" in html else html + script


def install_execution_prerequisite_policy() -> None:
    global _INSTALLED, _BASE_PREREQUISITE_STATUS, _BASE_RENDER_PANEL_PAGE
    if _INSTALLED:
        return
    _BASE_PREREQUISITE_STATUS = web.prerequisite_status
    _BASE_RENDER_PANEL_PAGE = web.render_panel_page
    web.prerequisite_status = _patched_prerequisite_status
    web.render_panel_page = _patched_render_panel_page
    _INSTALLED = True
