(() => {
  "use strict";

  if (window.__crapScraperPreparationSectionsCanonicalV8Installed) return;
  window.__crapScraperPreparationSectionsCanonicalV8Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const cleanText = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if ($("#cs-preparation-canonical-v8-style")) return;
    const style = document.createElement("style");
    style.id = "cs-preparation-canonical-v8-style";
    style.textContent = `
      /* Preparação: um único componente visual para Atualizar e Adicionar. */
      #tab_panel_atualizacoes .cs-preparation-canonical,
      #tab_panel_adicoes .cs-preparation-canonical{
        padding:16px 18px!important;
        border:1px solid var(--line)!important;
        border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;
        overflow:visible!important;
      }
      #tab_panel_atualizacoes .cs-preparation-canonical>.cs-preparation-header,
      #tab_panel_adicoes .cs-preparation-canonical>.cs-preparation-header{
        display:flex!important;align-items:center!important;justify-content:space-between!important;
        gap:14px!important;width:100%!important;min-height:30px!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;box-shadow:none!important;
      }
      #tab_panel_atualizacoes .cs-preparation-canonical>.cs-preparation-header .standard-update-accordion-toggle-copy,
      #tab_panel_adicoes .cs-preparation-canonical>.cs-preparation-header .cs-op-summary-left{
        display:inline-flex!important;align-items:center!important;gap:8px!important;min-width:0!important;
      }
      #tab_panel_atualizacoes .cs-preparation-canonical>.cs-preparation-header .standard-update-accordion-title,
      #tab_panel_adicoes .cs-preparation-canonical>.cs-preparation-header .section-title{
        margin:0!important;color:var(--text)!important;font-size:16px!important;font-weight:850!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-preparation-summary,
      #tab_panel_adicoes .cs-preparation-summary{
        margin-left:auto!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-preparation-canonical.is-collapsed>.cs-preparation-canonical-body{display:none!important}
      #tab_panel_atualizacoes .cs-preparation-canonical-body,
      #tab_panel_adicoes .cs-preparation-canonical-body{margin:0!important;padding:0!important}
      #tab_panel_atualizacoes .cs-preparation-description,
      #tab_panel_adicoes .cs-preparation-description{
        margin:10px 0 12px!important;padding:0!important;color:var(--text-muted)!important;font-size:11px!important;line-height:1.5!important;
      }
      #tab_panel_atualizacoes .cs-preparation-canonical .updates-subtitle{display:none!important}

      /* Buscar | Estado | Atualizar */
      #tab_panel_atualizacoes .cs-preparation-toolbar,
      #tab_panel_adicoes .cs-preparation-toolbar{
        display:grid!important;grid-template-columns:minmax(280px,1fr) minmax(180px,230px) auto!important;
        gap:10px!important;align-items:end!important;width:100%!important;margin:0 0 10px!important;padding:0!important;border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-preparation-field,
      #tab_panel_adicoes .cs-preparation-field{
        display:grid!important;gap:6px!important;min-width:0!important;margin:0!important;color:var(--text-muted)!important;
        font-size:11px!important;font-weight:750!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-preparation-field input,
      #tab_panel_atualizacoes .cs-preparation-field select,
      #tab_panel_adicoes .cs-preparation-field input,
      #tab_panel_adicoes .cs-preparation-field select{
        width:100%!important;min-width:0!important;min-height:42px!important;margin:0!important;
        border:1px solid var(--line-strong)!important;border-radius:9px!important;background:var(--bg-input)!important;color:var(--text)!important;box-shadow:none!important;
      }
      #tab_panel_atualizacoes .cs-preparation-refresh,
      #tab_panel_adicoes .cs-preparation-refresh{min-width:104px!important;min-height:42px!important;margin:0!important;padding:0 16px!important}

      /* Segunda linha: filtros específicos + limpar filtros. */
      #tab_panel_atualizacoes .cs-preparation-advanced,
      #tab_panel_adicoes .cs-preparation-advanced{
        display:grid!important;grid-template-columns:repeat(2,minmax(190px,1fr)) auto!important;gap:10px!important;align-items:end!important;
        width:100%!important;min-height:58px!important;margin:0 0 10px!important;padding:10px!important;
        border:1px solid var(--line)!important;border-radius:10px!important;background:rgba(255,255,255,.015)!important;
      }
      #tab_panel_adicoes .cs-preparation-advanced-note{
        grid-column:1/3!important;align-self:center!important;color:var(--text-faint)!important;font-size:10px!important;line-height:1.4!important;
      }
      #tab_panel_atualizacoes .cs-preparation-advanced button,
      #tab_panel_adicoes .cs-preparation-advanced button{min-height:42px!important;margin:0!important}

      /* Meta: resultados à esquerda, page size à direita. */
      #tab_panel_atualizacoes .cs-preparation-meta,
      #tab_panel_adicoes .cs-preparation-meta{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;
        min-height:34px!important;margin:4px 0 8px!important;padding:0 2px!important;border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-preparation-meta strong,
      #tab_panel_atualizacoes .cs-preparation-meta .small,
      #tab_panel_adicoes .cs-preparation-meta strong,
      #tab_panel_adicoes .cs-preparation-meta .small{margin:0!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important}
      #tab_panel_atualizacoes .cs-preparation-meta .listing-page-size,
      #tab_panel_adicoes .cs-preparation-meta .listing-page-size{
        display:inline-flex!important;align-items:center!important;gap:8px!important;margin-left:auto!important;
      }
      #tab_panel_atualizacoes .cs-preparation-meta .listing-page-size input,
      #tab_panel_adicoes .cs-preparation-meta .listing-page-size input{
        width:58px!important;min-width:58px!important;min-height:32px!important;padding:4px 7px!important;text-align:center!important;
      }

      /* Seleção e ações em lote. */
      #tab_panel_atualizacoes .cs-preparation-bulk,
      #tab_panel_adicoes .cs-preparation-bulk{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-height:58px!important;margin:8px 0 12px!important;padding:10px 12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.022)!important;
      }
      #tab_panel_atualizacoes .cs-preparation-selection,
      #tab_panel_adicoes .cs-preparation-selection{
        display:flex!important;align-items:center!important;gap:12px!important;flex:1 1 auto!important;min-width:0!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-preparation-selection label,
      #tab_panel_adicoes .cs-preparation-selection label{
        display:inline-flex!important;align-items:center!important;gap:7px!important;margin:0!important;color:var(--text-soft)!important;
        font-size:11px!important;font-weight:750!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-preparation-selection input[type=checkbox],
      #tab_panel_adicoes .cs-preparation-selection input[type=checkbox]{width:17px!important;height:17px!important;min-height:0!important;margin:0!important;accent-color:#7c3aed!important}
      #tab_panel_atualizacoes .cs-preparation-selection-count,
      #tab_panel_adicoes .cs-preparation-selection-count{color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-preparation-actions,
      #tab_panel_adicoes .cs-preparation-actions{
        display:flex!important;align-items:center!important;justify-content:flex-end!important;gap:8px!important;flex:0 0 auto!important;margin-left:auto!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-preparation-actions button,
      #tab_panel_adicoes .cs-preparation-actions button{min-height:40px!important;padding:0 14px!important;border-radius:9px!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-preparation-original-bulk-triggers{display:none!important}

      /* Mesma linguagem de row-card. */
      #tab_panel_adicoes .cs-preparation-table-head{display:none!important}
      #tab_panel_atualizacoes .cs-preparation-list,
      #tab_panel_adicoes .cs-preparation-list{display:grid!important;gap:8px!important;width:100%!important;margin:0!important}
      #tab_panel_atualizacoes .cs-preparation-list>.update-job,
      #tab_panel_adicoes .cs-preparation-list>.addition-op-row{
        width:100%!important;min-width:0!important;margin:0!important;padding:12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.014)!important;box-shadow:none!important;
      }
      #tab_panel_atualizacoes .cs-preparation-list>.update-job{
        display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(140px,180px) minmax(220px,auto)!important;gap:12px!important;align-items:center!important;
      }
      #tab_panel_adicoes .cs-preparation-list>.addition-op-row{
        display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(180px,.8fr) minmax(155px,.7fr) minmax(210px,auto)!important;gap:12px!important;align-items:center!important;
      }
      #tab_panel_atualizacoes .cs-preparation-list>.notice,
      #tab_panel_adicoes .cs-preparation-list>.addition-empty,
      #tab_panel_adicoes .cs-preparation-list>.addition-loading{
        display:grid!important;place-items:center!important;min-height:88px!important;margin:0!important;padding:18px!important;
        border:1px dashed var(--line-strong)!important;border-radius:11px!important;background:rgba(255,255,255,.012)!important;color:var(--text-muted)!important;text-align:center!important;
      }

      /* Paginação comum. */
      #tab_panel_atualizacoes .cs-preparation-pagination,
      #tab_panel_adicoes .cs-preparation-pagination{
        display:grid!important;grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
        gap:10px!important;align-items:center!important;width:100%!important;margin:12px 0 0!important;padding:0!important;
      }
      #tab_panel_atualizacoes .cs-preparation-pagination>button,
      #tab_panel_adicoes .cs-preparation-pagination>button{width:100%!important;min-height:38px!important}
      #tab_panel_atualizacoes .cs-preparation-pagination .badge,
      #tab_panel_adicoes .cs-preparation-pagination .badge{justify-self:center!important;white-space:nowrap!important}

      @media(max-width:900px){
        #tab_panel_atualizacoes .cs-preparation-toolbar,#tab_panel_adicoes .cs-preparation-toolbar,
        #tab_panel_atualizacoes .cs-preparation-advanced,#tab_panel_adicoes .cs-preparation-advanced{grid-template-columns:1fr!important}
        #tab_panel_adicoes .cs-preparation-advanced-note{grid-column:auto!important}
        #tab_panel_atualizacoes .cs-preparation-refresh,#tab_panel_adicoes .cs-preparation-refresh,
        #tab_panel_atualizacoes .cs-preparation-advanced button,#tab_panel_adicoes .cs-preparation-advanced button{width:100%!important}
        #tab_panel_atualizacoes .cs-preparation-bulk,#tab_panel_adicoes .cs-preparation-bulk{align-items:stretch!important;flex-direction:column!important}
        #tab_panel_atualizacoes .cs-preparation-actions,#tab_panel_adicoes .cs-preparation-actions{width:100%!important;margin-left:0!important;justify-content:flex-start!important}
        #tab_panel_atualizacoes .cs-preparation-list>.update-job,#tab_panel_adicoes .cs-preparation-list>.addition-op-row{grid-template-columns:30px minmax(0,1fr)!important;align-items:start!important}
        #tab_panel_atualizacoes .cs-preparation-pagination,#tab_panel_adicoes .cs-preparation-pagination{grid-template-columns:1fr!important}
      }
    `;
    document.head.appendChild(style);
  }

  function markField(control) {
    const field = control?.closest?.("label") || control?.closest?.(".field");
    field?.classList.add("cs-preparation-field");
    return field;
  }

  function ensureBody(root, id) {
    let body = $(`#${id}`, root);
    if (!body) {
      body = document.createElement("div");
      body.id = id;
      body.className = "cs-preparation-canonical-body";
      root.appendChild(body);
    }
    body.classList.add("cs-preparation-canonical-body");
    body.removeAttribute("hidden");
    return body;
  }

  function dedupeEmpty(list) {
    if (!list) return;
    const seen = new Set();
    $$(":scope > .notice", list).forEach(node => {
      const key = cleanText(node.textContent);
      if (!key) return;
      if (seen.has(key)) node.remove();
      else seen.add(key);
    });
  }

  function normalizeUpdatePreparation() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root) return false;
    root.classList.add("cs-preparation-canonical", "cs-preparation-canonical-update");

    const header = $(":scope > .standard-update-accordion-toggle", root);
    if (!header) return false;
    header.classList.add("cs-preparation-header");

    const summary = $("#cs_v4_update_preparation_summary", root);
    if (summary) {
      summary.classList.add("cs-preparation-summary", "standard-update-accordion-meta");
      if (summary.parentElement !== header) header.appendChild(summary);
    }

    const legacyHead = $(".cs-v4-preparation-head", root);
    const legacyWrapper = legacyHead?.parentElement;
    if (legacyHead) legacyHead.hidden = true;

    let description = $(".cs-v4-preparation-hint", root);
    if (!description) description = $$(".cs-preparation-description", root)[0] || null;
    if (!description) {
      description = document.createElement("div");
      description.textContent = "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os planos antes de enviá-los para a fila de atualização.";
    }
    description.classList.add("cs-preparation-description");

    const body = ensureBody(root, "cs_updates_preparation_body");
    const oldControls = $("#updates_working_controls", root);
    if (oldControls) oldControls.removeAttribute("hidden");

    const toolbar = $(".updates-filters", root);
    toolbar?.classList.add("cs-preparation-toolbar");
    markField($("#updates_search_filter", root));
    markField($("#updates_status_filter", root));
    ($(".cs-v4-preparation-refresh", root) || toolbar?.querySelector("button"))?.classList.add("cs-preparation-refresh");

    const advanced = $(".cs-v4-preparation-advanced", root);
    advanced?.classList.add("cs-preparation-advanced");
    markField($("#updates_version_filter", root));
    markField($("#updates_relationship_filter", root));

    const meta = $(".listing-meta-row", root);
    meta?.classList.add("cs-preparation-meta");

    const bulk = $(".updates-bulkbar", root);
    bulk?.classList.add("cs-preparation-bulk");
    $(".cs-preparation-selection", bulk)?.classList.add("cs-preparation-selection");
    $(".cs-preparation-actions", bulk)?.classList.add("cs-preparation-actions");
    $("#updates_selected_count", root)?.classList.add("cs-preparation-selection-count");
    $(".cs-bulk-selection-line", bulk)?.classList.add("cs-preparation-original-bulk-triggers");
    $(".cs-bulk-action-line", bulk)?.classList.add("cs-preparation-original-bulk-triggers");

    const progress = $("#updates_batch_progress", root);
    const list = $("#updates_jobs", root);
    list?.classList.add("cs-preparation-list");
    const pagination = $(".listing-pagination", root);
    pagination?.classList.add("cs-preparation-pagination");

    [description, toolbar, advanced, meta, bulk, progress, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });

    if (legacyWrapper && legacyWrapper !== body) legacyWrapper.hidden = true;
    if (oldControls && oldControls !== body) oldControls.hidden = true;
    dedupeEmpty(list);
    return true;
  }

  function ensureAdditionAdvanced(root) {
    let advanced = $("#addition_preparation_advanced", root);
    if (advanced) return advanced;
    advanced = document.createElement("div");
    advanced.id = "addition_preparation_advanced";
    advanced.className = "cs-preparation-advanced";

    const note = document.createElement("div");
    note.className = "cs-preparation-advanced-note";
    note.textContent = "A preparação de adições não possui filtros adicionais neste momento.";

    const clear = document.createElement("button");
    clear.id = "addition_preparation_clear_filters";
    clear.type = "button";
    clear.className = "btn-secondary";
    clear.textContent = "Limpar filtros";
    clear.addEventListener("click", () => {
      const search = $("#addition_preparation_search");
      const state = $("#addition_preparation_state");
      if (search) {
        search.value = "";
        search.dispatchEvent(new Event("input", {bubbles:true}));
      }
      if (state) {
        state.value = "";
        state.dispatchEvent(new Event("change", {bubbles:true}));
      }
    });
    advanced.append(note, clear);
    return advanced;
  }

  function updateAdditionSelectedCount(root) {
    const count = $$("#addition_preparation_rows [data-add-select=\"preparation\"]:checked", root).length;
    const label = $("#addition_preparation_selected_count", root);
    if (label) label.textContent = `${count} selecionado${count === 1 ? "" : "s"}`;
  }

  function normalizeAdditionPreparation() {
    const root = $("#addition_preparation_accordion");
    if (!root) return false;
    root.classList.add("cs-preparation-canonical", "cs-preparation-canonical-addition");

    const header = $(":scope > summary", root);
    if (!header) return false;
    header.classList.add("cs-preparation-header");
    $("#addition_preparation_summary", root)?.classList.add("cs-preparation-summary");

    let description = $(":scope > .cs-preparation-description", root);
    if (!description) {
      description = document.createElement("div");
      description.textContent = "Revise os produtos aprovados, prepare os dados necessários para o cadastro e envie os itens prontos para a fila de adição.";
    }
    description.classList.add("cs-preparation-description");
    const duplicateHint = $(":scope > .addition-section-hint", root);
    if (duplicateHint && duplicateHint !== description) duplicateHint.remove();

    const body = ensureBody(root, "cs_addition_preparation_body");
    const toolbar = $(".addition-toolbar", root);
    toolbar?.classList.add("cs-preparation-toolbar");
    markField($("#addition_preparation_search", root));
    markField($("#addition_preparation_state", root));
    $("#addition_preparation_refresh", root)?.classList.add("cs-preparation-refresh");

    const advanced = ensureAdditionAdvanced(root);
    const meta = $(".addition-list-meta", root);
    meta?.classList.add("cs-preparation-meta");
    const metaLeft = $(".addition-list-meta-left", meta);
    const resultMeta = $("#addition_preparation_meta", root);
    if (metaLeft && resultMeta && resultMeta.parentElement !== metaLeft) metaLeft.appendChild(resultMeta);

    const selectPageLabel = $("#addition_preparation_select_all", root)?.closest("label");
    const bulk = $(".addition-bulk-actions", root);
    if (bulk) {
      bulk.classList.add("cs-preparation-bulk");
      let selection = $(":scope > .cs-preparation-selection", bulk);
      if (!selection) {
        selection = document.createElement("div");
        selection.className = "cs-preparation-selection";
        bulk.prepend(selection);
      }
      if (selectPageLabel && selectPageLabel.parentElement !== selection) selection.appendChild(selectPageLabel);

      let selectedCount = $("#addition_preparation_selected_count", root);
      if (!selectedCount) {
        selectedCount = document.createElement("span");
        selectedCount.id = "addition_preparation_selected_count";
        selectedCount.className = "cs-preparation-selection-count";
        selectedCount.textContent = "0 selecionados";
      }
      if (selectedCount.parentElement !== selection) selection.appendChild(selectedCount);

      let clearSelection = $("#addition_preparation_clear_selection", root);
      if (!clearSelection) {
        clearSelection = document.createElement("button");
        clearSelection.id = "addition_preparation_clear_selection";
        clearSelection.type = "button";
        clearSelection.className = "btn-secondary";
        clearSelection.textContent = "Limpar seleção";
        clearSelection.addEventListener("click", () => {
          const page = $("#addition_preparation_select_all");
          if (page?.checked) {
            page.checked = false;
            page.dispatchEvent(new Event("change", {bubbles:true}));
          } else {
            $$("#addition_preparation_rows [data-add-select=\"preparation\"]:checked").forEach(input => {
              input.checked = false;
              input.dispatchEvent(new Event("change", {bubbles:true}));
            });
          }
          queueMicrotask(() => updateAdditionSelectedCount(root));
        });
      }
      if (clearSelection.parentElement !== selection) selection.appendChild(clearSelection);

      let actions = $(":scope > .cs-preparation-actions", bulk);
      if (!actions) {
        actions = document.createElement("div");
        actions.className = "cs-preparation-actions";
        $$(':scope > button', bulk).forEach(button => actions.appendChild(button));
        bulk.appendChild(actions);
      }
    }

    const tableHead = $(".addition-table-head", root);
    tableHead?.classList.add("cs-preparation-table-head");
    const list = $("#addition_preparation_rows", root);
    list?.classList.add("cs-preparation-list");
    const pagination = $(".addition-pagination", root);
    pagination?.classList.add("cs-preparation-pagination");

    [description, toolbar, advanced, meta, bulk, tableHead, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });

    updateAdditionSelectedCount(root);
    return true;
  }

  function normalizeAll() {
    normalizeUpdatePreparation();
    normalizeAdditionPreparation();
  }

  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(normalizeAll, 0);
  }

  function bindHooks() {
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#tab_btn_atualizacoes,#tab_btn_adicoes,#updates_refresh_btn,#addition_preparation_refresh,#updates_clear_filters,#addition_preparation_clear_filters")) schedule();
    }, true);

    document.addEventListener("change", event => {
      const target = event.target instanceof HTMLInputElement ? event.target : null;
      if (!target) return;
      if (target.id === "addition_preparation_select_all" || target.matches('[data-add-select="preparation"]')) {
        queueMicrotask(() => {
          const root = $("#addition_preparation_accordion");
          if (root) updateAdditionSelectedCount(root);
        });
      }
    }, true);

    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "adicoes") schedule();
    });
  }

  function start() {
    installStyles();
    normalizeAll();
    bindHooks();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
