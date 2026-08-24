(() => {
  "use strict";

  if (window.__crapScraperQueueStandardizationV1Installed) return;
  window.__crapScraperQueueStandardizationV1Installed = true;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const $$ = (selector, root = document) => Array.from(root?.querySelectorAll?.(selector) || []);
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  const updateSelection = new Set();
  const additionSelection = new Set();
  let normalizing = false;
  let scheduled = 0;
  let additionSummaryTimer = 0;
  let additionSummaryBusy = false;
  let additionSummaryCache = null;

  const UPDATE_RECOVERABLE = new Set(["error", "failed", "blocked", "canceled", "interrupted"]);
  const UPDATE_PROGRESS = Object.freeze({
    approved: 8, validating: 18, downloading: 30, staging: 42, prepared: 50, planned: 58,
    plan_ready: 65, queued: 70, executing: 76, installing: 82, filesystem_validated: 86,
    updating_wordpress: 90, validating_wordpress: 94, validated: 97, dry_run_ready: 98,
    completed: 100, blocked: 100, error: 100, failed: 100, interrupted: 100,
    canceled: 100, rollback_required: 100, rolling_back: 70, rolled_back: 100,
  });

  function installStyles() {
    if ($("#cs-queue-standardization-v1-style")) return;
    const style = document.createElement("style");
    style.id = "cs-queue-standardization-v1-style";
    style.textContent = `
      /* Fila v1: Atualizar e Adicionar compartilham a mesma anatomia visual. */
      #tab_panel_atualizacoes .cs-queue-v1,
      #tab_panel_adicoes .cs-queue-v1{
        width:100%!important;min-width:0!important;padding:16px 18px!important;
        border:1px solid var(--line)!important;border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;box-sizing:border-box!important;overflow:visible!important;
      }
      #tab_panel_atualizacoes .cs-queue-v1>.cs-queue-v1-header,
      #tab_panel_adicoes .cs-queue-v1>.cs-queue-v1-header{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-height:34px!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;box-shadow:none!important;list-style:none!important;cursor:pointer!important;
      }
      #tab_panel_adicoes .cs-queue-v1>.cs-queue-v1-header::-webkit-details-marker{display:none!important}
      #tab_panel_atualizacoes .cs-queue-v1-header .standard-update-accordion-toggle-copy,
      #tab_panel_adicoes .cs-queue-v1-header .cs-op-summary-left{display:inline-flex!important;align-items:center!important;gap:8px!important;min-width:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-header .standard-update-accordion-title,
      #tab_panel_adicoes .cs-queue-v1-header .section-title{font-size:17px!important;font-weight:850!important;line-height:1.2!important;margin:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-summary,
      #tab_panel_adicoes .cs-queue-v1-summary{margin-left:auto!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-queue-v1.is-collapsed>.cs-queue-v1-body{display:none!important}
      #tab_panel_adicoes .cs-queue-v1:not([open])>.cs-queue-v1-body{display:none!important}
      #tab_panel_atualizacoes .cs-queue-v1-body,
      #tab_panel_adicoes .cs-queue-v1-body{display:grid!important;gap:12px!important;width:100%!important;min-width:0!important;margin:8px 0 0!important;padding:0!important}

      /* Descrição + gerenciador */
      #tab_panel_atualizacoes .cs-queue-v1-management,
      #tab_panel_adicoes .cs-queue-v1-management{
        display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;gap:18px!important;align-items:center!important;
        width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-description,
      #tab_panel_adicoes .cs-queue-v1-description{margin:0!important;color:var(--text-muted)!important;font-size:11px!important;line-height:1.5!important}
      #tab_panel_atualizacoes .cs-queue-v1-management .catalog-management-button,
      #tab_panel_adicoes .cs-queue-v1-management .catalog-management-button{min-height:36px!important;margin:0!important;white-space:nowrap!important}

      /* Lista ativa */
      #tab_panel_atualizacoes .cs-queue-v1-selector,
      #tab_panel_adicoes .cs-queue-v1-selector{
        display:flex!important;align-items:end!important;gap:12px!important;flex-wrap:wrap!important;width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-selector>label,
      #tab_panel_adicoes .cs-queue-v1-selector>label{display:grid!important;gap:6px!important;min-width:min(360px,100%)!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important}
      #tab_panel_atualizacoes .cs-queue-v1-selector select,
      #tab_panel_adicoes .cs-queue-v1-selector select{min-height:46px!important;border-radius:9px!important}
      #tab_panel_atualizacoes .cs-queue-v1-checkpoint,
      #tab_panel_adicoes .cs-queue-v1-checkpoint{padding-bottom:11px!important;color:var(--text-muted)!important;font-size:11px!important}

      /* Ações principais */
      #tab_panel_atualizacoes .cs-queue-v1-primary,
      #tab_panel_adicoes .cs-queue-v1-primary{
        display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:10px!important;width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-primary>.operational-action-control,
      #tab_panel_adicoes .cs-queue-v1-primary>.operational-action-control{display:grid!important;grid-template-columns:minmax(0,1fr) 28px!important;gap:6px!important;align-items:center!important;min-width:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-primary button:not(.comparison-help),
      #tab_panel_adicoes .cs-queue-v1-primary button:not(.comparison-help){width:100%!important;min-height:46px!important;margin:0!important;border-radius:9px!important}
      #tab_panel_adicoes .cs-queue-v1-primary>button{width:100%!important;min-height:46px!important;margin:0!important;border-radius:9px!important}

      /* Cards de estado */
      #tab_panel_atualizacoes .cs-queue-v1-summary-grid,
      #tab_panel_adicoes .cs-queue-v1-summary-grid{
        display:grid!important;grid-template-columns:repeat(6,minmax(0,1fr))!important;gap:8px!important;width:100%!important;margin:0!important;padding:0!important;border:0!important;background:none!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-summary-grid .cs-update-operational-guidance{display:none!important}
      #tab_panel_atualizacoes .cs-queue-v1-chip,
      #tab_panel_atualizacoes .cs-update-operational-chip,
      #tab_panel_adicoes .cs-queue-v1-chip{
        display:flex!important;flex-direction:column!important;justify-content:center!important;align-items:stretch!important;gap:5px!important;
        width:100%!important;min-width:0!important;min-height:72px!important;margin:0!important;padding:11px!important;
        border:1px solid var(--line)!important;border-radius:10px!important;background:rgba(255,255,255,.025)!important;
        color:var(--text)!important;text-align:left!important;font:inherit!important;box-shadow:none!important;cursor:pointer!important;box-sizing:border-box!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-chip:hover,
      #tab_panel_atualizacoes .cs-update-operational-chip:hover,
      #tab_panel_adicoes .cs-queue-v1-chip:hover{border-color:var(--line-accent)!important;background:var(--accent-soft)!important}
      #tab_panel_atualizacoes .cs-queue-v1-chip.is-filter-active,
      #tab_panel_atualizacoes .cs-update-operational-chip.is-filter-active,
      #tab_panel_adicoes .cs-queue-v1-chip.is-filter-active{border-color:rgba(124,58,237,.75)!important;background:rgba(124,58,237,.13)!important;box-shadow:inset 0 0 0 1px rgba(124,58,237,.16)!important}
      #tab_panel_atualizacoes .cs-queue-v1-chip>strong,
      #tab_panel_atualizacoes .cs-update-operational-chip>strong,
      #tab_panel_adicoes .cs-queue-v1-chip>strong{font-size:20px!important;font-weight:850!important;line-height:1!important;font-variant-numeric:tabular-nums!important}
      #tab_panel_adicoes .cs-queue-v1-chip>span{color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important}

      /* Buscar | Estado | Atualizar */
      #tab_panel_atualizacoes .cs-queue-v1-filterbar,
      #tab_panel_adicoes .cs-queue-v1-filterbar{
        display:grid!important;grid-template-columns:minmax(300px,1fr) minmax(190px,280px) auto!important;gap:10px!important;align-items:end!important;
        width:100%!important;margin:0!important;padding:12px!important;border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.014)!important;box-sizing:border-box!important
      }
      #tab_panel_atualizacoes .cs-queue-v1-filterbar>label,
      #tab_panel_atualizacoes .cs-queue-v1-filterbar>.field,
      #tab_panel_adicoes .cs-queue-v1-filterbar>label,
      #tab_panel_adicoes .cs-queue-v1-filterbar>.field{display:grid!important;gap:6px!important;min-width:0!important;margin:0!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important}
      #tab_panel_atualizacoes .cs-queue-v1-filterbar input,
      #tab_panel_atualizacoes .cs-queue-v1-filterbar select,
      #tab_panel_adicoes .cs-queue-v1-filterbar input,
      #tab_panel_adicoes .cs-queue-v1-filterbar select{width:100%!important;min-width:0!important;min-height:46px!important;margin:0!important;border-radius:9px!important}
      #tab_panel_atualizacoes .cs-queue-v1-filterbar>.cs-queue-v1-refresh,
      #tab_panel_adicoes .cs-queue-v1-filterbar>#addition_queue_refresh{min-width:108px!important;min-height:46px!important;margin:0!important;border-radius:9px!important}

      /* Contagem */
      #tab_panel_atualizacoes .cs-queue-v1-meta,
      #tab_panel_adicoes .cs-queue-v1-meta{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;width:100%!important;min-height:34px!important;margin:0!important;padding:0 2px!important}
      #tab_panel_atualizacoes .cs-queue-v1-meta .cs-result-count,
      #tab_panel_adicoes .cs-queue-v1-meta #addition_queue_meta{color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;margin:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-meta .listing-page-size,
      #tab_panel_adicoes .cs-queue-v1-meta .listing-page-size{display:inline-flex!important;align-items:center!important;gap:8px!important;margin-left:auto!important;color:var(--text-soft)!important;font-size:11px!important;font-weight:700!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-queue-v1-meta .listing-page-size input,
      #tab_panel_adicoes .cs-queue-v1-meta .listing-page-size input{width:58px!important;min-width:58px!important;min-height:32px!important;margin:0!important;padding:4px 7px!important;text-align:center!important}

      /* Seleção e ações em lote */
      #tab_panel_atualizacoes .cs-queue-v1-bulk,
      #tab_panel_adicoes .cs-queue-v1-bulk{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;flex-wrap:wrap!important;width:100%!important;min-height:60px!important;margin:0!important;padding:10px 12px!important;border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.022)!important;box-sizing:border-box!important}
      #tab_panel_atualizacoes .cs-queue-v1-selection,
      #tab_panel_adicoes .cs-queue-v1-selection{display:flex!important;align-items:center!important;gap:12px!important;flex:1 1 420px!important;min-width:0!important;flex-wrap:wrap!important}
      #tab_panel_atualizacoes .cs-queue-v1-check,
      #tab_panel_adicoes .cs-queue-v1-check{display:inline-flex!important;align-items:center!important;gap:7px!important;margin:0!important;color:var(--text-soft)!important;font-size:11px!important;font-weight:750!important;white-space:nowrap!important;cursor:pointer!important}
      #tab_panel_atualizacoes .cs-queue-v1-check input,
      #tab_panel_adicoes .cs-queue-v1-check input{width:17px!important;height:17px!important;min-height:0!important;margin:0!important;accent-color:#7c3aed!important}
      #tab_panel_atualizacoes .cs-queue-v1-bulk-actions,
      #tab_panel_adicoes .cs-queue-v1-bulk-actions{display:flex!important;align-items:center!important;justify-content:flex-end!important;gap:8px!important;flex:1 1 560px!important;margin-left:auto!important;flex-wrap:wrap!important}
      #tab_panel_atualizacoes .cs-queue-v1-selected-count,
      #tab_panel_adicoes .cs-queue-v1-selected-count{color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important;white-space:nowrap!important;margin-right:2px!important}
      #tab_panel_atualizacoes .cs-queue-v1-bulk-actions button,
      #tab_panel_adicoes .cs-queue-v1-bulk-actions button{min-height:40px!important;margin:0!important;padding:0 13px!important;border-radius:9px!important;white-space:nowrap!important}

      /* Jobs: mesma moldura e mesma hierarquia de estado/ações */
      #tab_panel_atualizacoes .cs-queue-v1-list,
      #tab_panel_adicoes .cs-queue-v1-list{display:grid!important;gap:8px!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-list>.update-queue-row,
      #tab_panel_adicoes .cs-queue-v1-list>.addition-op-row{width:100%!important;min-width:0!important;margin:0!important;padding:12px!important;border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.014)!important;box-shadow:none!important;box-sizing:border-box!important}
      #tab_panel_atualizacoes .cs-queue-v1-list>.update-queue-row{grid-template-columns:30px minmax(300px,1fr) minmax(180px,.55fr) minmax(130px,auto)!important;gap:12px!important;align-items:center!important}
      #tab_panel_adicoes .cs-queue-v1-list>.addition-op-row{grid-template-columns:30px minmax(300px,1.3fr) minmax(180px,.7fr) minmax(190px,.8fr) minmax(110px,auto)!important;gap:12px!important;align-items:center!important}
      #tab_panel_atualizacoes .cs-queue-v1-row-select{display:grid!important;place-items:center!important;margin:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-row-select input{width:17px!important;height:17px!important;margin:0!important;accent-color:#7c3aed!important}
      #tab_panel_atualizacoes .cs-queue-v1-position-note{display:inline-flex!important;margin:0 7px 4px 0!important;color:var(--text-faint)!important;font-size:10px!important;font-weight:800!important}
      #tab_panel_atualizacoes .cs-queue-v1-state-wrap,
      #tab_panel_adicoes .addition-state-wrap{display:grid!important;gap:6px!important;min-width:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-progress-mini,
      #tab_panel_adicoes .addition-progress-mini{height:6px!important;overflow:hidden!important;border-radius:999px!important;background:#24242b!important}
      #tab_panel_atualizacoes .cs-queue-v1-progress-mini>span,
      #tab_panel_adicoes .addition-progress-mini>span{display:block!important;height:100%!important;background:var(--success)!important;transition:width .2s ease!important}
      #tab_panel_atualizacoes .cs-queue-v1-row-actions,
      #tab_panel_adicoes .addition-op-actions{display:flex!important;justify-content:flex-end!important;gap:6px!important;flex-wrap:wrap!important}
      #tab_panel_atualizacoes .cs-queue-v1-row-actions button,
      #tab_panel_adicoes .addition-op-actions button{min-height:34px!important;padding:7px 10px!important;font-size:11px!important}
      #tab_panel_atualizacoes .cs-queue-v1-state-wrap.is-success .badge{border-color:rgba(16,185,129,.38)!important;background:rgba(16,185,129,.09)!important;color:#a7f3d0!important}
      #tab_panel_atualizacoes .cs-queue-v1-state-wrap.is-active .badge{border-color:rgba(96,165,250,.42)!important;background:rgba(96,165,250,.08)!important;color:#bfdbfe!important}
      #tab_panel_atualizacoes .cs-queue-v1-state-wrap.is-warning .badge{border-color:rgba(245,158,11,.38)!important;background:rgba(245,158,11,.08)!important;color:#fde68a!important}
      #tab_panel_atualizacoes .cs-queue-v1-state-wrap.is-danger .badge{border-color:rgba(239,68,68,.42)!important;background:rgba(239,68,68,.08)!important;color:#fecaca!important}
      #tab_panel_atualizacoes .update-operational-detail,
      #tab_panel_adicoes .addition-operational-detail{grid-column:1/-1!important}
      #tab_panel_adicoes .addition-table-head{display:none!important}

      /* Paginação */
      #tab_panel_atualizacoes .cs-queue-v1-pagination,
      #tab_panel_adicoes .cs-queue-v1-pagination{display:grid!important;grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;gap:10px!important;align-items:center!important;width:100%!important;margin:2px 0 0!important;padding:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-pagination>button,
      #tab_panel_adicoes .cs-queue-v1-pagination>button{width:100%!important;min-height:42px!important;margin:0!important}
      #tab_panel_atualizacoes .cs-queue-v1-pagination .badge,
      #tab_panel_adicoes .cs-queue-v1-pagination .badge{justify-self:center!important;white-space:nowrap!important}

      /* Legado visual eliminado depois que os nós funcionais são movidos. */
      #tab_panel_atualizacoes .cs-queue-v1 .updates-section-heading:not(.cs-queue-v1-management),
      #tab_panel_atualizacoes .cs-queue-v1 #updates_queue_list_controls,
      #tab_panel_adicoes .cs-queue-v1 .addition-queue-heading-standard,
      #tab_panel_adicoes .cs-queue-v1>.addition-section-hint{display:none!important}

      @media(max-width:1180px){
        #tab_panel_atualizacoes .cs-queue-v1-summary-grid,#tab_panel_adicoes .cs-queue-v1-summary-grid{grid-template-columns:repeat(4,minmax(0,1fr))!important}
        #tab_panel_adicoes .cs-queue-v1-list>.addition-op-row{grid-template-columns:30px minmax(280px,1fr) minmax(180px,.7fr) minmax(170px,.8fr)!important}
        #tab_panel_adicoes .cs-queue-v1-list>.addition-op-row>.addition-op-actions{grid-column:2/-1!important;justify-content:flex-end!important}
      }
      @media(max-width:850px){
        #tab_panel_atualizacoes .cs-queue-v1-management,#tab_panel_adicoes .cs-queue-v1-management{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-queue-v1-primary,#tab_panel_adicoes .cs-queue-v1-primary,
        #tab_panel_atualizacoes .cs-queue-v1-filterbar,#tab_panel_adicoes .cs-queue-v1-filterbar{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-queue-v1-summary-grid,#tab_panel_adicoes .cs-queue-v1-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
        #tab_panel_atualizacoes .cs-queue-v1-list>.update-queue-row,#tab_panel_adicoes .cs-queue-v1-list>.addition-op-row{grid-template-columns:30px minmax(0,1fr)!important;align-items:start!important}
        #tab_panel_atualizacoes .cs-queue-v1-list>.update-queue-row>*:not(.cs-queue-v1-row-select),
        #tab_panel_adicoes .cs-queue-v1-list>.addition-op-row>*:not(:first-child){grid-column:2!important}
        #tab_panel_atualizacoes .cs-queue-v1-row-actions,#tab_panel_adicoes .addition-op-actions{justify-content:flex-start!important}
      }
      @media(max-width:520px){#tab_panel_atualizacoes .cs-queue-v1-summary-grid,#tab_panel_adicoes .cs-queue-v1-summary-grid{grid-template-columns:1fr!important}}
    `;
    document.head.appendChild(style);
  }

  function addClass(node, ...classes) {
    if (!node) return;
    classes.filter(Boolean).forEach(value => node.classList.add(value));
  }

  function ensureBlock(parent, id, className) {
    let node = $(`#${id}`, parent) || document.getElementById(id);
    if (!node) {
      node = document.createElement("div");
      node.id = id;
      node.className = className;
    }
    if (parent && node.parentElement !== parent) parent.appendChild(node);
    return node;
  }

  function ensureOrdered(parent, nodes) {
    if (!parent) return;
    const wanted = nodes.filter(Boolean);
    let previous = null;
    wanted.forEach(node => {
      const expected = previous ? previous.nextElementSibling : parent.firstElementChild;
      if (expected !== node) parent.insertBefore(node, expected || null);
      previous = node;
    });
  }

  async function requestJson(url, options = {}, timeoutMs = 25000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        cache:"no-store", credentials:"same-origin",
        headers:{...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {})},
        ...options, signal:options.signal || controller.signal,
      });
      let data = {};
      try { data = await response.json(); } catch (_error) {}
      if (!response.ok || data?.ok === false) throw new Error(data?.message || data?.error || `HTTP ${response.status}`);
      return data;
    } finally { clearTimeout(timer); }
  }

  const postJson = (url, payload = {}) => requestJson(url, {method:"POST", body:JSON.stringify(payload)});

  function notify(message, kind = "ok") {
    $("#cs_queue_v1_toast")?.remove();
    const node = document.createElement("div");
    node.id = "cs_queue_v1_toast";
    node.textContent = clean(message);
    Object.assign(node.style, {
      position:"fixed", right:"18px", bottom:"18px", zIndex:"190000", maxWidth:"560px",
      padding:"12px 14px", borderRadius:"11px", fontWeight:"750",
      background:kind === "error" ? "#451a1a" : kind === "warning" ? "#3b2a05" : "#063d2b",
      color:"#fff", border:`1px solid ${kind === "error" ? "#ef4444" : kind === "warning" ? "#f59e0b" : "#10b981"}`,
      boxShadow:"0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 5200);
  }

  function currentUpdateRows() {
    return $$("#updates_queue_jobs .update-queue-row");
  }

  function updateRowId(row) {
    return clean($("[data-update-detail]", row)?.dataset?.updateDetail || row?.dataset?.updateJobId || "");
  }

  function visibleUpdateRows() {
    return currentUpdateRows().filter(row => !row.hidden && getComputedStyle(row).display !== "none");
  }

  function syncUpdateSelectionUi() {
    currentUpdateRows().forEach(row => {
      const id = updateRowId(row);
      const box = $(".cs-queue-v1-update-select", row);
      if (box && id) box.checked = updateSelection.has(id);
    });
    const visible = visibleUpdateRows().map(updateRowId).filter(Boolean);
    const page = $("#cs_updates_queue_select_page_v1");
    if (page) {
      const selected = visible.filter(id => updateSelection.has(id)).length;
      page.checked = visible.length > 0 && selected === visible.length;
      page.indeterminate = selected > 0 && selected < visible.length;
    }
    const count = $("#cs_updates_queue_selected_count_v1");
    if (count) count.textContent = `${updateSelection.size} selecionado${updateSelection.size === 1 ? "" : "s"}`;
  }

  async function loadUpdateJobs() {
    const data = await requestJson("/atualizacoes/jobs");
    return {jobs:Array.isArray(data?.jobs) ? data.jobs : [], queue:data?.queue || {}};
  }

  async function filteredUpdateIds() {
    const {jobs, queue} = await loadUpdateJobs();
    const active = clean($("#updates_queue_select")?.value || queue?.active_queue || "default") || "default";
    const q = clean($("#updates_queue_search")?.value).toLowerCase();
    const state = clean($("#updates_queue_status_filter")?.value);
    return jobs.filter(job => {
      if (clean(job?.queue_name || "default") !== active) return false;
      if (state && clean(job?.state) !== state) return false;
      if (!q) return true;
      return clean(job?.name).toLowerCase().includes(q) || String(job?.woo_product_id || "").includes(q);
    }).map(job => clean(job?.job_id)).filter(Boolean);
  }

  function createUpdateBulk() {
    let bulk = $("#cs_updates_queue_bulk_v1");
    if (bulk) return bulk;
    bulk = document.createElement("div");
    bulk.id = "cs_updates_queue_bulk_v1";
    bulk.className = "cs-queue-v1-bulk";
    bulk.innerHTML = `
      <div class="cs-queue-v1-selection">
        <label class="cs-queue-v1-check"><input type="checkbox" id="cs_updates_queue_select_page_v1"><span>Selecionar página</span></label>
        <label class="cs-queue-v1-check"><input type="checkbox" id="cs_updates_queue_select_all_v1"><span>Selecionar todo resultado</span></label>
        <button type="button" class="btn-secondary" id="cs_updates_queue_clear_selection_v1">Limpar seleção</button>
      </div>
      <div class="cs-queue-v1-bulk-actions">
        <strong class="cs-queue-v1-selected-count" id="cs_updates_queue_selected_count_v1">0 selecionados</strong>
        <button type="button" class="btn-success" id="cs_updates_queue_enqueue_v1">Adicionar selecionados à fila</button>
        <button type="button" class="btn-secondary" id="cs_updates_queue_retry_v1">Tentar novamente</button>
        <button type="button" class="btn-danger" id="cs_updates_queue_cancel_v1">Cancelar selecionados</button>
        <button type="button" class="btn-secondary" id="cs_updates_queue_clear_completed_v1">Limpar concluídos da fila</button>
      </div>`;

    $("#cs_updates_queue_select_page_v1", bulk)?.addEventListener("change", event => {
      visibleUpdateRows().forEach(row => {
        const id = updateRowId(row);
        if (!id) return;
        event.target.checked ? updateSelection.add(id) : updateSelection.delete(id);
      });
      syncUpdateSelectionUi();
    });
    $("#cs_updates_queue_select_all_v1", bulk)?.addEventListener("change", async event => {
      const box = event.target;
      box.disabled = true;
      try {
        if (box.checked) (await filteredUpdateIds()).forEach(id => updateSelection.add(id));
        else updateSelection.clear();
      } catch (error) {
        box.checked = false;
        notify(error.message, "error");
      } finally {
        box.disabled = false;
        syncUpdateSelectionUi();
      }
    });
    $("#cs_updates_queue_clear_selection_v1", bulk)?.addEventListener("click", () => {
      updateSelection.clear();
      const all = $("#cs_updates_queue_select_all_v1"); if (all) all.checked = false;
      syncUpdateSelectionUi();
    });
    $("#cs_updates_queue_enqueue_v1", bulk)?.addEventListener("click", async () => {
      const ids = [...updateSelection];
      if (!ids.length) return notify("Selecione ao menos um item.", "warning");
      try {
        const result = await postJson("/atualizacoes/fila/adicionar", {job_ids:ids});
        notify(`${Number(result?.added || 0)} item(ns) enviados para a fila.`);
        updateSelection.clear(); refreshUpdateQueue();
      } catch (error) { notify(error.message, "error"); }
    });
    $("#cs_updates_queue_retry_v1", bulk)?.addEventListener("click", async event => {
      if (!updateSelection.size) return notify("Selecione ao menos um item.", "warning");
      const button = event.currentTarget;
      button.disabled = true;
      const original = button.textContent;
      try {
        const {jobs} = await loadUpdateJobs();
        const map = new Map(jobs.map(job => [clean(job?.job_id), job]));
        const retryable = [...updateSelection].map(id => map.get(id)).filter(job => job && UPDATE_RECOVERABLE.has(clean(job.state)));
        if (!retryable.length) throw new Error("Nenhum item selecionado está em estado recuperável.");
        let ok = 0, failed = 0;
        for (let index = 0; index < retryable.length; index += 1) {
          const job = retryable[index];
          button.textContent = `${index + 1}/${retryable.length} · preparando`;
          try {
            const prepared = await postJson("/atualizacoes/preparar", {job_id:job.job_id});
            if (prepared?.preview?.ready !== true) throw new Error(prepared?.preview?.message || "Preparação bloqueada.");
            button.textContent = `${index + 1}/${retryable.length} · gerando plano`;
            const planned = await postJson("/atualizacoes/plano", {job_id:job.job_id});
            if (planned?.plan?.ready !== true) throw new Error(planned?.plan?.message || "Plano não ficou pronto.");
            ok += 1;
          } catch (_error) { failed += 1; }
        }
        notify(`${ok} recuperado(s) · ${failed} ainda exigem atenção.`, failed ? "warning" : "ok");
        refreshUpdateQueue();
      } catch (error) { notify(error.message, "error"); }
      finally { button.disabled = false; button.textContent = original; }
    });
    $("#cs_updates_queue_cancel_v1", bulk)?.addEventListener("click", async () => {
      const ids = [...updateSelection];
      if (!ids.length) return notify("Selecione ao menos um item.", "warning");
      if (!confirm("Cancelar somente os itens selecionados que ainda não iniciaram a execução?")) return;
      try {
        const result = await postJson("/atualizacoes/fila/cancelar-selecionados", {job_ids:ids});
        notify(`${Number(result?.canceled || 0)} item(ns) cancelados.`);
        updateSelection.clear(); refreshUpdateQueue();
      } catch (error) { notify(error.message, "error"); }
    });
    $("#cs_updates_queue_clear_completed_v1", bulk)?.addEventListener("click", async () => {
      if (!confirm("Remover os concluídos apenas da lista visual? O histórico operacional será preservado.")) return;
      try {
        const result = await postJson("/atualizacoes/fila/limpar-concluidos", {});
        notify(`${Number(result?.removed || 0)} concluído(s) removidos da lista.`);
        refreshUpdateQueue();
      } catch (error) { notify(error.message, "error"); }
    });
    return bulk;
  }

  function refreshUpdateQueue() {
    const button = $("#updates_refresh_btn");
    if (button) button.click();
    else location.reload();
    setTimeout(() => { normalizeAll(); syncUpdateSelectionUi(); }, 250);
  }

  function normalizeUpdateRows() {
    currentUpdateRows().forEach(row => {
      addClass(row, "cs-queue-v1-row");
      const id = updateRowId(row);
      if (!id) return;

      let select = $(".cs-queue-v1-row-select", row);
      if (!select) {
        select = document.createElement("label");
        select.className = "cs-queue-v1-row-select";
        select.innerHTML = `<input type="checkbox" class="cs-queue-v1-update-select" aria-label="Selecionar ${esc($("strong", row)?.textContent || "item")}">`;
        row.insertBefore(select, row.firstElementChild);
        $("input", select)?.addEventListener("change", event => {
          event.target.checked ? updateSelection.add(id) : updateSelection.delete(id);
          const all = $("#cs_updates_queue_select_all_v1"); if (all) all.checked = false;
          syncUpdateSelectionUi();
        });
      }

      const position = $(".update-queue-position", row);
      const main = row.children?.[1] === position ? row.children?.[2] : $$(":scope > div", row).find(node => !node.classList.contains("update-operational-detail") && node !== position);
      if (position && main && position.parentElement === row) {
        addClass(position, "cs-queue-v1-position-note");
        main.insertBefore(position, main.firstElementChild);
      }

      const state = clean(row.dataset.liveUpdateState || "");
      const badge = $(":scope > .badge", row) || $(".cs-queue-v1-state-wrap .badge", row);
      let stateWrap = $(".cs-queue-v1-state-wrap", row);
      if (!stateWrap) {
        stateWrap = document.createElement("div");
        stateWrap.className = "cs-queue-v1-state-wrap";
        if (badge?.parentElement === row) row.insertBefore(stateWrap, badge);
        else row.appendChild(stateWrap);
      }
      if (badge && badge.parentElement !== stateWrap) stateWrap.appendChild(badge);
      stateWrap.classList.remove("is-success","is-active","is-warning","is-danger");
      if (["completed","rolled_back"].includes(state)) stateWrap.classList.add("is-success");
      else if (["executing","installing","updating_wordpress","validating","downloading","staging","rolling_back"].includes(state)) stateWrap.classList.add("is-active");
      else if (["interrupted","rollback_required"].includes(state)) stateWrap.classList.add("is-warning");
      else if (["blocked","error","failed","canceled"].includes(state)) stateWrap.classList.add("is-danger");
      let progress = $(".cs-queue-v1-progress-mini", stateWrap);
      if (!progress) {
        progress = document.createElement("div"); progress.className = "cs-queue-v1-progress-mini"; progress.innerHTML = "<span></span>";
        stateWrap.appendChild(progress);
      }
      const bar = $("span", progress); if (bar) bar.style.width = `${UPDATE_PROGRESS[state] ?? 12}%`;

      const detail = $("button.update-history-details", row);
      let actions = $(".cs-queue-v1-row-actions", row);
      if (!actions) {
        actions = document.createElement("div"); actions.className = "cs-queue-v1-row-actions";
        if (detail?.parentElement === row) row.insertBefore(actions, detail);
        else row.appendChild(actions);
      }
      if (detail && detail.parentElement !== actions) actions.appendChild(detail);
    });
    syncUpdateSelectionUi();
  }

  function normalizeUpdateQueue() {
    const card = $("#tab_panel_atualizacoes .updates-queue-section");
    if (!card) return false;
    addClass(card, "cs-queue-v1", "cs-queue-v1-update");
    const header = $("button.standard-update-accordion-toggle", card);
    addClass(header, "cs-queue-v1-header");
    const summaryText = $(".standard-update-accordion-meta", header);
    addClass(summaryText, "cs-queue-v1-summary");

    const body = ensureBlock(card, "cs_updates_queue_v1_body", "cs-queue-v1-body");
    const management = ensureBlock(body, "cs_updates_queue_management_v1", "cs-queue-v1-management");
    let description = $(".cs-queue-v1-description", management);
    if (!description) {
      description = document.createElement("div"); description.className = "cs-queue-v1-description";
      description.textContent = "Organize as atualizações em listas independentes, escolha a lista ativa e controle sua execução sequencial.";
      management.appendChild(description);
    }
    const manager = $("#open_update_lists_modal", card) || $("#open_update_lists_modal");
    if (manager && manager.parentElement !== management) management.appendChild(manager);
    ensureOrdered(management, [description, manager]);

    const selector = $(".updates-queue-selector", card);
    addClass(selector, "cs-queue-v1-selector");
    addClass($("#updates_queue_checkpoint", selector), "cs-queue-v1-checkpoint");

    const primary = $(".updates-queue-actions", card);
    addClass(primary, "cs-queue-v1-primary");

    const summaryGrid = $("#cs_update_operational_summary", card);
    addClass(summaryGrid, "cs-queue-v1-summary-grid");
    $(".cs-update-operational-guidance", summaryGrid)?.remove();

    const controls = $("#updates_queue_list_controls", card);
    const filters = $(".updates-list-controls", controls);
    addClass(filters, "cs-queue-v1-filterbar");
    let refresh = $("#cs_updates_queue_refresh_v1", filters);
    if (!refresh && filters) {
      refresh = document.createElement("button");
      refresh.type = "button"; refresh.id = "cs_updates_queue_refresh_v1"; refresh.className = "btn-secondary cs-queue-v1-refresh"; refresh.textContent = "Atualizar";
      refresh.addEventListener("click", refreshUpdateQueue);
      filters.appendChild(refresh);
    }

    const meta = $(".cs-queue-meta-row", controls) || $(".listing-meta-row:has(#updates_queue_found_count)", controls);
    addClass(meta, "cs-queue-v1-meta");
    const strayMeta = $("[data-cs-update-queue-meta]", controls); if (strayMeta && strayMeta !== meta) strayMeta.remove();

    const bulk = createUpdateBulk();
    const list = $("#updates_queue_jobs", card); addClass(list, "cs-queue-v1-list");
    const pagination = $(".listing-pagination", controls); addClass(pagination, "cs-queue-v1-pagination");
    normalizeUpdateRows();

    ensureOrdered(body, [management, selector, primary, summaryGrid, filters, meta, bulk, list, pagination]);
    $$(".updates-section-heading", card).forEach(node => { if (node !== management && !node.contains(manager)) node.remove(); });
    if (controls && !controls.children.length) controls.remove();
    return true;
  }

  function currentAdditionRows() { return $$("#addition_queue_rows .addition-op-row"); }
  function additionRowId(row) { return clean($("[data-add-select='queue']", row)?.dataset?.job || row?.dataset?.addJob || ""); }

  function syncAdditionSelectionUi() {
    currentAdditionRows().forEach(row => {
      const id = additionRowId(row);
      const box = $("[data-add-select='queue']", row);
      if (box && id) box.checked = additionSelection.has(id);
    });
    const pageIds = currentAdditionRows().map(additionRowId).filter(Boolean);
    const page = $("#addition_queue_select_all");
    if (page) {
      const selected = pageIds.filter(id => additionSelection.has(id)).length;
      page.checked = pageIds.length > 0 && selected === pageIds.length;
      page.indeterminate = selected > 0 && selected < pageIds.length;
    }
    const count = $("#cs_addition_queue_selected_count_v1");
    if (count) count.textContent = `${additionSelection.size} selecionado${additionSelection.size === 1 ? "" : "s"}`;
  }

  async function allAdditionFilteredIds() {
    const q = clean($("#addition_queue_search")?.value);
    const state = clean($("#addition_queue_state")?.value);
    const ids = [];
    let page = 1, pages = 1;
    do {
      const params = new URLSearchParams({scope:"queue", page:String(page), page_size:"100"});
      if (q) params.set("q", q); if (state) params.set("state", state);
      const payload = await requestJson(`/adicoes/operacoes?${params}`);
      (Array.isArray(payload?.items) ? payload.items : []).forEach(item => { const id = clean(item?.job_id); if (id) ids.push(id); });
      pages = Math.max(1, Number(payload?.pages || 1)); page += 1;
    } while (page <= pages);
    return [...new Set(ids)];
  }

  function wireAdditionBulk(bulk) {
    if (!bulk || bulk.dataset.queueV1Bound === "1") return;
    bulk.dataset.queueV1Bound = "1";
    const page = $("#addition_queue_select_all", bulk) || $("#addition_queue_select_all");
    page?.addEventListener("change", event => {
      currentAdditionRows().forEach(row => {
        const id = additionRowId(row); if (!id) return;
        event.target.checked ? additionSelection.add(id) : additionSelection.delete(id);
      });
      syncAdditionSelectionUi();
    }, true);
    $("#cs_addition_queue_select_all_v1", bulk)?.addEventListener("change", async event => {
      const box = event.target; box.disabled = true;
      try {
        if (box.checked) (await allAdditionFilteredIds()).forEach(id => additionSelection.add(id));
        else additionSelection.clear();
      } catch (error) { box.checked = false; notify(error.message, "error"); }
      finally { box.disabled = false; syncAdditionSelectionUi(); }
    });
    $("#cs_addition_queue_clear_selection_v1", bulk)?.addEventListener("click", () => {
      additionSelection.clear(); const all = $("#cs_addition_queue_select_all_v1"); if (all) all.checked = false; syncAdditionSelectionUi();
    });

    const operations = [
      ["#addition_queue_add_selected", "/adicoes/fila/adicionar", "Enviar os produtos selecionados para a fila?"],
      ["#addition_queue_retry_selected", "/adicoes/fila/retry", "Tentar novamente os itens selecionados?"],
      ["#addition_queue_cancel_selected", "/adicoes/fila/cancelar", "Cancelar os itens selecionados quando for seguro?"],
    ];
    operations.forEach(([selector, url, confirmation]) => {
      const button = $(selector, bulk);
      button?.addEventListener("click", async event => {
        event.preventDefault(); event.stopImmediatePropagation();
        const ids = [...additionSelection]; if (!ids.length) return notify("Selecione ao menos um produto.", "warning");
        if (url.includes("cancelar") && !confirm(confirmation)) return;
        try {
          await postJson(url, {job_ids:ids});
          notify("Operação iniciada."); additionSelection.clear(); refreshAdditionQueue();
        } catch (error) { notify(error.message, "error"); }
      }, true);
    });
    $("#addition_queue_clear_completed", bulk)?.addEventListener("click", async event => {
      event.preventDefault(); event.stopImmediatePropagation();
      if (!confirm("Remover os concluídos apenas da fila visual? O histórico será preservado.")) return;
      try { await postJson("/adicoes/fila/limpar-concluidos", {}); notify("Concluídos removidos da fila visual."); refreshAdditionQueue(); }
      catch (error) { notify(error.message, "error"); }
    }, true);
  }

  function refreshAdditionQueue() {
    $("#addition_queue_refresh")?.click();
    scheduleAdditionSummary(true);
    setTimeout(() => { normalizeAll(); syncAdditionSelectionUi(); }, 220);
  }

  function prepareAdditionBulk() {
    const bulk = $("#addition_queue_accordion .addition-bulk-actions");
    if (!bulk) return null;
    addClass(bulk, "cs-queue-v1-bulk");
    let selection = $(".cs-queue-v1-selection", bulk);
    if (!selection) { selection = document.createElement("div"); selection.className = "cs-queue-v1-selection"; bulk.insertBefore(selection, bulk.firstChild); }
    const pageBox = $("#addition_queue_select_all");
    const pageLabel = pageBox?.closest("label");
    if (pageLabel) { addClass(pageLabel, "cs-queue-v1-check"); if (pageLabel.parentElement !== selection) selection.appendChild(pageLabel); }
    let allLabel = $("#cs_addition_queue_select_all_v1", bulk)?.closest("label");
    if (!allLabel) {
      allLabel = document.createElement("label"); allLabel.className = "cs-queue-v1-check";
      allLabel.innerHTML = '<input type="checkbox" id="cs_addition_queue_select_all_v1"><span>Selecionar todo resultado</span>';
      selection.appendChild(allLabel);
    }
    let clear = $("#cs_addition_queue_clear_selection_v1", bulk);
    if (!clear) { clear = document.createElement("button"); clear.type="button"; clear.id="cs_addition_queue_clear_selection_v1"; clear.className="btn-secondary"; clear.textContent="Limpar seleção"; selection.appendChild(clear); }

    let actions = $(".cs-queue-v1-bulk-actions", bulk);
    if (!actions) { actions = document.createElement("div"); actions.className="cs-queue-v1-bulk-actions"; bulk.appendChild(actions); }
    let count = $("#cs_addition_queue_selected_count_v1", actions);
    if (!count) { count=document.createElement("strong"); count.id="cs_addition_queue_selected_count_v1"; count.className="cs-queue-v1-selected-count"; count.textContent="0 selecionados"; actions.appendChild(count); }
    ["addition_queue_add_selected","addition_queue_retry_selected","addition_queue_cancel_selected","addition_queue_clear_completed"].forEach(id => {
      const button = document.getElementById(id); if (button && button.parentElement !== actions) actions.appendChild(button);
    });
    ensureOrdered(bulk, [selection, actions]);
    wireAdditionBulk(bulk);
    syncAdditionSelectionUi();
    return bulk;
  }

  function normalizeAdditionRows() {
    currentAdditionRows().forEach(row => {
      addClass(row, "cs-queue-v1-row");
      addClass($(".addition-state-wrap", row), "cs-queue-v1-state-wrap");
      addClass($(".addition-op-actions", row), "cs-queue-v1-row-actions");
      const box = $("[data-add-select='queue']", row);
      if (box && box.dataset.queueV1Bound !== "1") {
        box.dataset.queueV1Bound = "1";
        box.addEventListener("change", event => {
          const id = clean(event.target.dataset.job); if (!id) return;
          event.target.checked ? additionSelection.add(id) : additionSelection.delete(id);
          const all = $("#cs_addition_queue_select_all_v1"); if (all) all.checked = false;
          syncAdditionSelectionUi();
        }, true);
      }
    });
    syncAdditionSelectionUi();
  }

  function queueStatusLabel(value) {
    const status = clean(value).toLowerCase();
    if (status === "running") return "Fila executando";
    if (status === "paused") return "Fila pausada";
    return "Fila parada";
  }

  function renderAdditionQueueSummary(payload) {
    additionSummaryCache = payload || additionSummaryCache || {};
    const counts = additionSummaryCache?.counts || {};
    const grid = $("#cs_addition_queue_summary_v1");
    if (grid) {
      const active = clean($("#addition_queue_state")?.value);
      const chips = [
        ["Total", counts.total || 0, ""], ["Aguardando", counts.waiting || 0, "waiting"],
        ["Preparando", counts.preparing || 0, "preparing"], ["Pronto", counts.ready || 0, "ready"],
        ["Na fila", counts.queued || 0, "queued"], ["Executando", counts.executing || 0, "executing"],
        ["Concluídos", counts.completed || 0, "completed"], ["Erros", counts.error || 0, "error"],
        ["Interrompidos", counts.interrupted || 0, "interrupted"], ["Cancelados", counts.canceled || 0, "canceled"],
      ];
      grid.innerHTML = chips.map(([label,count,state]) => `<button type="button" class="cs-queue-v1-chip ${active===state?"is-filter-active":""}" data-cs-addition-queue-state="${esc(state)}"><strong>${Number(count)||0}</strong><span>${esc(label)}</span></button>`).join("");
      $$("[data-cs-addition-queue-state]", grid).forEach(button => button.addEventListener("click", () => {
        const select = $("#addition_queue_state"); if (!select) return;
        select.value = button.dataset.csAdditionQueueState || "";
        select.dispatchEvent(new Event("change", {bubbles:true}));
        setTimeout(() => renderAdditionQueueSummary(additionSummaryCache), 80);
      }));
    }
    const status = queueStatusLabel(additionSummaryCache?.queue?.status || clean($("#addition_queue_status")?.textContent));
    const select = $("#addition_queue_list_select");
    const list = clean(select?.selectedOptions?.[0]?.textContent || select?.value || "Padrão") || "Padrão";
    const header = $("#addition_queue_summary");
    if (header) header.textContent = `${Number(counts.queued||0)} na fila · ${Number(counts.executing||0)} executando · ${Number(counts.completed||0)} concluídos · ${status} · ${list}`;
  }

  function scheduleAdditionSummary(force = false) {
    clearTimeout(additionSummaryTimer);
    additionSummaryTimer = setTimeout(async () => {
      if (additionSummaryBusy) return;
      if (!force && additionSummaryCache) { renderAdditionQueueSummary(additionSummaryCache); return; }
      additionSummaryBusy = true;
      try { renderAdditionQueueSummary(await requestJson("/adicoes/operacoes?scope=overview")); }
      catch (_error) { renderAdditionQueueSummary(additionSummaryCache); }
      finally { additionSummaryBusy = false; }
    }, force ? 20 : 100);
  }

  function normalizeAdditionQueue() {
    const card = $("#addition_queue_accordion");
    if (!card) return false;
    addClass(card, "cs-queue-v1", "cs-queue-v1-addition");
    const header = $(":scope > summary", card); addClass(header, "cs-queue-v1-header");
    addClass($("#addition_queue_summary", header), "cs-queue-v1-summary");

    const body = ensureBlock(card, "cs_addition_queue_v1_body", "cs-queue-v1-body");
    const management = ensureBlock(body, "cs_addition_queue_management_v1", "cs-queue-v1-management");
    let description = $(".cs-queue-v1-description", management);
    if (!description) { description=document.createElement("div"); description.className="cs-queue-v1-description"; description.textContent="Organize os produtos em listas independentes, escolha a lista ativa e controle sua execução sequencial."; management.appendChild(description); }
    const manager = $("#open_addition_lists_modal", card) || $("#open_addition_lists_modal"); if (manager && manager.parentElement !== management) management.appendChild(manager);
    ensureOrdered(management, [description, manager]);

    const selector = $(".cs-v4-queue-selector", card) || $("#addition_queue_list_select", card)?.closest("div");
    addClass(selector, "cs-queue-v1-selector");
    addClass($("#addition_queue_list_checkpoint", selector), "cs-queue-v1-checkpoint");

    const primary = $("#addition_queue_primary_actions", card); addClass(primary, "cs-queue-v1-primary");
    const summaryGrid = ensureBlock(body, "cs_addition_queue_summary_v1", "cs-queue-v1-summary-grid");

    const filters = $(".addition-toolbar", card); addClass(filters, "cs-queue-v1-filterbar");
    const meta = $(".addition-list-meta", card); addClass(meta, "cs-queue-v1-meta");
    const pageLabel = $("#addition_queue_select_all")?.closest("label"); if (pageLabel?.parentElement) pageLabel.parentElement.removeChild(pageLabel);
    const metaText = $("#addition_queue_meta", meta); if (metaText && metaText.parentElement !== meta) meta.insertBefore(metaText, meta.firstChild);
    const bulk = prepareAdditionBulk(); if (pageLabel) $(".cs-queue-v1-selection", bulk)?.insertBefore(pageLabel, $(".cs-queue-v1-selection", bulk)?.firstChild || null);

    const list = $("#addition_queue_rows", card); addClass(list, "cs-queue-v1-list");
    const pagination = $(".addition-pagination", card); addClass(pagination, "cs-queue-v1-pagination");
    normalizeAdditionRows();

    ensureOrdered(body, [management, selector, primary, summaryGrid, filters, meta, bulk, list, pagination]);
    $(".cs-v4-queue-management", card)?.remove();
    $(".addition-queue-heading-standard", card)?.remove();
    $$(".addition-section-hint", card).forEach(node => node.remove());
    $(".addition-table-head", card)?.remove();
    scheduleAdditionSummary(false);
    return true;
  }

  function normalizeAll() {
    if (normalizing) return;
    normalizing = true;
    try {
      installStyles();
      normalizeUpdateQueue();
      normalizeAdditionQueue();
    } finally { normalizing = false; }
  }

  function schedule() {
    clearTimeout(scheduled);
    scheduled = setTimeout(normalizeAll, 35);
  }

  function observe() {
    [$("#tab_panel_atualizacoes"), $("#tab_panel_adicoes")].filter(Boolean).forEach(panel => {
      new MutationObserver(() => { if (!normalizing) schedule(); }).observe(panel, {childList:true, subtree:true, attributes:true, attributeFilter:["style","class","open"]});
    });
  }

  function start() {
    normalizeAll();
    observe();
    [90,220,500,900,1600,3000].forEach(delay => setTimeout(normalizeAll, delay));
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => { schedule(); setTimeout(syncUpdateSelectionUi, 180); }, true);
    $("#tab_btn_adicoes")?.addEventListener("click", () => { schedule(); scheduleAdditionSummary(true); }, true);
    $("#updates_queue_select")?.addEventListener("change", () => { updateSelection.clear(); schedule(); }, true);
    $("#addition_queue_list_select")?.addEventListener("change", () => { additionSelection.clear(); scheduleAdditionSummary(true); schedule(); }, true);
    document.addEventListener("crapscraper:main-tab-changed", schedule, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
