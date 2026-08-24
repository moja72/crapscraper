(() => {
  "use strict";

  if (window.__crapScraperOperationalOverviewStandardizationInstalled) return;
  window.__crapScraperOperationalOverviewStandardizationInstalled = true;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();
  let normalizing = false;
  let scheduled = 0;

  function installStyles() {
    if ($("#cs-operational-overview-standardization-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-overview-standardization-style";
    style.textContent = `
      #tab_panel_atualizacoes .updates-overview-card.cs-standard-overview,
      #tab_panel_adicoes #addition_intro_card.cs-standard-overview{
        display:grid!important;grid-template-columns:1fr!important;gap:14px!important;width:100%!important;
        padding:18px!important;border:1px solid var(--line)!important;border-radius:var(--radius-md)!important;
        background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,.01)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;box-sizing:border-box!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-heading,
      #tab_panel_adicoes .cs-standard-overview-heading{
        display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;align-items:start!important;
        gap:18px!important;width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-copy,
      #tab_panel_adicoes .cs-standard-overview-copy{display:grid!important;gap:6px!important;min-width:0!important;margin:0!important}
      #tab_panel_atualizacoes .cs-standard-overview-copy .section-title,
      #tab_panel_adicoes .cs-standard-overview-copy .section-title{
        margin:0!important;padding:0!important;font-size:16px!important;line-height:1.25!important;font-weight:800!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-copy .small,
      #tab_panel_adicoes .cs-standard-overview-copy .small{
        max-width:980px!important;margin:0!important;color:var(--text-muted)!important;font-size:12px!important;line-height:1.5!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-actions,
      #tab_panel_adicoes .cs-standard-overview-actions{
        display:flex!important;align-items:flex-start!important;justify-content:flex-end!important;gap:8px!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-actions>button,
      #tab_panel_adicoes .cs-standard-overview-actions>button{min-height:42px!important;margin:0!important}

      #tab_panel_atualizacoes .cs-standard-overview-progress,
      #tab_panel_adicoes .cs-standard-overview-progress{
        display:grid!important;gap:7px!important;width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-copy,
      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-copy,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-copy,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-copy{
        display:flex!important;align-items:baseline!important;gap:10px!important;width:100%!important;margin:0!important;padding:0!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-copy strong,
      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-copy strong,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-copy strong,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-copy strong{
        margin:0!important;font-size:24px!important;line-height:1!important;font-weight:850!important;
        letter-spacing:-.02em!important;font-variant-numeric:tabular-nums!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-track,
      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-track,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-track,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-track{
        position:relative!important;width:100%!important;height:6px!important;min-height:6px!important;margin:0!important;
        overflow:hidden!important;border:0!important;border-radius:999px!important;background:rgba(255,255,255,.06)!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-track>span,
      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-track>span,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-track>span,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-track>span{
        display:block!important;height:100%!important;border-radius:inherit!important;background:var(--success)!important
      }
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-now,
      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-now,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-now,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-now,
      #tab_panel_adicoes .cs-standard-overview-progress [data-addition-progress-now]{
        display:flex!important;align-items:center!important;width:100%!important;min-height:36px!important;margin:0!important;
        padding:9px 11px!important;border:1px solid rgba(255,255,255,.045)!important;border-radius:8px!important;
        background:rgba(255,255,255,.022)!important;color:var(--text-muted)!important;font-size:12px!important;
        line-height:1.4!important;box-sizing:border-box!important
      }

      #tab_panel_atualizacoes .cs-standard-overview>#updates_summary,
      #tab_panel_adicoes .cs-standard-overview #addition_summary_grid{margin:2px 0 0!important}
      #tab_panel_atualizacoes #updates_execution_lock,
      #tab_panel_adicoes #addition_guidance{display:none!important}
      #tab_panel_adicoes #addition_intro_card .addition-flow-strip{display:none!important}

      @media(max-width:760px){
        #tab_panel_atualizacoes .cs-standard-overview-heading,
        #tab_panel_adicoes .cs-standard-overview-heading{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-standard-overview-actions,
        #tab_panel_adicoes .cs-standard-overview-actions{justify-content:stretch!important}
        #tab_panel_atualizacoes .cs-standard-overview-actions>button,
        #tab_panel_adicoes .cs-standard-overview-actions>button{width:100%!important}
      }
    `;
    document.head.appendChild(style);
  }

  function setText(node, value) {
    if (node && normalize(node.textContent) !== value) node.textContent = value;
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

  function addClass(node, value) {
    if (node && !node.classList.contains(value)) node.classList.add(value);
  }

  function ensureBlock(parent, id, className) {
    let node = $(`#${id}`, parent);
    if (!node) {
      node = document.createElement("div");
      node.id = id;
      node.className = className;
    }
    return node;
  }

  function normalizeUpdateOverview() {
    const card = $("#tab_panel_atualizacoes .updates-overview-card");
    const head = $(".updates-hero", card);
    if (!card || !head) return false;

    addClass(card, "cs-standard-overview");
    addClass(head, "cs-standard-overview-heading");

    const copy = head.firstElementChild;
    addClass(copy, "cs-standard-overview-copy");
    setText($(".section-title", copy), "Atualiza produtos");
    setText($(".small", copy), "Prepare os produtos aprovados, revise os dados e execute as atualizações com segurança no WooCommerce.");

    const actions = ensureBlock(head, "updates_overview_actions", "cs-standard-overview-actions");
    addClass(actions, "cs-standard-overview-actions");
    const refresh = $("#updates_refresh_btn", card);
    if (refresh?.parentElement !== actions) actions.appendChild(refresh);
    ensureOrdered(head, [copy, actions]);

    const progress = ensureBlock(card, "updates_overview_progress", "cs-standard-overview-progress");
    addClass(progress, "cs-standard-overview-progress");
    const percent = $("#updates_progress_percent", card);
    const progressCopy = percent?.parentElement || $(".updates-progress-copy,.cs-op-progress-copy", card);
    const bar = $("#updates_progress_bar", card);
    const progressTrack = bar?.parentElement || $(".updates-progress-track,.cs-op-progress-track", card);
    const now = $("#updates_now", card);
    addClass(progressCopy, "cs-op-progress-copy");
    addClass(progressTrack, "cs-op-progress-track");
    addClass(now, "cs-op-now");
    ensureOrdered(progress, [progressCopy, progressTrack, now]);

    const summary = $("#updates_summary", card);
    $("#updates_execution_lock", card)?.remove();
    ensureOrdered(card, [head, progress, summary]);
    return true;
  }

  function locateAdditionProgress(card) {
    const explicit = $("#addition_progress_block", card);
    if (explicit) return explicit;

    const percent = $("#addition_progress_percent,[data-addition-progress-percent],.addition-progress-percent", card);
    const progressCopy = percent?.parentElement || $(".addition-progress-copy,.cs-op-progress-copy", card);
    const bar = $("#addition_progress_bar,[data-addition-progress-bar]", card);
    const progressTrack = bar?.parentElement || $(".addition-progress-track,.cs-op-progress-track", card);
    const now = $("#addition_progress_now,[data-addition-progress-now],.addition-progress-now,.cs-op-now", card);
    if (!progressCopy && !progressTrack && !now) return null;

    const block = ensureBlock(card, "addition_progress_block", "cs-standard-overview-progress");
    ensureOrdered(block, [progressCopy, progressTrack, now]);
    return block;
  }

  function removeAdditionFlow(card) {
    const flow = $(".addition-flow-strip", card);
    if (flow) flow.remove();
    Array.from(card.children).forEach(node => {
      if (!(node instanceof HTMLElement)) return;
      const value = normalize(node.textContent);
      if (
        value.includes("Aprovação") && value.includes("Preparação") && value.includes("Fila") &&
        value.includes("Publicação") && value.includes("Histórico") && node.id !== "addition_overview_content"
      ) node.remove();
    });
  }

  function normalizeAdditionOverview() {
    const card = $("#tab_panel_adicoes #addition_intro_card");
    if (!card) return false;

    addClass(card, "cs-standard-overview");
    const head = $(".addition-intro-head", card);
    addClass(head, "cs-standard-overview-heading");
    const copy = $(".addition-intro-copy", card);
    addClass(copy, "cs-standard-overview-copy");
    setText($(".section-title", copy), "Adicionar produtos");
    setText($(".small", copy), "Gerencie os produtos aprovados, prepare os dados e publique novos itens com segurança no WooCommerce.");

    const actions = $("#addition_intro_actions", card);
    addClass(actions, "cs-standard-overview-actions");
    const sync = $("#addition_sync_approved");
    if (actions && sync?.parentElement !== actions) actions.appendChild(sync);
    ensureOrdered(head, [copy, actions]);

    const content = ensureBlock(card, "addition_overview_content", "cs-addition-overview-body");
    addClass(content, "cs-addition-overview-body");
    const progress = locateAdditionProgress(card);
    if (progress) {
      addClass(progress, "cs-standard-overview-progress");
      const progressCopy = $(".addition-progress-copy,.cs-op-progress-copy", progress);
      const progressTrack = $(".addition-progress-track,.cs-op-progress-track", progress);
      const now = $(".addition-progress-now,[data-addition-progress-now],.cs-op-now", progress);
      addClass(progressCopy, "cs-op-progress-copy");
      addClass(progressTrack, "cs-op-progress-track");
      addClass(now, "cs-op-now");
      ensureOrdered(progress, [progressCopy, progressTrack, now]);
    }

    const grid = $("#addition_summary_grid", card) || $("#addition_summary_grid");
    $("#addition_guidance", card)?.remove();
    $("#addition_guidance")?.remove();
    ensureOrdered(content, [progress, grid]);
    removeAdditionFlow(card);
    ensureOrdered(card, [head, content]);
    return true;
  }

  function normalizeAll() {
    if (normalizing) return;
    normalizing = true;
    try {
      installStyles();
      normalizeUpdateOverview();
      normalizeAdditionOverview();
    } finally {
      normalizing = false;
    }
  }

  function schedule() {
    clearTimeout(scheduled);
    scheduled = setTimeout(normalizeAll, 30);
  }

  function observe() {
    [$("#tab_panel_atualizacoes"), $("#tab_panel_adicoes")].filter(Boolean).forEach(panel => {
      new MutationObserver(() => { if (!normalizing) schedule(); }).observe(panel, {childList:true, subtree:true});
    });
  }

  function start() {
    normalizeAll();
    observe();
    [80,220,500,900,1600,3000].forEach(delay => setTimeout(normalizeAll, delay));
    $("#tab_btn_atualizacoes")?.addEventListener("click", schedule, true);
    $("#tab_btn_adicoes")?.addEventListener("click", schedule, true);
    document.addEventListener("crapscraper:main-tab-changed", schedule, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
