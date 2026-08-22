(() => {
  "use strict";

  if (window.__crapScraperUpdateOperationalFiltersInstalled) return;
  window.__crapScraperUpdateOperationalFiltersInstalled = true;

  const STATE_OPTIONS = [
    ["", "Todos"], ["approved", "Aprovado"], ["validating", "Validando"],
    ["downloading", "Baixando"], ["staging", "Preparando staging"], ["prepared", "Preparado"],
    ["planned", "Planejado"], ["plan_ready", "Plano pronto"], ["queued", "Aguardando execução"],
    ["executing", "Executando"], ["installing", "Instalando"],
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

  const TERMINAL_ERROR = new Set(["blocked", "error", "failed", "interrupted", "rollback_required"]);
  const PREPARATION = new Set(["approved", "validating", "downloading", "staging", "prepared", "planned"]);
  const EXECUTION = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "dry_run_ready", "rolling_back",
  ]);
  const $ = (selector, root = document) => root.querySelector(selector);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function panelVisible() {
    const panel = $("#tab_panel_atualizacoes");
    return !!panel && !panel.classList.contains("hidden");
  }

  function installStyles() {
    if ($("#cs-update-operational-filter-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-operational-filter-style";
    style.textContent = `
      .cs-update-operational-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:8px;margin:12px 0}
      .cs-update-operational-chip{display:grid;align-content:center;gap:4px;min-height:72px;padding:11px 12px;border:1px solid var(--line);border-radius:var(--radius-xs);background:var(--bg-elev-2);color:var(--text);font-size:11px;font-weight:700;text-align:left;cursor:default}
      button.cs-update-operational-chip{cursor:pointer}
      .cs-update-operational-chip strong{color:var(--text);font-size:21px;line-height:1;font-variant-numeric:tabular-nums}
      button.cs-update-operational-chip:hover{border-color:var(--line-accent);background:var(--accent-soft)}
      .cs-update-operational-guidance{grid-column:1/-1;margin-top:2px;padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius-xs);background:rgba(255,255,255,.018);color:var(--text-muted);font-size:12px;line-height:1.45}
      .cs-zip-local-badge{display:inline-flex;align-items:center;gap:4px;margin-left:7px;padding:3px 7px;border:1px solid rgba(16,185,129,.38);border-radius:999px;background:rgba(16,185,129,.09);color:#8ce0bf;font-size:10px;font-weight:800;vertical-align:middle}
      @media(max-width:620px){.cs-update-operational-summary{grid-template-columns:1fr}}
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
    fillSelect($("#updates_queue_status_filter"), STATE_OPTIONS);
    fillSelect($("#updates_status_filter"), PREPARATION_OPTIONS);
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

  function selectState(state) {
    const select = $("#updates_queue_status_filter");
    if (!select) return;
    select.value = state;
    select.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function chip(label, count, state = "") {
    const tag = state ? "button" : "span";
    const stateAttribute = state ? `type="button" data-cs-update-state="${state}"` : "";
    return `<${tag} ${stateAttribute} class="cs-update-operational-chip"><strong>${count}</strong><span>${label}</span></${tag}>`;
  }

  function renderSummary(data) {
    const controls = $("#updates_queue_list_controls");
    if (!controls) return;
    let summary = $("#cs_update_operational_summary");
    if (!summary) {
      summary = document.createElement("div");
      summary.id = "cs_update_operational_summary";
      summary.className = "cs-update-operational-summary cs-operational-stats";
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
    else if (attention > 0) guidance = `${attention} item(ns) exigem atenção. Use o filtro Estado para separar bloqueios e erros.`;
    else if (completed > 0) guidance = "Os concluídos ficam disponíveis pelo filtro Concluído e no Histórico.";
    else guidance = "A fila está vazia. Use a Preparação para gerar planos e adicionar produtos.";

    summary.innerHTML = [
      chip("Total", jobs.length),
      chip("Aguardando", counts.approved || 0, "approved"),
      chip("Preparados", planReady, "plan_ready"),
      chip("Na fila", queued, "queued"),
      chip("Executando", executing, executing ? "executing" : ""),
      chip("Concluídos", completed, "completed"),
      chip("Erros", (counts.error || 0) + (counts.failed || 0), counts.error ? "error" : "failed"),
      local ? chip("ZIP local", local) : "",
      `<div class="cs-update-operational-guidance">${guidance}</div>`,
    ].join("");

    summary.querySelectorAll("[data-cs-update-state]").forEach(button => {
      button.addEventListener("click", () => selectState(button.dataset.csUpdateState || ""));
    });
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
      badge.title = "Há staging e SHA-256 persistidos; o arquivo será revalidado antes do reaproveitamento.";
      const firstStrong = main.querySelector("strong");
      if (firstStrong) firstStrong.insertAdjacentElement("afterend", badge);
      else main.prepend(badge);
    });
  }

  let refreshing = false;
  async function refresh() {
    if (refreshing || !panelVisible() || !$("#updates_queue_jobs")) return;
    refreshing = true;
    try {
      improveFilterControls();
      const data = await loadRuntime();
      renderSummary(data);
      annotateVisibleRows(data);
    } catch (_error) {
      // O painel nativo continua funcional mesmo se este resumo adicional falhar.
    } finally {
      refreshing = false;
    }
  }

  function activate() {
    if (!panelVisible()) return;
    improveFilterControls();
    refresh();
  }

  function scheduleAfterOperation() {
    [700, 2200].forEach(delay => window.setTimeout(() => {
      if (panelVisible() && !document.hidden) refresh();
    }, delay));
  }

  function start() {
    installStyles();
    improveFilterControls();
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => setTimeout(activate, 0));
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes") activate();
    });
    [
      "updates_refresh_btn", "updates_prepare_selected", "updates_enqueue_selected",
      "updates_queue_start", "updates_queue_pause", "updates_queue_cancel",
    ].forEach(id => {
      document.getElementById(id)?.addEventListener("click", scheduleAfterOperation);
    });
    if (panelVisible()) activate();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();