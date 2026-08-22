(() => {
  "use strict";

  const STATE_OPTIONS = [
    ["", "Todos"],
    ["approved", "Aprovado"],
    ["validating", "Validando"],
    ["downloading", "Baixando"],
    ["staging", "Preparando staging"],
    ["prepared", "Preparado"],
    ["planned", "Planejado"],
    ["plan_ready", "Plano pronto"],
    ["queued", "Aguardando execução"],
    ["executing", "Executando"],
    ["installing", "Instalando"],
    ["filesystem_validated", "Sistema de arquivos validado"],
    ["updating_wordpress", "Atualizando WordPress"],
    ["validating_wordpress", "Validando WordPress"],
    ["validated", "Validado"],
    ["dry_run_ready", "Simulação pronta"],
    ["completed", "Concluído"],
    ["blocked", "Bloqueado"],
    ["error", "Erro"],
    ["failed", "Falhou"],
    ["interrupted", "Interrompido"],
    ["canceled", "Cancelado"],
    ["rollback_required", "Rollback necessário"],
    ["rolling_back", "Rollback em andamento"],
    ["rolled_back", "Rollback concluído"],
  ];

  const PREPARATION_OPTIONS = [
    ["", "Todos"],
    ["approved", "Aprovado"],
    ["validating", "Validando"],
    ["downloading", "Baixando"],
    ["staging", "Preparando staging"],
    ["prepared", "Preparado"],
    ["planned", "Planejado"],
    ["plan_ready", "Plano pronto"],
    ["blocked", "Bloqueado"],
  ];

  const TERMINAL_ERROR = new Set(["blocked", "error", "failed", "interrupted", "rollback_required"]);
  const PREPARATION = new Set(["approved", "validating", "downloading", "staging", "prepared", "planned"]);
  const EXECUTION = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "dry_run_ready", "rolling_back"
  ]);

  const UPDATE_HELP = Object.freeze({
    Total: "Quantidade total de itens pertencentes à lista de atualização ativa.",
    Concluídos: "Itens da lista ativa cuja atualização foi concluída com sucesso.",
    Aprovados: "Itens aprovados que ainda precisam avançar pelo fluxo de preparação ou execução.",
    Validando: "Itens que estão passando pelas validações necessárias antes da atualização.",
    "Plano pronto": "Itens já preparados, com plano de atualização pronto para seguir para a fila.",
    "Na fila": "Itens aguardando execução sequencial na fila de atualização.",
    Executando: "Itens atualmente em execução. Clique no card para filtrar este estado.",
    Bloqueados: "Itens impedidos de avançar porque alguma validação ou requisito bloqueou a execução.",
    Erros: "Itens encerrados com erro ou falha e que exigem revisão.",
    "Rollback necessário": "Itens que precisam de rollback antes de poderem ser considerados concluídos.",
    "ZIP local registrado": "Itens que possuem ZIP de staging e SHA-256 registrados localmente para possível reaproveitamento após revalidação.",
  });

  const ADDITION_HELP = Object.freeze({
    "Total aprovado": "Quantidade total de produtos aprovados na comparação e disponíveis para o fluxo de adições.",
    Aguardando: "Itens aguardando início da preparação.",
    Preparando: "Itens que estão tendo conteúdo, imagem, categoria, preços ou ZIP preparados.",
    Pronto: "Itens já preparados e liberados para entrar na fila de execução.",
    "Na fila": "Itens posicionados na fila de adições, aguardando processamento.",
    "Em execução": "Itens atualmente sendo processados no fluxo de adição.",
    Concluído: "Itens finalizados com sucesso no WooCommerce.",
    "Com erro": "Itens cuja execução terminou com erro e podem exigir revisão.",
    Cancelado: "Itens removidos ou cancelados antes da conclusão.",
  });

  const FIELD_HELP = Object.freeze({
    updates_queue_search: "Filtra a fila pelo nome do produto ou pelo ID do WooCommerce.",
    updates_queue_status_filter: "Mostra somente os itens no estado escolhido. Clicar nos cards de status acima também altera este filtro.",
    updates_queue_page_size: "Define quantos itens da fila são exibidos em cada página.",
  });

  const ACTION_HELP = Object.freeze({
    updates_queue_start: "Inicia ou continua o processamento sequencial da lista ativa.",
    updates_queue_pause: "Pausa a fila após a etapa segura atual, preservando o progresso para continuação.",
    updates_queue_cancel: "Cancela somente os itens pendentes que ainda não começaram a execução.",
  });

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  function installStyles() {
    if ($("#cs-update-operational-filter-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-operational-filter-style";
    style.textContent = `
      #addition_intro_card,
      #tab_panel_atualizacoes .updates-queue-section{overflow:visible!important}

      .cs-update-operational-summary,
      #addition_summary_grid.operational-summary-grid{
        display:grid!important;
        gap:8px!important;
        margin:12px 0 10px!important;
        padding:0!important;
        border:0!important;
        background:transparent!important;
      }
      .cs-update-operational-summary{grid-template-columns:repeat(6,minmax(0,1fr))!important}
      #addition_summary_grid.operational-summary-grid{grid-template-columns:repeat(5,minmax(0,1fr))!important}

      .cs-update-operational-chip,
      #addition_summary_grid .addition-summary-chip{
        position:relative!important;
        display:flex!important;
        flex-direction:column!important;
        justify-content:center!important;
        align-items:stretch!important;
        gap:5px!important;
        width:100%!important;
        min-width:0!important;
        min-height:82px!important;
        padding:12px!important;
        border:1px solid var(--line)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.025)!important;
        color:var(--text)!important;
        text-align:left!important;
        font:inherit!important;
        box-shadow:none!important;
        transform:none!important;
        overflow:visible!important;
      }
      button.cs-update-operational-chip,
      #addition_summary_grid button.addition-summary-chip,
      #addition_summary_grid .addition-summary-chip[role="button"]{cursor:pointer!important}
      button.cs-update-operational-chip:hover,
      .cs-update-operational-chip[role="button"]:hover,
      #addition_summary_grid button.addition-summary-chip:hover,
      #addition_summary_grid .addition-summary-chip[role="button"]:hover{
        border-color:var(--line-accent)!important;
        background:var(--accent-soft)!important;
      }
      .cs-update-operational-chip.is-filter-active,
      #addition_summary_grid .addition-summary-chip.is-filter-active{
        border-color:rgba(124,58,237,.72)!important;
        background:rgba(124,58,237,.13)!important;
        box-shadow:inset 0 0 0 1px rgba(124,58,237,.16)!important;
      }
      .cs-update-operational-chip>strong,
      #addition_summary_grid .addition-summary-chip>strong{
        display:block!important;
        margin:0!important;
        color:var(--text)!important;
        font-size:20px!important;
        font-weight:800!important;
        line-height:1!important;
        font-variant-numeric:tabular-nums;
      }
      .operational-summary-footer{
        display:flex!important;
        align-items:center!important;
        justify-content:flex-start!important;
        gap:6px!important;
        min-width:0;
        margin-top:3px!important;
        color:var(--text-muted)!important;
      }
      .operational-summary-label{
        min-width:0;
        color:var(--text-muted)!important;
        font-size:12px!important;
        font-weight:600!important;
        line-height:1.25!important;
        overflow-wrap:anywhere;
      }
      .operational-summary-help,.operational-field-help,.operational-action-help{
        flex:0 0 24px!important;width:24px!important;min-width:24px!important;max-width:24px!important;
        height:24px!important;min-height:24px!important;max-height:24px!important;font-size:11px!important;z-index:80
      }
      .cs-update-operational-chip:has(.operational-summary-help:hover),
      #addition_summary_grid .addition-summary-chip:has(.operational-summary-help:hover){z-index:90}
      .cs-update-operational-guidance{
        grid-column:1/-1!important;margin:0!important;padding:9px 11px!important;
        border:1px solid var(--line)!important;border-radius:10px!important;
        background:rgba(255,255,255,.018)!important;color:var(--text-muted)!important;
        font-size:11px!important;line-height:1.45!important
      }

      #tab_panel_atualizacoes .updates-queue-actions.operational-action-grid{
        display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;
        gap:8px!important;width:100%!important;margin:12px 0!important
      }
      #tab_panel_atualizacoes .operational-action-control{
        display:grid;grid-template-columns:minmax(0,1fr) 28px;gap:6px;align-items:center;min-width:0
      }
      #tab_panel_atualizacoes .operational-action-control>button:not(.comparison-help){
        width:100%!important;min-width:0!important;min-height:46px!important
      }

      #updates_queue_list_controls.operational-queue-controls{
        display:grid!important;align-content:start!important;gap:10px!important;
        margin-top:12px!important;padding:12px!important
      }
      #updates_queue_list_controls.operational-queue-controls .updates-list-controls,
      #updates_queue_list_controls.operational-queue-controls .cs-op-filterbar{
        grid-template-columns:minmax(280px,1.45fr) minmax(220px,.7fr)!important;
        gap:10px!important;margin:0!important
      }
      #updates_queue_list_controls.operational-queue-controls .cs-op-list-meta[data-cs-update-queue-meta]{
        min-height:30px!important;margin:0!important;padding:0 2px!important
      }
      #updates_queue_list_controls.operational-queue-controls .listing-pagination,
      #updates_queue_list_controls.operational-queue-controls .cs-op-pagination{margin:0!important}
      .operational-field-label-row{display:inline-flex;align-items:center;gap:6px;width:max-content;max-width:100%;color:var(--text-muted);font-size:11px;font-weight:700;line-height:1.2}
      #updates_queue_list_controls .cs-op-inline-page-size .operational-field-label-row{margin-right:2px}

      .cs-zip-local-badge{display:inline-flex;align-items:center;gap:4px;margin-left:7px;padding:3px 7px;border:1px solid rgba(16,185,129,.38);border-radius:999px;background:rgba(16,185,129,.09);color:#8ce0bf;font-size:10px;font-weight:800;vertical-align:middle}

      @media(max-width:1180px){
        .cs-update-operational-summary{grid-template-columns:repeat(4,minmax(0,1fr))!important}
        #addition_summary_grid.operational-summary-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
      }
      @media(max-width:760px){
        #tab_panel_atualizacoes .updates-queue-actions.operational-action-grid{grid-template-columns:1fr!important}
        #updates_queue_list_controls.operational-queue-controls .updates-list-controls,
        #updates_queue_list_controls.operational-queue-controls .cs-op-filterbar{grid-template-columns:1fr!important}
        .cs-update-operational-summary,#addition_summary_grid.operational-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
      }
      @media(max-width:480px){.cs-update-operational-summary,#addition_summary_grid.operational-summary-grid{grid-template-columns:1fr!important}}
    `;
    document.head.appendChild(style);
  }

  function fillSelect(select, options) {
    if (!select) return;
    const current = select.value;
    const values = new Set(options.map(([value]) => value));
    [...select.options].forEach(option => {
      if (!values.has(option.value)) option.remove();
    });
    options.forEach(([value, label]) => {
      let option = [...select.options].find(item => item.value === value);
      if (!option) {
        option = document.createElement("option");
        option.value = value;
        select.appendChild(option);
      }
      option.textContent = label;
    });
    if (values.has(current)) select.value = current;
  }

  function improveFilterControls() {
    const queueState = $("#updates_queue_status_filter");
    if (queueState) fillSelect(queueState, STATE_OPTIONS);
    const preparationState = $("#updates_status_filter");
    if (preparationState) fillSelect(preparationState, PREPARATION_OPTIONS);
  }

  async function loadRuntime() {
    const response = await fetch("/atualizacoes/jobs", {cache:"no-store", credentials:"same-origin"});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
    return data;
  }

  function activeQueueJobs(data) {
    const activeName = text(data?.queue?.active_queue || "default");
    const jobs = Array.isArray(data?.jobs) ? data.jobs : [];
    return jobs.filter(job => text(job?.queue_name || "default") === activeName);
  }

  function localArtifact(job) {
    return Boolean(text(job?.local_staging_path) && text(job?.new_sha256));
  }

  function helpMarkup(label, tooltip, cls = "operational-summary-help") {
    return `<span class="comparison-help ${cls}" aria-label="Ajuda sobre ${esc(label)}" data-tooltip="${esc(tooltip)}">?</span>`;
  }

  function selectState(state) {
    const select = $("#updates_queue_status_filter");
    if (!select) return;
    select.value = state;
    select.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function updateChip(label, count, state, filterable = true) {
    const tooltip = UPDATE_HELP[label] || "Informação sobre este estado da fila.";
    const tag = filterable ? "button" : "div";
    const attrs = filterable ? `type="button" data-cs-update-state="${esc(state)}"` : "";
    return `<${tag} ${attrs} class="cs-update-operational-chip"><strong>${esc(count)}</strong><span class="operational-summary-footer"><span class="operational-summary-label">${esc(label)}</span>${helpMarkup(label, tooltip)}</span></${tag}>`;
  }

  function syncUpdateActiveCard(summary = $("#cs_update_operational_summary")) {
    if (!summary) return;
    const current = text($("#updates_queue_status_filter")?.value);
    $$("[data-cs-update-state]", summary).forEach(card => card.classList.toggle("is-filter-active", text(card.dataset.csUpdateState) === current));
  }

  function renderSummary(data) {
    const controls = $("#updates_queue_list_controls");
    if (!controls) return;
    let summary = $("#cs_update_operational_summary");
    if (!summary) {
      summary = document.createElement("div");
      summary.id = "cs_update_operational_summary";
      summary.className = "cs-update-operational-summary";
      controls.before(summary);
    }

    const jobs = activeQueueJobs(data);
    const counts = Object.create(null);
    jobs.forEach(job => { counts[job.state] = (counts[job.state] || 0) + 1; });
    const local = jobs.filter(localArtifact).length;
    const preparing = jobs.filter(job => PREPARATION.has(job.state)).length;
    const executing = jobs.filter(job => EXECUTION.has(job.state)).length;
    const attention = jobs.filter(job => TERMINAL_ERROR.has(job.state)).length;
    const completed = counts.completed || 0;
    const queued = counts.queued || 0;
    const planReady = counts.plan_ready || 0;

    let guidance = "";
    if (executing > 0) guidance = `${executing} item(ns) em execução. A linha da fila mostra a etapa e o log ao vivo.`;
    else if (queued > 0) guidance = `${queued} item(ns) aguardando execução. A fila pode ser iniciada.`;
    else if (planReady > 0) guidance = `Não há itens aguardando execução, mas ${planReady} possuem plano pronto.`;
    else if (preparing > 0) guidance = `${preparing} item(ns) ainda estão na preparação.`;
    else if (attention > 0) guidance = `${attention} item(ns) exigem atenção. Use o filtro Estado para separar Bloqueados, Erros e Rollback necessário.`;
    else if (completed > 0) guidance = `Os concluídos ficam disponíveis pelo filtro “Concluído” e no Histórico.`;
    else guidance = "Nenhum item pendente de execução nesta lista.";

    summary.innerHTML = [
      updateChip("Total", jobs.length, "", true),
      updateChip("Concluídos", completed, "completed", true),
      updateChip("Aprovados", counts.approved || 0, "approved", true),
      updateChip("Validando", counts.validating || 0, "validating", true),
      updateChip("Plano pronto", planReady, "plan_ready", true),
      updateChip("Na fila", queued, "queued", true),
      updateChip("Executando", executing, "executing", true),
      updateChip("Bloqueados", counts.blocked || 0, "blocked", true),
      updateChip("Erros", (counts.error || 0) + (counts.failed || 0), counts.error ? "error" : "failed", true),
      updateChip("Rollback necessário", counts.rollback_required || 0, "rollback_required", true),
      updateChip("ZIP local registrado", local, "", false),
      `<div class="cs-update-operational-guidance">${esc(guidance)}</div>`,
    ].join("");

    summary.querySelectorAll("[data-cs-update-state]").forEach(button => {
      button.addEventListener("click", event => {
        if (event.target.closest?.(".comparison-help")) return;
        selectState(button.dataset.csUpdateState || "");
      });
    });
    summary.querySelectorAll(".comparison-help").forEach(help => {
      help.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); });
    });
    syncUpdateActiveCard(summary);
  }

  function additionCardLabel(card) {
    return text($(".operational-summary-label", card)?.textContent || $(":scope > span", card)?.textContent || "");
  }

  function decorateAdditionCard(card) {
    if (!card || card.dataset.operationalMetricDecorated === "1") return;
    const label = additionCardLabel(card);
    if (!label) return;
    card.dataset.operationalMetricDecorated = "1";

    const originalLabel = $(":scope > span", card);
    if (!originalLabel) return;
    const footer = document.createElement("span");
    footer.className = "operational-summary-footer";
    originalLabel.className = "operational-summary-label";
    footer.appendChild(originalLabel);
    footer.insertAdjacentHTML("beforeend", helpMarkup(label, ADDITION_HELP[label] || "Informação sobre este estado das adições."));
    card.appendChild(footer);
    $(".comparison-help", footer)?.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); });

    if (label === "Total aprovado") {
      card.setAttribute("role", "button");
      card.tabIndex = 0;
      const clearFilter = () => {
        const select = $("#addition_queue_state");
        if (!select) return;
        select.value = "";
        select.dispatchEvent(new Event("change", {bubbles:true}));
        const accordion = $("#addition_queue_accordion");
        if (accordion) accordion.open = true;
        accordion?.scrollIntoView({behavior:"smooth", block:"start"});
      };
      card.addEventListener("click", event => { if (!event.target.closest?.(".comparison-help")) clearFilter(); });
      card.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        clearFilter();
      });
    }
  }

  function syncAdditionActiveCard(root = $("#addition_summary_grid")) {
    if (!root) return;
    const current = text($("#addition_queue_state")?.value);
    $$(".addition-summary-chip", root).forEach(card => {
      const label = additionCardLabel(card);
      const state = text(card.dataset.summaryState);
      card.classList.toggle("is-filter-active", state ? state === current : label === "Total aprovado" && !current);
    });
  }

  function decorateAdditionSummary(root = $("#addition_summary_grid")) {
    if (!root) return false;
    root.classList.add("operational-summary-grid");
    $$(".addition-summary-chip", root).forEach(decorateAdditionCard);
    syncAdditionActiveCard(root);
    return true;
  }

  function annotateVisibleRows(data) {
    const map = new Map((Array.isArray(data?.jobs) ? data.jobs : []).map(job => [text(job.job_id), job]));
    document.querySelectorAll("#updates_queue_jobs [data-update-detail]").forEach(detail => {
      const job = map.get(text(detail.dataset.updateDetail));
      if (!job || !localArtifact(job)) return;
      const row = detail.closest(".update-queue-row") || detail.parentElement;
      const main = row?.children?.[1] || row?.querySelector("div");
      if (!main || $(".cs-zip-local-badge", main)) return;
      const badge = document.createElement("span");
      badge.className = "cs-zip-local-badge";
      badge.textContent = "ZIP local";
      badge.title = "Há caminho de staging e SHA-256 persistidos para este job. O arquivo ainda será revalidado antes do reaproveitamento.";
      const firstStrong = main.querySelector("strong");
      if (firstStrong) firstStrong.insertAdjacentElement("afterend", badge);
      else main.prepend(badge);
    });
  }

  function decorateField(controlId) {
    const control = $(`#${controlId}`);
    const label = control?.closest("label");
    const tooltip = FIELD_HELP[controlId];
    if (!control || !label || !tooltip || label.dataset.operationalHelpBound === "1") return;
    label.dataset.operationalHelpBound = "1";
    const labelText = text(Array.from(label.childNodes).filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join(" "));
    Array.from(label.childNodes).forEach(node => { if (node.nodeType === Node.TEXT_NODE) node.remove(); });
    const row = document.createElement("span");
    row.className = "operational-field-label-row";
    const copy = document.createElement("span");
    copy.textContent = labelText || (controlId === "updates_queue_search" ? "Buscar na fila" : controlId === "updates_queue_status_filter" ? "Estado" : "Itens por página");
    row.appendChild(copy);
    row.insertAdjacentHTML("beforeend", helpMarkup(copy.textContent, tooltip, "operational-field-help"));
    label.insertBefore(row, control);
  }

  function decorateUpdateActions() {
    const root = $("#tab_panel_atualizacoes .updates-queue-actions");
    if (!root) return false;
    root.classList.add("operational-action-grid");
    Object.entries(ACTION_HELP).forEach(([id, tooltip]) => {
      const button = $(`#${id}`, root);
      if (!button || button.closest(".operational-action-control")) return;
      const wrapper = document.createElement("div");
      wrapper.className = "operational-action-control";
      button.insertAdjacentElement("beforebegin", wrapper);
      wrapper.appendChild(button);
      wrapper.insertAdjacentHTML("beforeend", helpMarkup(text(button.textContent), tooltip, "operational-action-help"));
    });
    return true;
  }

  function compactUpdateQueueControls() {
    const controls = $("#updates_queue_list_controls");
    if (!controls) return false;
    controls.classList.add("operational-queue-controls");
    decorateField("updates_queue_search");
    decorateField("updates_queue_status_filter");
    decorateField("updates_queue_page_size");
    return true;
  }

  function panelVisible(id) {
    const panel = $(id);
    return !!panel && !panel.classList.contains("hidden");
  }

  let refreshTimer = null;
  let refreshing = false;
  async function refresh(force = false) {
    if (refreshing || !$("#updates_queue_jobs")) return;
    if (!force && !panelVisible("#tab_panel_atualizacoes")) return;
    refreshing = true;
    try {
      improveFilterControls();
      decorateUpdateActions();
      compactUpdateQueueControls();
      const data = await loadRuntime();
      renderSummary(data);
      annotateVisibleRows(data);
    } catch (_error) {
      // A interface nativa continua funcional mesmo se este refinamento falhar.
    } finally {
      refreshing = false;
    }
  }

  function scheduleRefresh(delays = [80, 350, 900]) {
    clearTimeout(refreshTimer);
    delays.forEach(delay => {
      window.setTimeout(() => refresh(), delay);
    });
  }

  function scheduleAddition(delays = [0, 60, 180, 450, 900, 1800, 3500, 5500]) {
    delays.forEach(delay => window.setTimeout(() => {
      const root = $("#addition_summary_grid");
      if (!root) return;
      decorateAdditionSummary(root);
      if (root.dataset.operationalSummaryObserver !== "1") {
        root.dataset.operationalSummaryObserver = "1";
        new MutationObserver(() => decorateAdditionSummary(root)).observe(root, {childList:true});
      }
    }, delay));
  }

  function observeQueueRows() {
    const rows = $("#updates_queue_jobs");
    if (!rows || rows.dataset.operationalQueueObserver === "1") return;
    rows.dataset.operationalQueueObserver = "1";
    new MutationObserver(() => {
      if (panelVisible("#tab_panel_atualizacoes")) scheduleRefresh([80]);
    }).observe(rows, {childList:true});
  }

  function start() {
    installStyles();
    improveFilterControls();
    decorateUpdateActions();
    compactUpdateQueueControls();
    observeQueueRows();

    if (panelVisible("#tab_panel_atualizacoes")) refresh(true);
    if (panelVisible("#tab_panel_adicoes")) scheduleAddition();

    $("#tab_btn_atualizacoes")?.addEventListener("click", () => scheduleRefresh([0, 100, 450, 1100]));
    $("#tab_btn_adicoes")?.addEventListener("click", () => scheduleAddition());

    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes") scheduleRefresh([0, 100, 450, 1100]);
      if (key === "adicoes") scheduleAddition();
    });

    document.addEventListener("change", event => {
      if (event.target?.id === "updates_queue_status_filter") syncUpdateActiveCard();
      if (event.target?.id === "addition_queue_state") syncAdditionActiveCard();
    }, true);

    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#updates_refresh_btn,#updates_queue_start,#updates_queue_pause,#updates_queue_cancel,#updates_queue_select,#open_update_lists_modal")) {
        scheduleRefresh([100, 500, 1400]);
      }
    }, true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
