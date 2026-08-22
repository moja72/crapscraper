(() => {
  "use strict";

  if (window.__crapScraperOperationalUiCardParityV5Installed) return;
  window.__crapScraperOperationalUiCardParityV5Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  const UPDATE_FILTERS = Object.freeze({
    Total: {kind:"total"},
    Aguardando: {kind:"preparation", value:"approved"},
    Preparados: {kind:"preparation", value:"plan_ready"},
    "Na fila": {kind:"queue", value:"queued"},
    Executando: {kind:"queue", value:"executing"},
    Concluídos: {kind:"history", tab:"completed"},
    Erros: {kind:"history", tab:"errors"},
  });

  const ADDITION_FILTERS = Object.freeze({
    "Total aprovado": "",
    Aguardando: "waiting",
    Preparando: "preparing",
    Pronto: "ready",
    "Na fila": "queued",
    "Em execução": "executing",
    Concluído: "completed",
    "Com erro": "error",
    Cancelado: "canceled",
  });

  let updateSummaryObserver = null;
  let additionSummaryObserver = null;

  function installStyles() {
    if ($("#cs-operational-ui-card-parity-v5-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operational-ui-card-parity-v5-style";
    style.textContent = `
      /* Atualizar passa a usar exatamente a mesma malha de Adicionar: 5 cards por linha. */
      #updates_summary,
      #addition_summary_grid {
        display:grid!important;
        grid-template-columns:repeat(5,minmax(0,1fr))!important;
        gap:8px!important;
        width:100%!important;
        margin:12px 0 0!important;
        padding:0!important;
        border:0!important;
        background:transparent!important;
      }

      #updates_summary>.cs-v5-metric-card,
      #addition_summary_grid>.cs-v5-metric-card {
        position:relative!important;
        display:flex!important;
        flex-direction:column!important;
        justify-content:center!important;
        align-items:stretch!important;
        gap:4px!important;
        width:100%!important;
        min-width:0!important;
        min-height:66px!important;
        padding:9px 10px!important;
        border:1px solid var(--line)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.022)!important;
        color:var(--text)!important;
        text-align:left!important;
        box-shadow:none!important;
        transform:none!important;
        overflow:visible!important;
        transition:border-color var(--transition-fast),background var(--transition-fast),box-shadow var(--transition-fast)!important;
      }

      #updates_summary>.cs-v5-metric-card,
      #addition_summary_grid>.cs-v5-metric-card { cursor:pointer!important; }

      #updates_summary>.cs-v5-metric-card:hover,
      #addition_summary_grid>.cs-v5-metric-card:hover {
        border-color:var(--line-accent)!important;
        background:var(--accent-soft)!important;
      }

      #updates_summary>.cs-v5-metric-card.is-filter-active,
      #addition_summary_grid>.cs-v5-metric-card.is-filter-active {
        border-color:rgba(124,58,237,.88)!important;
        background:linear-gradient(180deg,rgba(124,58,237,.20),rgba(124,58,237,.10))!important;
        box-shadow:inset 0 0 0 1px rgba(143,91,255,.20)!important;
      }

      #updates_summary>.cs-v5-metric-card>strong,
      #addition_summary_grid>.cs-v5-metric-card>strong {
        display:block!important;
        margin:0!important;
        color:var(--text)!important;
        font-size:18px!important;
        font-weight:800!important;
        line-height:1!important;
        font-variant-numeric:tabular-nums!important;
      }

      #updates_summary .cs-v5-metric-footer,
      #addition_summary_grid .cs-v5-metric-footer {
        display:flex!important;
        align-items:center!important;
        justify-content:flex-start!important;
        gap:5px!important;
        min-width:0!important;
        min-height:22px!important;
        margin:2px 0 0!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:650!important;
        line-height:1.2!important;
      }

      #updates_summary .operational-summary-label,
      #addition_summary_grid .operational-summary-label {
        min-width:0!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        font-weight:650!important;
        line-height:1.2!important;
      }

      #updates_summary .operational-summary-help,
      #addition_summary_grid .operational-summary-help {
        flex:0 0 22px!important;
        width:22px!important;
        min-width:22px!important;
        max-width:22px!important;
        height:22px!important;
        min-height:22px!important;
        max-height:22px!important;
        margin:0!important;
        padding:0!important;
        align-self:center!important;
        font-size:10px!important;
        line-height:20px!important;
      }

      /* A moldura das duas seções usa o mesmo tratamento visual; a altura continua dependente do conteúdo. */
      #tab_panel_atualizacoes .updates-overview-card,
      #tab_panel_adicoes #addition_intro_card,
      #tab_panel_adicoes .addition-summary-card {
        border:1px solid var(--line)!important;
        border-radius:var(--radius-md)!important;
        background:linear-gradient(180deg,rgba(255,255,255,.02),rgba(255,255,255,.01)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;
      }

      @media(max-width:1180px){
        #updates_summary,#addition_summary_grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}
      }
      @media(max-width:760px){
        #updates_summary,#addition_summary_grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
      }
      @media(max-width:480px){
        #updates_summary,#addition_summary_grid{grid-template-columns:1fr!important}
      }
    `;
    document.head.appendChild(style);
  }

  function directCards(root) {
    return root ? Array.from(root.children).filter(node => node instanceof HTMLElement) : [];
  }

  function cardLabel(card) {
    const explicit = normalize(card.dataset.metricLabel || card.dataset.summaryLabel || "");
    if (explicit) return explicit;
    const labelNode = $(".operational-summary-label,.cs-v4-metric-label", card);
    if (labelNode) return normalize(labelNode.textContent);
    const footer = $(".operational-summary-footer,.cs-v4-metric-footer", card);
    if (footer) {
      const clone = footer.cloneNode(true);
      clone.querySelectorAll(".comparison-help").forEach(node => node.remove());
      return normalize(clone.textContent).replace(/\?$/, "").trim();
    }
    const span = $("span", card);
    if (!span) return "";
    const clone = span.cloneNode(true);
    clone.querySelectorAll(".comparison-help").forEach(node => node.remove());
    return normalize(clone.textContent).replace(/\?$/, "").trim();
  }

  function normalizeCard(card, scope) {
    const label = cardLabel(card);
    if (!label) return;
    card.classList.add("cs-v5-metric-card");
    card.dataset.v5MetricLabel = label;
    card.setAttribute("role", "button");
    card.tabIndex = 0;

    const footer = $(".operational-summary-footer,.cs-v4-metric-footer", card) || $("span", card);
    if (footer) footer.classList.add("operational-summary-footer", "cs-v5-metric-footer");

    const labelNode = $(".operational-summary-label,.cs-v4-metric-label", card);
    if (labelNode) labelNode.classList.add("operational-summary-label");

    const help = $(".comparison-help", card);
    if (help) help.classList.add("operational-summary-help");

    if (card.dataset.v5FilterBound === "1") return;
    card.dataset.v5FilterBound = "1";

    card.addEventListener("click", event => {
      if (event.target?.closest?.(".comparison-help")) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      if (scope === "update") activateUpdateCard(label);
      else activateAdditionCard(label);
    }, true);

    if (card.tagName !== "BUTTON") {
      card.addEventListener("keydown", event => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (scope === "update") activateUpdateCard(label);
        else activateAdditionCard(label);
      }, true);
    }
  }

  function setSelect(id, value) {
    const select = $(`#${id}`);
    if (!select) return false;
    if (!Array.from(select.options || []).some(option => option.value === value)) return false;
    select.value = value;
    select.dispatchEvent(new Event("change", {bubbles:true}));
    return true;
  }

  function closeUpdateHistory() {
    const history = $("#updates_history_accordion");
    if (history) history.open = false;
  }

  function activateUpdateCard(label) {
    const action = UPDATE_FILTERS[label];
    if (!action) return;

    if (action.kind === "total") {
      $("#updates_clear_filters")?.click();
      setSelect("updates_queue_status_filter", "");
      setSelect("updates_history_status_filter", "");
      closeUpdateHistory();
      syncUpdateActive();
      return;
    }

    if (action.kind === "preparation") {
      setSelect("updates_queue_status_filter", "");
      closeUpdateHistory();
      if (!setSelect("updates_status_filter", action.value) && action.value === "plan_ready") {
        setSelect("updates_status_filter", "prepared");
      }
      $("#tab_panel_atualizacoes .updates-working-card")?.scrollIntoView({behavior:"smooth", block:"start"});
    } else if (action.kind === "queue") {
      setSelect("updates_status_filter", "");
      closeUpdateHistory();
      setSelect("updates_queue_status_filter", action.value);
      $("#tab_panel_atualizacoes .updates-queue-section")?.scrollIntoView({behavior:"smooth", block:"start"});
    } else if (action.kind === "history") {
      setSelect("updates_status_filter", "");
      setSelect("updates_queue_status_filter", "");
      const history = $("#updates_history_accordion");
      if (history) history.open = true;
      (action.tab === "errors" ? $("#updates_history_errors") : $("#updates_history_completed"))?.click();
      history?.scrollIntoView({behavior:"smooth", block:"start"});
    }
    window.setTimeout(syncUpdateActive, 0);
  }

  function activateAdditionCard(label) {
    if (!(label in ADDITION_FILTERS)) return;
    const value = ADDITION_FILTERS[label];
    setSelect("addition_queue_state", value);
    const queue = $("#addition_queue_accordion");
    if (queue) queue.open = true;
    queue?.scrollIntoView({behavior:"smooth", block:"start"});
    window.setTimeout(syncAdditionActive, 0);
  }

  function syncUpdateActive() {
    const root = $("#updates_summary");
    if (!root) return;
    const preparation = normalize($("#updates_status_filter")?.value);
    const queue = normalize($("#updates_queue_status_filter")?.value);
    const history = $("#updates_history_accordion");
    const completed = $("#updates_history_completed")?.classList.contains("is-active");
    const errors = $("#updates_history_errors")?.classList.contains("is-active");

    directCards(root).forEach(card => {
      const label = card.dataset.v5MetricLabel || cardLabel(card);
      let active = false;
      if (label === "Total") active = !preparation && !queue && !history?.open;
      else if (label === "Aguardando") active = ["approved", "pending"].includes(preparation);
      else if (label === "Preparados") active = ["prepared", "plan_ready"].includes(preparation);
      else if (label === "Na fila") active = queue === "queued";
      else if (label === "Executando") active = queue === "executing";
      else if (label === "Concluídos") active = Boolean(history?.open && completed);
      else if (label === "Erros") active = Boolean(history?.open && errors);
      card.classList.toggle("is-filter-active", active);
      card.setAttribute("aria-pressed", String(active));
    });
  }

  function syncAdditionActive() {
    const root = $("#addition_summary_grid");
    if (!root) return;
    const value = normalize($("#addition_queue_state")?.value);
    directCards(root).forEach(card => {
      const label = card.dataset.v5MetricLabel || cardLabel(card);
      const expected = ADDITION_FILTERS[label];
      const active = label === "Com erro"
        ? ["error", "interrupted"].includes(value)
        : expected !== undefined && value === expected;
      card.classList.toggle("is-filter-active", active);
      card.setAttribute("aria-pressed", String(active));
    });
  }

  function normalizeUpdateCards() {
    const root = $("#updates_summary");
    if (!root) return false;
    directCards(root).forEach(card => normalizeCard(card, "update"));
    syncUpdateActive();
    return true;
  }

  function normalizeAdditionCards() {
    const root = $("#addition_summary_grid");
    if (!root) return false;
    directCards(root).forEach(card => normalizeCard(card, "addition"));
    syncAdditionActive();
    return true;
  }

  function observeSummaryContainers() {
    const updateRoot = $("#updates_summary");
    if (updateRoot && !updateSummaryObserver) {
      updateSummaryObserver = new MutationObserver(() => normalizeUpdateCards());
      updateSummaryObserver.observe(updateRoot, {childList:true});
    }
    const additionRoot = $("#addition_summary_grid");
    if (additionRoot && !additionSummaryObserver) {
      additionSummaryObserver = new MutationObserver(() => normalizeAdditionCards());
      additionSummaryObserver.observe(additionRoot, {childList:true});
    }
  }

  function bindFilterSync() {
    document.addEventListener("change", event => {
      const id = event.target?.id || "";
      if (["updates_status_filter", "updates_queue_status_filter", "updates_history_status_filter"].includes(id)) {
        window.setTimeout(syncUpdateActive, 0);
      }
      if (id === "addition_queue_state") window.setTimeout(syncAdditionActive, 0);
    }, true);
    document.addEventListener("click", event => {
      if (event.target?.closest?.("#updates_history_completed,#updates_history_errors")) {
        window.setTimeout(syncUpdateActive, 0);
      }
    }, true);
  }

  function run() {
    installStyles();
    normalizeUpdateCards();
    normalizeAdditionCards();
    observeSummaryContainers();
  }

  function start() {
    run();
    bindFilterSync();
    [60,180,450,900,1800,3500].forEach(delay => window.setTimeout(run, delay));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
