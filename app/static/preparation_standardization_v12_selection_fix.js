(() => {
  "use strict";
  if (window.__crapScraperPreparationV12SelectionFixInstalled) return;
  window.__crapScraperPreparationV12SelectionFixInstalled = true;

  const $ = selector => document.querySelector(selector);
  const $$ = selector => Array.from(document.querySelectorAll(selector));

  /*
   * O checkbox original de página mantém um Set privado no módulo de Adicionar.
   * Antes de esse módulo rerenderizar as linhas, propagamos a decisão para os
   * checkboxes visíveis. Assim o contrato v12 e o estado operacional original
   * permanecem sincronizados sem duplicar a lógica da fila.
   */
  document.addEventListener("change", event => {
    const target = event.target instanceof HTMLInputElement ? event.target : null;
    if (!target) return;

    if (target.id === "addition_preparation_select_all") {
      $$('#addition_preparation_rows [data-add-select="preparation"]').forEach(box => {
        if (box.checked === target.checked) return;
        box.checked = target.checked;
        box.dispatchEvent(new Event("change", {bubbles:true}));
      });
      return;
    }

    if (target.matches('#addition_preparation_rows [data-add-select="preparation"]') && !target.checked) {
      const all = $("#cs_addition_select_all_results");
      if (all) all.checked = false;
    }
  }, true);

  /* Uma nova busca invalida qualquer seleção transversal anterior. */
  document.addEventListener("input", event => {
    const target = event.target instanceof HTMLInputElement ? event.target : null;
    if (target?.id !== "addition_preparation_search") return;
    $("#addition_preparation_clear_selection_v12")?.click();
  }, true);
})();
