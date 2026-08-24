(() => {
  "use strict";

  if (window.__crapScraperQueueStandardizationV1CompatInstalled) return;
  window.__crapScraperQueueStandardizationV1CompatInstalled = true;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const $$ = (selector, root = document) => Array.from(root?.querySelectorAll?.(selector) || []);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  const UPDATE_CARDS = Object.freeze([
    ["Total", "", "Quantidade total de itens pertencentes à lista de atualização ativa."],
    ["Aprovados", "approved", "Itens aprovados que ainda precisam avançar pelo fluxo de atualização."],
    ["Validando", "validating", "Itens que estão passando pelas validações necessárias antes da atualização."],
    ["Plano pronto", "plan_ready", "Itens já preparados, com plano de atualização pronto para entrar na fila."],
    ["Na fila", "queued", "Itens aguardando execução sequencial na fila de atualização."],
    ["Executando", "executing", "Itens atualmente em execução na fila de atualização."],
    ["Concluídos", "completed", "Itens cuja atualização foi concluída com sucesso."],
    ["Bloqueados", "blocked", "Itens impedidos de avançar porque alguma validação ou requisito bloqueou a execução."],
    ["Erros", "error", "Itens encerrados com erro e que exigem revisão antes de nova tentativa."],
    ["Interrompidos", "interrupted", "Itens cuja execução foi interrompida e precisa ser retomada ou revalidada."],
    ["Rollback necessário", "rollback_required", "Itens que precisam de rollback antes de serem considerados resolvidos."],
  ]);

  const ADDITION_CARD_HELP = Object.freeze({
    "": "Quantidade total de produtos da lista de adições ativa.",
    waiting: "Itens aguardando início da preparação.",
    preparing: "Itens que estão tendo conteúdo, imagem, categoria, preços ou ZIP preparados.",
    ready: "Itens já preparados e liberados para entrar na fila de execução.",
    queued: "Itens posicionados na fila de adições, aguardando processamento.",
    executing: "Itens atualmente sendo processados no fluxo de adição.",
    completed: "Itens finalizados com sucesso no WooCommerce.",
    error: "Itens cuja execução terminou com erro e podem exigir revisão.",
    interrupted: "Itens cuja execução foi interrompida e pode ser recuperada.",
    canceled: "Itens removidos ou cancelados antes da conclusão.",
  });

  const ACTION_HELP = Object.freeze({
    updates_queue_start: "Inicia ou continua o processamento sequencial da lista ativa.",
    updates_queue_pause: "Pausa a fila após a etapa segura atual, preservando o progresso para continuação.",
    updates_queue_cancel: "Cancela somente os itens pendentes que ainda não começaram a execução.",
    addition_queue_start: "Inicia ou continua o processamento sequencial da lista ativa de adições.",
    addition_queue_pause: "Pausa a fila de adições após a etapa segura atual, preservando o progresso.",
    addition_queue_recover: "Recupera itens interrompidos para que possam voltar ao fluxo com segurança.",
  });

  const FIELD_HELP = Object.freeze({
    updates_queue_search: "Filtra a fila pelo nome do produto ou pelo ID do WooCommerce.",
    addition_queue_search: "Filtra a fila por nome, desenvolvedor, origem ou ID do WooCommerce.",
    updates_queue_page_size: "Define quantos itens da fila de atualização são exibidos em cada página.",
    addition_queue_page_size: "Define quantos itens da fila de adições são exibidos em cada página.",
  });

  let updatePayload = null;
  let updateFetchBusy = false;
  let refineTimer = 0;
  let updateTimer = 0;

  function installStyles() {
    if ($("#cs-queue-standardization-v1-compat-style")) return;
    const style = document.createElement("style");
    style.id = "cs-queue-standardization-v1-compat-style";
    style.textContent = `
      .cs-queue-v1-state-hidden{display:none!important}
      #tab_panel_atualizacoes .cs-queue-v1-filterbar.cs-queue-v1-no-state,
      #tab_panel_adicoes .cs-queue-v1-filterbar.cs-queue-v1-no-state{grid-template-columns:minmax(300px,1fr) auto!important}

      #cs_updates_queue_management_v1,#cs_addition_queue_management_v1{order:10!important}
      #cs_updates_queue_v1_body>.updates-queue-selector,#cs_addition_queue_v1_body>.cs-v4-queue-selector{order:20!important}
      #cs_updates_queue_v1_body>.cs-queue-v1-primary,#cs_addition_queue_v1_body>.cs-queue-v1-primary{order:30!important}
      #cs_updates_queue_summary_v1,#cs_addition_queue_summary_v1{order:40!important}
      #cs_updates_queue_v1_body>.updates-list-controls,#cs_addition_queue_v1_body>.addition-toolbar{order:50!important}
      #cs_updates_queue_v1_body>.listing-meta-row,#cs_addition_queue_v1_body>.addition-list-meta{order:60!important}
      #cs_updates_queue_bulk_v1,#cs_addition_queue_v1_body>.addition-bulk-actions{order:70!important}
      #cs_updates_queue_v1_body>.listing-pagination,#cs_addition_queue_v1_body>.addition-pagination{order:80!important}
      #updates_queue_jobs,#addition_queue_rows{order:90!important}

      #tab_panel_atualizacoes .cs-queue-v1-update.cs-queue-v1-total-filter #updates_queue_jobs .update-queue-row{display:grid!important}
      #tab_panel_atualizacoes .cs-queue-v1-update.cs-queue-v1-total-filter #updates_queue_jobs .cs-active-queue-empty{display:none!important}

      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip],
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]{position:relative!important;padding-right:42px!important;overflow:visible!important}
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]::after,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]::after{
        content:"?";position:absolute;right:10px;bottom:10px;width:23px;height:23px;display:grid;place-items:center;
        border:1px solid var(--line-strong,var(--line));border-radius:999px;background:var(--bg-elev-2,#1a1a20);
        color:var(--text-muted);font-size:11px;font-weight:850;line-height:1;pointer-events:none
      }
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]::before,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]::before{
        content:attr(data-tooltip);position:absolute;left:10px;bottom:calc(100% + 8px);z-index:220;
        width:min(300px,calc(100vw - 60px));padding:8px 10px;border:1px solid var(--line-strong,var(--line));
        border-radius:9px;background:#111116;color:var(--text-soft,#d5d8df);font-size:11px;font-weight:600;line-height:1.45;
        box-shadow:0 12px 34px rgba(0,0,0,.38);opacity:0;visibility:hidden;transform:translateY(4px);
        transition:opacity .14s ease,transform .14s ease,visibility .14s ease;pointer-events:none;text-align:left;white-space:normal
      }
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]:hover,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]:hover,
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]:focus-visible,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]:focus-visible{z-index:210!important}
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]:hover::before,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]:hover::before,
      #tab_panel_atualizacoes .cs-queue-v1-chip[data-tooltip]:focus-visible::before,
      #tab_panel_adicoes .cs-queue-v1-chip[data-tooltip]:focus-visible::before{opacity:1;visibility:visible;transform:translateY(0)}

      #tab_panel_adicoes .operational-action-control{
        display:grid!important;grid-template-columns:minmax(0,1fr) 28px!important;gap:6px!important;align-items:center!important;min-width:0!important
      }
      #tab_panel_adicoes .operational-action-control>button:not(.comparison-help){width:100%!important;min-width:0!important;min-height:46px!important}
      #tab_panel_adicoes .operational-field-label-row,
      #tab_panel_atualizacoes .operational-field-label-row{
        display:inline-flex!important;align-items:center!important;gap:6px!important;width:max-content!important;max-width:100%!important
      }

      :is(.listing-pagination,.cs-op-pagination,.addition-pagination,[class*="pagination"])
      :is(.badge,.cs-page-jump,.cs-op-page-jump):has(input[type="number"]){
        display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:7px!important;
        min-height:38px!important;padding:4px 10px!important;border:1px solid var(--line-strong,var(--line))!important;
        border-radius:999px!important;background:var(--bg-elev-2,#17171c)!important;box-sizing:border-box!important;white-space:nowrap!important
      }
      :is(.listing-pagination,.cs-op-pagination,.addition-pagination,[class*="pagination"])
      :is(.badge,.cs-page-jump,.cs-op-page-jump):has(input[type="number"]) input[type="number"],
      input[data-cs-page-input]{
        width:52px!important;min-width:52px!important;max-width:52px!important;min-height:30px!important;height:30px!important;
        margin:0!important;padding:3px 7px!important;border:1px solid var(--line-strong,var(--line))!important;
        border-radius:8px!important;background:var(--bg-input,#0d0d11)!important;text-align:center!important;box-sizing:border-box!important
      }
      .listing-page-size-input{
        min-height:32px!important;border:1px solid var(--line-strong,var(--line))!important;border-radius:9px!important;box-sizing:border-box!important
      }

      @media(max-width:850px){
        #tab_panel_atualizacoes .cs-queue-v1-filterbar.cs-queue-v1-no-state,
        #tab_panel_adicoes .cs-queue-v1-filterbar.cs-queue-v1-no-state{grid-template-columns:1fr!important}
      }
    `;
    document.head.appendChild(style);
  }

  function ensureUpdateQueueMetaContract() {
    const card = $("#tab_panel_atualizacoes .updates-queue-section");
    if (!card) return;
    let meta = $("#updates_queue_meta");
    if (!meta) {
      meta = document.createElement("span");
      meta.id = "updates_queue_meta";
      card.appendChild(meta);
    }
    meta.hidden = true;
    meta.setAttribute("aria-hidden", "true");
    meta.style.display = "none";
  }

  function helpNode(label, tooltip, kind) {
    const node = document.createElement("span");
    node.className = `comparison-help ${kind}`;
    node.textContent = "?";
    node.setAttribute("aria-label", `Ajuda sobre ${label}`);
    node.dataset.tooltip = tooltip;
    return node;
  }

  function ensureActionHelp(buttonId, tooltip) {
    const button = $(`#${buttonId}`);
    if (!button || !tooltip) return;
    let wrapper = button.closest(".operational-action-control");
    if (!wrapper) {
      wrapper = document.createElement("div");
      wrapper.className = "operational-action-control";
      button.parentElement?.insertBefore(wrapper, button);
      wrapper.appendChild(button);
    }
    if (!$(".operational-action-help", wrapper)) {
      wrapper.appendChild(helpNode(text(button.textContent) || buttonId, tooltip, "operational-action-help"));
    }
  }

  function ensureFieldHelp(controlId, tooltip) {
    const control = $(`#${controlId}`);
    if (!control || !tooltip) return;
    let label = control.closest("label");
    if (!label) label = control.parentElement?.querySelector?.(`label[for="${controlId}"]`) || control.parentElement?.querySelector?.("label") || null;
    if (!label || $(".operational-field-label-row", label)) return;
    const fallback = controlId.includes("search") ? "Buscar na fila" : controlId.includes("page_size") ? "Itens por página" : "Campo";
    const copyText = text(label.textContent) || fallback;
    label.textContent = "";
    const row = document.createElement("span");
    row.className = "operational-field-label-row";
    const copy = document.createElement("span");
    copy.textContent = copyText;
    row.appendChild(copy);
    row.appendChild(helpNode(copyText, tooltip, "operational-field-help"));
    label.appendChild(row);
  }

  function hideStateControl(selectId) {
    const select = $(`#${selectId}`);
    if (!select) return;
    const wrapper = select.closest(".field") || select.closest("label");
    if (wrapper) {
      wrapper.classList.add("cs-queue-v1-state-hidden");
      wrapper.setAttribute("aria-hidden", "true");
    }
    const filterbar = select.closest(".cs-queue-v1-filterbar") || select.closest(".updates-list-controls,.addition-toolbar");
    filterbar?.classList.add("cs-queue-v1-no-state");
  }

  function ensureUpdateCardsHost() {
    const body = $("#cs_updates_queue_v1_body");
    if (!body) return null;
    let host = $("#cs_updates_queue_summary_v1");
    if (!host) {
      host = document.createElement("div");
      host.id = "cs_updates_queue_summary_v1";
      host.className = "cs-queue-v1-summary-grid";
      body.appendChild(host);
    }
    return host;
  }

  function activeUpdateJobs(payload) {
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    const active = text($("#updates_queue_select")?.value || payload?.queue?.active_queue || "default") || "default";
    return jobs.filter(job => (text(job?.queue_name || "default") || "default") === active);
  }

  function syncUpdateTotalFilter() {
    const card = $("#tab_panel_atualizacoes .cs-queue-v1-update");
    const state = text($("#updates_queue_status_filter")?.value);
    card?.classList.toggle("cs-queue-v1-total-filter", !state);
  }

  function renderUpdateCards(payload = updatePayload) {
    if (!payload) return;
    updatePayload = payload;
    const host = ensureUpdateCardsHost();
    if (!host) return;
    const jobs = activeUpdateJobs(payload);
    const counts = Object.create(null);
    jobs.forEach(job => {
      const state = text(job?.state);
      counts[state] = (counts[state] || 0) + 1;
    });
    const activeState = text($("#updates_queue_status_filter")?.value);
    const signature = JSON.stringify([activeState, jobs.length, ...UPDATE_CARDS.map(([, state]) => state ? counts[state] || 0 : jobs.length)]);
    if (host.dataset.queueCardSignature === signature) {
      syncUpdateTotalFilter();
      return;
    }
    host.dataset.queueCardSignature = signature;
    host.innerHTML = UPDATE_CARDS.map(([label, state, tooltip]) => {
      const count = state ? counts[state] || 0 : jobs.length;
      return `<button type="button" class="cs-queue-v1-chip ${activeState === state ? "is-filter-active" : ""}" ` +
        `data-cs-update-queue-state="${esc(state)}" data-tooltip="${esc(tooltip)}" ` +
        `aria-label="${esc(`${label}: ${count}. ${tooltip}`)}"><strong>${count}</strong><span>${esc(label)}</span></button>`;
    }).join("");
    $$("[data-cs-update-queue-state]", host).forEach(button => button.addEventListener("click", () => {
      const select = $("#updates_queue_status_filter");
      if (!select) return;
      select.value = button.dataset.csUpdateQueueState || "";
      select.dispatchEvent(new Event("change", {bubbles:true}));
      renderUpdateCards(updatePayload);
    }));
    syncUpdateTotalFilter();
  }

  function decorateAdditionCards() {
    $$("#cs_addition_queue_summary_v1 .cs-queue-v1-chip").forEach(card => {
      const state = card.dataset.csAdditionQueueState || "";
      const tooltip = ADDITION_CARD_HELP[state] || "Informação sobre este estado da fila de adições.";
      card.dataset.tooltip = tooltip;
      const label = text($("span", card)?.textContent || "Estado");
      const count = text($("strong", card)?.textContent || "0");
      card.setAttribute("aria-label", `${label}: ${count}. ${tooltip}`);
    });
  }

  function refineQueueStructure() {
    installStyles();
    ensureUpdateQueueMetaContract();
    ensureUpdateCardsHost();
    hideStateControl("updates_queue_status_filter");
    hideStateControl("addition_queue_state");
    Object.entries(ACTION_HELP).forEach(([id, tooltip]) => ensureActionHelp(id, tooltip));
    Object.entries(FIELD_HELP).forEach(([id, tooltip]) => ensureFieldHelp(id, tooltip));
    decorateAdditionCards();
    syncUpdateTotalFilter();
    if (updatePayload) renderUpdateCards(updatePayload);
  }

  async function refreshUpdateCards(force = false) {
    if (updateFetchBusy || !$("#updates_queue_jobs")) return;
    const panel = $("#tab_panel_atualizacoes");
    if (!force && panel?.classList.contains("hidden")) return;
    updateFetchBusy = true;
    try {
      const response = await fetch("/atualizacoes/jobs", {cache:"no-store", credentials:"same-origin"});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      renderUpdateCards(payload);
    } catch (_error) {
      // A fila nativa permanece funcional se o resumo não puder ser atualizado.
    } finally {
      updateFetchBusy = false;
    }
  }

  function scheduleRefine(delay = 40) {
    clearTimeout(refineTimer);
    refineTimer = window.setTimeout(refineQueueStructure, delay);
  }

  function scheduleUpdateRefresh(delay = 80, force = false) {
    clearTimeout(updateTimer);
    updateTimer = window.setTimeout(() => refreshUpdateCards(force), delay);
  }

  function bindEvents() {
    document.addEventListener("change", event => {
      const id = event.target?.id || "";
      if (id === "updates_queue_status_filter") {
        syncUpdateTotalFilter();
        renderUpdateCards(updatePayload);
      } else if (id === "updates_queue_select") {
        scheduleUpdateRefresh(40, true);
      } else if (id === "addition_queue_state") {
        window.setTimeout(decorateAdditionCards, 80);
      }
    }, true);
    document.addEventListener("click", event => {
      const id = event.target?.closest?.("button")?.id || "";
      if (["tab_btn_atualizacoes","updates_refresh_btn","cs_updates_queue_refresh_v1"].includes(id)) {
        scheduleRefine(60);
        scheduleUpdateRefresh(id === "tab_btn_atualizacoes" ? 80 : 260, true);
      }
      if (["tab_btn_adicoes","addition_queue_refresh"].includes(id)) {
        scheduleRefine(100);
        window.setTimeout(decorateAdditionCards, 220);
      }
    }, true);
  }

  function observe() {
    [$("#tab_panel_atualizacoes"), $("#tab_panel_adicoes")].filter(Boolean).forEach(panel => {
      new MutationObserver(() => scheduleRefine(45)).observe(panel, {childList:true, subtree:true});
    });
  }

  function start() {
    installStyles();
    refineQueueStructure();
    bindEvents();
    observe();
    scheduleUpdateRefresh(100, true);
    [120,320,700,1400,2800].forEach(delay => window.setTimeout(refineQueueStructure, delay));
    window.setInterval(() => {
      if (document.hidden) return;
      refineQueueStructure();
      const updatePanel = $("#tab_panel_atualizacoes");
      if (updatePanel && !updatePanel.classList.contains("hidden")) refreshUpdateCards();
    }, 1800);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
