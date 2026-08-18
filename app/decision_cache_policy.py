from __future__ import annotations

from typing import Any, Callable, Mapping

import app.comparison as comparison
import app.web as web

_INSTALLED = False
_BASE_SAVE_DECISION: Callable[..., Any] | None = None
_BASE_SAVE_DECISIONS_BULK: Callable[..., Any] | None = None
_BASE_RESET_DECISION: Callable[..., Any] | None = None
_BASE_RENDER: Callable[..., str] | None = None
_BASE_MAKE_HANDLER: Callable[..., Any] | None = None

_DECISION_UI_SCRIPT = r'''
(() => {
  "use strict";

  const labels = {
    pending: "Pendente",
    approve_update: "Atualização aprovada",
    ignore: "Ignorado",
    review_later: "Revisar depois",
    same_product: "Mesmo produto confirmado",
    different_products: "Produtos diferentes",
    approve_new_product: "Cadastro novo aprovado",
  };

  const clean = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  function badgeClass(decision) {
    if (["approve_update", "approve_new_product", "same_product"].includes(decision)) return "is-success";
    if (decision === "review_later") return "is-warning";
    if (["ignore", "different_products"].includes(decision)) return "is-danger";
    return "";
  }

  function paintDecision(button, decision, label) {
    const cell = button.closest("td");
    const badge = cell?.querySelector(".comparison-decision");
    const select = cell?.querySelector(".comparison-row-decision-select");

    if (select) select.value = decision;
    if (badge) {
      badge.textContent = label || labels[decision] || decision;
      badge.classList.remove("is-success", "is-warning", "is-danger");
      const klass = badgeClass(decision);
      if (klass) badge.classList.add(klass);
    }
  }

  async function saveImmediately(button) {
    if (button.dataset.directSaving === "1") return;

    const itemId = clean(button.dataset.comparisonItemId);
    const cell = button.closest("td");
    const select = cell?.querySelector(".comparison-row-decision-select");
    const decision = clean(select?.value) || "pending";
    const sourceId = clean(document.getElementById("comparison_source_catalog")?.value);
    const targetId = clean(document.getElementById("comparison_target_catalog")?.value);

    if (!itemId || !sourceId || !targetId) {
      window.alert("Não foi possível identificar a linha e os catálogos da comparação.");
      return;
    }

    const oldText = button.textContent;
    button.dataset.directSaving = "1";
    button.disabled = true;
    button.textContent = "Salvando...";

    try {
      const response = await fetch("/comparacao/decisao/salvar-direto", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          comparison_item_id: itemId,
          decision,
          note: "Decisão alterada diretamente pelo painel.",
          operator: "local",
          source_id: sourceId,
          target_id: targetId,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.message || payload?.error || `HTTP ${response.status}`);
      }

      const saved = payload?.decision || {};
      const savedDecision = clean(saved.decision || decision);
      const savedLabel = clean(saved.decision_label || labels[savedDecision] || savedDecision);

      paintDecision(button, savedDecision, savedLabel);
      button.textContent = "Salvo";

      const row = button.closest("tr");
      if (row) {
        row.dataset.savedDecision = savedDecision;
        row.classList.add("comparison-decision-just-saved");
        window.setTimeout(() => row.classList.remove("comparison-decision-just-saved"), 900);
      }

      window.setTimeout(() => {
        if (button.isConnected) button.textContent = oldText;
      }, 700);
    } catch (error) {
      button.textContent = oldText;
      window.alert(`Falha ao salvar a decisão: ${error?.message || error}`);
    } finally {
      button.disabled = false;
      delete button.dataset.directSaving;
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.(".comparison-decision-save");
    if (!button) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    saveImmediately(button);
  }, true);
})();
'''


def _invalidate_comparison_cache() -> None:
    with comparison._CACHE_LOCK:
        comparison._CACHE_KEY = None
        comparison._CACHE_PAYLOAD = None


def _save_decision(*args: Any, **kwargs: Any) -> Any:
    if _BASE_SAVE_DECISION is None:
        raise RuntimeError("Política de decisão não inicializada")
    result = _BASE_SAVE_DECISION(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def _save_decisions_bulk(*args: Any, **kwargs: Any) -> Any:
    if _BASE_SAVE_DECISIONS_BULK is None:
        raise RuntimeError("Política de decisão não inicializada")
    result = _BASE_SAVE_DECISIONS_BULK(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def _reset_decision(*args: Any, **kwargs: Any) -> Any:
    if _BASE_RESET_DECISION is None:
        raise RuntimeError("Política de decisão não inicializada")
    result = _BASE_RESET_DECISION(*args, **kwargs)
    _invalidate_comparison_cache()
    return result


def _find_comparison_row(source_id: Any, target_id: Any, comparison_item_id: Any) -> dict[str, Any]:
    source_path = web._resolve_comparison_catalog_path(str(source_id or "").strip())
    target_path = web._resolve_comparison_catalog_path(str(target_id or "").strip())
    item_id = str(comparison_item_id or "").strip()

    if source_path is None or target_path is None:
        raise ValueError("Catálogo de origem ou PluginTema não encontrado.")
    if not item_id:
        raise ValueError("comparison_item_id obrigatório")

    payload = comparison._get_cached_comparison(source_path, target_path, force=True)
    for row in payload.get("rows", []):
        if str(row.get("comparison_item_id", "") or "").strip() == item_id:
            return dict(row)

    raise ValueError("A linha selecionada não foi encontrada na comparação atual.")


def _save_direct_decision(payload: Mapping[str, Any]) -> dict[str, Any]:
    row = _find_comparison_row(
        payload.get("source_id"),
        payload.get("target_id"),
        payload.get("comparison_item_id"),
    )

    saved = web.save_decision(
        payload.get("comparison_item_id"),
        payload.get("decision", "pending"),
        note=payload.get("note", ""),
        operator=payload.get("operator", "local"),
        site_id=row.get("site_id", ""),
        site_name=row.get("site_name", ""),
        source_name=row.get("source_name", ""),
        status=row.get("status", ""),
        recommended_action=row.get("recommended_action", ""),
        woo_product_id=row.get("woo_product_id") or row.get("site_id", ""),
        site_version=row.get("site_version", ""),
        site_product_url=row.get("site_product_url", ""),
        site_official_url=row.get("site_official_url", ""),
        source_version=row.get("source_version", ""),
        source_product_url=row.get("source_product_url", ""),
        source_official_url=row.get("source_official_url", ""),
        relationship_state=row.get("relationship_state", ""),
        relationship_label=row.get("relationship_label", ""),
    )

    _invalidate_comparison_cache()
    return {
        "ok": True,
        "message": "Decisão salva e aplicada na comparação.",
        "decision": saved,
    }


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    if _BASE_RENDER is None:
        return web.render_panel_page(*args, **kwargs)
    html = _BASE_RENDER(*args, **kwargs)
    safe_script = _DECISION_UI_SCRIPT.replace("</script>", "<\\/script>")
    block = f"\n<script data-decision-immediate-ui>\n{safe_script}\n</script>\n"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _patched_make_handler(*args: Any, **kwargs: Any) -> Any:
    if _BASE_MAKE_HANDLER is None:
        return web.make_handler(*args, **kwargs)

    base_handler = _BASE_MAKE_HANDLER(*args, **kwargs)

    class DecisionHandler(base_handler):
        def _route_post(self, path: str, payload: dict[str, Any]) -> bool:
            if path == "/comparacao/decisao/salvar-direto":
                try:
                    self._send_json(_save_direct_decision(payload))
                except ValueError as error:
                    self._send_json({"ok": False, "message": str(error)}, code=400)
                except Exception as error:
                    self._send_json(web.build_error_payload(error), code=500)
                return True
            return super()._route_post(path, payload)

    return DecisionHandler


def install_decision_cache_policy() -> None:
    global _INSTALLED, _BASE_SAVE_DECISION, _BASE_SAVE_DECISIONS_BULK, _BASE_RESET_DECISION
    global _BASE_RENDER, _BASE_MAKE_HANDLER

    if _INSTALLED:
        return

    _BASE_SAVE_DECISION = web.save_decision
    _BASE_SAVE_DECISIONS_BULK = web.save_decisions_bulk
    _BASE_RESET_DECISION = web.reset_decision
    _BASE_RENDER = web.render_panel_page
    _BASE_MAKE_HANDLER = web.make_handler

    web.save_decision = _save_decision
    web.save_decisions_bulk = _save_decisions_bulk
    web.reset_decision = _reset_decision
    web.render_panel_page = _patched_render_panel_page
    web.make_handler = _patched_make_handler
    _INSTALLED = True
