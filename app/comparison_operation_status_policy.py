from __future__ import annotations

import copy
import re
import sqlite3
from pathlib import Path
from typing import Any, Mapping

import app.comparison as comparison
import app.new_product_workflow_policy as additions
import app.web as web
from app.operations.runtime import history_jobs


_INSTALLED = False
_BASE_GET_CACHED = None
_BASE_RENDER = None
_BASE_LIST_APPROVED_UPDATES = None


def _generic_origin_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\bUltraPackV?2\b|\bUltrapackV?2\b|\bUltraPack\b|\bUltrapack\b", "site de origem", text, flags=re.I)
    text = re.sub(r"\bNovo no site de origem\b", "Novo", text, flags=re.I)
    if text.startswith("site de origem"):
        text = "Site de origem" + text[len("site de origem"):]
    return text


def _genericize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key in (
        "status_label", "status_reason", "recommended_action_label",
        "site_version_reason", "source_version_reason", "match_method_label",
        "match_level_label", "decision_label", "decision_note",
    ):
        if key in result:
            result[key] = _generic_origin_text(result.get(key))
    for key in ("match_favorable_signals", "match_conflicting_signals"):
        result[key] = [_generic_origin_text(item) for item in (result.get(key) or [])]
    candidates = []
    for candidate in result.get("match_candidates", []) or []:
        if not isinstance(candidate, Mapping):
            continue
        current = dict(candidate)
        if "match_level_label" in current:
            current["match_level_label"] = _generic_origin_text(current.get("match_level_label"))
        current["favorable_signals"] = [_generic_origin_text(item) for item in (current.get("favorable_signals") or [])]
        current["conflicting_signals"] = [_generic_origin_text(item) for item in (current.get("conflicting_signals") or [])]
        candidates.append(current)
    if "match_candidates" in result:
        result["match_candidates"] = candidates
    return result


def _completed_additions() -> list[dict[str, Any]]:
    path = Path(additions._DB_PATH)
    if not path.exists():
        return []
    try:
        connection = sqlite3.connect(str(path), timeout=5)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT comparison_item_id, woo_product_id, source_version, completed_at "
            "FROM addition_jobs WHERE state='completed' AND woo_product_id > 0"
        ).fetchall()
        connection.close()
    except Exception:
        return []
    return [dict(row) for row in rows]


def _completed_update_ids() -> set[str]:
    try:
        updates = history_jobs()
    except Exception:
        updates = []
    return {
        str(row.get("comparison_item_id") or "").strip()
        for row in updates
        if str(row.get("state") or "") == "completed"
        and str(row.get("comparison_item_id") or "").strip()
    }


def _pending_approved_updates() -> list[dict[str, Any]]:
    """Expose only approvals that still require work.

    The decision database remains untouched so its audit/history stays intact.  A
    completed update is consumed operationally and must not be materialized into
    the update queue again after a refresh/restart.
    """
    if _BASE_LIST_APPROVED_UPDATES is None:
        return []
    completed = _completed_update_ids()
    return [
        dict(row)
        for row in (_BASE_LIST_APPROVED_UPDATES() or [])
        if str(row.get("comparison_item_id") or "").strip() not in completed
    ]


def _operation_overrides() -> dict[str, dict[str, Any]]:
    overrides: dict[str, dict[str, Any]] = {}

    def register(item_id: str, completed_at: str, status: str, label: str, reason: str, version: str = "") -> None:
        key = str(item_id or "").strip()
        if not key:
            return
        current = overrides.get(key)
        stamp = str(completed_at or "")
        if current and str(current.get("completed_at") or "") > stamp:
            return
        overrides[key] = {
            "completed_at": stamp,
            "status": status,
            "status_label": label,
            "status_reason": reason,
            "version": str(version or ""),
        }

    for row in _completed_additions():
        register(
            str(row.get("comparison_item_id") or ""),
            str(row.get("completed_at") or ""),
            "added",
            "Adicionado",
            f"Produto adicionado ao site como WooCommerce #{int(row.get('woo_product_id') or 0)}.",
            str(row.get("source_version") or ""),
        )

    try:
        updates = history_jobs()
    except Exception:
        updates = []
    for row in updates:
        if str(row.get("state") or "") != "completed":
            continue
        register(
            str(row.get("comparison_item_id") or ""),
            str(row.get("completed_at") or ""),
            "updated",
            "Atualizado",
            "Atualização concluída com sucesso no site.",
            str(row.get("effective_source_version") or row.get("approved_source_version") or ""),
        )
    return overrides


def _apply_operation_status(full: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(full))
    overrides = _operation_overrides()
    rows = []
    for raw in result.get("rows", []) or []:
        row = _genericize_row(raw)
        item_id = str(row.get("comparison_item_id") or "")
        operation = overrides.get(item_id)
        if operation:
            row["status"] = operation["status"]
            row["status_label"] = operation["status_label"]
            row["status_reason"] = operation["status_reason"]
            if operation.get("version"):
                row["site_version"] = operation["version"]
            if operation["status"] == "updated":
                # A aprovação permanece no histórico do banco, mas deixa de ser
                # apresentada como uma ação pendente depois da conclusão.
                row["decision"] = "pending"
                row["decision_label"] = "Atualizado"
                row["decision_note"] = "A aprovação de atualização foi consumida pela execução concluída."
                row["queue_type"] = ""
                row["recommended_action"] = "none"
                row["recommended_action_label"] = "Nenhuma ação necessária"
        rows.append(row)
    result["rows"] = rows

    labels = dict(comparison._STATUS_LABELS)
    labels["source_version_missing"] = "Versão ausente no site de origem"
    labels["new_source"] = "Novo"
    labels["added"] = "Adicionado"
    result["status_labels"] = labels
    counts = {key: 0 for key in labels}
    for row in rows:
        status = str(row.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    result["counts"] = counts
    result["unmatched_source_total"] = counts.get("new_source", 0)
    return result


def _get_cached_with_operations(source_path: Path, site_path: Path, *, force: bool = False) -> dict[str, Any]:
    full = _BASE_GET_CACHED(source_path, site_path, force=force)
    return _apply_operation_status(full)


def _render_with_generic_source_labels(*args: Any, **kwargs: Any) -> str:
    html = _BASE_RENDER(*args, **kwargs)
    replacements = {
        '<option value="updated">Atualizado</option>': '<option value="updated">Atualizado</option><option value="added">Adicionado</option>',
        '<option value="source_version_missing">Versão ausente no Ultrapack</option>': '<option value="source_version_missing">Versão ausente no site de origem</option>',
        '<option value="new_source">Novo no Ultrapack</option>': '<option value="new_source">Novo</option>',
        'Compare o catálogo selecionado do Ultrapack com o catálogo exportado do': 'Compare o catálogo selecionado do site de origem com o catálogo exportado do',
        '<span>Ultrapack</span>': '<span>Site de origem</span>',
        '<span>Versão ausente no Ultrapack</span>': '<span>Versão ausente no site de origem</span>',
        '<span>Versões suspeitas no Ultrapack</span>': '<span>Versões suspeitas na origem</span>',
        '<span>Catálogo Ultrapack</span>': '<span>Catálogo de origem</span>',
        '· Ultrapack:': '· Origem:',
    }
    for old, new in replacements.items():
        html = html.replace(old, new)

    script = r"""
<script data-comparison-operation-refresh>
(function () {
  function neutral(value) {
    let text = String(value || '').replace(/UltraPackV?2|UltrapackV?2|UltraPack|Ultrapack/gi, 'site de origem');
    text = text.replace(/Novo no site de origem/gi, 'Novo');
    return text;
  }
  function neutralize(root) {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(function (node) {
      const next = neutral(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
    });
    root.querySelectorAll('[title],[aria-label],[data-tooltip]').forEach(function (node) {
      ['title','aria-label','data-tooltip'].forEach(function (name) {
        if (!node.hasAttribute(name)) return;
        const value = node.getAttribute(name);
        const next = neutral(value);
        if (next !== value) node.setAttribute(name, next);
      });
    });
  }
  function comparisonRoot() { return document.getElementById('tab_panel_comparacao'); }
  const root = comparisonRoot();
  if (root) {
    neutralize(root);
    new MutationObserver(function () { neutralize(root); }).observe(root, {subtree:true, childList:true, characterData:true, attributes:true});
  }
  document.addEventListener('click', function(event) {
    const button = event.target && event.target.closest ? event.target.closest('button, a') : null;
    if (!button || String(button.textContent || '').trim() !== 'Comparar') return;
    window.setTimeout(function() {
      neutralize(comparisonRoot());
      const run = document.getElementById('comparison_run_btn');
      if (run && !run.disabled) run.click();
    }, 180);
  });
})();
</script>
"""
    return html.replace("</body>", script + "</body>", 1) if "</body>" in html else html + script


def install_comparison_operation_status_policy() -> None:
    global _INSTALLED, _BASE_GET_CACHED, _BASE_RENDER, _BASE_LIST_APPROVED_UPDATES
    if _INSTALLED:
        return
    _BASE_GET_CACHED = comparison._get_cached_comparison
    _BASE_RENDER = web.render_panel_page

    # update_operational_ui_policy imported the function directly, so patch its
    # bound global instead of mutating the decision database or losing history.
    try:
        import app.update_operational_ui_policy as update_ui
        _BASE_LIST_APPROVED_UPDATES = update_ui.list_approved_updates
        update_ui.list_approved_updates = _pending_approved_updates
    except Exception:
        _BASE_LIST_APPROVED_UPDATES = None

    comparison._STATUS_LABELS["source_version_missing"] = "Versão ausente no site de origem"
    comparison._STATUS_LABELS["new_source"] = "Novo"
    comparison._STATUS_LABELS["added"] = "Adicionado"
    comparison._STATUS_ORDER["added"] = 5.5
    comparison._get_cached_comparison = _get_cached_with_operations
    web.render_panel_page = _render_with_generic_source_labels
    _INSTALLED = True
