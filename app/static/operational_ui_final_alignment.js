(() => {
  "use strict";

  if (window.__crapScraperOperationalUiFinalAlignmentInstalled) return;
  window.__crapScraperOperationalUiFinalAlignmentInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if ($("#cs-operational-ui-final-alignment-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-ui-final-alignment-style";
    style.textContent = `
      /* Atualizar é a referência visual final para os dois fluxos. */
      #tab_panel_atualizacoes,
      #tab_panel_adicoes {
        --cs-final-gap-xs:6px;
        --cs-final-gap-sm:10px;
        --cs-final-gap-md:12px;
        --cs-final-gap-lg:16px;
        --cs-final-control:42px;
      }

      #tab_panel_atualizacoes .cs-op-section,
      #tab_panel_adicoes .cs-op-section,
      #tab_panel_adicoes .addition-accordion {
        padding:16px 18px;
      }

      #tab_panel_atualizacoes .cs-op-section>summary,
      #tab_panel_adicoes .cs-op-section>summary,
      #tab_panel_adicoes .addition-accordion>summary,
      #tab_panel_atualizacoes .updates-technical-log>summary {
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        min-height:28px;
        padding:0;
        margin:0;
        list-style:none;
        outline:none;
      }
      #tab_panel_atualizacoes .cs-op-section>summary::-webkit-details-marker,
      #tab_panel_adicoes .cs-op-section>summary::-webkit-details-marker,
      #tab_panel_adicoes .addition-accordion>summary::-webkit-details-marker,
      #tab_panel_atualizacoes .updates-technical-log>summary::-webkit-details-marker { display:none; }

      #tab_panel_atualizacoes .cs-op-section[open]>summary,
      #tab_panel_adicoes .cs-op-section[open]>summary,
      #tab_panel_adicoes .addition-accordion[open]>summary { margin-bottom:8px; }

      #tab_panel_atualizacoes .cs-op-summary-left,
      #tab_panel_adicoes .cs-op-summary-left,
      #tab_panel_adicoes .addition-accordion-title {
        display:inline-flex;
        align-items:center;
        gap:8px;
        min-width:0;
        margin:0;
      }
      #tab_panel_atualizacoes .cs-op-summary-left .section-title,
      #tab_panel_adicoes .cs-op-summary-left .section-title,
      #tab_panel_adicoes .addition-accordion-title .section-title {
        margin:0;
        font-size:16px;
        line-height:1.2;
        font-weight:800;
      }
      #tab_panel_atualizacoes .updates-disclosure-chevron,
      #tab_panel_adicoes .updates-disclosure-chevron {
        flex:0 0 auto;
      }

      /* Filtros e buscas: mesma altura, grade e alinhamento. */
      #tab_panel_atualizacoes .cs-op-filterbar,
      #tab_panel_adicoes .cs-op-filterbar,
      #tab_panel_adicoes .addition-toolbar {
        display:grid!important;
        grid-template-columns:minmax(260px,1fr) minmax(180px,250px) auto;
        gap:12px!important;
        align-items:end!important;
        margin:12px 0 10px!important;
      }
      #tab_panel_adicoes .addition-toolbar .field,
      #tab_panel_adicoes .addition-toolbar label,
      #tab_panel_atualizacoes .cs-op-filterbar label {
        min-width:0;
      }
      #tab_panel_adicoes .addition-toolbar input,
      #tab_panel_adicoes .addition-toolbar select,
      #tab_panel_adicoes .addition-toolbar button,
      #tab_panel_atualizacoes .cs-op-filterbar input,
      #tab_panel_atualizacoes .cs-op-filterbar select,
      #tab_panel_atualizacoes .cs-op-filterbar button {
        min-height:var(--cs-final-control)!important;
      }

      /* Meta da listagem: seleção/contagem à esquerda e itens por página à direita. */
      #tab_panel_atualizacoes .cs-op-list-meta,
      #tab_panel_adicoes .cs-op-list-meta,
      #tab_panel_adicoes .addition-list-meta,
      #tab_panel_atualizacoes .listing-meta-row {
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:12px!important;
        flex-wrap:wrap!important;
        min-height:30px;
        margin:10px 0!important;
        color:var(--text-muted);
        font-size:11px;
      }
      #tab_panel_adicoes .addition-list-meta-left,
      #tab_panel_atualizacoes .cs-op-list-meta-left {
        display:flex;
        align-items:center;
        gap:10px;
        flex-wrap:wrap;
      }
      #tab_panel_atualizacoes .listing-page-size,
      #tab_panel_adicoes .listing-page-size,
      #tab_panel_atualizacoes .cs-op-page-size,
      #tab_panel_adicoes .cs-op-page-size {
        display:inline-flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:7px!important;
        margin:0!important;
        white-space:nowrap;
      }
      #tab_panel_atualizacoes .listing-page-size-input,
      #tab_panel_adicoes .listing-page-size-input {
        width:58px!important;
        min-width:58px!important;
        min-height:30px!important;
        padding:5px 8px!important;
        text-align:center!important;
      }

      /* Paginação: o mesmo componente real em Atualizar e Adicionar. */
      #tab_panel_atualizacoes .listing-pagination,
      #tab_panel_adicoes .addition-pagination,
      #tab_panel_atualizacoes .cs-op-pagination,
      #tab_panel_adicoes .cs-op-pagination {
        display:grid!important;
        grid-template-columns:minmax(180px,1fr) auto minmax(180px,1fr)!important;
        align-items:center!important;
        gap:12px!important;
        width:100%!important;
        margin:14px 0 0!important;
      }
      #tab_panel_atualizacoes .listing-pagination>button,
      #tab_panel_adicoes .addition-pagination>button,
      #tab_panel_atualizacoes .cs-op-pagination>button,
      #tab_panel_adicoes .cs-op-pagination>button {
        width:100%!important;
        min-width:0!important;
        min-height:var(--cs-final-control)!important;
        padding:9px 14px!important;
      }
      #tab_panel_atualizacoes .listing-pagination>button:first-child,
      #tab_panel_adicoes .addition-pagination>button:first-child { grid-column:1; justify-self:stretch; }
      #tab_panel_atualizacoes .listing-pagination>button:last-child,
      #tab_panel_adicoes .addition-pagination>button:last-child { grid-column:3; justify-self:stretch; }
      #tab_panel_atualizacoes .listing-pagination>.badge,
      #tab_panel_adicoes .addition-pagination>.badge,
      #tab_panel_atualizacoes .cs-op-page-jump,
      #tab_panel_adicoes .cs-op-page-jump {
        grid-column:2;
        display:inline-flex!important;
        align-items:center!important;
        justify-content:center!important;
        gap:6px!important;
        min-width:126px!important;
        min-height:34px!important;
        padding:5px 9px!important;
        margin:0!important;
        white-space:nowrap;
        text-align:center;
      }
      #tab_panel_atualizacoes .listing-pagination>.badge input,
      #tab_panel_adicoes .addition-pagination>.badge input,
      #tab_panel_atualizacoes .cs-op-page-jump input,
      #tab_panel_adicoes .cs-op-page-jump input {
        width:52px!important;
        min-width:52px!important;
        min-height:28px!important;
        padding:4px 7px!important;
        text-align:center!important;
        font-variant-numeric:tabular-nums;
      }

      /* Ações equivalentes. */
      #tab_panel_atualizacoes .cs-op-actions,
      #tab_panel_adicoes .cs-op-actions,
      #tab_panel_adicoes .addition-bulk-actions {
        display:flex!important;
        align-items:center!important;
        gap:8px!important;
        flex-wrap:wrap!important;
        margin:10px 0 14px!important;
      }
      #tab_panel_atualizacoes .cs-op-actions>button,
      #tab_panel_adicoes .cs-op-actions>button,
      #tab_panel_adicoes .addition-bulk-actions>button {
        min-height:42px!important;
      }

      /* Cabeçalho e densidade de tabela/lista. */
      #tab_panel_atualizacoes .cs-op-table-head,
      #tab_panel_adicoes .cs-op-table-head,
      #tab_panel_adicoes .addition-table-head {
        margin-top:8px;
        padding-top:8px;
        border-top:1px solid var(--line);
        background:rgba(255,255,255,.008);
      }
      #tab_panel_atualizacoes .update-job,
      #tab_panel_atualizacoes .update-queue-row,
      #tab_panel_adicoes .addition-op-row {
        min-height:72px;
        padding-top:12px;
        padding-bottom:12px;
        border-bottom:1px solid var(--line);
      }
      #tab_panel_atualizacoes .update-row-actions button,
      #tab_panel_atualizacoes .update-history-details,
      #tab_panel_adicoes .addition-op-actions button { min-height:34px; }

      /* Empty states equivalentes. */
      #tab_panel_atualizacoes .cs-op-empty,
      #tab_panel_atualizacoes .notice.cs-op-empty,
      #tab_panel_atualizacoes .updates-working-card .notice,
      #tab_panel_atualizacoes #updates_queue_jobs>.notice,
      #tab_panel_adicoes .cs-op-empty,
      #tab_panel_adicoes .addition-empty {
        display:grid!important;
        place-items:center!important;
        min-height:64px!important;
        padding:16px!important;
        border:1px dashed var(--line-strong)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.012)!important;
        color:var(--text-muted)!important;
        text-align:center!important;
        font-size:11px!important;
        line-height:1.45!important;
      }

      /* Logs: mesmo cabeçalho e mesma área técnica. */
      #tab_panel_atualizacoes .updates-technical-log .log-output,
      #tab_panel_adicoes .updates-technical-log .log-output {
        min-height:180px;
        max-height:360px;
        margin-top:12px;
      }
      #addition_technical_summary[hidden] { display:none!important; }

      @media(max-width:700px) {
        #tab_panel_atualizacoes .cs-op-filterbar,
        #tab_panel_adicoes .cs-op-filterbar,
        #tab_panel_adicoes .addition-toolbar {
          grid-template-columns:1fr!important;
        }

        #tab_panel_atualizacoes .listing-pagination,
        #tab_panel_adicoes .addition-pagination,
        #tab_panel_atualizacoes .cs-op-pagination,
        #tab_panel_adicoes .cs-op-pagination {
          grid-template-columns:1fr 1fr!important;
        }
        #tab_panel_atualizacoes .listing-pagination>.badge,
        #tab_panel_adicoes .addition-pagination>.badge,
        #tab_panel_atualizacoes .cs-op-page-jump,
        #tab_panel_adicoes .cs-op-page-jump {
          grid-column:1/-1!important;
          grid-row:1!important;
          justify-self:center!important;
        }
        #tab_panel_atualizacoes .listing-pagination>button:first-child,
        #tab_panel_adicoes .addition-pagination>button:first-child {
          grid-column:1!important;
          grid-row:2!important;
        }
        #tab_panel_atualizacoes .listing-pagination>button:last-child,
        #tab_panel_adicoes .addition-pagination>button:last-child {
          grid-column:2!important;
          grid-row:2!important;
        }
      }
      @media(max-width:480px) {
        #tab_panel_atualizacoes .listing-pagination,
        #tab_panel_adicoes .addition-pagination,
        #tab_panel_atualizacoes .cs-op-pagination,
        #tab_panel_adicoes .cs-op-pagination {
          grid-template-columns:1fr!important;
        }
        #tab_panel_atualizacoes .listing-pagination>.badge,
        #tab_panel_adicoes .addition-pagination>.badge,
        #tab_panel_atualizacoes .cs-op-page-jump,
        #tab_panel_adicoes .cs-op-page-jump,
        #tab_panel_atualizacoes .listing-pagination>button:first-child,
        #tab_panel_adicoes .addition-pagination>button:first-child,
        #tab_panel_atualizacoes .listing-pagination>button:last-child,
        #tab_panel_adicoes .addition-pagination>button:last-child {
          grid-column:1!important;
          grid-row:auto!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function classSections() {
    [
      "#updates_history_accordion",
      "#tab_panel_atualizacoes .updates-technical-log",
      "#addition_preparation_accordion",
      "#addition_queue_accordion",
      "#addition_history_accordion",
      "#addition_technical_accordion",
    ].forEach(selector => $(selector)?.classList.add("cs-op-section"));

    [
      "#addition_preparation_accordion .addition-toolbar",
      "#addition_queue_accordion .addition-toolbar",
      "#updates_queue_list_controls .updates-list-controls",
    ].forEach(selector => $(selector)?.classList.add("cs-op-filterbar"));

    [
      "#addition_preparation_accordion .addition-bulk-actions",
      "#addition_queue_accordion .addition-bulk-actions",
    ].forEach(selector => $(selector)?.classList.add("cs-op-actions"));

    [
      "#addition_preparation_accordion .addition-list-meta",
      "#addition_queue_accordion .addition-list-meta",
      "#addition_history_accordion .addition-list-meta",
    ].forEach(selector => $(selector)?.classList.add("cs-op-list-meta"));

    [
      "#addition_preparation_accordion .addition-pagination",
      "#addition_queue_accordion .addition-pagination",
      "#addition_history_accordion .addition-pagination",
      "#updates_queue_list_controls .listing-pagination",
      "#updates_history_accordion .listing-pagination",
    ].forEach(selector => $(selector)?.classList.add("cs-op-pagination"));

    [
      "#addition_preparation_page",
      "#addition_queue_page",
      "#addition_history_page",
      "#updates_queue_page",
      "#updates_history_page",
    ].forEach(selector => $(selector)?.classList.add("cs-op-page-jump"));

    $$("#tab_panel_atualizacoes .notice, #tab_panel_adicoes .addition-empty").forEach(node => {
      const value = normalize(node.textContent);
      if (value.startsWith("Nenhum ") || value.startsWith("Abra a aba")) node.classList.add("cs-op-empty");
    });
  }

  function normalizeSummary(summary, titleText = "", { hideMeta = false } = {}) {
    if (!summary) return;
    const chevron = $(".updates-disclosure-chevron", summary);
    const title = $(".section-title", summary) || $$(':scope > span', summary).find(node => node !== chevron && !node.classList.contains("small"));
    if (title && titleText) title.textContent = titleText;

    let left = $(".cs-op-summary-left", summary);
    if (!left) {
      left = document.createElement("span");
      left.className = "cs-op-summary-left";
      summary.prepend(left);
    }
    if (chevron && chevron.parentElement !== left) left.appendChild(chevron);
    if (title && title.parentElement !== left) left.appendChild(title);

    const meta = $(".small", summary);
    if (meta && hideMeta) {
      meta.textContent = "";
      meta.hidden = true;
    }
  }

  function normalizeAccordionsAndLogs() {
    normalizeSummary($("#updates_history_accordion > summary"));
    normalizeSummary($("#addition_preparation_accordion > summary"));
    normalizeSummary($("#addition_queue_accordion > summary"));
    normalizeSummary($("#addition_history_accordion > summary"));

    const updateLog = $("#tab_panel_atualizacoes .updates-technical-log");
    if (updateLog) {
      updateLog.classList.add("cs-op-section");
      normalizeSummary($("summary", updateLog), "Log técnico da atualização");
    }

    const additionLog = $("#addition_technical_accordion");
    if (additionLog) {
      additionLog.classList.add("cs-op-section");
      normalizeSummary($("summary", additionLog), "Log técnico das adições", { hideMeta:true });
    }
  }

  function dedupeUpdatePreparationEmpty() {
    const card = $("#tab_panel_atualizacoes .updates-working-card");
    if (!card) return;
    const seen = new Set();
    $$(".notice", card).forEach(node => {
      const key = normalize(node.textContent);
      if (!key) return;
      if (seen.has(key)) node.remove();
      else seen.add(key);
    });
  }

  function normalizeAdditionTechnicalSummary() {
    const meta = $("#addition_technical_summary");
    if (!meta) return;
    meta.textContent = "";
    meta.hidden = true;
  }

  function run() {
    installStyles();
    classSections();
    normalizeAccordionsAndLogs();
    normalizeAdditionTechnicalSummary();
    dedupeUpdatePreparationEmpty();
  }

  function schedule(delays = [0, 50, 150, 350, 750, 1500, 2500, 4000, 6000]) {
    delays.forEach(delay => window.setTimeout(run, delay));
  }

  installStyles();
  run();

  $("#tab_btn_atualizacoes")?.addEventListener("click", () => schedule());
  $("#tab_btn_adicoes")?.addEventListener("click", () => schedule());
  $("#updates_refresh_btn")?.addEventListener("click", () => schedule([0, 80, 250, 700]));

  document.addEventListener("click", event => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    if (target.closest([
      "#addition_preparation_accordion > summary",
      "#addition_queue_accordion > summary",
      "#addition_technical_accordion > summary",
      "#tab_panel_atualizacoes .updates-technical-log > summary",
      "#addition_preparation_refresh",
      "#addition_queue_refresh",
    ].join(","))) {
      schedule([0, 60, 180, 500, 1100]);
    }
  }, true);

  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
    if (key === "atualizacoes" || key === "adicoes") schedule();
  });

  if (["atualizacoes", "adicoes"].includes(String(document.body?.dataset?.activeTab || ""))) schedule();
})();
