(() => {
  "use strict";

  const STYLE_ID = "crapscraper-unified-search-style";
  const DEFAULT_PAGE_SIZE = 5;
  const byId = id => document.getElementById(id);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .cs-search-system{
      --cs-border:#292931;
      --cs-panel:#111114;
      --cs-panel2:#151519;
      --cs-muted:#9ca3af;
      --cs-control:46px;
    }

    .cs-search-system input[type=search],
    .cs-search-system input[type=text],
    .cs-search-system input[type=number],
    .cs-search-system select{
      min-height:var(--cs-control)!important;
      height:var(--cs-control)!important;
      min-width:0!important;
      border:1px solid var(--cs-border)!important;
      border-radius:10px!important;
      background:#09090b!important;
      color:#fff!important;
      padding:0 14px!important;
    }

    .cs-search-system label{
      font-size:12px!important;
      font-weight:700!important;
      color:#d7d7df!important;
    }

    .cs-search-system button{border-radius:10px!important}

    /* Bloco de filtros: mesma linguagem visual em todas as listagens. */
    .cs-search-system .comparison-filter-grid,
    .cs-search-system .comparison-actions-grid,
    .cs-search-system .updates-filters,
    .cs-search-system .plugintema-manage-filters,
    .cs-search-system .updates-list-controls,
    .cs-search-system .updates-history-toolbar{
      gap:12px!important;
      align-items:end!important;
      padding:14px!important;
      background:var(--cs-panel)!important;
      border:1px solid var(--cs-border)!important;
      border-radius:14px!important;
    }

    .cs-search-system .updates-filters{
      display:grid!important;
      grid-template-columns:repeat(6,minmax(0,1fr))!important;
    }
    .cs-search-system .updates-filters>label,
    .cs-search-system .updates-filters>button{min-width:0!important;width:100%!important}
    .cs-search-system .updates-filters>button{min-height:var(--cs-control)!important}

    .cs-search-system .plugintema-manage-filters{
      display:grid!important;
      grid-template-columns:repeat(4,minmax(0,1fr))!important;
    }

    /* A fila usa somente busca + estado no bloco de filtros.
       Contagem e itens/página ficam na linha de metadados, como nas demais. */
    .cs-search-system .updates-list-controls{
      display:grid!important;
      grid-template-columns:minmax(280px,2fr) minmax(220px,1fr)!important;
      margin-bottom:0!important;
    }
    .cs-search-system .updates-list-controls>label{min-width:0!important}

    .cs-search-system .updates-history-toolbar{
      display:grid!important;
      grid-template-columns:minmax(0,1fr) auto!important;
      margin-bottom:12px!important;
    }
    .cs-search-system .updates-history-filter-group{
      display:grid!important;
      grid-template-columns:minmax(280px,3fr) minmax(220px,2fr)!important;
      gap:12px!important;
      min-width:0!important;
    }
    .cs-search-system .updates-history-actions{
      display:flex!important;
      gap:10px!important;
      align-items:end!important;
    }
    .cs-search-system .updates-history-actions button{min-height:var(--cs-control)!important}

    /* Linha padrão: quantidade à esquerda e itens por página à direita. */
    .cs-search-system .listing-meta-row,
    .cs-search-system .cs-queue-meta-row{
      display:flex!important;
      align-items:center!important;
      justify-content:space-between!important;
      gap:14px!important;
      min-height:48px!important;
      margin:8px 0 10px!important;
      color:var(--cs-muted)!important;
    }
    .cs-search-system .listing-page-size,
    .cs-search-system .cs-page-size-wrap{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      margin-left:auto!important;
      white-space:nowrap!important;
      color:var(--cs-muted)!important;
      font-size:13px!important;
      font-weight:400!important;
    }
    .cs-search-system .listing-page-size select,
    .cs-search-system .cs-page-size-wrap select,
    .cs-search-system .listing-page-size input,
    .cs-search-system .cs-page-size-wrap input{
      width:58px!important;
      min-width:58px!important;
      max-width:58px!important;
      height:32px!important;
      min-height:32px!important;
      padding:4px 6px!important;
    }

    /* Paginação única: anterior | página editável | próxima. */
    .cs-search-system .listing-pagination{
      display:grid!important;
      grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
      gap:12px!important;
      align-items:center!important;
      width:100%!important;
      margin:0 0 14px!important;
    }
    .cs-search-system .listing-pagination>button{
      width:100%!important;
      min-height:48px!important;
      margin:0!important;
    }
    .cs-search-system .cs-page-jump{
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      gap:6px!important;
      min-height:36px!important;
      padding:4px 10px!important;
      border:1px solid var(--cs-border)!important;
      border-radius:999px!important;
      background:#17171b!important;
      color:#fff!important;
      font-size:12px!important;
      font-weight:800!important;
      white-space:nowrap!important;
    }
    .cs-search-system .cs-page-jump input{
      width:58px!important;
      min-width:58px!important;
      height:28px!important;
      min-height:28px!important;
      padding:0 6px!important;
      text-align:center!important;
      border:1px solid #41414b!important;
      border-radius:7px!important;
      background:#09090b!important;
      color:#fff!important;
      font-size:12px!important;
      font-weight:800!important;
    }

    /* Operações em lote: duas linhas previsíveis em Comparar e Preparação. */
    .cs-search-system .comparison-bulk-toolbar,
    .cs-search-system .updates-bulkbar{
      display:flex!important;
      flex-direction:column!important;
      align-items:stretch!important;
      gap:10px!important;
      padding:12px!important;
      margin:10px 0 12px!important;
      border:1px solid var(--cs-border)!important;
      border-radius:12px!important;
      background:var(--cs-panel2)!important;
    }
    .cs-search-system .cs-bulk-selection-line,
    .cs-search-system .cs-bulk-action-line,
    .cs-search-system .comparison-bulk-actions-row{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      flex-wrap:wrap!important;
      width:100%!important;
    }
    .cs-search-system .cs-bulk-selection-line .badge,
    .cs-search-system .cs-bulk-selection-line #updates_selected_count,
    .cs-search-system .cs-bulk-selection-line #comparison_selected_count{
      margin-left:auto!important;
      white-space:nowrap!important;
    }
    .cs-search-system .cs-bulk-action-line button,
    .cs-search-system .comparison-bulk-actions-row button{
      min-height:46px!important;
    }
    .cs-search-system .cs-bulk-action-line{
      padding-top:10px!important;
      border-top:1px solid #25252c!important;
      justify-content:flex-end!important;
    }
    .cs-search-system .cs-bulk-action-line button{
      min-width:220px!important;
    }
    .cs-search-system .comparison-bulk-actions-row{
      padding-top:10px!important;
      border-top:1px solid #25252c!important;
    }
    .cs-search-system .comparison-bulk-actions-row select{
      flex:1 1 420px!important;
    }

    .cs-search-system .table-wrap,
    .cs-search-system .comparison-table-wrap,
    .cs-search-system .updates-history-panel,
    .cs-search-system #updates_jobs,
    .cs-search-system #updates_queue_jobs{
      border-color:#292931!important;
    }

    @media(max-width:1200px){
      .cs-search-system .updates-filters{grid-template-columns:repeat(3,minmax(0,1fr))!important}
      .cs-search-system .plugintema-manage-filters{grid-template-columns:repeat(2,minmax(0,1fr))!important}
    }
    @media(max-width:1050px){
      .cs-search-system .updates-list-controls{grid-template-columns:1fr 1fr!important}
      .cs-search-system .updates-history-toolbar{grid-template-columns:1fr!important}
      .cs-search-system .updates-history-actions{justify-content:flex-start!important}
    }
    @media(max-width:720px){
      .cs-search-system .updates-filters,
      .cs-search-system .updates-list-controls,
      .cs-search-system .updates-history-filter-group,
      .cs-search-system .plugintema-manage-filters{grid-template-columns:1fr!important}
      .cs-search-system .listing-meta-row,
      .cs-search-system .cs-queue-meta-row{align-items:flex-start!important;flex-direction:column!important}
      .cs-search-system .listing-page-size,
      .cs-search-system .cs-page-size-wrap{margin-left:0!important}
      .cs-search-system .listing-pagination{grid-template-columns:1fr 1fr!important}
      .cs-search-system .cs-page-jump{grid-column:1/-1!important;grid-row:1!important}
      .cs-search-system .cs-bulk-selection-line .badge,
      .cs-search-system .cs-bulk-selection-line #updates_selected_count,
      .cs-search-system .cs-bulk-selection-line #comparison_selected_count{margin-left:0!important}
      .cs-search-system .cs-bulk-action-line button{width:100%!important;min-width:0!important}
    }
  `;

  document.getElementById(STYLE_ID)?.remove();
  document.head.appendChild(style);

  function clearBrokenClasses() {
    const classes = [
      "search-system-standard","ss-filter-zone","ss-selection-zone","ss-meta-row",
      "ss-page-size","ss-pagination","ss-page-jump","ss-result-list",
      "cs-filter-row","cs-field","cs-span-4","cs-span-6","cs-span-8",
      "cs-action","cs-inline-actions","cs-meta-row","cs-page-size",
      "cs-pagination","cs-selection-row","cs-results-zone"
    ];
    document.querySelectorAll(`.${classes.join(",.")}`).forEach(node => node.classList.remove(...classes));
  }

  function findRoot(anchor) {
    return anchor?.closest?.("[role='dialog'],.comparison-link-modal-card,.modal-card,.updates-card-section,.card,details,section") || anchor?.parentElement || null;
  }

  function markSystem(root, key) {
    if (!root) return null;
    root.classList.add("cs-search-system");
    root.dataset.csSearchSystem = key;
    return root;
  }

  function normalizePageSizeSelect(select) {
    if (!select || select.tagName !== "INPUT") return;
    select.type = "number";
    select.min = "1";
    select.step = "1";
    select.inputMode = "numeric";
    if (!Number.isFinite(Number.parseInt(select.value,10)) || Number.parseInt(select.value,10) < 1) select.value = String(DEFAULT_PAGE_SIZE);
  }

  function normalizePageSize(root, id) {
    const select = byId(id);
    if (!root || !select) return;
    normalizePageSizeSelect(select);
    const container = select.closest(".listing-page-size") || select.parentElement;
    if (!container) return;
    [...container.querySelectorAll("label,span")].forEach(label => {
      if (/linhas por página|itens por página/i.test(normalize(label.textContent))) label.textContent = "Itens por página";
    });
  }

  function parsePage(label) {
    if (!label) return null;
    const input = label.querySelector("input[data-cs-page-input]");
    const totalNode = label.querySelector("span");
    if (input && totalNode) {
      const current = Number(input.value || 0);
      const total = Number(totalNode.textContent || 0);
      if (current > 0 && total > 0) return {current,total};
    }
    const raw = normalize(label.textContent);
    const match = raw.match(/Página\s+(\d+)\s+de\s+(\d+)/i);
    if (match) return {current:Number(match[1]),total:Number(match[2])};
    const current = Number(label.dataset.csCurrent || 0);
    const total = Number(label.dataset.csTotal || 0);
    return current > 0 && total > 0 ? {current,total} : null;
  }

  function fallbackJump(spec, target, current) {
    const id = target > current ? spec.next : spec.prev;
    let remaining = Math.abs(target - current);
    const step = () => {
      if (remaining <= 0) return;
      const button = byId(id);
      if (!button || button.disabled) return;
      button.click();
      remaining -= 1;
      if (remaining > 0) setTimeout(step,35);
    };
    step();
  }

  function installPageJump(spec) {
    const label = byId(spec.label);
    if (!label) return;
    const info = parsePage(label);
    if (!info) return;

    const existing = label.querySelector("input[data-cs-page-input]");
    if (existing && Number(label.dataset.csCurrent) === info.current && Number(label.dataset.csTotal) === info.total) return;

    label.dataset.csCurrent = String(info.current);
    label.dataset.csTotal = String(info.total);
    label.classList.add("cs-page-jump");
    label.innerHTML = `Página <input data-cs-page-input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;

    const input = label.querySelector("input[data-cs-page-input]");
    const go = () => {
      const target = Math.max(1,Math.min(info.total,Number(input.value) || info.current));
      if (target === info.current) return;
      const api = window.__crapscraperPagination;
      if (api && typeof api[spec.setter] === "function") api[spec.setter](target);
      else fallbackJump(spec,target,info.current);
    };
    input.addEventListener("keydown",event => {
      if (event.key === "Enter") {
        event.preventDefault();
        go();
      }
    });
    input.addEventListener("change",go);
  }

  function prepareKnownPagination(root, spec) {
    if (!root) return;
    const prev = byId(spec.prev), label = byId(spec.label), next = byId(spec.next);
    if (!prev || !label || !next) return;
    const row = prev.closest(".listing-pagination") || label.closest(".listing-pagination") || next.closest(".listing-pagination");
    if (row) row.classList.add("listing-pagination");
    installPageJump(spec);
  }

  function standardizeComparisonBulk(results) {
    const bar = results?.querySelector(".comparison-bulk-toolbar");
    if (!bar) return;
    bar.classList.add("comparison-bulk-toolbar");

    let selection = bar.querySelector(".cs-bulk-selection-line");
    const actions = bar.querySelector(".comparison-bulk-actions-row");
    if (!selection) {
      selection = document.createElement("div");
      selection.className = "cs-bulk-selection-line";
      [...bar.children].filter(node => node !== actions).forEach(node => selection.appendChild(node));
      bar.insertBefore(selection,actions || null);
    }
    actions?.classList.add("comparison-bulk-actions-row");
  }

  function standardizeWaitingBulk(root) {
    const bar = root?.querySelector(".updates-bulkbar");
    if (!bar) return;
    bar.classList.add("updates-bulkbar");

    let selection = bar.querySelector(".cs-bulk-selection-line");
    let actions = bar.querySelector(".cs-bulk-action-line");
    if (!selection) {
      selection = document.createElement("div");
      selection.className = "cs-bulk-selection-line";
      const ids = ["updates_select_page","updates_select_filtered","updates_clear_selection","updates_selected_count"];
      ids.map(byId).filter(Boolean).forEach(node => selection.appendChild(node));
      bar.prepend(selection);
    }
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "cs-bulk-action-line";
      [byId("updates_prepare_selected"),byId("updates_enqueue_selected")].filter(Boolean).forEach(node => actions.appendChild(node));
      bar.appendChild(actions);
    }
  }

  function standardizeQueueMeta(root) {
    const controls = root?.querySelector(".updates-list-controls");
    const pagination = byId("updates_queue_prev")?.closest(".listing-pagination");
    const pageSize = byId("updates_queue_page_size");
    const count = byId("updates_queue_found_count");
    if (!controls || !pagination || !pageSize || !count) return;

    const oldLabel = pageSize.closest("label");
    let meta = root.querySelector(".cs-queue-meta-row");
    if (!meta) {
      meta = document.createElement("div");
      meta.className = "listing-meta-row cs-queue-meta-row";
      pagination.parentElement?.insertBefore(meta,pagination);
    }

    count.classList.add("cs-result-count");
    if (count.parentElement !== meta) meta.appendChild(count);

    let pageWrap = meta.querySelector(".cs-page-size-wrap");
    if (!pageWrap) {
      pageWrap = document.createElement("div");
      pageWrap.className = "listing-page-size cs-page-size-wrap";
      const label = document.createElement("span");
      label.textContent = "Itens por página";
      pageWrap.appendChild(label);
      pageWrap.appendChild(pageSize);
      meta.appendChild(pageWrap);
    }
    if (oldLabel && oldLabel !== pageWrap && oldLabel.childElementCount === 0) oldLabel.remove();
  }

  function setupCatalogs() {
    const root = markSystem(findRoot(byId("catalogos_page_size")),"catalogs");
    if (!root) return;
    normalizePageSize(root,"catalogos_page_size");
    prepareKnownPagination(root,{label:"catalogos_page_label",prev:"catalogos_prev_page",next:"catalogos_next_page",setter:"catalogs"});
  }

  function setupComparison() {
    const panel = markSystem(byId("tab_panel_comparacao"),"comparison");
    const results = markSystem(byId("comparison_results_card"),"comparison-results");
    if (!panel || !results) return;
    panel.querySelector(".comparison-filter-grid")?.classList.add("comparison-filter-grid");
    panel.querySelector(".comparison-actions-grid")?.classList.add("comparison-actions-grid");
    standardizeComparisonBulk(results);
    normalizePageSize(results,"comparison_page_size");
    prepareKnownPagination(results,{label:"comparison_page_label",prev:"comparison_prev_btn",next:"comparison_next_btn",setter:"comparison"});
  }

  function setupWaiting() {
    const root = markSystem(findRoot(byId("updates_status_filter")),"updates-waiting");
    if (!root) return;
    root.querySelector(".updates-filters")?.classList.add("updates-filters");
    standardizeWaitingBulk(root);
    normalizePageSize(root,"updates_page_size");
    prepareKnownPagination(root,{label:"updates_page_label",prev:"updates_prev_page",next:"updates_next_page",setter:"updatesWaiting"});
  }

  function setupQueue() {
    const root = markSystem(findRoot(byId("updates_queue_search")),"updates-queue");
    if (!root) return;
    root.querySelector(".updates-list-controls")?.classList.add("updates-list-controls");
    normalizePageSizeSelect(byId("updates_queue_page_size"));
    standardizeQueueMeta(root);
    prepareKnownPagination(root,{label:"updates_queue_page",prev:"updates_queue_prev",next:"updates_queue_next",setter:"updatesQueue"});
  }

  function setupHistory() {
    const root = markSystem(byId("updates_history_accordion") || findRoot(byId("updates_history_search")),"updates-history");
    if (!root) return;
    root.querySelector(".updates-history-toolbar")?.classList.add("updates-history-toolbar");
    root.querySelector(".updates-history-filter-group")?.classList.add("updates-history-filter-group");
    root.querySelector(".updates-history-actions")?.classList.add("updates-history-actions");
    normalizePageSize(root,"updates_history_page_size");
    prepareKnownPagination(root,{label:"updates_history_page",prev:"updates_history_prev",next:"updates_history_next",setter:"updatesHistory"});
  }

  function setupPluginTemaManager() {
    const root = markSystem(findRoot(byId("plugintema_manage_search")),"plugintema-manager");
    if (!root) return;
    root.querySelector(".plugintema-manage-filters")?.classList.add("plugintema-manage-filters");
    normalizePageSize(root,"plugintema_manage_page_size");
    prepareKnownPagination(root,{label:"plugintema_manage_page_status",prev:"plugintema_manage_prev",next:"plugintema_manage_next",setter:"pluginTemaManager"});
  }

  function setupUpdateListPreview() {
    const root = markSystem(findRoot(byId("update_list_preview_search")),"update-list-preview");
    if (!root) return;
    normalizePageSize(root,"update_list_preview_page_size");
    prepareKnownPagination(root,{label:"update_list_preview_page",prev:"update_list_preview_prev",next:"update_list_preview_next",setter:"updateListPreview"});
  }

  function setupCatalogPreview() {
    const root = markSystem(findRoot(byId("catalogos_preview_search")),"catalog-preview");
    if (!root) return;
    normalizePageSize(root,"catalog_preview_page_size");

    const labels = [...root.querySelectorAll(".badge,span,div")].filter(node => /^Página\s+\d+\s+de\s+\d+$/i.test(normalize(node.textContent)));
    const label = labels[0];
    if (!label) return;
    const row = label.closest(".listing-pagination") || label.parentElement;
    if (!row) return;
    const buttons = [...row.querySelectorAll("button")];
    const prev = buttons.find(button => /anterior/i.test(button.textContent));
    const next = buttons.find(button => /próxima|proxima/i.test(button.textContent));
    if (!prev || !next) return;
    if (!label.id) label.id = "catalog_preview_page_label_dynamic";
    if (!prev.id) prev.id = "catalog_preview_prev_dynamic";
    if (!next.id) next.id = "catalog_preview_next_dynamic";
    row.classList.add("listing-pagination");
    installPageJump({label:label.id,prev:prev.id,next:next.id,setter:"catalogPreview"});
  }

  function standardizeAll() {
    clearBrokenClasses();
    setupCatalogs();
    setupComparison();
    setupWaiting();
    setupQueue();
    setupHistory();
    setupPluginTemaManager();
    setupUpdateListPreview();
    setupCatalogPreview();
  }

  let timer = null;
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(standardizeAll,80);
  };

  const start = () => {
    standardizeAll();
    new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",start,{once:true});
  else start();
})();
