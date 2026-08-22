(() => {
  "use strict";

  if (window.__crapScraperPanelLayoutStandardizationInstalled) return;
  window.__crapScraperPanelLayoutStandardizationInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function addClass(nodes, ...classes) {
    nodes.filter(Boolean).forEach(node => node.classList.add(...classes));
  }

  function installStyles() {
    if ($("#cs-panel-layout-standardization-style")) return;
    const style = document.createElement("style");
    style.id = "cs-panel-layout-standardization-style";
    style.textContent = `
      /* Shared operational design system: Atualizar + Adicionar. */
      #tab_panel_atualizacoes,
      #tab_panel_adicoes {
        --cs-op-gap-xs: 6px;
        --cs-op-gap-sm: 10px;
        --cs-op-gap-md: 12px;
        --cs-op-gap-lg: 16px;
        --cs-op-control-height: 42px;
      }

      #tab_panel_atualizacoes .cs-op-card,
      #tab_panel_adicoes .cs-op-card {
        margin-bottom: var(--cs-op-gap-lg);
        padding: 16px 18px;
        border-radius: var(--radius-md);
      }

      #tab_panel_atualizacoes .cs-op-section,
      #tab_panel_adicoes .cs-op-section {
        overflow: visible;
      }

      #tab_panel_atualizacoes .cs-op-section > summary,
      #tab_panel_adicoes .cs-op-section > summary,
      #tab_panel_atualizacoes .cs-op-section-heading,
      #tab_panel_adicoes .cs-op-section-heading {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--cs-op-gap-md);
        min-height: 44px;
        margin: 0;
      }

      #tab_panel_atualizacoes .cs-op-section > summary,
      #tab_panel_adicoes .cs-op-section > summary {
        cursor: pointer;
        list-style: none;
      }

      #tab_panel_atualizacoes .cs-op-section > summary::-webkit-details-marker,
      #tab_panel_adicoes .cs-op-section > summary::-webkit-details-marker { display: none; }

      #tab_panel_atualizacoes .cs-op-section .section-title,
      #tab_panel_adicoes .cs-op-section .section-title,
      #tab_panel_atualizacoes .cs-op-section-heading .section-title,
      #tab_panel_adicoes .cs-op-section-heading .section-title {
        margin: 0;
        font-size: 16px;
        line-height: 1.2;
      }

      #tab_panel_atualizacoes .cs-op-section-hint,
      #tab_panel_adicoes .cs-op-section-hint {
        margin: 0 0 var(--cs-op-gap-md);
        padding: 0 2px;
        color: var(--text-muted);
        font-size: 11px;
        line-height: 1.5;
      }

      #tab_panel_atualizacoes .cs-op-filterbar,
      #tab_panel_adicoes .cs-op-filterbar {
        display: grid;
        grid-template-columns: minmax(260px, 1fr) minmax(180px, 250px) auto;
        gap: var(--cs-op-gap-md);
        align-items: end;
        margin: 12px 0 10px;
      }

      #tab_panel_atualizacoes .cs-op-filterbar.cs-op-filterbar-wide,
      #tab_panel_adicoes .cs-op-filterbar.cs-op-filterbar-wide {
        grid-template-columns: repeat(4, minmax(150px, 1fr)) auto;
      }

      #tab_panel_atualizacoes #updates_queue_list_controls .cs-op-filterbar {
        grid-template-columns: minmax(260px, 1fr) minmax(180px, 250px);
      }

      #tab_panel_atualizacoes .cs-op-filterbar label,
      #tab_panel_adicoes .cs-op-filterbar label,
      #tab_panel_atualizacoes .cs-op-history-filters label,
      #tab_panel_adicoes .cs-op-history-filters label {
        display: grid;
        min-width: 0;
        gap: var(--cs-op-gap-xs);
        margin: 0;
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 700;
      }

      #tab_panel_atualizacoes .cs-op-filterbar input,
      #tab_panel_atualizacoes .cs-op-filterbar select,
      #tab_panel_atualizacoes .cs-op-filterbar button,
      #tab_panel_adicoes .cs-op-filterbar input,
      #tab_panel_adicoes .cs-op-filterbar select,
      #tab_panel_adicoes .cs-op-filterbar button,
      #tab_panel_atualizacoes .cs-op-history-filters input,
      #tab_panel_atualizacoes .cs-op-history-filters select,
      #tab_panel_adicoes .cs-op-history-filters input,
      #tab_panel_adicoes .cs-op-history-filters select {
        min-height: var(--cs-op-control-height);
      }

      #tab_panel_atualizacoes .cs-op-history-toolbar,
      #tab_panel_adicoes .cs-op-history-toolbar {
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        gap: var(--cs-op-gap-md);
        align-items: end;
        margin: 12px 0 10px;
      }

      #tab_panel_atualizacoes .cs-op-history-filters,
      #tab_panel_adicoes .cs-op-history-filters {
        display: grid;
        gap: var(--cs-op-gap-md);
        min-width: 0;
      }
      #tab_panel_atualizacoes .cs-op-history-filters {
        grid-template-columns: minmax(260px, 1fr) minmax(180px, .55fr);
      }
      #tab_panel_adicoes .cs-op-history-filters {
        grid-template-columns: minmax(260px, 1fr) minmax(180px, .55fr) minmax(220px, .7fr);
      }

      #tab_panel_atualizacoes .cs-op-history-actions,
      #tab_panel_adicoes .cs-op-history-actions,
      #tab_panel_atualizacoes .cs-op-actions,
      #tab_panel_adicoes .cs-op-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }

      #tab_panel_atualizacoes .cs-op-history-actions,
      #tab_panel_adicoes .cs-op-history-actions { justify-content: flex-end; }

      #tab_panel_atualizacoes .cs-op-actions button,
      #tab_panel_adicoes .cs-op-actions button,
      #tab_panel_atualizacoes .cs-op-history-actions button,
      #tab_panel_adicoes .cs-op-history-actions button {
        min-height: var(--cs-op-control-height);
      }

      #tab_panel_atualizacoes .cs-op-list-meta,
      #tab_panel_adicoes .cs-op-list-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--cs-op-gap-md);
        flex-wrap: wrap;
        min-height: 30px;
        margin: 8px 0 10px;
        color: var(--text-muted);
        font-size: 11px;
      }

      #tab_panel_atualizacoes .cs-op-list-meta-left,
      #tab_panel_adicoes .cs-op-list-meta-left {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        min-width: 0;
      }

      #tab_panel_atualizacoes .cs-op-page-size,
      #tab_panel_adicoes .cs-op-page-size,
      #tab_panel_atualizacoes .cs-op-inline-page-size,
      #tab_panel_adicoes .cs-op-inline-page-size {
        display: inline-flex;
        align-items: center;
        justify-content: flex-end;
        gap: 7px;
        margin: 0;
        white-space: nowrap;
        color: var(--text-muted);
        font-size: 11px;
        font-weight: 600;
      }

      #tab_panel_atualizacoes .cs-op-page-size input,
      #tab_panel_adicoes .cs-op-page-size input,
      #tab_panel_atualizacoes .cs-op-inline-page-size input,
      #tab_panel_adicoes .cs-op-inline-page-size input {
        width: 58px;
        min-width: 58px;
        min-height: 30px;
        padding: 5px 8px;
        text-align: center;
      }

      #tab_panel_atualizacoes .cs-op-pagination,
      #tab_panel_adicoes .cs-op-pagination {
        display: grid;
        grid-template-columns: minmax(150px, 1fr) auto minmax(150px, 1fr);
        align-items: center;
        gap: var(--cs-op-gap-md);
        width: 100%;
        margin: 14px 0 0;
      }

      #tab_panel_atualizacoes .cs-op-pagination > button,
      #tab_panel_adicoes .cs-op-pagination > button {
        width: 100%;
        min-width: 0;
        min-height: var(--cs-op-control-height);
        padding: 9px 14px;
      }

      #tab_panel_atualizacoes .cs-op-pagination > button:first-child,
      #tab_panel_adicoes .cs-op-pagination > button:first-child { justify-self: start; }
      #tab_panel_atualizacoes .cs-op-pagination > button:last-child,
      #tab_panel_adicoes .cs-op-pagination > button:last-child { justify-self: end; }

      #tab_panel_atualizacoes .cs-op-page-jump,
      #tab_panel_adicoes .cs-op-page-jump {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        min-width: 120px;
        min-height: 34px;
        padding: 5px 9px;
        white-space: nowrap;
        text-align: center;
      }

      #tab_panel_atualizacoes .cs-op-page-jump input,
      #tab_panel_adicoes .cs-op-page-jump input {
        width: 52px;
        min-width: 52px;
        min-height: 28px;
        padding: 4px 7px;
        text-align: center;
        font-variant-numeric: tabular-nums;
      }

      #tab_panel_atualizacoes .cs-op-empty,
      #tab_panel_adicoes .cs-op-empty {
        display: grid;
        place-items: center;
        min-height: 64px;
        padding: 16px;
        border: 1px dashed var(--line-strong);
        border-radius: 10px;
        background: rgba(255,255,255,.012);
        color: var(--text-muted);
        text-align: center;
        font-size: 11px;
        line-height: 1.45;
      }

      #tab_panel_atualizacoes .cs-op-table-head,
      #tab_panel_adicoes .cs-op-table-head {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px solid var(--line);
        background: rgba(255,255,255,.008);
      }
      #tab_panel_atualizacoes .update-job,
      #tab_panel_atualizacoes .update-queue-row,
      #tab_panel_adicoes .addition-op-row {
        padding-top: 12px;
        padding-bottom: 12px;
        border-bottom-color: var(--line);
      }

      #tab_panel_atualizacoes .updates-working-card .notice,
      #tab_panel_atualizacoes #updates_queue_jobs > .notice,
      #tab_panel_atualizacoes .updates-history-panel > .notice,
      #tab_panel_adicoes .addition-empty {
        display: grid;
        place-items: center;
        min-height: 64px;
        padding: 16px;
        border: 1px dashed var(--line-strong);
        border-radius: 10px;
        background: rgba(255,255,255,.012);
        color: var(--text-muted);
        text-align: center;
        font-size: 11px;
        line-height: 1.45;
      }

      #tab_panel_atualizacoes .cs-op-summary-card,
      #tab_panel_adicoes .cs-op-summary-card {
        min-height: 70px;
        border-radius: 12px;
      }

      /* Adicionar keeps its specific data model, but uses the shared shell. */
      #tab_panel_adicoes .addition-operations-center.addition-layout-standard { gap: 16px; }
      #tab_panel_adicoes .addition-operations-center > .card { margin-bottom: 0; }
      #tab_panel_adicoes .addition-intro-card { display: grid; gap: 14px; padding: 16px 18px; }
      #tab_panel_adicoes .addition-intro-head { display: grid; grid-template-columns: minmax(0,1fr) auto; gap: 22px; align-items: start; }
      #tab_panel_adicoes .addition-intro-copy { min-width: 0; }
      #tab_panel_adicoes .addition-intro-copy .section-title { margin: 0; font-size: 16px; }
      #tab_panel_adicoes .addition-intro-copy .small { max-width: 920px; margin-top: 7px; line-height: 1.55; }
      #tab_panel_adicoes .addition-intro-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
      #tab_panel_adicoes .addition-flow-strip { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: rgba(255,255,255,.018); color: var(--text-muted); font-size: 11px; font-weight: 700; }
      #tab_panel_adicoes .addition-flow-step { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
      #tab_panel_adicoes .addition-flow-step::after { content: "→"; margin-left: 2px; color: var(--text-faint); }
      #tab_panel_adicoes .addition-flow-step:last-child::after { display: none; }
      #tab_panel_adicoes .addition-summary-card { padding: 16px 18px; }
      #tab_panel_adicoes .addition-summary-title { align-items: flex-start; margin-bottom: 12px; }
      #tab_panel_adicoes .addition-summary-title > .addition-summary-heading { display: grid; gap: 5px; }
      #tab_panel_adicoes .addition-summary-title .section-title { font-size: 15px; }
      #tab_panel_adicoes .addition-summary-grid { grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
      #tab_panel_adicoes .addition-summary-chip { min-height: 70px; padding: 11px 12px; border-radius: 12px; }
      #tab_panel_adicoes .addition-summary-chip strong { font-size: 21px; }
      #tab_panel_adicoes .addition-guidance { margin-top: 8px; }
      #tab_panel_adicoes .addition-table-head { padding: 8px 7px; }
      #tab_panel_adicoes .addition-op-row { padding: 12px 7px; }

      /* Atualizar queue summary uses the same card language as Adicionar. */
      #tab_panel_atualizacoes .cs-update-operational-summary {
        display: grid;
        grid-template-columns: repeat(5,minmax(0,1fr));
        gap: 8px;
        margin: 12px 0;
        padding: 0;
        border: 0;
        border-radius: 0;
        background: transparent;
      }
      #tab_panel_atualizacoes .cs-update-operational-chip {
        display: grid;
        align-content: center;
        gap: 4px;
        min-width: 0;
        min-height: 58px;
        padding: 10px 11px;
        border: 1px solid var(--line);
        border-radius: 12px;
        background: var(--bg-elev-2);
        text-align: left;
        font-size: 10px;
      }
      #tab_panel_atualizacoes button.cs-update-operational-chip { cursor: pointer; }
      #tab_panel_atualizacoes .cs-update-operational-chip strong { display: block; font-size: 17px; line-height: 1; }
      #tab_panel_atualizacoes .cs-update-operational-guidance {
        grid-column: 1 / -1;
        margin: 0;
        padding: 9px 11px;
        border: 1px solid var(--line);
        border-radius: 10px;
        background: rgba(255,255,255,.012);
      }

      /* Closed accordion content should not leak into the layout. */
      #tab_panel_adicoes #addition_history_accordion:not([open]) > :not(summary),
      #tab_panel_adicoes #addition_technical_accordion:not([open]) > :not(summary),
      #tab_panel_atualizacoes details.cs-op-section:not([open]) > :not(summary) { display: none; }

      @media (max-width: 1050px) {
        #tab_panel_atualizacoes .cs-op-filterbar.cs-op-filterbar-wide,
        #tab_panel_adicoes .cs-op-filterbar.cs-op-filterbar-wide { grid-template-columns: repeat(2,minmax(0,1fr)); }
        #tab_panel_atualizacoes .cs-update-operational-summary { grid-template-columns: repeat(3,minmax(0,1fr)); }
      }

      @media (max-width: 900px) {
        #tab_panel_atualizacoes .cs-op-filterbar,
        #tab_panel_adicoes .cs-op-filterbar,
        #tab_panel_atualizacoes .cs-op-history-toolbar,
        #tab_panel_adicoes .cs-op-history-toolbar { grid-template-columns: 1fr; }
        #tab_panel_atualizacoes .cs-op-history-filters,
        #tab_panel_adicoes .cs-op-history-filters { grid-template-columns: 1fr; }
        #tab_panel_adicoes .addition-intro-head { grid-template-columns: 1fr; }
        #tab_panel_adicoes .addition-intro-actions { justify-content: flex-start; }
        #tab_panel_adicoes .addition-summary-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
      }

      @media (max-width: 700px) {
        #tab_panel_atualizacoes .cs-op-list-meta,
        #tab_panel_adicoes .cs-op-list-meta { flex-direction: column; align-items: stretch; }
        #tab_panel_atualizacoes .cs-op-page-size,
        #tab_panel_adicoes .cs-op-page-size,
        #tab_panel_atualizacoes .cs-op-inline-page-size,
        #tab_panel_adicoes .cs-op-inline-page-size { width: 100%; justify-content: space-between; }
        #tab_panel_atualizacoes .cs-op-pagination,
        #tab_panel_adicoes .cs-op-pagination { grid-template-columns: 1fr 1fr; }
        #tab_panel_atualizacoes .cs-op-page-jump,
        #tab_panel_adicoes .cs-op-page-jump { grid-column: 1 / -1; grid-row: 1; justify-self: center; }
        #tab_panel_atualizacoes .cs-update-operational-summary { grid-template-columns: repeat(2,minmax(0,1fr)); }
      }

      @media (max-width: 560px) {
        #tab_panel_atualizacoes .cs-op-filterbar.cs-op-filterbar-wide,
        #tab_panel_adicoes .cs-op-filterbar.cs-op-filterbar-wide,
        #tab_panel_adicoes .addition-summary-grid,
        #tab_panel_atualizacoes .cs-update-operational-summary { grid-template-columns: 1fr; }
        #tab_panel_adicoes .addition-intro-actions > * { width: 100%; }
      }
    `;
    document.head.appendChild(style);
  }

  function sectionHint(details, message) {
    if (!details || $(".cs-op-section-hint", details)) return;
    const summary = details.querySelector(":scope > summary");
    if (!summary) return;
    const hint = document.createElement("div");
    hint.className = "cs-op-section-hint addition-section-hint";
    hint.textContent = message;
    summary.insertAdjacentElement("afterend", hint);
  }

  function introMarkup() {
    const section = document.createElement("section");
    section.className = "card addition-intro-card cs-op-card";
    section.id = "addition_intro_card";
    section.innerHTML = `
      <div class="addition-intro-head">
        <div class="addition-intro-copy">
          <div class="section-title">Adicionar produtos</div>
          <div class="small">Gerencie os produtos aprovados na Comparação, prepare conteúdo e arquivos, organize a fila e acompanhe a publicação no WooCommerce. As etapas concluídas são reaproveitadas para evitar trabalho duplicado.</div>
        </div>
        <div class="addition-intro-actions cs-op-actions" id="addition_intro_actions"></div>
      </div>
      <div class="addition-flow-strip" aria-label="Fluxo de adição">
        <span class="addition-flow-step">Aprovação</span>
        <span class="addition-flow-step">Preparação</span>
        <span class="addition-flow-step">Fila</span>
        <span class="addition-flow-step">Publicação</span>
        <span class="addition-flow-step">Histórico</span>
      </div>`;
    return section;
  }

  function standardizePagination(root) {
    $$(".listing-pagination, .addition-pagination", root).forEach(pagination => {
      pagination.classList.add("cs-op-pagination");
      const page = $(".badge, [id$='_page'], [id$='_page_label']", pagination);
      if (page) page.classList.add("cs-op-page-jump");
    });
  }

  function standardizePageSizes(root) {
    $$(".listing-page-size", root).forEach(node => node.classList.add("cs-op-page-size"));
  }

  function standardizeEmptyStates(root) {
    $$(".addition-empty, .notice", root).forEach(node => node.classList.add("cs-op-empty"));
  }

  function dedupeUpdatePreparationEmpty(panel) {
    const card = $(".updates-working-card", panel);
    if (!card) return;
    const seen = new Set();
    $$(".notice", card).forEach(node => {
      const key = normalize(node.textContent);
      if (!key) return;
      if (seen.has(key)) node.remove();
      else seen.add(key);
    });
  }

  function normalizeUpdateQueueMeta(panel) {
    const controls = $("#updates_queue_list_controls", panel);
    const filters = $(".updates-list-controls", controls || panel);
    const found = $("#updates_queue_found_count", controls || panel);
    const pageInput = $("#updates_queue_page_size", controls || panel);
    const pageLabel = pageInput?.closest("label");
    const pagination = $(".listing-pagination", controls || panel);
    if (!controls || !filters || !found || !pageLabel || !pagination) return;

    filters.classList.add("cs-op-filterbar");
    let meta = $(".cs-op-list-meta[data-cs-update-queue-meta]", controls);
    if (!meta) {
      meta = document.createElement("div");
      meta.className = "listing-meta-row cs-op-list-meta";
      meta.dataset.csUpdateQueueMeta = "1";
      pagination.insertAdjacentElement("beforebegin", meta);
    }
    found.classList.add("small");
    pageLabel.classList.add("cs-op-inline-page-size");
    if (found.parentElement !== meta) meta.appendChild(found);
    if (pageLabel.parentElement !== meta) meta.appendChild(pageLabel);
  }

  function standardizeUpdate() {
    const panel = $("#tab_panel_atualizacoes");
    if (!panel) return false;

    panel.classList.add("cs-op-panel");
    addClass($$(":scope > .card", panel), "cs-op-card");
    addClass($$(".updates-card-section", panel), "cs-op-section");
    addClass($$(".updates-section-heading", panel), "cs-op-section-heading");
    addClass($$(".updates-filters", panel), "cs-op-filterbar", "cs-op-filterbar-wide");
    addClass($$(".updates-history-toolbar", panel), "cs-op-history-toolbar");
    addClass($$(".updates-history-filter-group", panel), "cs-op-history-filters");
    addClass($$(".updates-history-actions", panel), "cs-op-history-actions");
    addClass($$(".updates-queue-actions, .updates-bulkbar", panel), "cs-op-actions");
    addClass($$(".listing-meta-row", panel), "cs-op-list-meta");
    addClass($$(".updates-history-panel", panel), "cs-op-results");

    $$("details.updates-card-section, details.updates-technical-log", panel).forEach(details => {
      details.classList.add("cs-op-section");
    });

    normalizeUpdateQueueMeta(panel);
    standardizePagination(panel);
    standardizePageSizes(panel);
    standardizeEmptyStates(panel);
    dedupeUpdatePreparationEmpty(panel);
    return true;
  }

  function standardizeAddition() {
    const panel = $("#tab_panel_adicoes");
    const root = $("#addition_operational_root", panel || document);
    if (!panel || !root) return false;

    root.classList.add("addition-layout-standard", "cs-op-panel");
    addClass($$(":scope > .card", root), "cs-op-card");
    addClass($$("details.addition-accordion", root), "cs-op-section");
    addClass($$(".addition-toolbar", root), "cs-op-filterbar");
    addClass($$(".addition-list-meta", root), "cs-op-list-meta");
    addClass($$(".addition-list-meta-left", root), "cs-op-list-meta-left");
    addClass($$(".addition-bulk-actions, .addition-modal-actions", root), "cs-op-actions");
    addClass($$(".updates-history-toolbar", root), "cs-op-history-toolbar");
    const historyFilters = $(".updates-history-filter-group", root);
    if (historyFilters) historyFilters.removeAttribute("style");
    addClass($$(".updates-history-filter-group", root), "cs-op-history-filters");
    addClass($$(".updates-history-actions", root), "cs-op-history-actions");
    addClass($$(".addition-table-head", root), "cs-op-table-head");
    addClass($$(".addition-summary-chip", root), "cs-op-summary-card");

    const summary = $(".addition-summary-card", root);
    if (summary && !$("#addition_intro_card", root)) {
      const intro = introMarkup();
      root.insertBefore(intro, summary);
      const sync = $("#addition_sync_approved", summary);
      const actions = $("#addition_intro_actions", intro);
      if (sync && actions) {
        sync.classList.remove("btn-sm");
        actions.appendChild(sync);
      }
    }

    const titleWrap = $(".addition-summary-title", summary || root);
    if (titleWrap) {
      const heading = titleWrap.firstElementChild;
      if (heading) {
        heading.classList.add("addition-summary-heading");
        const title = $(".section-title", heading);
        const subtitle = $(".small", heading);
        if (title) title.textContent = "Resumo das adições";
        if (subtitle) subtitle.textContent = "Visão geral dos produtos aprovados e do andamento da operação.";
      }
    }

    sectionHint($("#addition_preparation_accordion", root), "Revise os itens aprovados, confira dados essenciais e prepare conteúdo, imagem, categoria, preços e ZIP antes de enviá-los para a fila.");
    sectionHint($("#addition_queue_accordion", root), "Acompanhe os produtos prontos para execução, o estado persistido de cada item e controle o processamento sequencial da fila.");
    sectionHint($("#addition_history_accordion", root), "Consulte tentativas anteriores, resultados, duração e registros persistidos de cada cadastro.");
    sectionHint($("#addition_technical_accordion", root), "Eventos técnicos desta sessão para diagnóstico. Use apenas quando precisar investigar uma operação.");

    const history = $("#addition_history_accordion", root);
    const technical = $("#addition_technical_accordion", root);
    if (history && history.dataset.csInitialCollapse !== "1") {
      history.open = false;
      history.dataset.csInitialCollapse = "1";
    }
    if (technical && technical.dataset.csInitialCollapse !== "1") {
      technical.open = false;
      technical.dataset.csInitialCollapse = "1";
    }

    standardizePagination(root);
    standardizePageSizes(root);
    standardizeEmptyStates(root);
    return true;
  }

  function standardizeActiveTab() {
    const key = String(document.body?.dataset?.activeTab || "");
    if (key === "atualizacoes") standardizeUpdate();
    if (key === "adicoes") standardizeAddition();
  }

  function scheduleStandardization(kind) {
    const run = kind === "adicoes" ? standardizeAddition : standardizeUpdate;
    [0, 40, 120, 300, 700].forEach(delay => window.setTimeout(run, delay));
  }

  installStyles();
  standardizeUpdate();
  $("#tab_btn_atualizacoes")?.addEventListener("click", () => scheduleStandardization("atualizacoes"));
  $("#tab_btn_adicoes")?.addEventListener("click", () => scheduleStandardization("adicoes"));
  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
    if (key === "atualizacoes" || key === "adicoes") scheduleStandardization(key);
  });
  standardizeActiveTab();
})();
