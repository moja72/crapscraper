(() => {
  "use strict";

  if (window.__crapScraperPreparationSectionsParityV7Installed) return;
  window.__crapScraperPreparationSectionsParityV7Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function installStyles() {
    if ($("#cs-preparation-sections-parity-v7-style")) return;

    const style = document.createElement("style");
    style.id = "cs-preparation-sections-parity-v7-style";
    style.textContent = `
      /* ================================================================
         PREPARAÇÃO V7
         Um único sistema visual para Atualizar e Adicionar.
         ================================================================ */

      #tab_panel_atualizacoes .updates-working-card.cs-preparation-unified,
      #tab_panel_adicoes #addition_preparation_accordion.cs-preparation-unified {
        padding:16px 18px!important;
        border:1px solid var(--line)!important;
        border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;
        overflow:visible!important;
      }

      #tab_panel_atualizacoes .cs-preparation-header,
      #tab_panel_adicoes #addition_preparation_accordion>.cs-preparation-header {
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:14px!important;
        width:100%!important;
        min-height:44px!important;
        margin:0!important;
        padding:0!important;
        border:0!important;
        background:none!important;
        box-shadow:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-header .section-title,
      #tab_panel_adicoes .cs-preparation-header .addition-accordion-title {
        margin:0!important;
        color:var(--text)!important;
        font-size:16px!important;
        font-weight:850!important;
        line-height:1.2!important;
      }

      #tab_panel_atualizacoes .cs-preparation-summary,
      #tab_panel_adicoes .cs-preparation-summary {
        flex:0 0 auto!important;
        margin-left:auto!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:700!important;
        line-height:1.3!important;
        white-space:nowrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-description,
      #tab_panel_adicoes .cs-preparation-description {
        margin:5px 0 14px!important;
        padding:0!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:500!important;
        line-height:1.5!important;
      }

      /* Barra principal: Buscar | Estado | Atualizar */
      #tab_panel_atualizacoes .cs-preparation-toolbar,
      #tab_panel_adicoes .cs-preparation-toolbar {
        display:grid!important;
        grid-template-columns:minmax(280px,1fr) minmax(180px,230px) auto!important;
        gap:10px!important;
        align-items:end!important;
        width:100%!important;
        margin:0 0 10px!important;
        padding:0!important;
        border:0!important;
        background:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-field,
      #tab_panel_adicoes .cs-preparation-field {
        display:grid!important;
        gap:6px!important;
        min-width:0!important;
        margin:0!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:750!important;
        line-height:1.2!important;
      }

      #tab_panel_atualizacoes .cs-preparation-field input,
      #tab_panel_atualizacoes .cs-preparation-field select,
      #tab_panel_adicoes .cs-preparation-field input,
      #tab_panel_adicoes .cs-preparation-field select {
        width:100%!important;
        min-width:0!important;
        min-height:42px!important;
        margin:0!important;
        border:1px solid var(--line-strong)!important;
        border-radius:9px!important;
        background:var(--bg-input)!important;
        color:var(--text)!important;
        box-shadow:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-refresh,
      #tab_panel_adicoes .cs-preparation-refresh {
        min-width:104px!important;
        min-height:42px!important;
        margin:0!important;
        padding:0 16px!important;
      }

      /* Atualizar possui filtros extras, mas eles usam a mesma linguagem visual. */
      #tab_panel_atualizacoes .cs-preparation-advanced {
        display:grid!important;
        grid-template-columns:repeat(2,minmax(190px,1fr)) auto!important;
        gap:10px!important;
        align-items:end!important;
        margin:0 0 10px!important;
        padding:10px!important;
        border:1px solid var(--line)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.015)!important;
      }

      #tab_panel_atualizacoes .cs-preparation-advanced .cs-preparation-field {
        margin:0!important;
      }

      #tab_panel_atualizacoes .cs-preparation-advanced #updates_clear_filters {
        min-height:42px!important;
        margin:0!important;
      }

      /* Metadados de listagem e tamanho de página. */
      #tab_panel_atualizacoes .cs-preparation-meta,
      #tab_panel_adicoes .cs-preparation-meta {
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:12px!important;
        min-height:38px!important;
        margin:6px 0 8px!important;
        padding:0!important;
        border:0!important;
        background:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-meta strong,
      #tab_panel_atualizacoes .cs-preparation-meta .small,
      #tab_panel_adicoes .cs-preparation-meta strong,
      #tab_panel_adicoes .cs-preparation-meta .small {
        margin:0!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:700!important;
      }

      #tab_panel_atualizacoes .cs-preparation-meta .listing-page-size,
      #tab_panel_adicoes .cs-preparation-meta .listing-page-size {
        display:flex!important;
        align-items:center!important;
        gap:8px!important;
        margin-left:auto!important;
      }

      #tab_panel_atualizacoes .cs-preparation-meta .listing-page-size input,
      #tab_panel_adicoes .cs-preparation-meta .listing-page-size input {
        width:62px!important;
        min-height:32px!important;
        padding:4px 7px!important;
        text-align:center!important;
      }

      /* Seleção e operações em lote: mesma caixa nas duas abas. */
      #tab_panel_atualizacoes .cs-preparation-bulk,
      #tab_panel_adicoes .cs-preparation-bulk {
        display:flex!important;
        flex-direction:row!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:14px!important;
        flex-wrap:nowrap!important;
        width:100%!important;
        min-height:58px!important;
        margin:10px 0 12px!important;
        padding:10px 12px!important;
        border:1px solid var(--line)!important;
        border-radius:11px!important;
        background:rgba(255,255,255,.022)!important;
        box-shadow:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-selection,
      #tab_panel_adicoes .cs-preparation-selection {
        display:flex!important;
        align-items:center!important;
        gap:12px!important;
        flex:1 1 auto!important;
        min-width:0!important;
        flex-wrap:wrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-selection label,
      #tab_panel_adicoes .cs-preparation-selection label {
        display:inline-flex!important;
        align-items:center!important;
        gap:7px!important;
        margin:0!important;
        color:var(--text-soft)!important;
        font-size:11px!important;
        font-weight:750!important;
        white-space:nowrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-selection input[type="checkbox"],
      #tab_panel_adicoes .cs-preparation-selection input[type="checkbox"] {
        width:17px!important;
        height:17px!important;
        min-height:0!important;
        margin:0!important;
        accent-color:#7c3aed!important;
      }

      #tab_panel_atualizacoes .cs-preparation-selection-count,
      #tab_panel_adicoes .cs-preparation-selection-count {
        margin:0!important;
        padding:0!important;
        border:0!important;
        background:none!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:750!important;
        white-space:nowrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-actions,
      #tab_panel_adicoes .cs-preparation-actions {
        display:flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:8px!important;
        flex:0 0 auto!important;
        flex-wrap:wrap!important;
        margin-left:auto!important;
      }

      #tab_panel_atualizacoes .cs-preparation-actions button,
      #tab_panel_adicoes .cs-preparation-actions button {
        min-height:40px!important;
        padding:0 14px!important;
        border-radius:9px!important;
        white-space:nowrap!important;
      }

      /* Progresso de preparação. */
      #tab_panel_atualizacoes .cs-preparation-progress,
      #tab_panel_adicoes .cs-preparation-progress {
        margin:8px 0!important;
      }

      /* Listas: as duas passam a ter linhas-card, sem uma tabela em uma aba e cards na outra. */
      #tab_panel_adicoes #addition_preparation_accordion .addition-table-head {
        display:none!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list,
      #tab_panel_adicoes .cs-preparation-list {
        display:grid!important;
        gap:8px!important;
        width:100%!important;
        margin:8px 0 0!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list>.update-job,
      #tab_panel_adicoes .cs-preparation-list>.addition-op-row {
        width:100%!important;
        min-width:0!important;
        margin:0!important;
        padding:12px!important;
        border:1px solid var(--line)!important;
        border-radius:11px!important;
        background:rgba(255,255,255,.014)!important;
        box-shadow:none!important;
        transition:border-color var(--transition-fast),background var(--transition-fast)!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list>.update-job:hover,
      #tab_panel_adicoes .cs-preparation-list>.addition-op-row:hover {
        border-color:var(--line-strong)!important;
        background:rgba(255,255,255,.024)!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list>.update-job {
        display:grid!important;
        grid-template-columns:30px minmax(300px,1fr) minmax(120px,160px) minmax(220px,auto)!important;
        gap:12px!important;
        align-items:center!important;
      }

      #tab_panel_adicoes .cs-preparation-list>.addition-op-row {
        display:grid!important;
        grid-template-columns:30px minmax(260px,1.25fr) minmax(180px,.8fr) minmax(155px,.7fr) minmax(210px,auto)!important;
        gap:12px!important;
        align-items:center!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-select,
      #tab_panel_adicoes .cs-preparation-list [data-add-select="preparation"] {
        width:17px!important;
        height:17px!important;
        margin:0!important;
        accent-color:#7c3aed!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-job-main,
      #tab_panel_adicoes .cs-preparation-list .addition-op-main {
        min-width:0!important;
        display:grid!important;
        gap:4px!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-job-main>strong,
      #tab_panel_adicoes .cs-preparation-list .addition-op-name {
        color:var(--text)!important;
        font-size:13px!important;
        font-weight:850!important;
        line-height:1.3!important;
        overflow-wrap:anywhere!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .small,
      #tab_panel_adicoes .cs-preparation-list .addition-op-meta,
      #tab_panel_adicoes .cs-preparation-list .addition-op-fields,
      #tab_panel_adicoes .cs-preparation-list .addition-op-message {
        color:var(--text-muted)!important;
        font-size:10px!important;
        line-height:1.45!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list>.update-job>.badge,
      #tab_panel_adicoes .cs-preparation-list .addition-state-badge {
        display:inline-flex!important;
        align-items:center!important;
        justify-content:center!important;
        width:max-content!important;
        max-width:100%!important;
        min-height:28px!important;
        padding:5px 9px!important;
        border:1px solid var(--line-strong)!important;
        border-radius:999px!important;
        background:rgba(255,255,255,.035)!important;
        color:var(--text-soft)!important;
        font-size:10px!important;
        font-weight:800!important;
        line-height:1.2!important;
        white-space:nowrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-row-actions,
      #tab_panel_adicoes .cs-preparation-list .addition-op-actions {
        display:flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:6px!important;
        flex-wrap:wrap!important;
        min-width:0!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-row-actions button,
      #tab_panel_adicoes .cs-preparation-list .addition-op-actions button {
        min-height:34px!important;
        padding:6px 9px!important;
        border-radius:8px!important;
        font-size:10px!important;
        white-space:nowrap!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list .update-preview-slot,
      #tab_panel_adicoes .cs-preparation-list .addition-stage-list {
        grid-column:2 / -1!important;
      }

      #tab_panel_atualizacoes .cs-preparation-list>.notice,
      #tab_panel_adicoes .cs-preparation-list>.addition-empty,
      #tab_panel_adicoes .cs-preparation-list>.addition-loading {
        min-height:88px!important;
        display:flex!important;
        align-items:center!important;
        justify-content:center!important;
        margin:0!important;
        padding:18px!important;
        border:1px dashed var(--line-strong)!important;
        border-radius:11px!important;
        background:rgba(255,255,255,.012)!important;
        color:var(--text-muted)!important;
        text-align:center!important;
      }

      /* Paginação com a mesma geometria nas duas abas. */
      #tab_panel_atualizacoes .cs-preparation-pagination,
      #tab_panel_adicoes .cs-preparation-pagination {
        display:grid!important;
        grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
        gap:10px!important;
        align-items:center!important;
        width:100%!important;
        margin:12px 0 0!important;
        padding:0!important;
      }

      #tab_panel_atualizacoes .cs-preparation-pagination>button,
      #tab_panel_adicoes .cs-preparation-pagination>button {
        width:100%!important;
        min-height:38px!important;
      }

      #tab_panel_atualizacoes .cs-preparation-pagination>button:last-child,
      #tab_panel_adicoes .cs-preparation-pagination>button:last-child {
        justify-self:stretch!important;
      }

      #tab_panel_atualizacoes .cs-preparation-pagination .badge,
      #tab_panel_adicoes .cs-preparation-pagination .badge {
        justify-self:center!important;
        white-space:nowrap!important;
      }

      @media(max-width:1180px) {
        #tab_panel_atualizacoes .cs-preparation-list>.update-job {
          grid-template-columns:30px minmax(240px,1fr) minmax(110px,145px)!important;
        }
        #tab_panel_atualizacoes .cs-preparation-list .update-row-actions {
          grid-column:2 / -1!important;
          justify-content:flex-start!important;
        }
        #tab_panel_adicoes .cs-preparation-list>.addition-op-row {
          grid-template-columns:30px minmax(250px,1fr) minmax(180px,.8fr) minmax(150px,.7fr)!important;
        }
        #tab_panel_adicoes .cs-preparation-list .addition-op-actions {
          grid-column:2 / -1!important;
          justify-content:flex-start!important;
        }
      }

      @media(max-width:900px) {
        #tab_panel_atualizacoes .cs-preparation-toolbar,
        #tab_panel_adicoes .cs-preparation-toolbar,
        #tab_panel_atualizacoes .cs-preparation-advanced {
          grid-template-columns:1fr!important;
        }
        #tab_panel_atualizacoes .cs-preparation-refresh,
        #tab_panel_adicoes .cs-preparation-refresh,
        #tab_panel_atualizacoes .cs-preparation-advanced #updates_clear_filters {
          width:100%!important;
        }
        #tab_panel_atualizacoes .cs-preparation-bulk,
        #tab_panel_adicoes .cs-preparation-bulk {
          align-items:stretch!important;
          flex-direction:column!important;
        }
        #tab_panel_atualizacoes .cs-preparation-actions,
        #tab_panel_adicoes .cs-preparation-actions {
          width:100%!important;
          margin-left:0!important;
          justify-content:flex-start!important;
        }
        #tab_panel_atualizacoes .cs-preparation-list>.update-job,
        #tab_panel_adicoes .cs-preparation-list>.addition-op-row {
          grid-template-columns:30px minmax(0,1fr)!important;
          align-items:start!important;
        }
        #tab_panel_atualizacoes .cs-preparation-list>.update-job>.badge,
        #tab_panel_atualizacoes .cs-preparation-list .update-row-actions,
        #tab_panel_adicoes .cs-preparation-list .addition-op-fields,
        #tab_panel_adicoes .cs-preparation-list .addition-state-wrap,
        #tab_panel_adicoes .cs-preparation-list .addition-op-actions {
          grid-column:2!important;
          justify-content:flex-start!important;
        }
        #tab_panel_atualizacoes .cs-preparation-pagination,
        #tab_panel_adicoes .cs-preparation-pagination {
          grid-template-columns:1fr!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function markField(node) {
    const label = node?.closest?.("label");
    if (label) label.classList.add("cs-preparation-field");
    return label;
  }

  function normalizeUpdatePreparation() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root) return false;

    root.classList.add("cs-preparation-unified", "cs-preparation-unified-update");

    let header = $(".cs-v4-preparation-head", root) || $(".cs-preparation-header", root);
    const title = $("#updates_working_title", root);
    if (!header && title) {
      header = document.createElement("div");
      title.insertAdjacentElement("beforebegin", header);
      header.appendChild(title);
    }
    header?.classList.add("cs-preparation-header");

    const summary = $("#cs_v4_update_preparation_summary", root);
    summary?.classList.add("cs-preparation-summary");

    let description = $(".cs-v4-preparation-hint", root) || $(".cs-preparation-description", root);
    if (!description && header) {
      description = document.createElement("div");
      description.textContent = "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os planos antes de enviá-los para a fila de atualização.";
      header.insertAdjacentElement("afterend", description);
    }
    description?.classList.add("cs-preparation-description");

    const toolbar = $(".updates-filters", root);
    toolbar?.classList.add("cs-preparation-toolbar");
    markField($("#updates_search_filter", root));
    markField($("#updates_status_filter", root));

    const refresh = $(".cs-v4-preparation-refresh", root);
    refresh?.classList.add("cs-preparation-refresh");

    const advanced = $(".cs-v4-preparation-advanced", root);
    advanced?.classList.add("cs-preparation-advanced");
    markField($("#updates_version_filter", root));
    markField($("#updates_relationship_filter", root));

    const meta = $(".listing-meta-row", root);
    meta?.classList.add("cs-preparation-meta");

    const bulk = $(".updates-bulkbar", root);
    bulk?.classList.add("cs-preparation-bulk");
    const selection = $(".cs-preparation-selection", bulk) || bulk?.firstElementChild;
    selection?.classList.add("cs-preparation-selection");
    const actions = $(".cs-preparation-actions", bulk) || bulk;
    if (actions !== bulk) actions.classList.add("cs-preparation-actions");
    $("#updates_selected_count", bulk)?.classList.add("cs-preparation-selection-count");

    $("#updates_batch_progress", root)?.classList.add("cs-preparation-progress");
    $("#updates_jobs", root)?.classList.add("cs-preparation-list");
    $(".listing-pagination", root)?.classList.add("cs-preparation-pagination");

    return true;
  }

  function normalizeAdditionPreparation() {
    const root = $("#addition_preparation_accordion");
    if (!root) return false;

    root.classList.add("cs-preparation-unified", "cs-preparation-unified-addition");

    const header = $(":scope > summary", root);
    header?.classList.add("cs-preparation-header");
    $("#addition_preparation_summary", root)?.classList.add("cs-preparation-summary");

    let description = $(":scope > .cs-preparation-description", root);
    if (!description && header) {
      description = document.createElement("div");
      description.className = "cs-preparation-description";
      description.textContent = "Revise os produtos aprovados, prepare os dados necessários para o cadastro e envie os itens prontos para a fila de adição.";
      header.insertAdjacentElement("afterend", description);
    }

    const toolbar = $(".addition-toolbar", root);
    toolbar?.classList.add("cs-preparation-toolbar");
    markField($("#addition_preparation_search", root));
    markField($("#addition_preparation_state", root));
    $("#addition_preparation_refresh", root)?.classList.add("cs-preparation-refresh");

    const meta = $(".addition-list-meta", root);
    meta?.classList.add("cs-preparation-meta");

    const bulk = $(".addition-bulk-actions", root);
    if (bulk) {
      bulk.classList.add("cs-preparation-bulk");

      const selection = $(".addition-list-meta-left", root);
      if (selection) {
        selection.classList.add("cs-preparation-selection");
        if (selection.parentElement !== bulk) bulk.prepend(selection);
      }

      let actions = $(":scope > .cs-preparation-actions", bulk);
      if (!actions) {
        actions = document.createElement("div");
        actions.className = "cs-preparation-actions";
        const actionButtons = $$(':scope > button', bulk);
        actionButtons.forEach(button => actions.appendChild(button));
        bulk.appendChild(actions);
      }

      $("#addition_preparation_meta", bulk)?.classList.add("cs-preparation-selection-count");
    }

    $("#addition_preparation_rows", root)?.classList.add("cs-preparation-list");
    $(".addition-pagination", root)?.classList.add("cs-preparation-pagination");

    return true;
  }

  function normalizeAll() {
    normalizeUpdatePreparation();
    normalizeAdditionPreparation();
  }

  let timer = null;
  function schedule(delay = 0) {
    window.clearTimeout(timer);
    timer = window.setTimeout(normalizeAll, delay);
  }

  function bindRefreshHooks() {
    document.addEventListener("click", event => {
      if (!event.target?.closest?.(
        "#tab_btn_atualizacoes,#tab_btn_adicoes,#updates_refresh_btn,#updates_clear_filters,#updates_prepare_selected,#updates_enqueue_selected,#addition_preparation_refresh,#addition_prepare_selected,#addition_add_selected_from_prep"
      )) return;
      schedule(60);
      window.setTimeout(normalizeAll, 400);
    }, true);

    document.addEventListener("change", event => {
      const id = event.target?.id || "";
      if (![
        "updates_status_filter","updates_version_filter","updates_relationship_filter","updates_page_size",
        "addition_preparation_state","addition_preparation_page_size"
      ].includes(id)) return;
      schedule(50);
    }, true);
  }

  function start() {
    installStyles();
    normalizeAll();
    bindRefreshHooks();
    [80, 250, 700, 1600].forEach(delay => window.setTimeout(normalizeAll, delay));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once:true});
  } else {
    start();
  }
})();
