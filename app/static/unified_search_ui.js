(() => {
  "use strict";

  const STYLE_ID = "unified-search-ui-style";
  const PAGE_SIZE_VALUES = [5, 10, 25, 50, 100, 250];

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .u-search-system{--u-gap:12px;--u-control-h:46px;--u-border:#2a2a32;--u-panel:#111114;--u-panel-2:#151519;--u-muted:#a7a7b2;--u-accent:#7c3aed;--u-success:#27c997}
    .u-search-system .u-search-filter-zone,
    .u-search-filter-zone{display:grid!important;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--u-gap)!important;align-items:end!important;background:var(--u-panel)!important;border:1px solid var(--u-border)!important;border-radius:14px!important;padding:14px!important;margin:0 0 12px!important}
    .u-search-system .field,.u-search-filter-zone .field{min-width:0!important;margin:0!important;gap:6px!important}
    .u-search-system .field label,.u-search-filter-zone label{font-size:12px!important;font-weight:700!important;color:#d7d7df!important;margin:0!important}
    .u-search-system input[type="search"],.u-search-system input[type="text"],.u-search-system input[type="number"],.u-search-system select,
    .u-search-filter-zone input[type="search"],.u-search-filter-zone input[type="text"],.u-search-filter-zone input[type="number"],.u-search-filter-zone select{min-height:var(--u-control-h)!important;height:var(--u-control-h)!important;border-radius:10px!important;border:1px solid var(--u-border)!important;background:#09090b!important;padding:0 14px!important}
    .u-search-system button,.u-search-filter-zone button{min-height:var(--u-control-h);border-radius:10px!important}
    .u-search-filter-zone > .field,.u-search-filter-zone > label,.u-search-filter-zone > input,.u-search-filter-zone > select{grid-column:span 3}
    .u-search-filter-zone .comparison-search-field{grid-column:span 4}
    .u-search-filter-zone .comparison-run-button{grid-column:span 5}
    .u-search-filter-zone .comparison-reload-button{grid-column:span 3}
    .u-search-system .comparison-bulk-toolbar,.u-search-system [id*="working_controls"]{border:1px solid var(--u-border)!important;border-radius:12px!important;background:var(--u-panel-2)!important;padding:12px!important;gap:10px!important}
    .u-search-system .listing-meta-row,.u-search-system [id$="_result_meta"]{color:var(--u-muted)}
    .u-search-system .listing-meta-row{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;margin:12px 0 10px!important;min-height:46px}
    .u-search-system .listing-page-size,.u-search-system .u-page-size-wrap{display:flex!important;align-items:center!important;justify-content:flex-end!important;gap:10px!important;margin-left:auto!important;white-space:nowrap}
    .u-search-system .listing-page-size select,.u-search-system .u-page-size-wrap select{width:92px!important;min-width:92px!important;height:42px!important;min-height:42px!important;padding:0 32px 0 12px!important}
    .u-search-system .listing-pagination,.u-search-system .u-pagination-row{display:grid!important;grid-template-columns:minmax(140px,1fr) auto minmax(140px,1fr)!important;gap:12px!important;align-items:center!important;margin:0 0 14px!important}
    .u-search-system .listing-pagination > button,.u-search-system .u-pagination-row > button{width:100%!important;min-height:48px!important}
    .u-search-system .u-page-jump{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:34px;padding:4px 10px;border:1px solid var(--u-border);border-radius:999px;background:#16161a;color:#fff;font-size:12px;font-weight:700;white-space:nowrap}
    .u-search-system .u-page-jump input{width:54px!important;min-width:54px!important;height:28px!important;min-height:28px!important;padding:0 6px!important;text-align:center!important;border-radius:7px!important;background:#09090b!important;border:1px solid #3b3b45!important;font-weight:800!important;color:#fff!important}
    .u-search-system .u-page-jump input::-webkit-inner-spin-button,.u-search-system .u-page-jump input::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
    .u-search-system .u-selection-toolbar{display:flex!important;align-items:center!important;gap:10px!important;flex-wrap:wrap!important;border:1px solid var(--u-border)!important;border-radius:12px!important;background:var(--u-panel-2)!important;padding:12px!important;margin:10px 0 12px!important}
    .u-search-system .u-selection-toolbar .badge{margin-left:auto}
    .u-search-system table,.u-search-system .update-job,.u-search-system .update-queue-row{border-color:#292931!important}
    .u-search-system .u-result-zone{border-top:1px solid #25252c;padding-top:4px}
    .u-search-system .small[id*="result"],.u-search-system .small[id*="found"]{font-weight:600;color:#c8c8d1!important}
    .u-search-system [data-unified-action-zone]{display:flex!important;gap:10px!important;align-items:end!important;flex-wrap:wrap!important}
    @media(max-width:1100px){.u-search-filter-zone > .field,.u-search-filter-zone > label,.u-search-filter-zone > input,.u-search-filter-zone > select,.u-search-filter-zone .comparison-search-field,.u-search-filter-zone .comparison-run-button,.u-search-filter-zone .comparison-reload-button{grid-column:span 6}}
    @media(max-width:720px){.u-search-filter-zone{grid-template-columns:1fr!important}.u-search-filter-zone > *{grid-column:1!important}.u-search-system .listing-meta-row{align-items:flex-start!important;flex-direction:column!important}.u-search-system .listing-page-size,.u-search-system .u-page-size-wrap{margin-left:0!important}.u-search-system .listing-pagination,.u-search-system .u-pagination-row{grid-template-columns:1fr 1fr!important}.u-search-system .u-page-jump{grid-column:1 / -1;grid-row:1}.u-search-system .u-selection-toolbar .badge{margin-left:0}}
  `;
  if (!document.getElementById(STYLE_ID)) document.head.appendChild(style);

  const byId = (id) => document.getElementById(id);
  const normalize = (value) => String(value ?? "").trim();
  const text = (node) => normalize(node?.textContent).toLowerCase();

  function closestUseful(node) {
    return node?.closest?.("[role='dialog'], .comparison-link-modal-card, .modal-card, .card, .updates-card-section, section, details") || node?.parentElement || null;
  }

  function findByHeading(pattern) {
    const nodes = [...document.querySelectorAll("h1,h2,h3,h4,.section-title,summary,strong")];
    const heading = nodes.find(node => pattern.test(text(node)));
    return closestUseful(heading);
  }

  function addPageSizeOption(select) {
    if (!select || select.tagName !== "SELECT") return;
    const current = normalize(select.value);
    const numericOptions = [...select.options].every(option => /^\d+$/.test(normalize(option.value)));
    if (!numericOptions) return;
    PAGE_SIZE_VALUES.forEach(value => {
      if (![...select.options].some(option => Number(option.value) === value)) {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = String(value);
        select.appendChild(option);
      }
    });
    [...select.options].sort((a,b) => Number(a.value) - Number(b.value)).forEach(option => select.appendChild(option));
    if ([...select.options].some(option => option.value === current)) select.value = current;
  }

  function normalizePageSizeLabels(root) {
    root.querySelectorAll("label,span,div").forEach(node => {
      if (/^linhas por página$/i.test(normalize(node.textContent))) node.textContent = "Itens por página";
    });
    root.querySelectorAll("select").forEach(select => {
      const label = root.querySelector(`label[for='${CSS.escape(select.id || "")}']`);
      const nearby = normalize(select.parentElement?.textContent);
      if (/itens por página|linhas por página/i.test(label?.textContent || nearby)) addPageSizeOption(select);
    });
  }

  function currentPageInfo(label) {
    const match = normalize(label?.textContent).match(/Página\s+(\d+)\s+de\s+(\d+)/i);
    return match ? {current:Number(match[1]), total:Number(match[2])} : null;
  }

  function installPageJump(root) {
    const labels = [...root.querySelectorAll("span,.badge,div")].filter(node => /^Página\s+\d+\s+de\s+\d+$/i.test(normalize(node.textContent)));
    labels.forEach(label => {
      if (label.dataset.unifiedPageJump === "1") return;
      const info = currentPageInfo(label);
      if (!info) return;
      const row = label.parentElement;
      if (!row) return;
      const buttons = [...row.querySelectorAll("button")];
      const prev = buttons.find(button => /anterior/i.test(button.textContent));
      const next = buttons.find(button => /próxima|proxima/i.test(button.textContent));
      if (!prev || !next) return;
      row.classList.add("u-pagination-row");
      label.dataset.unifiedPageJump = "1";
      label.classList.add("u-page-jump");
      label.innerHTML = `Página <input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;
      const input = label.querySelector("input");
      let jumping = false;
      const go = () => {
        if (jumping) return;
        const target = Math.max(1, Math.min(info.total, Number(input.value) || info.current));
        const latest = currentPageInfo({textContent:`Página ${input.defaultValue || info.current} de ${info.total}`});
        const parseLive = () => {
          const candidates = [...row.parentElement.querySelectorAll(".u-page-jump")];
          const live = candidates[0];
          const liveInput = live?.querySelector("input");
          return Number(liveInput?.value || latest?.current || info.current);
        };
        let remaining = Math.abs(target - parseLive());
        if (!remaining) return;
        const direction = target > parseLive() ? "next" : "prev";
        jumping = true;
        const timer = setInterval(() => {
          if (remaining <= 0) { clearInterval(timer); jumping = false; return; }
          const liveRoot = root.isConnected ? root : document;
          const liveRows = [...liveRoot.querySelectorAll(".u-pagination-row")];
          const liveRow = liveRows.find(candidate => candidate.contains(label) || candidate.querySelector(".u-page-jump"));
          const liveButtons = [...(liveRow || row).querySelectorAll("button")];
          const button = liveButtons.find(btn => direction === "next" ? /próxima|proxima/i.test(btn.textContent) : /anterior/i.test(btn.textContent));
          if (!button || button.disabled) { clearInterval(timer); jumping = false; return; }
          button.click();
          remaining -= 1;
        }, 35);
      };
      input.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); go(); } });
      input.addEventListener("change", go);
    });
  }

  function markSelection(root) {
    const selectionNodes = [...root.querySelectorAll("input[type='checkbox']")].filter(input => /select|selecion/i.test(input.id || input.getAttribute("aria-label") || input.parentElement?.textContent || ""));
    if (!selectionNodes.length) return;
    const candidates = [...root.querySelectorAll("div")].filter(node => /selecionar página|selecionar todo|selecionados/i.test(node.textContent || ""));
    const toolbar = candidates.sort((a,b) => (a.textContent?.length || 0) - (b.textContent?.length || 0))[0];
    toolbar?.classList.add("u-selection-toolbar");
  }

  function markFilterZones(root) {
    const known = [
      ".comparison-filter-grid", ".comparison-actions-grid", ".comparison-toolbar",
      "#updates_working_controls", "#updates_queue_controls", "#updates_history_controls",
      ".plugintema-catalog-manager-filters", ".catalog-filters", ".catalog-preview-filters"
    ];
    known.forEach(selector => root.querySelectorAll(selector).forEach(node => node.classList.add("u-search-filter-zone")));

    const searchInputs = [...root.querySelectorAll("input[type='search']")];
    searchInputs.forEach(input => {
      let zone = input.closest(".form-grid,.comparison-filter-grid,.comparison-toolbar,.updates-filter-grid,.catalog-filter-grid");
      if (!zone) {
        const parent = input.parentElement;
        zone = parent?.parentElement;
      }
      if (zone && root.contains(zone) && zone.children.length <= 12) zone.classList.add("u-search-filter-zone");
    });
  }

  function markMetaAndPagination(root) {
    root.querySelectorAll(".listing-meta-row").forEach(node => node.classList.add("u-result-zone"));
    [...root.querySelectorAll("select")].forEach(select => {
      const parentText = normalize(select.parentElement?.textContent);
      if (/itens por página|linhas por página/i.test(parentText)) select.parentElement?.classList.add("u-page-size-wrap");
    });
  }

  function unifyRoot(root, key) {
    if (!root) return;
    root.classList.add("u-search-system");
    root.dataset.unifiedSearchSystem = key;
    normalizePageSizeLabels(root);
    markFilterZones(root);
    markSelection(root);
    markMetaAndPagination(root);
    installPageJump(root);
  }

  function locateSystems() {
    const systems = [];

    const comparison = byId("comparison_results_card");
    if (comparison) {
      const panel = byId("tab_panel_comparacao");
      const toolbar = panel?.querySelector(".comparison-toolbar");
      if (toolbar) toolbar.classList.add("u-search-system", "u-search-filter-zone");
      systems.push([comparison, "comparison-results"]);
    }

    const waitingAnchor = byId("updates_status_filter") || byId("updates_search_filter");
    systems.push([closestUseful(waitingAnchor), "updates-waiting"]);

    const queueAnchor = byId("updates_queue_search") || byId("updates_queue_state_filter") || byId("updates_queue_page_size");
    systems.push([closestUseful(queueAnchor), "updates-queue"]);

    const historyAnchor = byId("updates_history_search") || byId("updates_history_status_filter") || byId("updates_history_page_size");
    systems.push([closestUseful(historyAnchor), "updates-history"]);

    const pluginManager = findByHeading(/gerenciar catálogos plugintema/i);
    systems.push([pluginManager, "plugintema-manager"]);

    const catalogModal = [...document.querySelectorAll("[role='dialog'],.modal-card,.comparison-link-modal-card")].find(node => {
      const content = text(node);
      return /catálogos/.test(content) && /buscar catálogos e contextos|buscar na prévia|atualizar catálogos/.test(content) && !/plugintema/.test(content);
    }) || findByHeading(/^catálogos$/i);
    systems.push([catalogModal, "catalog-manager"]);

    systems.forEach(([root,key]) => unifyRoot(root,key));
  }

  let scheduled = null;
  function schedule() {
    clearTimeout(scheduled);
    scheduled = setTimeout(locateSystems, 60);
  }

  document.addEventListener("change", event => {
    const target = event.target;
    if (target?.matches?.("select") && /itens por página|linhas por página/i.test(target.parentElement?.textContent || "")) schedule();
  });

  const observer = new MutationObserver(schedule);
  const start = () => {
    observer.observe(document.body, {childList:true, subtree:true, characterData:true});
    locateSystems();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
