(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const int = (value, fallback = 0) => {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const STATE_OPTIONS = [
    ["", "Todos"], ["approved", "Aprovado"], ["validating", "Validando"],
    ["downloading", "Baixando"], ["staging", "Preparando staging"],
    ["prepared", "Preparado"], ["planned", "Planejado"], ["plan_ready", "Plano pronto"],
    ["queued", "Aguardando execução"], ["executing", "Executando"], ["installing", "Instalando"],
    ["filesystem_validated", "Sistema de arquivos validado"], ["updating_wordpress", "Atualizando WordPress"],
    ["validating_wordpress", "Validando WordPress"], ["validated", "Validado"],
    ["dry_run_ready", "Simulação pronta"], ["completed", "Concluído"], ["blocked", "Bloqueado"],
    ["error", "Erro"], ["failed", "Falhou"], ["interrupted", "Interrompido"],
    ["canceled", "Cancelado"], ["rollback_required", "Rollback necessário"],
    ["rolling_back", "Rollback em andamento"], ["rolled_back", "Rollback concluído"],
  ];

  const PREPARATION_OPTIONS = [
    ["", "Todos"], ["approved", "Aprovado"], ["validating", "Validando"],
    ["downloading", "Baixando"], ["staging", "Preparando staging"], ["prepared", "Preparado"],
    ["planned", "Planejado"], ["plan_ready", "Plano pronto"], ["blocked", "Bloqueado"],
  ];

  // Contrato público da Etapa 1. A mesma definição alimenta contagem e listagem.
  const UPDATE_GROUPS = Object.freeze({
    total: Object.freeze({label: "Total", states: null, help: "Todos os produtos da lista de atualização ativa."}),
    prepared: Object.freeze({label: "Preparados", states: Object.freeze(["plan_ready"]), help: "Produtos realmente liberados para execução: plano pronto."}),
    running: Object.freeze({
      label: "Em andamento",
      states: Object.freeze(["executing", "installing", "filesystem_validated", "updating_wordpress", "validating_wordpress", "validated", "dry_run_ready", "rolling_back"]),
      help: "Produtos que já entraram na execução e ainda não chegaram a um estado terminal.",
    }),
    completed: Object.freeze({label: "Concluídos", states: Object.freeze(["completed"]), help: "Atualizações concluídas com sucesso."}),
    errors: Object.freeze({
      label: "Erros",
      states: Object.freeze(["blocked", "error", "failed", "interrupted", "rollback_required"]),
      help: "Itens bloqueados, com erro, falha, interrupção ou rollback necessário.",
    }),
  });

  const VIEW = {
    activeGroup: "total",
    page: 1,
    runtime: null,
    refreshing: false,
    timers: [],
    summaryObserver: null,
    rowsObserver: null,
  };

  function installStyles() {
    if ($("#cs-update-stage1-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-stage1-style";
    style.textContent = `
      #cs_update_operational_summary{display:none!important}
      #updates_summary.cs-update-stage1-summary{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:8px!important;margin:12px 0 10px!important;padding:0!important;border:0!important;background:transparent!important}
      #updates_summary .cs-update-stage1-card{display:flex!important;flex-direction:column!important;align-items:stretch!important;justify-content:center!important;gap:5px!important;min-width:0!important;min-height:82px!important;padding:12px!important;border:1px solid var(--line)!important;border-radius:10px!important;background:rgba(255,255,255,.025)!important;color:var(--text)!important;text-align:left!important;font:inherit!important;box-shadow:none!important;transform:none!important;cursor:pointer!important}
      #updates_summary .cs-update-stage1-card:hover,#updates_summary .cs-update-stage1-card.is-active{border-color:rgba(124,58,237,.72)!important;background:rgba(124,58,237,.13)!important}
      #updates_summary .cs-update-stage1-card>strong{font-size:20px!important;font-weight:800!important;line-height:1!important}
      #updates_summary .cs-update-stage1-footer{display:flex!important;align-items:center!important;gap:6px!important;color:var(--text-muted)!important;font-size:12px!important;font-weight:600!important}
      #updates_summary .comparison-help{flex:0 0 24px!important;width:24px!important;min-width:24px!important;height:24px!important;min-height:24px!important;font-size:11px!important}
      #updates_queue_meta .cs-update-stage1-context{display:inline-flex;align-items:center;gap:5px;margin-left:7px;padding:3px 7px;border:1px solid var(--line);border-radius:999px;color:var(--text-muted);font-size:10px;font-weight:800}
      .cs-stage1-local-zip{display:inline-flex;margin-left:7px;padding:3px 7px;border:1px solid rgba(16,185,129,.38);border-radius:999px;background:rgba(16,185,129,.09);color:#8ce0bf;font-size:10px;font-weight:800}
      @media(max-width:1180px){#updates_summary.cs-update-stage1-summary{grid-template-columns:repeat(3,minmax(0,1fr))!important}}
      @media(max-width:760px){#updates_summary.cs-update-stage1-summary{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
      @media(max-width:480px){#updates_summary.cs-update-stage1-summary{grid-template-columns:1fr!important}}
    `;
    document.head.appendChild(style);
  }

  function fillSelect(select, options) {
    if (!select) return;
    const current = select.value;
    const allowed = new Set(options.map(([value]) => value));
    [...select.options].forEach(option => { if (!allowed.has(option.value)) option.remove(); });
    options.forEach(([value, label]) => {
      let option = [...select.options].find(item => item.value === value);
      if (!option) { option = document.createElement("option"); option.value = value; select.appendChild(option); }
      option.textContent = label;
    });
    if (allowed.has(current)) select.value = current;
  }

  function improveSelects() {
    fillSelect($("#updates_queue_status_filter"), STATE_OPTIONS);
    fillSelect($("#updates_status_filter"), PREPARATION_OPTIONS);
  }

  async function loadRuntime() {
    const response = await fetch("/atualizacoes/jobs", {cache: "no-store", credentials: "same-origin"});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
    return data;
  }

  function activeQueueJobs(data) {
    const queueName = text(data?.queue?.active_queue || "default");
    return (Array.isArray(data?.jobs) ? data.jobs : []).filter(job => text(job?.queue_name || "default") === queueName);
  }

  function jobsForGroup(data, key) {
    const jobs = activeQueueJobs(data);
    const group = UPDATE_GROUPS[key] || UPDATE_GROUPS.total;
    return group.states ? jobs.filter(job => group.states.includes(text(job?.state))) : jobs;
  }

  function helpButton(group) {
    return `<button type="button" class="comparison-help" aria-label="Ajuda sobre ${esc(group.label)}" data-tooltip="${esc(group.help)}">?</button>`;
  }

  function renderSummary(data) {
    const summary = $("#updates_summary");
    if (!summary) return;
    $("#cs_update_operational_summary")?.remove();
    VIEW.summaryObserver?.disconnect();
    summary.className = "cs-update-stage1-summary";
    summary.innerHTML = Object.entries(UPDATE_GROUPS).map(([key, group]) => {
      const count = jobsForGroup(data, key).length;
      return `<button type="button" class="cs-update-stage1-card${VIEW.activeGroup === key && !text($("#updates_queue_status_filter")?.value) ? " is-active" : ""}" data-cs-stage1-group="${esc(key)}" aria-pressed="${VIEW.activeGroup === key ? "true" : "false"}"><strong>${count}</strong><span class="cs-update-stage1-footer"><span>${esc(group.label)}</span>${helpButton(group)}</span></button>`;
    }).join("");
    VIEW.summaryObserver?.observe(summary, {childList: true});

    $$('[data-cs-stage1-group]', summary).forEach(card => card.addEventListener("click", event => {
      if (event.target.closest?.(".comparison-help")) return;
      activateGroup(card.dataset.csStage1Group || "total");
    }));
    $$(".comparison-help", summary).forEach(button => button.addEventListener("click", event => {
      event.preventDefault(); event.stopPropagation();
    }));
  }

  function stateLabel(state) {
    return STATE_OPTIONS.find(([value]) => value === state)?.[1] || text(state, "Estado não reconhecido");
  }

  function sourceLabel(job) {
    const explicit = text(job?.source_name || job?.source_site || job?.source_site_key || job?.origin_site || job?.origin);
    if (explicit) return explicit;
    const url = text(job?.source_product_url || job?.source_url || job?.ultrapack_url).toLowerCase();
    if (url.includes("plugintheme")) return "PluginTheme";
    if (url.includes("ultrapack")) return "UltraPackV2";
    return "Origem não informada";
  }

  function compactRow(job, position) {
    const nextVersion = text(job?.effective_source_version || job?.approved_source_version || job?.ultrapack_version, "-");
    const error = text(job?.execution_error || job?.blocked_reason);
    const local = text(job?.local_staging_path) && text(job?.new_sha256) ? '<span class="cs-stage1-local-zip">ZIP local</span>' : "";
    return `<article class="update-queue-row" data-cs-stage1-job="${esc(job?.job_id)}"><div class="update-queue-position">${esc(position)}</div><div><strong>${esc(job?.name || "Produto sem nome")}</strong>${local}<div class="small">Woo #${esc(job?.woo_product_id)} · ${esc(job?.plugintema_version || "-")} → ${esc(nextVersion)}</div><div class="small">Origem: ${esc(sourceLabel(job))}</div>${error ? `<div class="updates-error">${esc(error)}</div>` : ""}</div><span class="badge">${esc(stateLabel(text(job?.state)))}</span><button type="button" class="btn-secondary" data-cs-stage1-detail="${esc(job?.job_id)}" aria-expanded="false">Detalhes</button><div class="update-operational-detail hidden"></div></article>`;
  }

  function bindDetails(root, jobs) {
    $$('[data-cs-stage1-detail]', root).forEach(button => button.addEventListener("click", () => {
      const job = jobs.find(item => text(item?.job_id) === text(button.dataset.csStage1Detail));
      const slot = $(".update-operational-detail", button.closest(".update-queue-row"));
      if (!job || !slot) return;
      const hidden = slot.classList.toggle("hidden");
      button.setAttribute("aria-expanded", String(!hidden));
      if (!hidden && slot.dataset.rendered !== "1") {
        const logs = Array.isArray(job?.execution_logs) ? job.execution_logs.join("\n") : "";
        slot.innerHTML = `<div class="small"><strong>${esc(job?.name)}</strong><br>Woo #${esc(job?.woo_product_id)} · Tentativas: ${esc(job?.attempts ?? 0)} · Última etapa: ${esc(job?.last_completed_step || "-")}</div>${logs ? `<details><summary>Ver log técnico</summary><pre>${esc(logs)}</pre></details>` : ""}`;
        slot.dataset.rendered = "1";
      }
    }));
  }

  function rangeText(total, page, size) {
    if (!total) return "Mostrando 0 de 0 itens";
    const start = ((page - 1) * size) + 1;
    return `Mostrando ${start}–${Math.min(page * size, total)} de ${total} itens`;
  }

  function renderGroupedList(data) {
    if (!VIEW.activeGroup) return false;
    const wrap = $("#updates_queue_jobs");
    if (!wrap) return false;
    const query = text($("#updates_queue_search")?.value).toLowerCase();
    const source = jobsForGroup(data, VIEW.activeGroup);
    const filtered = source.filter(job => !query || `${job?.name || ""} ${job?.woo_product_id || ""}`.toLowerCase().includes(query));
    const size = Math.max(1, int($("#updates_queue_page_size")?.value, 5));
    const pages = Math.max(1, Math.ceil(filtered.length / size));
    VIEW.page = Math.min(Math.max(1, VIEW.page), pages);
    const visible = filtered.slice((VIEW.page - 1) * size, VIEW.page * size);
    const group = UPDATE_GROUPS[VIEW.activeGroup] || UPDATE_GROUPS.total;

    VIEW.rowsObserver?.disconnect();
    $("#updates_queue_list_controls")?.classList.toggle("hidden", activeQueueJobs(data).length === 0);
    if ($("#updates_queue_found_count")) $("#updates_queue_found_count").textContent = rangeText(filtered.length, VIEW.page, size);
    if ($("#updates_queue_page")) $("#updates_queue_page").textContent = `Página ${VIEW.page} de ${pages}`;
    if ($("#updates_queue_prev")) $("#updates_queue_prev").disabled = VIEW.page <= 1;
    if ($("#updates_queue_next")) $("#updates_queue_next").disabled = VIEW.page >= pages;
    if ($("#updates_queue_meta")) $("#updates_queue_meta").innerHTML = `${activeQueueJobs(data).length} produtos <span class="cs-update-stage1-context">Filtro: ${esc(group.label)}</span>`;
    wrap.innerHTML = visible.map((job, index) => compactRow(job, job?.state === "executing" ? "Agora" : (job?.queue_position || ((VIEW.page - 1) * size) + index + 1))).join("") || '<div class="notice">Nenhum produto corresponde a este filtro.</div>';
    VIEW.rowsObserver?.observe(wrap, {childList: true});
    bindDetails(wrap, visible);
    return true;
  }

  function activateGroup(key) {
    VIEW.activeGroup = UPDATE_GROUPS[key] ? key : "total";
    VIEW.page = 1;
    const technical = $("#updates_queue_status_filter");
    if (technical) technical.value = "";
    if (VIEW.runtime) { renderSummary(VIEW.runtime); renderGroupedList(VIEW.runtime); }
  }

  async function refresh() {
    if (VIEW.refreshing || !$("#updates_queue_jobs")) return;
    VIEW.refreshing = true;
    try {
      improveSelects();
      const data = await loadRuntime();
      VIEW.runtime = data;
      renderSummary(data);
      if (VIEW.activeGroup) renderGroupedList(data);
    } catch (_error) {
      // A implementação nativa continua disponível se a camada canônica falhar.
    } finally {
      VIEW.refreshing = false;
    }
  }

  function schedule(delays = [0, 120]) {
    VIEW.timers.forEach(window.clearTimeout);
    VIEW.timers = delays.map(delay => window.setTimeout(refresh, delay));
  }

  function observeNativeRenders() {
    const summary = $("#updates_summary");
    if (summary) {
      VIEW.summaryObserver = new MutationObserver(() => schedule([0]));
      VIEW.summaryObserver.observe(summary, {childList: true});
    }
    const rows = $("#updates_queue_jobs");
    if (rows) {
      VIEW.rowsObserver = new MutationObserver(() => { if (VIEW.activeGroup) schedule([0]); });
      VIEW.rowsObserver.observe(rows, {childList: true});
    }
  }

  function bindControls() {
    document.addEventListener("change", event => {
      if (event.target?.id === "updates_queue_status_filter") {
        // Só ação explícita no filtro técnico encerra o grupo. Polling não dispara change.
        VIEW.activeGroup = "";
        VIEW.page = 1;
        schedule([20]);
      } else if (event.target?.id === "updates_queue_page_size" && VIEW.activeGroup) {
        VIEW.page = 1;
        if (VIEW.runtime) renderGroupedList(VIEW.runtime);
      } else if (event.target?.id === "updates_queue_select") {
        VIEW.page = 1;
        schedule([80, 300]);
      }
    }, true);

    document.addEventListener("input", event => {
      if (event.target?.id === "updates_queue_search" && VIEW.activeGroup) {
        VIEW.page = 1;
        if (VIEW.runtime) renderGroupedList(VIEW.runtime);
      }
    }, true);

    $("#updates_queue_prev")?.addEventListener("click", event => {
      if (!VIEW.activeGroup) return;
      event.preventDefault(); event.stopImmediatePropagation();
      VIEW.page = Math.max(1, VIEW.page - 1);
      if (VIEW.runtime) renderGroupedList(VIEW.runtime);
    }, true);
    $("#updates_queue_next")?.addEventListener("click", event => {
      if (!VIEW.activeGroup) return;
      event.preventDefault(); event.stopImmediatePropagation();
      VIEW.page += 1;
      if (VIEW.runtime) renderGroupedList(VIEW.runtime);
    }, true);

    $("#tab_btn_atualizacoes")?.addEventListener("click", () => schedule([0, 100, 400]));
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes") schedule([0, 100, 400]);
    });
  }

  function exposeContract() {
    window.__crapscraperUpdateOperationalStage1 = Object.freeze({
      groups: UPDATE_GROUPS,
      jobsForGroup,
      get activeGroup() { return VIEW.activeGroup; },
    });
  }

  function start() {
    installStyles();
    improveSelects();
    observeNativeRenders();
    bindControls();
    exposeContract();
    schedule([0, 100]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
