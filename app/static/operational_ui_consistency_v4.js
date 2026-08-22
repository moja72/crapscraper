(() => {
  "use strict";

  if (window.__crapScraperOperationalUiConsistencyV4Installed) return;
  window.__crapScraperOperationalUiConsistencyV4Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  const UPDATE_TOP_FILTERS = Object.freeze({
    Total: {kind:"clear"},
    Aguardando: {kind:"preparation", value:"approved"},
    Preparados: {kind:"preparation", value:"prepared"},
    "Na fila": {kind:"queue", value:"queued"},
    Executando: {kind:"queue", value:"executing"},
    Concluídos: {kind:"history", tab:"completed"},
    Erros: {kind:"history", tab:"errors"},
  });

  const UPDATE_TOP_HELP = Object.freeze({
    Total: "Todos os produtos materializados para atualização. Clique para limpar os filtros operacionais.",
    Aguardando: "Produtos aprovados que ainda aguardam preparação. Clique para filtrar a Preparação.",
    Preparados: "Produtos preparados ou com plano pronto. Clique para filtrar a Preparação.",
    "Na fila": "Produtos na lista ativa aguardando execução. Clique para filtrar a Fila de atualização.",
    Executando: "Produtos atualmente em execução. Clique para filtrar a Fila de atualização.",
    Concluídos: "Atualizações concluídas. Clique para abrir o Histórico em Concluídos.",
    Erros: "Atualizações bloqueadas ou com falha. Clique para abrir o Histórico em Erros.",
  });

  let listSnapshot = null;
  let listLoading = false;
  let additionSummaryObserver = null;
  let updateSummaryObserver = null;
  let updateJobsObserver = null;

  function installStyles() {
    if ($("#cs-operational-ui-consistency-v4-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-ui-consistency-v4-style";
    style.textContent = `
      /* ===== Métricas compactas compartilhadas ===== */
      #updates_summary,
      #addition_summary_grid,
      #cs_update_operational_summary {
        display:grid!important;
        grid-template-columns:repeat(7,minmax(0,1fr))!important;
        gap:8px!important;
        margin:12px 0 0!important;
        padding:0!important;
        border:0!important;
        background:transparent!important;
      }
      #addition_summary_grid { grid-template-columns:repeat(5,minmax(0,1fr))!important; }
      #cs_update_operational_summary { grid-template-columns:repeat(6,minmax(0,1fr))!important; }

      #updates_summary>.cs-v4-metric-card,
      #addition_summary_grid .addition-summary-chip,
      #cs_update_operational_summary .cs-update-operational-chip {
        position:relative!important;
        display:flex!important;
        flex-direction:column!important;
        justify-content:center!important;
        align-items:stretch!important;
        gap:4px!important;
        width:100%!important;
        min-width:0!important;
        min-height:64px!important;
        padding:9px 10px!important;
        border:1px solid var(--line)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.022)!important;
        color:var(--text)!important;
        text-align:left!important;
        font:inherit!important;
        box-shadow:none!important;
        transform:none!important;
        overflow:visible!important;
      }
      #updates_summary>.cs-v4-metric-card[role="button"],
      #addition_summary_grid .addition-summary-chip[role="button"],
      #addition_summary_grid button.addition-summary-chip,
      #cs_update_operational_summary button.cs-update-operational-chip { cursor:pointer!important; }
      #updates_summary>.cs-v4-metric-card[role="button"]:hover,
      #addition_summary_grid .addition-summary-chip[role="button"]:hover,
      #addition_summary_grid button.addition-summary-chip:hover,
      #cs_update_operational_summary button.cs-update-operational-chip:hover {
        border-color:var(--line-accent)!important;
        background:var(--accent-soft)!important;
      }
      #updates_summary>.cs-v4-metric-card.is-filter-active,
      #addition_summary_grid .addition-summary-chip.is-filter-active,
      #cs_update_operational_summary .cs-update-operational-chip.is-filter-active {
        border-color:rgba(124,58,237,.85)!important;
        background:linear-gradient(180deg,rgba(124,58,237,.20),rgba(124,58,237,.10))!important;
        box-shadow:inset 0 0 0 1px rgba(143,91,255,.20)!important;
      }
      #updates_summary>.cs-v4-metric-card>strong,
      #addition_summary_grid .addition-summary-chip>strong,
      #cs_update_operational_summary .cs-update-operational-chip>strong {
        margin:0!important;
        color:var(--text)!important;
        font-size:18px!important;
        font-weight:800!important;
        line-height:1!important;
        font-variant-numeric:tabular-nums;
      }
      #updates_summary .cs-v4-metric-footer,
      #addition_summary_grid .operational-summary-footer,
      #cs_update_operational_summary .operational-summary-footer {
        display:flex!important;
        align-items:center!important;
        justify-content:flex-start!important;
        gap:5px!important;
        min-width:0;
        margin-top:2px!important;
      }
      #updates_summary .cs-v4-metric-label,
      #addition_summary_grid .operational-summary-label,
      #cs_update_operational_summary .operational-summary-label {
        min-width:0;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:650!important;
        line-height:1.2!important;
      }
      #updates_summary .comparison-help,
      #addition_summary_grid .operational-summary-help,
      #cs_update_operational_summary .operational-summary-help {
        flex:0 0 22px!important;
        width:22px!important;min-width:22px!important;max-width:22px!important;
        height:22px!important;min-height:22px!important;max-height:22px!important;
        padding:0!important;font-size:10px!important;
      }

      /* ===== Preparação: mesma anatomia nos dois fluxos ===== */
      #tab_panel_atualizacoes .updates-working-card.cs-v4-preparation {
        padding:16px 18px!important;
      }
      #tab_panel_atualizacoes .cs-v4-preparation-head,
      #tab_panel_adicoes #addition_preparation_accordion>summary {
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:12px!important;
      }
      #tab_panel_atualizacoes .cs-v4-preparation-head .section-title { margin:0!important; }
      #tab_panel_atualizacoes .cs-v4-preparation-summary,
      #tab_panel_adicoes #addition_preparation_summary {
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:600!important;
        white-space:nowrap;
      }
      #tab_panel_atualizacoes .cs-v4-preparation-hint,
      #tab_panel_adicoes #addition_preparation_accordion>.small {
        display:block!important;
        margin:8px 0 10px!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        line-height:1.45!important;
      }
      #tab_panel_atualizacoes .updates-working-card .updates-filters.cs-v4-preparation-filters {
        display:grid!important;
        grid-template-columns:minmax(300px,1fr) minmax(180px,230px) auto!important;
        gap:10px!important;
        align-items:end!important;
        margin:10px 0!important;
      }
      #tab_panel_atualizacoes .cs-v4-preparation-advanced {
        display:grid!important;
        grid-template-columns:repeat(2,minmax(190px,1fr)) auto!important;
        gap:10px!important;
        align-items:end!important;
        margin:0 0 8px!important;
      }
      #tab_panel_atualizacoes .cs-v4-preparation-refresh { min-height:42px!important; }
      #tab_panel_atualizacoes .updates-working-card .listing-meta-row,
      #tab_panel_adicoes #addition_preparation_accordion .addition-list-meta { margin:8px 0 10px!important; }
      #tab_panel_atualizacoes .updates-working-card .listing-pagination,
      #tab_panel_adicoes #addition_preparation_accordion .addition-pagination { margin-top:12px!important; }

      /* ===== Filas: cabeçalho/lista ativa/ações/filtros equivalentes ===== */
      #tab_panel_adicoes #addition_queue_accordion .cs-v4-queue-management,
      #tab_panel_atualizacoes .updates-queue-section .catalog-management-head {
        display:flex!important;
        align-items:flex-start!important;
        justify-content:space-between!important;
        gap:12px!important;
        margin:8px 0 10px!important;
      }
      #tab_panel_adicoes .cs-v4-queue-selector,
      #tab_panel_atualizacoes .updates-queue-selector {
        display:grid!important;
        grid-template-columns:minmax(240px,360px) minmax(0,1fr)!important;
        gap:12px!important;
        align-items:end!important;
        margin:8px 0 10px!important;
      }
      #tab_panel_adicoes .cs-v4-queue-selector label,
      #tab_panel_atualizacoes .updates-queue-selector label {
        display:grid!important;gap:6px!important;min-width:0!important;
        color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;
      }
      #tab_panel_adicoes #addition_queue_list_select,
      #tab_panel_atualizacoes #updates_queue_select { min-height:42px!important; }
      #tab_panel_adicoes #addition_queue_list_checkpoint,
      #tab_panel_atualizacoes #updates_queue_checkpoint {
        align-self:center!important;color:var(--text-muted)!important;font-size:11px!important;
      }
      #tab_panel_adicoes #addition_queue_accordion .updates-section-heading,
      #tab_panel_atualizacoes .updates-queue-actions.operational-action-grid {
        margin:10px 0!important;
      }
      #tab_panel_adicoes #addition_queue_accordion .addition-toolbar,
      #tab_panel_atualizacoes #updates_queue_list_controls .updates-list-controls {
        margin:10px 0 8px!important;
      }
      #tab_panel_adicoes #addition_queue_accordion .addition-list-meta,
      #tab_panel_atualizacoes #updates_queue_list_controls .cs-op-list-meta { margin:6px 0 8px!important; }
      #tab_panel_adicoes #addition_queue_accordion .addition-pagination,
      #tab_panel_atualizacoes #updates_queue_list_controls .listing-pagination { margin:12px 0 0!important; }

      /* ===== Histórico: Atualizar é a referência ===== */
      #tab_panel_adicoes #addition_history_accordion { padding:16px 18px!important; }
      #tab_panel_adicoes #addition_history_accordion>.small.cs-v4-history-description { display:none!important; }
      #tab_panel_adicoes #addition_history_accordion .updates-history-toolbar {
        margin:12px 0 10px!important;
      }
      #tab_panel_adicoes #addition_history_tabs,
      #tab_panel_atualizacoes .updates-history-tabs {
        display:flex!important;
        align-items:flex-end!important;
        gap:4px!important;
        margin:10px 0 8px!important;
        border-bottom:1px solid var(--line)!important;
      }
      #tab_panel_adicoes #addition_history_tabs .updates-history-tab,
      #tab_panel_atualizacoes .updates-history-tab {
        min-height:40px!important;
        padding:8px 14px!important;
        border:1px solid var(--line)!important;
        border-bottom-color:transparent!important;
        border-radius:9px 9px 0 0!important;
        background:rgba(255,255,255,.025)!important;
        color:var(--text-muted)!important;
        font-weight:800!important;
        box-shadow:none!important;
      }
      #tab_panel_adicoes #addition_history_tabs .updates-history-tab.is-active,
      #tab_panel_atualizacoes .updates-history-tab.is-active {
        border-color:var(--accent)!important;
        border-bottom-color:var(--bg-elev-1)!important;
        background:linear-gradient(180deg,rgba(124,58,237,.17),rgba(124,58,237,.08))!important;
        color:var(--text)!important;
      }
      #tab_panel_adicoes #addition_history_refresh { display:none!important; }
      #tab_panel_adicoes #addition_history_delete { min-height:42px!important; }

      /* ===== Modal de listas de Adições ===== */
      #addition_lists_modal {
        position:fixed;inset:0;z-index:180500;display:none;align-items:center;justify-content:center;
        padding:20px;background:rgba(0,0,0,.76);
      }
      #addition_lists_modal.is-open { display:flex; }
      #addition_lists_modal .cs-v4-list-modal-card {
        width:min(920px,96vw);max-height:90vh;overflow:auto;padding:18px;
        border:1px solid var(--line-strong);border-radius:18px;background:#0c0c0e;
        box-shadow:0 24px 80px rgba(0,0,0,.55);
      }
      #addition_lists_modal .cs-v4-list-modal-head {
        display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px;
      }
      #addition_lists_modal .cs-v4-list-create {
        display:grid;grid-template-columns:minmax(220px,1fr) auto;gap:8px;margin-bottom:14px;
      }
      #addition_lists_modal .cs-v4-list-row {
        display:grid;grid-template-columns:minmax(180px,1fr) auto;gap:12px;align-items:center;
        padding:12px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.018);margin-bottom:8px;
      }
      #addition_lists_modal .cs-v4-list-name { font-weight:800; }
      #addition_lists_modal .cs-v4-list-meta { margin-top:3px;color:var(--text-muted);font-size:11px; }
      #addition_lists_modal .cs-v4-list-actions { display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end; }
      #addition_lists_modal .cs-v4-list-move {
        display:grid;grid-template-columns:minmax(200px,1fr) auto;gap:8px;align-items:end;
        margin-top:14px;padding-top:14px;border-top:1px solid var(--line);
      }

      @media(max-width:1180px){
        #updates_summary{grid-template-columns:repeat(4,minmax(0,1fr))!important}
        #addition_summary_grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
      }
      @media(max-width:760px){
        #updates_summary,#addition_summary_grid,#cs_update_operational_summary{grid-template-columns:repeat(2,minmax(0,1fr))!important}
        #tab_panel_atualizacoes .updates-working-card .updates-filters.cs-v4-preparation-filters,
        #tab_panel_atualizacoes .cs-v4-preparation-advanced,
        #tab_panel_adicoes .cs-v4-queue-selector,
        #tab_panel_atualizacoes .updates-queue-selector,
        #addition_lists_modal .cs-v4-list-create,
        #addition_lists_modal .cs-v4-list-move { grid-template-columns:1fr!important; }
        #addition_lists_modal .cs-v4-list-row { grid-template-columns:1fr!important; }
        #addition_lists_modal .cs-v4-list-actions { justify-content:flex-start; }
      }
      @media(max-width:480px){
        #updates_summary,#addition_summary_grid,#cs_update_operational_summary{grid-template-columns:1fr!important}
      }
    `;
    document.head.appendChild(style);
  }

  function helpMarkup(label, tooltip) {
    return `<button type="button" class="comparison-help" aria-label="Ajuda sobre ${esc(label)}" data-tooltip="${esc(tooltip)}">?</button>`;
  }

  function updateTopLabel(card) {
    return normalize(card.querySelector("span")?.childNodes?.[0]?.textContent || card.querySelector("span")?.textContent || "").replace(/\?$/, "").trim();
  }

  function ensureUpdateTopCards() {
    const root = $("#updates_summary");
    if (!root) return false;
    $$(':scope > div', root).forEach(card => {
      const label = updateTopLabel(card);
      if (!label) return;
      card.classList.add("cs-v4-metric-card");
      card.dataset.metricLabel = label;
      card.setAttribute("role", "button");
      card.tabIndex = 0;
      const strong = $("strong", card);
      const oldSpan = $("span", card);
      if (oldSpan && !$(".cs-v4-metric-footer", card)) {
        const oldHelp = $(".comparison-help", oldSpan);
        oldHelp?.remove();
        const footer = document.createElement("span");
        footer.className = "cs-v4-metric-footer";
        const labelNode = document.createElement("span");
        labelNode.className = "cs-v4-metric-label";
        labelNode.textContent = label;
        footer.appendChild(labelNode);
        footer.insertAdjacentHTML("beforeend", helpMarkup(label, UPDATE_TOP_HELP[label] || "Informação sobre este estado da atualização."));
        oldSpan.replaceWith(footer);
      }
      if (strong) strong.classList.add("operational-summary-value");
      if (card.dataset.v4ClickBound !== "1") {
        card.dataset.v4ClickBound = "1";
        const activate = event => {
          if (event?.target?.closest?.(".comparison-help")) return;
          applyUpdateTopFilter(label);
        };
        card.addEventListener("click", activate);
        card.addEventListener("keydown", event => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          activate(event);
        });
      }
      $(".comparison-help", card)?.addEventListener("click", event => {
        event.preventDefault();event.stopPropagation();
      }, {once:true});
    });
    syncUpdateTopActive();
    return true;
  }

  function setSelectValue(id, value) {
    const node = $(`#${id}`);
    if (!node) return false;
    node.value = value;
    node.dispatchEvent(new Event("change", {bubbles:true}));
    return true;
  }

  function applyUpdateTopFilter(label) {
    const action = UPDATE_TOP_FILTERS[label];
    if (!action) return;
    if (action.kind === "clear") {
      ["updates_status_filter","updates_queue_status_filter","updates_history_status_filter"].forEach(id => setSelectValue(id, ""));
      syncUpdateTopActive();
      return;
    }
    if (action.kind === "preparation") {
      setSelectValue("updates_status_filter", action.value);
      $("#tab_panel_atualizacoes .updates-working-card")?.scrollIntoView({behavior:"smooth",block:"start"});
    } else if (action.kind === "queue") {
      setSelectValue("updates_queue_status_filter", action.value);
      $("#tab_panel_atualizacoes .updates-queue-section")?.scrollIntoView({behavior:"smooth",block:"start"});
    } else if (action.kind === "history") {
      const history = $("#updates_history_accordion");
      if (history) history.open = true;
      const tab = action.tab === "errors" ? $("#updates_history_errors") : $("#updates_history_completed");
      tab?.click();
      history?.scrollIntoView({behavior:"smooth",block:"start"});
    }
    window.setTimeout(syncUpdateTopActive, 50);
  }

  function syncUpdateTopActive() {
    const root = $("#updates_summary");
    if (!root) return;
    const prep = normalize($("#updates_status_filter")?.value);
    const queue = normalize($("#updates_queue_status_filter")?.value);
    const history = $("#updates_history_accordion");
    const historyCompleted = $("#updates_history_completed")?.classList.contains("is-active");
    const historyErrors = $("#updates_history_errors")?.classList.contains("is-active");
    $$(":scope > .cs-v4-metric-card", root).forEach(card => {
      const label = card.dataset.metricLabel || "";
      const action = UPDATE_TOP_FILTERS[label];
      let active = false;
      if (action?.kind === "clear") active = !prep && !queue && !history?.open;
      if (action?.kind === "preparation") active = prep === action.value;
      if (action?.kind === "queue") active = queue === action.value;
      if (action?.kind === "history") active = Boolean(history?.open && (action.tab === "errors" ? historyErrors : historyCompleted));
      card.classList.toggle("is-filter-active", active);
    });
  }

  function observeMetricContainers() {
    const updateRoot = $("#updates_summary");
    if (updateRoot && !updateSummaryObserver) {
      updateSummaryObserver = new MutationObserver(() => ensureUpdateTopCards());
      updateSummaryObserver.observe(updateRoot, {childList:true});
    }
    const additionRoot = $("#addition_summary_grid");
    if (additionRoot && !additionSummaryObserver) {
      additionSummaryObserver = new MutationObserver(() => {
        additionRoot.classList.add("operational-summary-grid");
      });
      additionSummaryObserver.observe(additionRoot, {childList:true});
    }
  }

  function labelFor(control, label) {
    const wrapper = control?.closest("label");
    if (!wrapper) return;
    const textNodes = Array.from(wrapper.childNodes).filter(node => node.nodeType === Node.TEXT_NODE);
    if (textNodes.length) textNodes[0].textContent = label;
  }

  function standardizeUpdatePreparation() {
    const card = $("#tab_panel_atualizacoes .updates-working-card");
    if (!card) return false;
    card.classList.add("cs-v4-preparation");
    const title = $("#updates_working_title", card);
    if (title && !$(".cs-v4-preparation-head", card)) {
      const head = document.createElement("div");
      head.className = "cs-v4-preparation-head";
      title.insertAdjacentElement("beforebegin", head);
      head.appendChild(title);
      const summary = document.createElement("span");
      summary.className = "cs-v4-preparation-summary";
      summary.id = "cs_v4_update_preparation_summary";
      head.appendChild(summary);
      const hint = document.createElement("div");
      hint.className = "cs-v4-preparation-hint";
      hint.textContent = "Revise os itens aprovados, filtre o que precisa de atenção e prepare os dados antes de enviá-los para a fila de atualização.";
      head.insertAdjacentElement("afterend", hint);
    }

    const filters = $(".updates-filters", card);
    const search = $("#updates_search_filter", filters);
    const state = $("#updates_status_filter", filters);
    const version = $("#updates_version_filter", filters);
    const relationship = $("#updates_relationship_filter", filters);
    const clear = $("#updates_clear_filters", filters);
    if (filters && search && state && version && relationship && clear && filters.dataset.v4Prepared !== "1") {
      filters.dataset.v4Prepared = "1";
      filters.classList.add("cs-v4-preparation-filters");
      const searchLabel = search.closest("label");
      const stateLabel = state.closest("label");
      labelFor(search, "Buscar");labelFor(state, "Estado");
      if (searchLabel) filters.appendChild(searchLabel);
      if (stateLabel) filters.appendChild(stateLabel);
      const refresh = document.createElement("button");
      refresh.type = "button";refresh.className = "btn-secondary cs-v4-preparation-refresh";refresh.textContent = "Atualizar";
      refresh.addEventListener("click", () => $("#updates_refresh_btn")?.click());
      filters.appendChild(refresh);
      const advanced = document.createElement("div");
      advanced.className = "cs-v4-preparation-advanced";
      const versionLabel = version.closest("label");
      const relationshipLabel = relationship.closest("label");
      if (versionLabel) advanced.appendChild(versionLabel);
      if (relationshipLabel) advanced.appendChild(relationshipLabel);
      advanced.appendChild(clear);
      filters.insertAdjacentElement("afterend", advanced);
    }
    updatePreparationSummary();
    dedupePreparationNotices();
    return true;
  }

  function updatePreparationSummary() {
    const target = $("#cs_v4_update_preparation_summary");
    const source = $("#updates_found_count");
    if (target) target.textContent = normalize(source?.textContent || "0 itens");
  }

  function dedupePreparationNotices() {
    const card = $("#tab_panel_atualizacoes .updates-working-card");
    if (!card) return;
    const seen = new Set();
    $$(".notice", card).forEach(node => {
      const key = normalize(node.textContent).toLowerCase();
      if (!key) return;
      if (seen.has(key)) node.hidden = true;
      else { seen.add(key); node.hidden = false; }
    });
  }

  function observeUpdateJobs() {
    const jobs = $("#updates_jobs");
    if (!jobs || updateJobsObserver) return;
    updateJobsObserver = new MutationObserver(() => {
      window.setTimeout(() => { updatePreparationSummary();dedupePreparationNotices(); }, 0);
    });
    updateJobsObserver.observe(jobs, {childList:true});
  }

  function queueManagementMarkup() {
    return `
      <div class="cs-v4-queue-management">
        <div><div class="small">Organize os produtos em listas independentes e defina qual lista será executada.</div></div>
        <button class="btn-secondary catalog-management-button" id="open_addition_lists_modal" type="button">Gerenciar Listas de Adições</button>
      </div>
      <div class="cs-v4-queue-selector">
        <label>Lista ativa<select id="addition_queue_list_select"><option value="default">Padrão</option></select></label>
        <span class="small" id="addition_queue_list_checkpoint">Carregando lista ativa…</span>
      </div>`;
  }

  function ensureAdditionQueueManagement() {
    const queue = $("#addition_queue_accordion");
    if (!queue) return false;
    const summary = $("summary", queue);
    if (!$("#addition_queue_list_select", queue) && summary) summary.insertAdjacentHTML("afterend", queueManagementMarkup());
    if (!$("#addition_lists_modal")) document.body.insertAdjacentHTML("beforeend", listModalMarkup());
    bindListUiOnce();
    return true;
  }

  function listModalMarkup() {
    return `<div id="addition_lists_modal" aria-hidden="true">
      <div class="cs-v4-list-modal-card" role="dialog" aria-modal="true" aria-labelledby="addition_lists_title">
        <div class="cs-v4-list-modal-head"><div><div class="section-title" id="addition_lists_title">Listas de Adições</div><div class="small">Crie listas, troque a lista ativa e mova itens selecionados sem misturar operações.</div></div><button class="btn-secondary" id="addition_lists_close" type="button">Fechar</button></div>
        <div class="cs-v4-list-create"><input id="addition_list_new_name" type="text" maxlength="60" placeholder="Nome da nova lista"><button class="btn-success" id="addition_list_create" type="button">Criar lista</button></div>
        <div id="addition_lists_rows"></div>
        <div class="cs-v4-list-move"><label class="field">Mover selecionados da fila<select id="addition_list_move_target"></select></label><button class="btn-secondary" id="addition_list_move_selected" type="button">Mover selecionados</button></div>
      </div>
    </div>`;
  }

  async function apiJson(url, options = {}, timeoutMs = 12000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        cache:"no-store",credentials:"same-origin",
        headers:{...(options.body?{"Content-Type":"application/json"}:{}),...(options.headers||{})},
        ...options,signal:controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      return payload;
    } finally { window.clearTimeout(timer); }
  }

  async function loadAdditionLists({openModal=false}={}) {
    if (listLoading) return;
    listLoading = true;
    try {
      listSnapshot = await apiJson("/adicoes/fila/listas");
      renderAdditionLists();
      if (openModal) openAdditionListsModal();
    } catch (error) {
      const checkpoint = $("#addition_queue_list_checkpoint");
      if (checkpoint) checkpoint.textContent = `Falha ao carregar listas: ${normalize(error?.message)}`;
    } finally { listLoading = false; }
  }

  function renderAdditionLists() {
    if (!listSnapshot) return;
    const select = $("#addition_queue_list_select");
    const queues = Array.isArray(listSnapshot.queues) ? listSnapshot.queues : [];
    if (select) {
      const current = String(listSnapshot.active_queue || "default");
      select.innerHTML = queues.map(row => `<option value="${esc(row.name)}">${esc(row.label || row.name)}</option>`).join("");
      select.value = current;
    }
    const active = queues.find(row => row.name === listSnapshot.active_queue) || {};
    const checkpoint = $("#addition_queue_list_checkpoint");
    if (checkpoint) checkpoint.textContent = `${listSnapshot.active_label || "Padrão"} · ${active.total || 0} itens · ${active.completed || 0} concluídos`;

    const rows = $("#addition_lists_rows");
    if (rows) rows.innerHTML = queues.map(row => `<div class="cs-v4-list-row" data-list-name="${esc(row.name)}"><div><div class="cs-v4-list-name">${esc(row.label || row.name)}${row.name===listSnapshot.active_queue?' <span class="badge">Ativa</span>':''}</div><div class="cs-v4-list-meta">${row.total||0} itens · ${row.queued||0} na fila · ${row.executing||0} executando · ${row.completed||0} concluídos · ${row.errors||0} erros</div></div><div class="cs-v4-list-actions"><button class="btn-secondary btn-sm" data-list-action="select" type="button" ${row.name===listSnapshot.active_queue?'disabled':''}>Ativar</button><button class="btn-secondary btn-sm" data-list-action="rename" type="button" ${row.name==='default'?'disabled':''}>Renomear</button><button class="btn-danger btn-sm" data-list-action="delete" type="button" ${row.name==='default'||row.name===listSnapshot.active_queue?'disabled':''}>Excluir</button></div></div>`).join("");
    const move = $("#addition_list_move_target");
    if (move) move.innerHTML = queues.map(row => `<option value="${esc(row.name)}">${esc(row.label || row.name)}</option>`).join("");
  }

  async function listAction(payload) {
    const result = await apiJson("/adicoes/fila/listas", {method:"POST",body:JSON.stringify(payload)});
    listSnapshot = result;
    renderAdditionLists();
    refreshAdditionOperationalViews();
    return result;
  }

  function refreshAdditionOperationalViews() {
    $("#addition_preparation_refresh")?.click();
    $("#addition_queue_refresh")?.click();
    window.setTimeout(() => $("#addition_history_refresh")?.click(), 80);
  }

  function openAdditionListsModal() {
    const modal = $("#addition_lists_modal");
    if (!modal) return;
    modal.classList.add("is-open");modal.setAttribute("aria-hidden","false");
  }
  function closeAdditionListsModal() {
    const modal = $("#addition_lists_modal");
    if (!modal) return;
    modal.classList.remove("is-open");modal.setAttribute("aria-hidden","true");
  }

  function bindListUiOnce() {
    const select = $("#addition_queue_list_select");
    if (select && select.dataset.boundV4 !== "1") {
      select.dataset.boundV4 = "1";
      select.addEventListener("change", async event => {
        try { await listAction({action:"select",name:event.target.value}); }
        catch (error) { alert(normalize(error?.message) || "Não foi possível trocar a lista."); await loadAdditionLists(); }
      });
    }
    const open = $("#open_addition_lists_modal");
    if (open && open.dataset.boundV4 !== "1") {
      open.dataset.boundV4 = "1";open.addEventListener("click", () => loadAdditionLists({openModal:true}));
    }
    const close = $("#addition_lists_close");
    if (close && close.dataset.boundV4 !== "1") {
      close.dataset.boundV4 = "1";close.addEventListener("click", closeAdditionListsModal);
    }
    const create = $("#addition_list_create");
    if (create && create.dataset.boundV4 !== "1") {
      create.dataset.boundV4 = "1";create.addEventListener("click", async () => {
        const input = $("#addition_list_new_name");
        const name = normalize(input?.value);
        if (!name) return alert("Informe o nome da lista.");
        try { await listAction({action:"create",name});if(input)input.value=""; }
        catch (error) { alert(normalize(error?.message)); }
      });
    }
    const rows = $("#addition_lists_rows");
    if (rows && rows.dataset.boundV4 !== "1") {
      rows.dataset.boundV4 = "1";rows.addEventListener("click", async event => {
        const button = event.target.closest?.("[data-list-action]");
        const row = button?.closest?.("[data-list-name]");
        if (!button || !row) return;
        const name = row.dataset.listName || "";
        try {
          if (button.dataset.listAction === "select") await listAction({action:"select",name});
          if (button.dataset.listAction === "rename") {
            const next = prompt("Novo nome da lista:", name);if(next && normalize(next)!==name)await listAction({action:"rename",name,new_name:normalize(next)});
          }
          if (button.dataset.listAction === "delete" && confirm(`Excluir a lista “${name}”? Os itens voltarão para Padrão.`)) await listAction({action:"delete",name});
        } catch (error) { alert(normalize(error?.message)); }
      });
    }
    const move = $("#addition_list_move_selected");
    if (move && move.dataset.boundV4 !== "1") {
      move.dataset.boundV4 = "1";move.addEventListener("click", async () => {
        const ids = $$("[data-add-select='queue']:checked").map(box => normalize(box.dataset.job)).filter(Boolean);
        const target = normalize($("#addition_list_move_target")?.value);
        if (!ids.length) return alert("Selecione ao menos um item na Fila de adições.");
        if (!target) return alert("Selecione a lista de destino.");
        try { await listAction({action:"move",target,job_ids:ids}); }
        catch (error) { alert(normalize(error?.message)); }
      });
    }
  }

  function standardizeAdditionHistory() {
    const history = $("#addition_history_accordion");
    if (!history) return false;
    const title = $(".section-title", history);
    if (title) title.textContent = "Histórico";
    const description = $(":scope > .small", history);
    if (description) description.classList.add("cs-v4-history-description");
    const actions = $(".updates-history-actions", history);
    if (actions && !$("#addition_history_delete", actions)) {
      const remove = document.createElement("button");
      remove.type="button";remove.id="addition_history_delete";remove.className="btn-danger btn-sm";remove.textContent="Apagar histórico";
      remove.addEventListener("click", async () => {
        if (!confirm("Apagar todo o histórico de tentativas de adição? Os produtos e a fila serão preservados.")) return;
        try {
          await apiJson("/adicoes/operacoes/historico/limpar", {method:"POST",body:"{}"});
          $("#addition_history_refresh")?.click();
        } catch (error) { alert(normalize(error?.message)); }
      });
      actions.appendChild(remove);
    }
    return true;
  }

  function bindGlobalEvents() {
    document.addEventListener("change", event => {
      const id = event.target?.id || "";
      if (["updates_status_filter","updates_queue_status_filter","updates_history_status_filter"].includes(id)) window.setTimeout(syncUpdateTopActive, 0);
    }, true);
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#updates_history_completed,#updates_history_errors")) window.setTimeout(syncUpdateTopActive, 0);
      if (target.closest("#tab_btn_adicoes")) window.setTimeout(() => { run();loadAdditionLists(); }, 80);
      if (target.closest("#tab_btn_atualizacoes")) window.setTimeout(run, 80);
    }, true);
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || "");
      if (key === "adicoes") window.setTimeout(() => { run();loadAdditionLists(); }, 80);
      if (key === "atualizacoes") window.setTimeout(run, 80);
    });
  }

  function run() {
    installStyles();
    ensureUpdateTopCards();
    standardizeUpdatePreparation();
    ensureAdditionQueueManagement();
    standardizeAdditionHistory();
    observeMetricContainers();
    observeUpdateJobs();
  }

  function finiteSchedule() {
    [0,60,180,450,900,1800,3500,5500].forEach(delay => window.setTimeout(run, delay));
  }

  function start() {
    finiteSchedule();
    bindGlobalEvents();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
