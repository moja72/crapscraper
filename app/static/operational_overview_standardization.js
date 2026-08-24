(() => {
  "use strict";

  if (window.__crapScraperOperationalOverviewStandardizationInstalled) return;
  window.__crapScraperOperationalOverviewStandardizationInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();
  let normalizing = false;
  let scheduled = 0;

  function installStyles() {
    if ($("#cs-operational-overview-standardization-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-overview-standardization-style";
    style.textContent = `
      /* Contrato visual único do resumo de Atualizar e Adicionar. */
      #tab_panel_atualizacoes .updates-overview-card.cs-standard-overview,
      #tab_panel_adicoes #addition_intro_card.cs-standard-overview {
        display:grid!important;
        grid-template-columns:1fr!important;
        gap:14px!important;
        width:100%!important;
        padding:18px!important;
        border:1px solid var(--line)!important;
        border-radius:var(--radius-md)!important;
        background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,.01)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;
        box-sizing:border-box!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-heading,
      #tab_panel_adicoes .cs-standard-overview-heading {
        display:grid!important;
        grid-template-columns:minmax(0,1fr) auto!important;
        align-items:start!important;
        gap:18px!important;
        width:100%!important;
        margin:0!important;
        padding:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-copy,
      #tab_panel_adicoes .cs-standard-overview-copy {
        display:grid!important;
        gap:6px!important;
        min-width:0!important;
        margin:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-copy .section-title,
      #tab_panel_adicoes .cs-standard-overview-copy .section-title {
        margin:0!important;
        padding:0!important;
        font-size:16px!important;
        line-height:1.25!important;
        font-weight:800!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-copy .small,
      #tab_panel_adicoes .cs-standard-overview-copy .small {
        max-width:980px!important;
        margin:0!important;
        color:var(--text-muted)!important;
        font-size:12px!important;
        line-height:1.5!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-heading .cs-standard-overview-actions,
      #tab_panel_adicoes .cs-standard-overview-heading .cs-standard-overview-actions {
        display:flex!important;
        align-items:flex-start!important;
        justify-content:flex-end!important;
        gap:8px!important;
        margin:0!important;
        padding:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-heading .cs-standard-overview-actions>button,
      #tab_panel_adicoes .cs-standard-overview-heading .cs-standard-overview-actions>button {
        min-height:42px!important;
        margin:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress,
      #tab_panel_adicoes .cs-standard-overview-progress {
        display:grid!important;
        gap:7px!important;
        width:100%!important;
        margin:0!important;
        padding:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-copy,
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-copy,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-copy,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-copy {
        display:flex!important;
        align-items:baseline!important;
        gap:10px!important;
        width:100%!important;
        margin:0!important;
        padding:0!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-copy strong,
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-copy strong,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-copy strong,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-copy strong {
        margin:0!important;
        font-size:24px!important;
        line-height:1!important;
        font-weight:850!important;
        letter-spacing:-.02em!important;
        font-variant-numeric:tabular-nums!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-track,
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-track,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-track,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-track {
        position:relative!important;
        width:100%!important;
        height:6px!important;
        min-height:6px!important;
        margin:0!important;
        overflow:hidden!important;
        border:0!important;
        border-radius:999px!important;
        background:rgba(255,255,255,.06)!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-progress-track>span,
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-progress-track>span,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-progress-track>span,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-track>span {
        display:block!important;
        height:100%!important;
        border-radius:inherit!important;
        background:var(--success)!important;
      }

      #tab_panel_atualizacoes .cs-standard-overview-progress .cs-op-now,
      #tab_panel_atualizacoes .cs-standard-overview-progress .updates-now,
      #tab_panel_adicoes .cs-standard-overview-progress .cs-op-now,
      #tab_panel_adicoes .cs-standard-overview-progress .addition-progress-now,
      #tab_panel_adicoes .cs-standard-overview-progress [data-addition-progress-now] {
        display:flex!important;
        align-items:center!important;
        width:100%!important;
        min-height:36px!important;
        margin:0!important;
        padding:9px 11px!important;
        border:1px solid rgba(255,255,255,.045)!important;
        border-radius:8px!important;
        background:rgba(255,255,255,.022)!important;
        color:var(--text-muted)!important;
        font-size:12px!important;
        line-height:1.4!important;
        box-sizing:border-box!important;
      }

      /* Os cards vêm imediatamente depois do bloco de progresso/processamento. */
      #tab_panel_atualizacoes .cs-standard-overview>#updates_summary,
      #tab_panel_adicoes .cs-standard-overview>#addition_overview_content>#addition_summary_grid {
        order:auto!important;
        margin:2px 0 0!important;
      }

      /* Estados auxiliares continuam disponíveis, mas deixam de interromper a sequência principal. */
      #tab_panel_atualizacoes .cs-standard-overview>#updates_execution_lock,
      #tab_panel_adicoes .cs-standard-overview #addition_guidance {
        margin:0!important;
      }
      #tab_panel_adicoes .cs-standard-overview #addition_guidance {
        margin-top:0!important;
      }

      /* Removido por decisão de produto: o fluxo textual duplicava a navegação real. */
      #tab_panel_adicoes #addition_intro_card .addition-flow-strip {
        display:none!important;
      }

      @media(max-width:760px) {
        #tab_panel_atualizacoes .cs-standard-overview-heading,
        #tab_panel_adicoes .cs-standard-overview-heading {
          grid-template-columns:1fr!important;
        }
        #tab_panel_atualizacoes .cs-standard-overview-heading .cs-standard-overview-actions,
        #tab_panel_adicoes .cs-standard-overview-heading .cs-standard-overview-actions {
          justify-content:stretch!important;
        }
        #tab_panel_atualizacoes .cs-standard-overview-heading .cs-standard-overview-actions>button,
        #tab_panel_adicoes .cs-standard-overview-heading .cs-standard-overview-actions>button {
          width:100%!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureProgressContainer(card, id) {
    let block = $(`#${id}`, card);
    if (block) return block;
    block = document.createElement("div");
    block.id = id;
    block.className = "cs-standard-overview-progress";
    return block;
  }

  function progressPart(root, selectors) {
    for (const selector of selectors) {
      const node = $(selector, root);
      if (node) return node;
    }
    return null;
  }

  function normalizeUpdateOverview() {
    const card = $("#tab_panel_atualizacoes .updates-overview-card");
    const hero = $(".updates-hero", card || document);
    if (!card || !hero) return false;

    card.classList.add("cs-standard-overview");
    hero.classList.add("cs-standard-overview-heading");

    const copy = hero.firstElementChild;
    if (copy) {
      copy.classList.add("cs-standard-overview-copy");
      const title = $(".section-title", copy);
      const description = $(".small", copy);
      if (title && title.textContent !== "Atualiza produtos") title.textContent = "Atualiza produtos";
      if (description) description.textContent = "Prepare os produtos aprovados, revise os dados e execute as atualizações com segurança no WooCommerce.";
    }

    const refresh = $("#updates_refresh_btn", card);
    let actions = $("#updates_overview_actions", hero);
    if (!actions) {
      actions = document.createElement("div");
      actions.id = "updates_overview_actions";
      actions.className = "cs-standard-overview-actions";
      hero.appendChild(actions);
    }
    if (refresh && refresh.parentElement !== actions) actions.appendChild(refresh);

    const progress = ensureProgressContainer(card, "updates_overview_progress");
    progress.classList.add("cs-standard-overview-progress");
    const percent = $("#updates_progress_percent", card);
    const copyNode = percent?.parentElement || progressPart(card, [".updates-progress-copy", ".cs-op-progress-copy"]);
    const bar = $("#updates_progress_bar", card);
    const track = bar?.parentElement || progressPart(card, [".updates-progress-track", ".cs-op-progress-track"]);
    const now = $("#updates_now", card);
    [copyNode, track, now].filter(Boolean).forEach(node => progress.appendChild(node));
    if (copyNode) copyNode.classList.add("cs-op-progress-copy");
    if (track) track.classList.add("cs-op-progress-track");
    if (now) now.classList.add("cs-op-now");

    if (progress.parentElement !== card) hero.insertAdjacentElement("afterend", progress);
    else if (hero.nextElementSibling !== progress) hero.insertAdjacentElement("afterend", progress);

    const summary = $("#updates_summary", card);
    if (summary && progress.nextElementSibling !== summary) progress.insertAdjacentElement("afterend", summary);

    const lock = $("#updates_execution_lock", card);
    if (lock && summary && summary.nextElementSibling !== lock) summary.insertAdjacentElement("afterend", lock);

    return true;
  }

  function additionProgressBlock(card) {
    const explicit = $("#addition_progress_block", card);
    if (explicit) return explicit;

    const percent = progressPart(card, [
      "#addition_progress_percent",
      "[data-addition-progress-percent]",
      ".addition-progress-percent",
    ]);
    const copyNode = percent?.parentElement || progressPart(card, [".addition-progress-copy", ".cs-op-progress-copy"]);
    const bar = progressPart(card, ["#addition_progress_bar", "[data-addition-progress-bar]"]);
    const track = bar?.parentElement || progressPart(card, [".addition-progress-track", ".cs-op-progress-track"]);
    const now = progressPart(card, [
      "#addition_progress_now",
      "[data-addition-progress-now]",
      ".addition-progress-now",
      ".cs-op-now",
    ]);
    if (!copyNode && !track && !now) return null;

    const block = ensureProgressContainer(card, "addition_progress_block");
    [copyNode, track, now].filter(Boolean).forEach(node => block.appendChild(node));
    return block;
  }

  function removeAdditionFlow(card) {
    const flow = $(".addition-flow-strip", card);
    if (flow) flow.remove();

    /* Compatibilidade com versões legadas em que a faixa não tinha classe. */
    Array.from(card.children).forEach(node => {
      if (!(node instanceof HTMLElement)) return;
      const value = normalize(node.textContent);
      if (
        value.includes("Aprovação") && value.includes("Preparação") &&
        value.includes("Fila") && value.includes("Publicação") && value.includes("Histórico") &&
        node !== $("#addition_overview_content", card)
      ) node.remove();
    });
  }

  function normalizeAdditionOverview() {
    const card = $("#tab_panel_adicoes #addition_intro_card");
    if (!card) return false;

    card.classList.add("cs-standard-overview");
    const head = $(".addition-intro-head", card);
    if (head) head.classList.add("cs-standard-overview-heading");

    const copy = $(".addition-intro-copy", card);
    if (copy) {
      copy.classList.add("cs-standard-overview-copy");
      const title = $(".section-title", copy);
      const description = $(".small", copy);
      if (title && title.textContent !== "Adicionar produtos") title.textContent = "Adicionar produtos";
      if (description) description.textContent = "Gerencie os produtos aprovados, prepare os dados e publique novos itens com segurança no WooCommerce.";
    }

    const actions = $("#addition_intro_actions", card);
    if (actions) actions.classList.add("cs-standard-overview-actions");

    let content = $("#addition_overview_content", card);
    if (!content) {
      content = document.createElement("div");
      content.id = "addition_overview_content";
      content.className = "cs-addition-overview-body";
      card.appendChild(content);
    }

    const progress = additionProgressBlock(card);
    if (progress) {
      progress.classList.add("cs-standard-overview-progress");
      const copyNode = progressPart(progress, [".addition-progress-copy", ".cs-op-progress-copy"]);
      const track = progressPart(progress, [".addition-progress-track", ".cs-op-progress-track"]);
      const now = progressPart(progress, [".addition-progress-now", "[data-addition-progress-now]", ".cs-op-now"]);
      if (copyNode) copyNode.classList.add("cs-op-progress-copy");
      if (track) track.classList.add("cs-op-progress-track");
      if (now) now.classList.add("cs-op-now");
      content.appendChild(progress);
    }

    const grid = $("#addition_summary_grid", card) || $("#addition_summary_grid");
    if (grid) content.appendChild(grid);

    const guidance = $("#addition_guidance", card) || $("#addition_guidance");
    if (guidance) content.appendChild(guidance);

    removeAdditionFlow(card);
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
    window.clearTimeout(scheduled);
    scheduled = window.setTimeout(normalizeAll, 25);
  }

  function observePanels() {
    [$("#tab_panel_atualizacoes"), $("#tab_panel_adicoes")].filter(Boolean).forEach(panel => {
      const observer = new MutationObserver(schedule);
      observer.observe(panel, {childList:true, subtree:true});
    });
  }

  function start() {
    normalizeAll();
    observePanels();
    [80, 220, 550, 1100, 2200].forEach(delay => window.setTimeout(normalizeAll, delay));
    $("#tab_btn_atualizacoes")?.addEventListener("click", schedule, true);
    $("#tab_btn_adicoes")?.addEventListener("click", schedule, true);
    document.addEventListener("crapscraper:main-tab-changed", schedule, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
