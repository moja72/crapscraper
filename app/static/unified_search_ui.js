(() => {
  "use strict";

  const STYLE_ID = "crapscraper-unified-search-style";
  const PAGE_SIZES = [5, 10, 25, 50, 100, 250];
  const byId = id => document.getElementById(id);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .cs-search-system{--cs-border:#292931;--cs-panel:#111114;--cs-panel2:#151519;--cs-muted:#9ca3af;--cs-control:46px}

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

    .cs-search-system .comparison-filter-grid,
    .cs-search-system .comparison-actions-grid,
    .cs-search-system .updates-filters,
    .cs-search-system .plugintema-manage-filters{
      gap:12px!important;
      align-items:end!important;
    }

    .cs-search-system .updates-filters,
    .cs-search-system .plugintema-manage-filters,
    .cs-search-system .comparison-filter-grid,
    .cs-search-system .comparison-actions-grid{
      padding:14px!important;
      background:var(--cs-panel)!important;
      border:1px solid var(--cs-border)!important;
      border-radius:14px!important;
    }

    .cs-search-system .updates-list-controls{
      display:grid!important;
      grid-template-columns:minmax(260px,5fr) minmax(190px,3fr) minmax(150px,2fr) minmax(130px,2fr)!important;
      gap:12px!important;
      align-items:end!important;
      padding:14px!important;
      background:var(--cs-panel)!important;
      border:1px solid var(--cs-border)!important;
      border-radius:14px!important;
      margin-bottom:12px!important;
    }
    .cs-search-system .updates-list-controls>label{min-width:0!important}
    .cs-search-system .updates-list-controls>strong{
      min-height:var(--cs-control)!important;
      display:flex!important;
      align-items:center!important;
      justify-content:flex-end!important;
      color:#d8d8e0!important;
      white-space:nowrap!important;
    }

    .cs-search-system .updates-history-toolbar{
      display:grid!important;
      grid-template-columns:minmax(0,1fr) auto!important;
      gap:12px!important;
      align-items:end!important;
      padding:14px!important;
      background:var(--cs-panel)!important;
      border:1px solid var(--cs-border)!important;
      border-radius:14px!important;
      margin-bottom:12px!important;
    }
    .cs-search-system .updates-history-filter-group{
      display:grid!important;
      grid-template-columns:minmax(260px,3fr) minmax(190px,2fr)!important;
      gap:12px!important;
      min-width:0!important;
    }
    .cs-search-system .updates-history-actions{
      display:flex!important;
      gap:10px!important;
      align-items:end!important;
    }
    .cs-search-system .updates-history-actions button{min-height:var(--cs-control)!important}

    .cs-search-system .listing-meta-row{
      display:flex!important;
      align-items:center!important;
      justify-content:space-between!important;
      gap:14px!important;
      min-height:48px!important;
      margin:8px 0 10px!important;
      color:var(--cs-muted)!important;
    }
    .cs-search-system .listing-page-size{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      margin-left:auto!important;
      white-space:nowrap!important;
    }
    .cs-search-system .listing-page-size select{
      width:92px!important;
      min-width:92px!important;
      height:42px!important;
      min-height:42px!important;
      padding:0 30px 0 12px!important;
    }

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

    .cs-search-system .comparison-bulk-toolbar,
    .cs-search-system .updates-bulkbar{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      flex-wrap:wrap!important;
      padding:12px!important;
      margin:10px 0 12px!important;
      border:1px solid var(--cs-border)!important;
      border-radius:12px!important;
      background:var(--cs-panel2)!important;
    }

    .cs-search-system .table-wrap,
    .cs-search-system .comparison-table-wrap,
    .cs-search-system .updates-history-panel,
    .cs-search-system #updates_jobs,
    .cs-search-system #updates_queue_jobs{
      border-color:#292931!important;
    }

    @media(max-width:1050px){
      .cs-search-system .updates-list-controls{grid-template-columns:1fr 1fr!important}
      .cs-search-system .updates-history-toolbar{grid-template-columns:1fr!important}
      .cs-search-system .updates-history-actions{justify-content:flex-start!important}
    }
    @media(max-width:720px){
      .cs-search-system .updates-list-controls,
      .cs-search-system .updates-history-filter-group{grid-template-columns:1fr!important}
      .cs-search-system .listing-meta-row{align-items:flex-start!important;flex-direction:column!important}
      .cs-search-system .listing-page-size{margin-left:0!important}
      .cs-search-system .listing-pagination{grid-template-columns:1fr 1fr!important}
      .cs-search-system .cs-page-jump{grid-column:1/-1!important;grid-row:1!important}
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

  function addFiveOption(select) {
    if (!select || select.tagName !== "SELECT") return;
    const numeric = [...select.options].every(option => /^\d+$/.test(normalize(option.value)));
    if (!numeric) return;
    const selected = select.value;
    PAGE_SIZES.forEach(size => {
      if (![...select.options].some(option => Number(option.value) === size)) {
        const option = document.createElement("option");
        option.value = String(size);
        option.textContent = String(size);
        select.appendChild(option);
      }
    });
    [...select.options].sort((a,b) => Number(a.value) - Number(b.value)).forEach(option => select.appendChild(option));
    if ([...select.options].some(option => option.value === selected)) select.value = selected;
  }

  function normalizePageSize(root, id) {
    const select = byId(id);
    if (!root || !select) return;
    addFiveOption(select);
    const container = select.closest(".listing-page-size") || select.parentElement;
    if (!container) return;
    [...container.querySelectorAll("label,span")].forEach(label => {
      if (/linhas por página|itens por página/i.test(normalize(label.textContent))) label.textContent = "Itens por página";
    });
  }

  function parsePage(label) {
    if (!label) return null;
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
      if (remaining > 0) setTimeout(step, 35);
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
      const target = Math.max(1, Math.min(info.total, Number(input.value) || info.current));
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

  function setupComparison() {
    const panel = markSystem(byId("tab_panel_comparacao"),"comparison");
    const results = markSystem(byId("comparison_results_card"),"comparison-results");
    if (!panel || !results) return;
    panel.querySelector(".comparison-filter-grid")?.classList.add("comparison-filter-grid");
    panel.querySelector(".comparison-actions-grid")?.classList.add("comparison-actions-grid");
    results.querySelector(".comparison-bulk-toolbar")?.classList.add("comparison-bulk-toolbar");
    normalizePageSize(results,"comparison_page_size");
    prepareKnownPagination(results,{label:"comparison_page_label",prev:"comparison_prev_btn",next:"comparison_next_btn",setter:"comparison"});
  }

  function setupWaiting() {
    const root = markSystem(findRoot(byId("updates_status_filter")),"updates-waiting");
    if (!root) return;
    root.querySelector(".updates-filters")?.classList.add("updates-filters");
    root.querySelector(".updates-bulkbar")?.classList.add("updates-bulkbar");
    normalizePageSize(root,"updates_page_size");
    prepareKnownPagination(root,{label:"updates_page_label",prev:"updates_prev_page",next:"updates_next_page",setter:"updatesWaiting"});
  }

  function setupQueue() {
    const root = markSystem(findRoot(byId("updates_queue_search")),"updates-queue");
    if (!root) return;
    root.querySelector(".updates-list-controls")?.classList.add("updates-list-controls");
    normalizePageSize(root,"updates_queue_page_size");
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
    setupComparison();
    setupWaiting();
    setupQueue();
    setupHistory();
    setupPluginTemaManager();
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
