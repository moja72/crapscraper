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
  const $ = (selector, root = document) => root.querySelector(selector);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if ($("#cs-update-operational-filter-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-operational-filter-style";
    style.textContent = `
      .cs-update-operational-summary{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0;padding:12px;border:1px solid #292931;border-radius:12px;background:#111114}
      .cs-update-operational-chip{display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border:1px solid #303039;border-radius:999px;background:#17171b;color:#d9d9e2;font-size:12px;line-height:1;cursor:default}
      button.cs-update-operational-chip{cursor:pointer}.cs-update-operational-chip strong{color:#fff;font-size:13px}
      button.cs-update-operational-chip:hover{border-color:#6d3bb5;background:#20182d}
      .cs-update-operational-guidance{flex:1 1 100%;margin-top:3px;padding-top:10px;border-top:1px solid #26262d;color:#a7a7b2;font-size:12px;line-height:1.45}
      .cs-zip-local-badge{display:inline-flex;align-items:center;gap:4px;margin-left:7px;padding:3px 7px;border:1px solid rgba(16,185,129,.38);border-radius:999px;background:rgba(16,185,129,.09);color:#8ce0bf;font-size:10px;font-weight:800;vertical-align:middle}
      @media(max-width:720px){.cs-update-operational-chip{flex:1 1 auto;justify-content:center}}
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

  function selectState(state) {
    const select = $("#updates_queue_status_filter");
    if (!select) return;
    select.value = state;
    select.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function chip(label, count, state = "") {
    const tag = state ? "button" : "span";
    return `<${tag} ${state ? `type="button" data-cs-update-state="${state}"` : ""} class="cs-update-operational-chip"><strong>${count}</strong>${label}</${tag}>`;
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
      chip("Total", jobs.length),
      chip("Concluídos", completed, "completed"),
      chip("Aprovados", counts.approved || 0, "approved"),
      chip("Validando", counts.validating || 0, "validating"),
      chip("Plano pronto", planReady, "plan_ready"),
      chip("Na fila", queued, "queued"),
      chip("Executando", executing, executing ? "executing" : ""),
      chip("Bloqueados", counts.blocked || 0, "blocked"),
      chip("Erros", (counts.error || 0) + (counts.failed || 0), counts.error ? "error" : "failed"),
      chip("Rollback necessário", counts.rollback_required || 0, "rollback_required"),
      chip("ZIP local registrado", local),
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
      badge.title = "Há caminho de staging e SHA-256 persistidos para este job. O arquivo ainda será revalidado antes do reaproveitamento.";
      const firstStrong = main.querySelector("strong");
      if (firstStrong) firstStrong.insertAdjacentElement("afterend", badge);
      else main.prepend(badge);
    });
  }

  let refreshTimer = null;
  let refreshing = false;
  async function refresh() {
    if (refreshing || !$("#updates_queue_jobs")) return;
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

  function schedule() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 100);
  }

  function start() {
    installStyles();
    improveFilterControls();
    refresh();
    new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true});
    window.setInterval(() => {
      if (!$("#tab_panel_atualizacoes")?.classList.contains("hidden")) refresh();
    }, 3000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
