(() => {
  "use strict";

  const STYLE_ID = "crapscraper-unified-search-style";
  const PAGE_SIZES = [5, 10, 25, 50, 100, 250];

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .cs-search-system{--cs-border:#292931;--cs-bg:#111114;--cs-bg2:#151519;--cs-muted:#9ca3af;--cs-control:46px}
    .cs-search-system .cs-filter-row{display:grid!important;grid-template-columns:repeat(12,minmax(0,1fr))!important;gap:12px!important;align-items:end!important;padding:14px!important;margin:0 0 14px!important;background:var(--cs-bg)!important;border:1px solid var(--cs-border)!important;border-radius:14px!important}
    .cs-search-system .cs-filter-row>.field,.cs-search-system .cs-filter-row>.cs-field,.cs-search-system .cs-filter-row>label{grid-column:span 3!important;min-width:0!important;margin:0!important}
    .cs-search-system .cs-filter-row>.cs-span-4{grid-column:span 4!important}
    .cs-search-system .cs-filter-row>.cs-span-6{grid-column:span 6!important}
    .cs-search-system .cs-filter-row>.cs-span-8{grid-column:span 8!important}
    .cs-search-system .cs-filter-row>.cs-action{grid-column:span 3!important;min-width:0!important}
    .cs-search-system .cs-filter-row label,.cs-search-system .cs-field-label{display:block!important;margin:0 0 6px!important;font-size:12px!important;font-weight:700!important;color:#d6d6df!important}
    .cs-search-system input[type=search],.cs-search-system input[type=text],.cs-search-system input[type=number],.cs-search-system select{min-height:var(--cs-control)!important;height:var(--cs-control)!important;border:1px solid var(--cs-border)!important;border-radius:10px!important;background:#09090b!important;color:#fff!important;padding:0 14px!important;min-width:0!important}
    .cs-search-system button{border-radius:10px!important}
    .cs-search-system .cs-meta-row{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;min-height:48px!important;margin:2px 0 10px!important;color:var(--cs-muted)!important}
    .cs-search-system .cs-result-count{font-weight:600!important;color:#c8c8d1!important}
    .cs-search-system .cs-page-size{display:flex!important;align-items:center!important;gap:10px!important;margin-left:auto!important;white-space:nowrap!important;color:var(--cs-muted)!important}
    .cs-search-system .cs-page-size select{width:92px!important;min-width:92px!important;height:42px!important;min-height:42px!important;padding:0 30px 0 12px!important}
    .cs-search-system .cs-pagination{display:grid!important;grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;gap:12px!important;align-items:center!important;margin:0 0 14px!important;width:100%!important}
    .cs-search-system .cs-pagination>button{width:100%!important;min-height:48px!important;margin:0!important}
    .cs-search-system .cs-page-jump{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:6px!important;min-height:36px!important;padding:4px 10px!important;background:#17171b!important;border:1px solid var(--cs-border)!important;border-radius:999px!important;color:#fff!important;font-size:12px!important;font-weight:800!important;white-space:nowrap!important}
    .cs-search-system .cs-page-jump input{width:58px!important;min-width:58px!important;height:28px!important;min-height:28px!important;padding:0 6px!important;text-align:center!important;border:1px solid #41414b!important;border-radius:7px!important;background:#09090b!important;color:#fff!important;font-size:12px!important;font-weight:800!important}
    .cs-search-system .cs-selection-row{display:flex!important;align-items:center!important;gap:10px!important;flex-wrap:wrap!important;padding:12px!important;margin:10px 0 12px!important;background:var(--cs-bg2)!important;border:1px solid var(--cs-border)!important;border-radius:12px!important}
    .cs-search-system .cs-selection-row .badge{margin-left:auto!important}
    .cs-search-system .cs-results-zone{border-top:1px solid #24242b!important;padding-top:2px!important}
    .cs-search-system table{border-color:#292931!important}
    .cs-search-system .cs-filter-row>.cs-action button{width:100%!important;min-height:var(--cs-control)!important}
    .cs-search-system .cs-filter-row>.cs-inline-actions{display:flex!important;align-items:end!important;gap:10px!important;grid-column:span 4!important}
    .cs-search-system .cs-filter-row>.cs-inline-actions button{min-height:var(--cs-control)!important;flex:1 1 auto!important}
    @media(max-width:1100px){
      .cs-search-system .cs-filter-row>.field,.cs-search-system .cs-filter-row>.cs-field,.cs-search-system .cs-filter-row>label,.cs-search-system .cs-filter-row>.cs-span-4,.cs-search-system .cs-filter-row>.cs-span-6,.cs-search-system .cs-filter-row>.cs-span-8,.cs-search-system .cs-filter-row>.cs-action,.cs-search-system .cs-filter-row>.cs-inline-actions{grid-column:span 6!important}
    }
    @media(max-width:720px){
      .cs-search-system .cs-filter-row{grid-template-columns:1fr!important}
      .cs-search-system .cs-filter-row>*{grid-column:1!important}
      .cs-search-system .cs-meta-row{align-items:flex-start!important;flex-direction:column!important}
      .cs-search-system .cs-page-size{margin-left:0!important}
      .cs-search-system .cs-pagination{grid-template-columns:1fr 1fr!important}
      .cs-search-system .cs-page-jump{grid-column:1/-1!important;grid-row:1!important}
      .cs-search-system .cs-selection-row .badge{margin-left:0!important}
    }
  `;

  const oldStyle = document.getElementById(STYLE_ID);
  if (oldStyle) oldStyle.remove();
  document.head.appendChild(style);

  const byId = id => document.getElementById(id);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function clearPreviousAttempt() {
    document.querySelectorAll(".search-system-standard,.ss-filter-zone,.ss-selection-zone,.ss-meta-row,.ss-page-size,.ss-pagination,.ss-page-jump,.ss-result-list").forEach(node => {
      node.classList.remove("search-system-standard","ss-filter-zone","ss-selection-zone","ss-meta-row","ss-page-size","ss-pagination","ss-page-jump","ss-result-list");
    });
  }

  function findSystemRoot(anchor) {
    return anchor?.closest?.("[role='dialog'],.comparison-link-modal-card,.modal-card,.updates-card-section,.card,details,section") || anchor?.parentElement || null;
  }

  function fieldWrapper(node) {
    if (!node) return null;
    return node.closest(".field") || node.parentElement;
  }

  function actionWrapper(node) {
    if (!node) return null;
    if (node.parentElement?.children?.length === 1) return node.parentElement;
    const wrapper = document.createElement("div");
    wrapper.className = "cs-action";
    node.parentElement?.insertBefore(wrapper, node);
    wrapper.appendChild(node);
    return wrapper;
  }

  function ensurePageSizeOption(select) {
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

  function ensureSystem(root, key) {
    if (!root) return null;
    root.classList.add("cs-search-system");
    root.dataset.csSearchSystem = key;
    return root;
  }

  function ensureFilterRow(root, key, controls, options = {}) {
    if (!root) return null;
    let row = root.querySelector(`.cs-filter-row[data-cs-row='${key}']`);
    if (!row) {
      row = document.createElement("div");
      row.className = "cs-filter-row";
      row.dataset.csRow = key;
      const anchor = controls.map(item => item?.node).find(Boolean);
      const insertBefore = options.insertBefore || anchor?.parentElement || root.firstChild;
      if (insertBefore && insertBefore.parentElement === root) root.insertBefore(row, insertBefore);
      else root.insertBefore(row, root.firstChild);
    }

    controls.forEach(item => {
      if (!item?.node) return;
      let wrapper = item.kind === "action" ? actionWrapper(item.node) : fieldWrapper(item.node);
      if (!wrapper) return;
      wrapper.classList.add("cs-field");
      if (item.span) wrapper.classList.add(`cs-span-${item.span}`);
      if (item.kind === "action") wrapper.classList.add("cs-action");
      row.appendChild(wrapper);
    });
    return row;
  }

  function ensureInlineActions(row, nodes) {
    const valid = nodes.filter(Boolean);
    if (!row || !valid.length) return;
    let wrap = row.querySelector(".cs-inline-actions");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "cs-inline-actions";
      row.appendChild(wrap);
    }
    valid.forEach(node => wrap.appendChild(node));
  }

  function normalizePageSize(root, selectId) {
    const select = byId(selectId);
    if (!root || !select) return null;
    ensurePageSizeOption(select);
    let wrap = select.closest(".cs-page-size");
    if (!wrap) {
      const originalParent = select.parentElement;
      wrap = document.createElement("div");
      wrap.className = "cs-page-size";
      const existingLabel = originalParent ? [...originalParent.children].find(node => node !== select && /itens por página|linhas por página/i.test(normalize(node.textContent))) : null;
      const label = existingLabel || document.createElement("span");
      label.textContent = "Itens por página";
      label.classList.add("small");
      if (originalParent) originalParent.insertBefore(wrap, select);
      wrap.appendChild(label);
      wrap.appendChild(select);
    } else {
      const label = [...wrap.children].find(node => node !== select);
      if (label) label.textContent = "Itens por página";
    }
    return wrap;
  }

  function parsePageLabel(label) {
    if (!label) return null;
    const fromDataset = Number(label.dataset.csCurrent || 0);
    const totalDataset = Number(label.dataset.csTotal || 0);
    const raw = normalize(label.textContent);
    const match = raw.match(/Página\s+(\d+)\s+de\s+(\d+)/i);
    if (match) return { current:Number(match[1]), total:Number(match[2]) };
    if (fromDataset > 0 && totalDataset > 0) return { current:fromDataset, total:totalDataset };
    return null;
  }

  function fallbackJump(prevId, nextId, target, current) {
    const direction = target > current ? nextId : prevId;
    let remaining = Math.abs(target - current);
    const step = () => {
      if (remaining <= 0) return;
      const button = byId(direction);
      if (!button || button.disabled) return;
      button.click();
      remaining -= 1;
      if (remaining > 0) window.setTimeout(step, 35);
    };
    step();
  }

  function installPageJump(label, spec) {
    const info = parsePageLabel(label);
    if (!label || !info) return;
    const existingInput = label.querySelector("input[data-cs-page-input]");
    if (existingInput && Number(label.dataset.csCurrent) === info.current && Number(label.dataset.csTotal) === info.total) return;

    label.dataset.csCurrent = String(info.current);
    label.dataset.csTotal = String(info.total);
    label.classList.add("cs-page-jump");
    label.innerHTML = `Página <input data-cs-page-input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;
    const input = label.querySelector("input[data-cs-page-input]");

    const go = () => {
      const target = Math.max(1, Math.min(info.total, Number(input.value) || info.current));
      if (target === info.current) return;
      const api = window.__crapscraperPagination;
      const setter = api && typeof api[spec.setter] === "function" ? api[spec.setter] : null;
      if (setter) setter(target);
      else fallbackJump(spec.prev, spec.next, target, info.current);
    };

    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        event.preventDefault();
        go();
      }
    });
    input.addEventListener("change", go);
  }

  function ensurePagination(root, spec) {
    const prev = byId(spec.prev), label = byId(spec.label), next = byId(spec.next);
    if (!root || !prev || !label || !next) return null;

    let row = root.querySelector(`.cs-pagination[data-cs-pagination='${spec.key}']`);
    if (!row) {
      row = document.createElement("div");
      row.className = "cs-pagination";
      row.dataset.csPagination = spec.key;
      const parent = prev.parentElement;
      if (parent) parent.insertBefore(row, prev);
      else root.appendChild(row);
    }
    row.append(prev, label, next);
    installPageJump(label, spec);
    return row;
  }

  function ensureMetaRow(root, key, resultId, pageSizeId, paginationRow) {
    if (!root) return null;
    const result = byId(resultId);
    const pageSize = normalizePageSize(root, pageSizeId);
    if (!result && !pageSize) return null;

    let row = root.querySelector(`.cs-meta-row[data-cs-meta='${key}']`);
    if (!row) {
      row = document.createElement("div");
      row.className = "cs-meta-row";
      row.dataset.csMeta = key;
      if (paginationRow?.parentElement) paginationRow.parentElement.insertBefore(row, paginationRow);
      else root.appendChild(row);
    }
    if (result) {
      result.classList.add("cs-result-count");
      row.appendChild(result);
    }
    if (pageSize) row.appendChild(pageSize);
    return row;
  }

  function markSelection(root, selector) {
    const row = selector ? root?.querySelector(selector) : null;
    row?.classList.add("cs-selection-row");
  }

  function markResults(resultId) {
    const node = byId(resultId);
    node?.parentElement?.classList.add("cs-results-zone");
  }

  function setupComparison() {
    const panel = byId("tab_panel_comparacao");
    const results = byId("comparison_results_card");
    if (!panel || !results) return;
    ensureSystem(panel, "comparison");
    ensureSystem(results, "comparison-results");

    const filterRow = ensureFilterRow(panel, "comparison-filters", [
      {node:byId("comparison_status_filter")},
      {node:byId("comparison_decision_filter")},
      {node:byId("comparison_query"), span:4},
      {node:byId("comparison_candidate_filter")},
    ]);
    const actionRow = ensureFilterRow(panel, "comparison-actions", [
      {node:byId("comparison_score_min")},
      {node:byId("comparison_score_max")},
      {node:byId("comparison_run_btn"), kind:"action", span:4},
      {node:byId("comparison_reload_sources_btn"), kind:"action"},
    ], {insertBefore:filterRow?.nextSibling});
    if (filterRow && actionRow && actionRow.previousElementSibling !== filterRow) filterRow.after(actionRow);

    markSelection(results, ".comparison-bulk-toolbar");
    const pagination = ensurePagination(results, {key:"comparison",label:"comparison_page_label",prev:"comparison_prev_btn",next:"comparison_next_btn",setter:"comparison"});
    ensureMetaRow(results,"comparison","comparison_result_meta","comparison_page_size",pagination);
    markResults("comparison_rows");
  }

  function setupUpdatesWaiting() {
    const anchor = byId("updates_status_filter") || byId("updates_search_filter");
    const root = ensureSystem(findSystemRoot(anchor), "updates-waiting");
    if (!root) return;

    const row = ensureFilterRow(root,"updates-waiting-filters",[
      {node:byId("updates_status_filter")},
      {node:byId("updates_type_filter")},
      {node:byId("updates_search_filter") || byId("updates_search")},
      {node:byId("updates_version_filter")},
      {node:byId("updates_relationship_filter")},
    ]);
    const clear = byId("updates_clear_filters");
    if (row && clear) ensureInlineActions(row,[clear]);

    const pagination = ensurePagination(root,{key:"updates-waiting",label:"updates_page_label",prev:"updates_prev_page",next:"updates_next_page",setter:"updatesWaiting"});
    ensureMetaRow(root,"updates-waiting","updates_found_count","updates_page_size",pagination);
    markSelection(root,"#updates_bulk_actions");
    markResults("updates_jobs");
  }

  function setupUpdatesQueue() {
    const anchor = byId("updates_queue_search");
    const root = ensureSystem(findSystemRoot(anchor), "updates-queue");
    if (!root) return;

    ensureFilterRow(root,"updates-queue-filters",[
      {node:byId("updates_queue_search"), span:8},
      {node:byId("updates_queue_status_filter"), span:4},
    ]);
    const pagination = ensurePagination(root,{key:"updates-queue",label:"updates_queue_page",prev:"updates_queue_prev",next:"updates_queue_next",setter:"updatesQueue"});
    ensureMetaRow(root,"updates-queue","updates_queue_found_count","updates_queue_page_size",pagination);
    markResults("updates_queue_jobs");
  }

  function setupUpdatesHistory() {
    const anchor = byId("updates_history_search");
    const root = ensureSystem(findSystemRoot(anchor), "updates-history");
    if (!root) return;

    const row = ensureFilterRow(root,"updates-history-filters",[
      {node:byId("updates_history_search"), span:6},
      {node:byId("updates_history_status_filter"), span:4},
    ]);
    if (row) ensureInlineActions(row,[byId("updates_history_download"),byId("updates_history_delete")]);

    const pagination = ensurePagination(root,{key:"updates-history",label:"updates_history_page",prev:"updates_history_prev",next:"updates_history_next",setter:"updatesHistory"});
    ensureMetaRow(root,"updates-history","updates_history_result_meta","updates_history_page_size",pagination);
    markResults("updates_history");
  }

  function setupPluginTemaManager() {
    const anchor = byId("plugintema_manage_search");
    const root = ensureSystem(findSystemRoot(anchor), "plugintema-manager");
    if (!root) return;

    const row = ensureFilterRow(root,"plugintema-manager-filters",[
      {node:byId("plugintema_manage_catalog")},
      {node:byId("plugintema_manage_search")},
      {node:byId("plugintema_manage_type")},
      {node:byId("plugintema_manage_status")},
    ]);
    if (row) ensureInlineActions(row,[byId("plugintema_manage_download"),byId("plugintema_manage_delete")]);

    const pagination = ensurePagination(root,{key:"plugintema-manager",label:"plugintema_manage_page_status",prev:"plugintema_manage_prev",next:"plugintema_manage_next",setter:"pluginTemaManager"});
    ensureMetaRow(root,"plugintema-manager","plugintema_manage_range","plugintema_manage_page_size",pagination);
    markResults("plugintema_manage_rows");
  }

  function setupCatalogPreview() {
    const anchor = byId("catalogos_preview_search");
    const root = ensureSystem(findSystemRoot(anchor), "catalog-preview");
    if (!root) return;

    ensureFilterRow(root,"catalog-preview-filters",[
      {node:byId("catalogos_preview_search"), span:12},
    ]);

    const labels = [...root.querySelectorAll("span,.badge,div")].filter(node => /Página\s+\d+\s+de\s+\d+/i.test(normalize(node.textContent)));
    const label = labels[0];
    if (!label) return;
    if (!label.id) label.id = "catalog_preview_dynamic_page_label";
    const vicinity = label.parentElement || root;
    const buttons = [...vicinity.querySelectorAll("button")];
    let prev = buttons.find(button => /anterior/i.test(button.textContent));
    let next = buttons.find(button => /próxima|proxima/i.test(button.textContent));
    if (!prev || !next) {
      const allButtons = [...root.querySelectorAll("button")];
      prev ||= allButtons.find(button => /anterior/i.test(button.textContent));
      next ||= allButtons.find(button => /próxima|proxima/i.test(button.textContent));
    }
    if (!prev || !next) return;
    if (!prev.id) prev.id = "catalog_preview_dynamic_prev";
    if (!next.id) next.id = "catalog_preview_dynamic_next";

    const pagination = ensurePagination(root,{key:"catalog-preview",label:label.id,prev:prev.id,next:next.id,setter:"catalogPreview"});
    const resultNode = [...root.querySelectorAll(".small,div")].find(node => /Mostrando\s+\d+.*de\s+\d+/i.test(normalize(node.textContent)) && !node.contains(label));
    if (resultNode && !resultNode.id) resultNode.id = "catalog_preview_dynamic_result";
    ensureMetaRow(root,"catalog-preview",resultNode?.id || "catalog_preview_dynamic_result","catalog_preview_page_size",pagination);
  }

  function standardizeAll() {
    clearPreviousAttempt();
    setupComparison();
    setupUpdatesWaiting();
    setupUpdatesQueue();
    setupUpdatesHistory();
    setupPluginTemaManager();
    setupCatalogPreview();
  }

  let timer = null;
  let observer = null;
  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(standardizeAll, 80);
  }

  function start() {
    standardizeAll();
    observer = new MutationObserver(schedule);
    observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",start,{once:true});
  else start();
})();
