(() => {
  "use strict";
  if (window.__crapScraperUpdateStateSyncInstalled) return;
  window.__crapScraperUpdateStateSyncInstalled = true;

  const LABELS = {
    approved: "Aprovado",
    pending: "Pendente",
    validating: "Validando",
    downloading: "Baixando",
    staging: "Preparando staging",
    prepared: "Preparado",
    planned: "Plano gerado",
    plan_ready: "Plano pronto",
    queued: "Aguardando execução",
    executing: "Executando",
    installing: "Instalando",
    filesystem_validated: "Filesystem validado",
    updating_wordpress: "Atualizando WordPress",
    validating_wordpress: "Validando WordPress",
    validated: "Validado",
    completed: "Concluído",
    blocked: "Bloqueado",
    error: "Erro",
    failed: "Falhou",
    interrupted: "Interrompido",
    rollback_required: "Rollback necessário",
    rolling_back: "Rollback em andamento",
    rolled_back: "Rollback concluído",
    canceled: "Cancelado",
  };
  const ERROR_STATES = new Set(["blocked", "error", "failed", "interrupted", "rollback_required"]);
  let busy = false;

  function text(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function installStyles() {
    if (document.getElementById("cs-update-state-sync-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-state-sync-style";
    style.textContent = `
      .updates-lock.cs-execution-completed{border-color:rgba(16,185,129,.45)!important;background:rgba(16,185,129,.10)!important;color:#a7f3d0!important}
      .execution-plan-ready.cs-execution-completed{border-color:rgba(16,185,129,.45)!important;color:#a7f3d0!important}
    `;
    document.head.appendChild(style);
  }

  async function runtimeSnapshot() {
    const shared = window.__CRAPSCRAPER_UPDATE_RUNTIME__;
    if (shared?.payload && Date.now() - Number(shared.at || 0) < 1800) return shared.payload;
    const response = await fetch("/atualizacoes/jobs", {cache: "no-store", credentials: "same-origin"});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
    window.__CRAPSCRAPER_UPDATE_RUNTIME__ = {payload: data, at: Date.now()};
    return data;
  }

  function syncDetail(row, job) {
    const detail = row.querySelector(".update-operational-detail");
    if (!detail || detail.classList.contains("hidden")) return;
    const state = text(job?.state);
    const completed = state === "completed";
    const lock = detail.querySelector(".updates-lock");
    const ready = detail.querySelector(".execution-plan-ready");
    const executeButton = detail.querySelector(".update-execute");

    if (completed) {
      if (lock) {
        lock.textContent = "Execução concluída com sucesso";
        lock.classList.add("cs-execution-completed");
      }
      if (ready) {
        ready.textContent = "✓ Execução concluída e registrada no histórico";
        ready.classList.add("cs-execution-completed");
      }
      if (executeButton) {
        executeButton.textContent = "Concluído";
        executeButton.disabled = true;
        executeButton.setAttribute("aria-disabled", "true");
      }
      return;
    }

    if (lock && job?.execution_enabled === true && /bloquead|homologa/i.test(lock.textContent || "")) {
      lock.textContent = "Execução real habilitada · o plano continua sujeito às pré-condições de segurança";
    }
  }

  function syncRow(row, job) {
    if (!row || !job) return;
    const state = text(job.state);
    row.dataset.liveUpdateState = state;
    const badge = row.querySelector(".badge");
    if (badge) badge.textContent = LABELS[state] || state || "Estado não informado";

    const reason = row.querySelector(".updates-error");
    if (reason && !ERROR_STATES.has(state)) reason.remove();
    syncDetail(row, job);
  }

  function project(runtime) {
    installStyles();
    const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
    const byId = new Map(jobs.map(job => [text(job?.job_id), job]));
    document.querySelectorAll("#updates_queue_jobs .update-queue-row").forEach(row => {
      const id = text(row.querySelector("[data-update-detail]")?.dataset?.updateDetail);
      syncRow(row, byId.get(id));
    });
  }

  async function refresh() {
    if (busy || document.hidden || !document.getElementById("updates_queue_jobs")) return;
    busy = true;
    try { project(await runtimeSnapshot()); }
    catch (_error) { /* A UI nativa permanece disponível. */ }
    finally { busy = false; }
  }

  document.addEventListener("click", event => {
    if (event.target?.closest?.("[data-update-detail]")) setTimeout(refresh, 80);
  }, true);
  document.addEventListener("change", event => {
    if (event.target?.id === "updates_queue_status_filter") setTimeout(refresh, 50);
  }, true);

  installStyles();
  setInterval(refresh, 950);
  setTimeout(refresh, 120);
})();
