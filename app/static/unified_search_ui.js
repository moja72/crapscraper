(() => {
  "use strict";

  const PAGE_SIZES = [5, 10, 25, 50, 100, 250];
  const STYLE_ID = "crapscraper-unified-search-style";

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .search-system-standard{--ss-border:#292931;--ss-bg:#111114;--ss-bg2:#151519;--ss-muted:#a7a7b2;--ss-control:46px}
    .search-system-standard .ss-filter-zone{display:grid!important;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px!important;align-items:end!important;padding:14px!important;margin:0 0 12px!important;background:var(--ss-bg)!important;border:1px solid var(--ss-border)!important;border-radius:14px!important}
    .search-system-standard .ss-filter-zone>.field,.search-system-standard .ss-filter-zone>label{grid-column:span 3;min-width:0!important;margin:0!important}
    .search-system-standard .ss-filter-zone .comparison-search-field{grid-column:span 4}
    .search-system-standard .ss-filter-zone .comparison-run-button{grid-column:span 5}
    .search-system-standard .ss-filter-zone .comparison-reload-button{grid-column:span 3}
    .search-system-standard .field{gap:6px!important}
    .search-system-standard .field label,.search-system-standard .ss-filter-zone label{font-size:12px!important;font-weight:700!important;color:#d6d6df!important;margin:0!important}
    .search-system-standard input[type=search],.search-system-standard input[type=text],.search-system-standard input[type=number],.search-system-standard select{min-height:var(--ss-control)!important;height:var(--ss-control)!important;border:1px solid var(--ss-border)!important;border-radius:10px!important;background:#09090b!important;padding:0 14px!important}
    .search-system-standard button{border-radius:10px!important}
    .search-system-standard .ss-selection-zone{display:flex!important;align-items:center!important;gap:10px!important;flex-wrap:wrap!important;padding:12px!important;margin:10px 0 12px!important;background:var(--ss-bg2)!important;border:1px solid var(--ss-border)!important;border-radius:12px!important}
    .search-system-standard .ss-selection-zone .badge{margin-left:auto}
    .search-system-standard .ss-meta-row{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;min-height:46px!important;margin:10px 0!important;color:var(--ss-muted)!important}
    .search-system-standard .ss-page-size{display:flex!important;align-items:center!important;gap:10px!important;margin-left:auto!important;white-space:nowrap!important}
    .search-system-standard .ss-page-size select{width:92px!important;min-width:92px!important;height:42px!important;min-height:42px!important;padding:0 30px 0 12px!important}
    .search-system-standard .ss-pagination{display:grid!important;grid-template-columns:minmax(150px,1fr) auto minmax(150px,1fr)!important;gap:12px!important;align-items:center!important;margin:0 0 14px!important}
    .search-system-standard .ss-pagination>button{width:100%!important;min-height:48px!important}
    .search-system-standard .ss-page-jump{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:6px!important;min-height:36px!important;padding:4px 10px!important;background:#17171b!important;border:1px solid var(--ss-border)!important;border-radius:999px!important;font-size:12px!important;font-weight:800!important;color:#fff!important;white-space:nowrap!important}
    .search-system-standard .ss-page-jump input{width:56px!important;min-width:56px!important;height:28px!important;min-height:28px!important;padding:0 6px!important;text-align:center!important;border-radius:7px!important;border:1px solid #41414b!important;background:#09090b!important;color:#fff!important;font-size:12px!important;font-weight:800!important}
    .search-system-standard .ss-result-list{border-top:1px solid #24242b!important;padding-top:2px!important}
    .search-system-standard table{border-color:#292931!important}
    @media(max-width:1100px){.search-system-standard .ss-filter-zone>.field,.search-system-standard .ss-filter-zone>label,.search-system-standard .ss-filter-zone .comparison-search-field,.search-system-standard .ss-filter-zone .comparison-run-button,.search-system-standard .ss-filter-zone .comparison-reload-button{grid-column:span 6}}
    @media(max-width:720px){.search-system-standard .ss-filter-zone{grid-template-columns:1fr!important}.search-system-standard .ss-filter-zone>*{grid-column:1!important}.search-system-standard .ss-meta-row{align-items:flex-start!important;flex-direction:column!important}.search-system-standard .ss-page-size{margin-left:0!important}.search-system-standard .ss-pagination{grid-template-columns:1fr 1fr!important}.search-system-standard .ss-page-jump{grid-column:1/-1;grid-row:1}.search-system-standard .ss-selection-zone .badge{margin-left:0}}
  `;
  if (!document.getElementById(STYLE_ID)) document.head.appendChild(style);

  const byId = id => document.getElementById(id);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function addFiveOption(select) {
    if (!select || select.tagName !== "SELECT") return;
    const values = [...select.options].map(option => normalize(option.value));
    if (!values.length || !values.every(value => /^\d+$/.test(value))) return;
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

  function pageInfo(node) {
    const match = normalize(node?.textContent).match(/^Página\s+(\d+)\s+de\s+(\d+)$/i);
    return match ? {current:Number(match[1]), total:Number(match[2])} : null;
  }

  function installJump(label, prev, next) {
    if (!label || !prev || !next || label.dataset.pageJumpInstalled === "1") return;
    const info = pageInfo(label);
    if (!info) return;
    label.dataset.pageJumpInstalled = "1";
    label.classList.add("ss-page-jump");
    label.innerHTML = `Página <input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;
    const input = label.querySelector("input");
    const go = () => {
      const target = Math.max(1, Math.min(info.total, Number(input.value) || info.current));
      const delta = target - info.current;
      if (!delta) return;
      const button = delta > 0 ? next : prev;
      let remaining = Math.abs(delta);
      input.disabled = true;
      const timer = setInterval(() => {
        if (remaining <= 0 || button.disabled) {
          clearInterval(timer);
          schedule();
          return;
        }
        button.click();
        remaining -= 1;
      }, 30);
    };
    input.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); go(); } });
    input.addEventListener("change", go);
  }

  function findRoot(anchor, fallbackSelector = ".card") {
    return anchor?.closest?.("[role=dialog],.comparison-link-modal-card,.modal-card,.updates-card-section,.card,details,section") || anchor?.closest?.(fallbackSelector) || null;
  }

  function normalizePageSize(root, selectId) {
    const select = selectId ? byId(selectId) : [...root.querySelectorAll("select")].find(node => /itens por página|linhas por página/i.test(node.parentElement?.textContent || ""));
    if (!select) return;
    addFiveOption(select);
    const wrap = select.parentElement;
    wrap?.classList.add("ss-page-size");
    [...(wrap?.querySelectorAll("label,span,div") || [])].forEach(node => {
      if (/^linhas por página$/i.test(normalize(node.textContent))) node.textContent = "Itens por página";
    });
  }

  function normalizePagination(root, labelId, prevId, nextId) {
    let label = labelId ? byId(labelId) : [...root.querySelectorAll("span,.badge,div")].find(node => pageInfo(node));
    if (!label) return;
    const row = label.parentElement;
    let prev = prevId ? byId(prevId) : [...(row?.querySelectorAll("button") || [])].find(button => /anterior/i.test(button.textContent));
    let next = nextId ? byId(nextId) : [...(row?.querySelectorAll("button") || [])].find(button => /próxima|proxima/i.test(button.textContent));
    if (!prev || !next) {
      const vicinity = row?.parentElement || root;
      prev ||= [...vicinity.querySelectorAll("button")].find(button => /anterior/i.test(button.textContent));
      next ||= [...vicinity.querySelectorAll("button")].find(button => /próxima|proxima/i.test(button.textContent));
    }
    if (!prev || !next) return;
    const pagination = label.parentElement;
    pagination?.classList.add("ss-pagination");
    installJump(label, prev, next);
  }

  function normalizeMeta(root, resultId, pageSizeId) {
    const result = resultId ? byId(resultId) : null;
    const pageSize = pageSizeId ? byId(pageSizeId) : null;
    const candidate = result?.parentElement;
    if (candidate && pageSize && candidate.contains(pageSize)) candidate.classList.add("ss-meta-row");
    else if (result && pageSize) {
      const common = result.parentElement?.parentElement;
      if (common?.contains(pageSize)) common.classList.add("ss-meta-row");
    }
  }

  function normalizeSelection(root) {
    const known = root.querySelector(".comparison-bulk-toolbar") || byId("updates_working_controls");
    if (known && root.contains(known)) known.classList.add("ss-selection-zone");
  }

  function normalizeFilterZones(root, selectors = []) {
    selectors.forEach(selector => root.querySelectorAll(selector).forEach(node => node.classList.add("ss-filter-zone")));
    root.querySelectorAll("input[type=search]").forEach(input => {
      const zone = input.closest(".comparison-filter-grid,.comparison-actions-grid,.form-grid,[class*=filter-grid]") || input.parentElement?.parentElement;
      if (zone && root.contains(zone) && zone.children.length <= 12) zone.classList.add("ss-filter-zone");
    });
  }

  function standardize(spec) {
    const anchor = byId(spec.anchor);
    const root = spec.root ? byId(spec.root) : findRoot(anchor);
    if (!root) return;
    root.classList.add("search-system-standard");
    root.dataset.searchSystem = spec.key;
    normalizeFilterZones(root, spec.filterSelectors || []);
    normalizeSelection(root);
    normalizePageSize(root, spec.pageSize);
    normalizeMeta(root, spec.result, spec.pageSize);
    normalizePagination(root, spec.pageLabel, spec.prev, spec.next);
    const resultNode = spec.resultList ? byId(spec.resultList) : null;
    resultNode?.parentElement?.classList.add("ss-result-list");
  }

  function standardizeComparison() {
    const root = byId("comparison_results_card");
    if (root) {
      standardize({key:"comparison",anchor:"comparison_page_size",root:"comparison_results_card",pageSize:"comparison_page_size",result:"comparison_result_meta",pageLabel:"comparison_page_label",prev:"comparison_prev_btn",next:"comparison_next_btn",resultList:"comparison_rows"});
    }
    const toolbar = byId("tab_panel_comparacao")?.querySelector(".comparison-toolbar");
    if (toolbar) {
      toolbar.classList.add("search-system-standard");
      toolbar.querySelectorAll(".comparison-filter-grid,.comparison-actions-grid").forEach(node => node.classList.add("ss-filter-zone"));
    }
  }

  function standardizePluginTemaManager() {
    const anchor = byId("plugintema_manage_search");
    const root = findRoot(anchor);
    if (!root) return;
    root.classList.add("search-system-standard");
    normalizeFilterZones(root, []);
    normalizePageSize(root, "plugintema_manage_page_size");
    normalizeMeta(root, "plugintema_manage_range", "plugintema_manage_page_size");
    normalizePagination(root, "plugintema_manage_page_status", "plugintema_manage_prev", "plugintema_manage_next");
    byId("plugintema_manage_rows")?.parentElement?.classList.add("ss-result-list");
  }

  function standardizeCatalogPreview() {
    const anchor = byId("catalogos_preview_search");
    const root = findRoot(anchor);
    if (!root) return;
    root.classList.add("search-system-standard");
    normalizeFilterZones(root, []);
    normalizePageSize(root, "catalog_preview_page_size");
    const labels = [...root.querySelectorAll("span,.badge,div")].filter(node => pageInfo(node));
    labels.forEach(label => {
      const row = label.parentElement;
      const buttons = [...(row?.querySelectorAll("button") || [])];
      const prev = buttons.find(button => /anterior/i.test(button.textContent));
      const next = buttons.find(button => /próxima|proxima/i.test(button.textContent));
      if (prev && next) { row.classList.add("ss-pagination"); installJump(label, prev, next); }
    });
  }

  function standardizeAll() {
    standardizeComparison();
    standardize({key:"updates-waiting",anchor:"updates_status_filter",pageSize:"updates_page_size",result:"updates_found_count",pageLabel:"updates_page_label",prev:"updates_prev_page",next:"updates_next_page",resultList:"updates_jobs",filterSelectors:["#updates_working_controls"]});
    standardize({key:"updates-queue",anchor:"updates_queue_search",pageSize:"updates_queue_page_size",result:"updates_queue_found_count",pageLabel:"updates_queue_page",prev:"updates_queue_prev",next:"updates_queue_next",resultList:"updates_queue_jobs",filterSelectors:["#updates_queue_list_controls"]});
    standardize({key:"updates-history",anchor:"updates_history_search",pageSize:"updates_history_page_size",result:"updates_history_result_meta",pageLabel:"updates_history_page",prev:"updates_history_prev",next:"updates_history_next",resultList:"updates_history",filterSelectors:["#updates_history_controls"]});
    standardizePluginTemaManager();
    standardizeCatalogPreview();
  }

  let timer = null;
  function schedule() { clearTimeout(timer); timer = setTimeout(standardizeAll, 70); }
  const observer = new MutationObserver(schedule);
  const start = () => { observer.observe(document.body,{childList:true,subtree:true,characterData:true}); standardizeAll(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",start,{once:true}); else start();
})();
