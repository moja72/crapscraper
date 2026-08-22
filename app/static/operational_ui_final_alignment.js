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
      #tab_panel_atualizacoes .cs-op-section,
      #tab_panel_adicoes .cs-op-section {
        padding:16px 18px;
      }
      #tab_panel_atualizacoes .cs-op-section>summary,
      #tab_panel_adicoes .cs-op-section>summary {
        min-height:28px;
        padding:0;
        outline:none;
      }
      #tab_panel_atualizacoes .cs-op-section>summary:focus-visible,
      #tab_panel_adicoes .cs-op-section>summary:focus-visible {
        outline:2px solid var(--accent);
        outline-offset:4px;
        border-radius:8px;
      }
      #tab_panel_atualizacoes .cs-op-section[open]>summary,
      #tab_panel_adicoes .cs-op-section[open]>summary { margin-bottom:8px; }

      #tab_panel_atualizacoes .cs-op-filterbar,
      #tab_panel_adicoes .cs-op-filterbar,
      #tab_panel_atualizacoes .cs-op-history-toolbar,
      #tab_panel_adicoes .cs-op-history-toolbar {
        margin:12px 0 10px;
      }
      #tab_panel_atualizacoes .cs-op-filterbar input,
      #tab_panel_atualizacoes .cs-op-filterbar select,
      #tab_panel_atualizacoes .cs-op-filterbar button,
      #tab_panel_adicoes .cs-op-filterbar input,
      #tab_panel_adicoes .cs-op-filterbar select,
      #tab_panel_adicoes .cs-op-filterbar button,
      #tab_panel_atualizacoes .cs-op-history-toolbar input,
      #tab_panel_atualizacoes .cs-op-history-toolbar select,
      #tab_panel_atualizacoes .cs-op-history-toolbar button,
      #tab_panel_adicoes .cs-op-history-toolbar input,
      #tab_panel_adicoes .cs-op-history-toolbar select,
      #tab_panel_adicoes .cs-op-history-toolbar button {
        min-height:42px;
      }

      #tab_panel_atualizacoes .cs-op-actions,
      #tab_panel_adicoes .cs-op-actions { margin:8px 0 12px; }
      #tab_panel_atualizacoes .cs-op-actions>button,
      #tab_panel_adicoes .cs-op-actions>button { min-height:42px; }

      #tab_panel_atualizacoes .cs-op-list-meta,
      #tab_panel_adicoes .cs-op-list-meta { margin:8px 0 10px; }
      #tab_panel_atualizacoes .cs-op-pagination,
      #tab_panel_adicoes .cs-op-pagination { margin:14px 0 0; }
      #tab_panel_atualizacoes .cs-op-pagination>button,
      #tab_panel_adicoes .cs-op-pagination>button { min-height:42px; }

      #tab_panel_adicoes .cs-addition-overview-body .addition-summary-chip {
        justify-items:start;
        align-content:center;
        text-align:left;
        border-radius:10px;
      }

      /* Histórico de Adições usa exatamente a estrutura do Histórico de Atualizar. */
      #tab_panel_adicoes #addition_history_accordion .updates-history-toolbar {
        display:grid;
        grid-template-columns:minmax(0,1fr) auto;
        align-items:end;
        gap:12px;
      }
      #tab_panel_adicoes #addition_history_accordion .updates-history-filter-group {
        display:grid!important;
        grid-template-columns:minmax(260px,1fr) minmax(170px,.55fr) minmax(220px,.75fr);
        gap:12px!important;
        min-width:0;
      }
      #tab_panel_adicoes #addition_history_accordion .updates-history-actions {
        display:flex;
        align-items:end;
        justify-content:flex-end;
        gap:8px;
      }
      #tab_panel_adicoes #addition_history_tabs { margin-top:10px; }
      #tab_panel_adicoes #addition_history_rows {
        margin-top:10px;
        border:1px solid var(--line);
        border-radius:10px;
        overflow:hidden;
        background:rgba(255,255,255,.008);
      }
      #tab_panel_adicoes #addition_history_rows:has(.addition-empty) {
        border:0;
        background:transparent;
      }
      #tab_panel_adicoes .addition-history-row {
        margin:0;
        padding:13px 14px;
        border:0;
        border-bottom:1px solid var(--line);
        border-radius:0;
        background:transparent;
      }
      #tab_panel_adicoes .addition-history-row:last-child { border-bottom:0; }

      /* Mesma densidade de linhas, divisores e ações. */
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

      /* Mesmo empty-state. */
      #tab_panel_atualizacoes .cs-op-empty,
      #tab_panel_atualizacoes .notice.cs-op-empty,
      #tab_panel_adicoes .cs-op-empty,
      #tab_panel_adicoes .addition-empty {
        min-height:64px;
        padding:16px;
        border:1px dashed var(--line-strong);
        border-radius:10px;
        background:rgba(255,255,255,.012);
        color:var(--text-muted);
        text-align:center;
      }

      /* Logs equivalentes. */
      #tab_panel_atualizacoes .updates-technical-log .log-output,
      #tab_panel_adicoes .updates-technical-log .log-output {
        min-height:180px;
        max-height:360px;
        margin-top:12px;
      }

      @media(max-width:980px) {
        #tab_panel_adicoes #addition_history_accordion .updates-history-filter-group {
          grid-template-columns:1fr 1fr;
        }
        #tab_panel_adicoes #addition_history_accordion .updates-history-filter-group label:first-child {
          grid-column:1/-1;
        }
      }
      @media(max-width:700px) {
        #tab_panel_adicoes #addition_history_accordion .updates-history-toolbar,
        #tab_panel_adicoes #addition_history_accordion .updates-history-filter-group {
          grid-template-columns:1fr;
        }
        #tab_panel_adicoes #addition_history_accordion .updates-history-filter-group label:first-child {
          grid-column:auto;
        }
        #tab_panel_adicoes #addition_history_accordion .updates-history-actions {
          justify-content:stretch;
        }
        #tab_panel_adicoes #addition_history_accordion .updates-history-actions>button {
          flex:1 1 0;
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

    $$("#tab_panel_atualizacoes .notice, #tab_panel_adicoes .addition-empty").forEach(node => {
      const text = normalize(node.textContent);
      if (text.startsWith("Nenhum ") || text.startsWith("Abra a aba")) node.classList.add("cs-op-empty");
    });
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

  function syncHistoryTabs(value = $("#addition_history_state")?.value || "") {
    const completed = $("#addition_history_completed_tab");
    const errors = $("#addition_history_errors_tab");
    const normalized = String(value || "");
    if (completed) {
      const active = normalized === "completed";
      completed.classList.toggle("is-active", active);
      completed.setAttribute("aria-selected", String(active));
    }
    if (errors) {
      const active = normalized === "error";
      errors.classList.toggle("is-active", active);
      errors.setAttribute("aria-selected", String(active));
    }
  }

  function updateHistoryTabCounts(counts = {}) {
    const completed = $("#addition_history_completed_tab");
    const errors = $("#addition_history_errors_tab");
    if (completed) completed.textContent = `Concluídos (${Math.max(0, Number(counts.completed || 0))})`;
    if (errors) errors.textContent = `Erros (${Math.max(0, Number(counts.error || 0))})`;
  }

  window.__crapScraperSyncAdditionHistoryTabs = counts => {
    updateHistoryTabCounts(counts || {});
    syncHistoryTabs();
  };

  function activateHistoryFilter(status) {
    const select = $("#addition_history_state");
    if (!select) return;
    select.value = status;
    syncHistoryTabs(status);
    select.dispatchEvent(new Event("change", { bubbles:true }));
  }

  function standardizeAdditionHistory() {
    const accordion = $("#addition_history_accordion");
    if (!accordion) return false;
    const toolbar = $(".updates-history-toolbar", accordion);
    const filters = $(".updates-history-filter-group", accordion);
    const meta = $(".addition-list-meta", accordion);
    const pagination = $(".addition-pagination", accordion);
    const rows = $("#addition_history_rows", accordion);
    const select = $("#addition_history_state", accordion);
    if (!toolbar || !meta || !pagination || !rows || !select) return false;

    filters?.removeAttribute("style");
    toolbar.classList.add("cs-op-history-toolbar");
    filters?.classList.add("cs-op-history-filters");
    meta.classList.add("cs-op-list-meta");
    pagination.classList.add("cs-op-pagination");
    $("#addition_history_page")?.classList.add("cs-op-page-jump");

    let tabs = $("#addition_history_tabs", accordion);
    if (!tabs) {
      tabs = document.createElement("div");
      tabs.id = "addition_history_tabs";
      tabs.className = "updates-history-tabs cs-op-history-tabs";
      tabs.setAttribute("role", "tablist");
      tabs.setAttribute("aria-label", "Tipo de histórico de adições");
      tabs.innerHTML = `
        <button class="updates-history-tab" id="addition_history_completed_tab" role="tab" aria-selected="false" type="button">Concluídos (0)</button>
        <button class="updates-history-tab" id="addition_history_errors_tab" role="tab" aria-selected="false" type="button">Erros (0)</button>`;
      toolbar.insertAdjacentElement("afterend", tabs);
      $("#addition_history_completed_tab", tabs)?.addEventListener("click", () => activateHistoryFilter("completed"));
      $("#addition_history_errors_tab", tabs)?.addEventListener("click", () => activateHistoryFilter("error"));
    }

    if (pagination.previousElementSibling !== meta) meta.insertAdjacentElement("afterend", pagination);

    if (!select.dataset.csHistoryTabsBound) {
      select.dataset.csHistoryTabsBound = "1";
      select.addEventListener("change", () => syncHistoryTabs(select.value));
    }

    if (!accordion.dataset.csHistoryDefaultBound) {
      accordion.dataset.csHistoryDefaultBound = "1";
      accordion.addEventListener("toggle", () => {
        if (!accordion.open || accordion.dataset.csHistoryDefaultApplied === "1") return;
        accordion.dataset.csHistoryDefaultApplied = "1";
        if (!select.value) activateHistoryFilter("completed");
        else syncHistoryTabs(select.value);
      }, true);
    }

    syncHistoryTabs(select.value);
    return true;
  }

  function run() {
    installStyles();
    classSections();
    standardizeAdditionHistory();
    dedupeUpdatePreparationEmpty();
  }

  function schedule() {
    [0, 40, 120, 300, 700, 1400].forEach(delay => window.setTimeout(run, delay));
  }

  installStyles();
  $("#tab_btn_atualizacoes")?.addEventListener("click", schedule);
  $("#tab_btn_adicoes")?.addEventListener("click", schedule);
  $("#updates_refresh_btn")?.addEventListener("click", schedule);
  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
    if (key === "atualizacoes" || key === "adicoes") schedule();
  });
  if (["atualizacoes", "adicoes"].includes(String(document.body?.dataset?.activeTab || ""))) schedule();
})();
