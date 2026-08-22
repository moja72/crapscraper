(() => {
  "use strict";

  if (window.__crapScraperOperationalUiParityInstalled) return;
  window.__crapScraperOperationalUiParityInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);

  function installStyles() {
    if ($("#cs-operational-ui-parity-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-ui-parity-style";
    style.textContent = `
      #tab_panel_atualizacoes .cs-op-overview-card,
      #tab_panel_adicoes .cs-op-overview-card {
        display: grid;
        gap: 14px;
        padding: 18px;
      }

      #tab_panel_atualizacoes .cs-op-progress-copy,
      #tab_panel_adicoes .cs-op-progress-copy {
        display: flex;
        align-items: baseline;
        gap: 10px;
        margin: 0;
      }
      #tab_panel_atualizacoes .cs-op-progress-copy strong,
      #tab_panel_adicoes .cs-op-progress-copy strong {
        color: var(--text);
        font-size: 24px;
        line-height: 1;
        font-weight: 850;
        letter-spacing: -.02em;
        font-variant-numeric: tabular-nums;
      }
      #tab_panel_atualizacoes .cs-op-progress-copy span,
      #tab_panel_adicoes .cs-op-progress-copy span {
        color: var(--text-soft);
        font-size: 12px;
        font-weight: 750;
      }

      #tab_panel_atualizacoes .cs-op-progress-track,
      #tab_panel_adicoes .cs-op-progress-track {
        position: relative;
        width: 100%;
        height: 7px;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(255,255,255,.055);
      }
      #tab_panel_atualizacoes .cs-op-progress-track > span,
      #tab_panel_adicoes .cs-op-progress-track > span {
        display: block;
        width: 0;
        height: 100%;
        border-radius: inherit;
        background: var(--success);
        box-shadow: 0 0 16px rgba(16,185,129,.24);
        transition: width 220ms ease;
      }

      #tab_panel_atualizacoes .cs-op-now,
      #tab_panel_adicoes .cs-op-now {
        min-height: 36px;
        padding: 9px 11px;
        border: 1px solid rgba(255,255,255,.035);
        border-radius: 8px;
        background: rgba(255,255,255,.022);
        color: var(--text-muted);
        font-size: 12px;
        line-height: 1.4;
      }

      #tab_panel_adicoes .cs-addition-overview-body {
        display: grid;
        gap: 12px;
      }
      #tab_panel_adicoes .cs-addition-overview-body .addition-guidance {
        margin: 0;
      }
      #tab_panel_adicoes .cs-addition-overview-body .addition-summary-grid {
        grid-template-columns: repeat(5,minmax(0,1fr));
        gap: 8px;
      }
      #tab_panel_adicoes .cs-addition-overview-body .addition-summary-chip {
        min-height: 66px;
        padding: 10px 11px;
        text-align: left;
      }
      #tab_panel_adicoes .cs-addition-overview-body .addition-summary-chip strong {
        font-size: 20px;
      }
      #tab_panel_adicoes .cs-addition-overview-body .addition-flow-strip {
        margin: 0;
      }

      #tab_panel_atualizacoes .updates-queue-actions.cs-op-queue-primary-actions,
      #tab_panel_adicoes .cs-op-queue-primary-actions {
        display: grid;
        grid-template-columns: repeat(3,minmax(0,1fr));
        gap: 8px;
        width: 100%;
        margin: 12px 0;
      }
      #tab_panel_atualizacoes .updates-queue-actions.cs-op-queue-primary-actions > button,
      #tab_panel_adicoes .cs-op-queue-primary-actions > button {
        width: 100%;
        min-height: 42px;
      }
      #tab_panel_adicoes .addition-queue-heading-standard {
        min-height: auto;
        margin: 0 0 4px;
      }

      #tab_panel_atualizacoes .cs-op-overview-card .section-title,
      #tab_panel_adicoes .cs-op-overview-card .section-title {
        margin-bottom: 6px;
      }

      @media(max-width:980px) {
        #tab_panel_adicoes .cs-addition-overview-body .addition-summary-grid {
          grid-template-columns: repeat(3,minmax(0,1fr));
        }
      }
      @media(max-width:700px) {
        #tab_panel_atualizacoes .updates-queue-actions.cs-op-queue-primary-actions,
        #tab_panel_adicoes .cs-op-queue-primary-actions {
          grid-template-columns: 1fr;
        }
        #tab_panel_adicoes .cs-addition-overview-body .addition-summary-grid {
          grid-template-columns: repeat(2,minmax(0,1fr));
        }
      }
      @media(max-width:480px) {
        #tab_panel_adicoes .cs-addition-overview-body .addition-summary-grid {
          grid-template-columns: 1fr;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function standardizeUpdateOverview() {
    const card = $("#tab_panel_atualizacoes .updates-overview-card");
    if (card) card.classList.add("cs-op-overview-card");

    const progressPercent = $("#updates_progress_percent");
    const progressCopy = progressPercent?.parentElement;
    if (progressCopy) progressCopy.classList.add("cs-op-progress-copy");

    const progressBar = $("#updates_progress_bar");
    const progressTrack = progressBar?.parentElement;
    if (progressTrack) progressTrack.classList.add("cs-op-progress-track");

    $("#updates_now")?.classList.add("cs-op-now");
    $("#tab_panel_atualizacoes .updates-queue-actions")?.classList.add("cs-op-queue-primary-actions");
  }

  function mergeAdditionOverview() {
    const root = $("#addition_operational_root");
    const intro = $("#addition_intro_card", root || document);
    const summary = root?.querySelector(".addition-summary-card");
    if (!root || !intro || !summary) return false;

    intro.classList.add("cs-op-overview-card");
    const actions = $("#addition_intro_actions", intro);
    const sync = $("#addition_sync_approved");
    if (actions && sync && sync.parentElement !== actions) actions.appendChild(sync);

    let body = $("#addition_overview_content", intro);
    if (!body) {
      body = document.createElement("div");
      body.id = "addition_overview_content";
      body.className = "cs-addition-overview-body";
      intro.appendChild(body);
    }

    const progress = $("#addition_progress_block");
    const guidance = $("#addition_guidance");
    const grid = $("#addition_summary_grid");
    const flow = $(".addition-flow-strip", intro);
    [progress, guidance, grid, flow].filter(Boolean).forEach(node => body.appendChild(node));

    summary.remove();
    return true;
  }

  function standardizeAdditionQueue() {
    const accordion = $("#addition_queue_accordion");
    if (!accordion) return false;
    const heading = $(".updates-section-heading", accordion);
    const start = $("#addition_queue_start", accordion);
    const pause = $("#addition_queue_pause", accordion);
    const recover = $("#addition_queue_recover", accordion);
    if (!start || !pause || !recover) return false;

    if (heading) heading.classList.add("addition-queue-heading-standard");

    let actions = $("#addition_queue_primary_actions", accordion);
    if (!actions) {
      actions = document.createElement("div");
      actions.id = "addition_queue_primary_actions";
      actions.className = "cs-op-queue-primary-actions";
      if (heading) heading.insertAdjacentElement("afterend", actions);
      else accordion.prepend(actions);
    }
    [start, pause, recover].forEach(button => actions.appendChild(button));
    return true;
  }

  function runParity() {
    installStyles();
    standardizeUpdateOverview();
    mergeAdditionOverview();
    standardizeAdditionQueue();
  }

  function scheduleParity() {
    [0, 30, 90, 180, 420, 800].forEach(delay => window.setTimeout(runParity, delay));
  }

  installStyles();
  standardizeUpdateOverview();
  $("#tab_btn_atualizacoes")?.addEventListener("click", scheduleParity);
  $("#tab_btn_adicoes")?.addEventListener("click", scheduleParity);
  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
    if (key === "atualizacoes" || key === "adicoes") scheduleParity();
  });
  if (["atualizacoes", "adicoes"].includes(String(document.body?.dataset?.activeTab || ""))) scheduleParity();
})();
