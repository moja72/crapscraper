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
  const RETRYABLE_STATES = new Set(["blocked", "error", "failed", "interrupted", "canceled"]);
  const ACTIVE_STATES = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "dry_run_ready", "rolling_back"
  ]);
  const TERMINAL_STATES = new Set(["completed", "error", "failed", "blocked", "interrupted", "rollback_required", "rolled_back", "canceled"]);
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
      #updates_queue_jobs .cs-update-individual-busy{opacity:.78;cursor:wait!important}
    `;
    document.head.appendChild(style);
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      headers: options.body ? {"Content-Type": "application/json", ...(options.headers || {})} : (options.headers || {}),
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (_error) {}
    if (!response.ok || data?.ok === false) {
      const error = new Error(data?.message || data?.error || `HTTP ${response.status}`);
      error.data = data;
      error.status = response.status;
      throw error;
    }
    return data;
  }

  const postJson = (url, payload = {}) => requestJson(url, {method: "POST", body: JSON.stringify(payload)});

  function notify(message, kind = "ok") {
    document.querySelector(".cs-update-individual-toast")?.remove();
    const node = document.createElement("div");
    node.className = "cs-update-individual-toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = text(message);
    Object.assign(node.style, {
      position: "fixed", right: "18px", bottom: "18px", zIndex: "100000",
      maxWidth: "560px", padding: "12px 14px", borderRadius: "12px",
      border: `1px solid ${kind === "error" ? "#ef4444" : "#10b981"}`,
      background: kind === "error" ? "#451a1a" : "#063d2b", color: "#fff",
      fontWeight: "700", boxShadow: "0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 6000);
  }

  async function runtimeSnapshot(force = false) {
    const shared = window.__CRAPSCRAPER_UPDATE_RUNTIME__;
    if (!force && shared?.payload && Date.now() - Number(shared.at || 0) < 900) return shared.payload;
    const data = await requestJson("/atualizacoes/jobs");
    window.__CRAPSCRAPER_UPDATE_RUNTIME__ = {payload: data, at: Date.now()};
    return data;
  }

  function jobFromRow(row, runtime) {
    const id = text(row?.querySelector("[data-update-detail]")?.dataset?.updateDetail);
    return (Array.isArray(runtime?.jobs) ? runtime.jobs : []).find(item => text(item?.job_id) === id) || null;
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

  function individualActionButton(target) {
    const button = target?.closest?.("button");
    if (!button || !button.closest("#updates_queue_jobs .update-queue-row")) return null;
    const label = text(button.textContent).toLowerCase();
    if (button.classList.contains("update-execute")) return button;
    if (label === "executar" || label === "tentar novamente") return button;
    return null;
  }

  async function waitUntilTerminal(jobId, row, button) {
    const deadline = Date.now() + (35 * 60 * 1000);
    while (Date.now() < deadline) {
      await new Promise(resolve => window.setTimeout(resolve, 650));
      const runtime = await runtimeSnapshot(true);
      const current = (Array.isArray(runtime?.jobs) ? runtime.jobs : []).find(job => text(job?.job_id) === jobId);
      if (!current) throw new Error("O job deixou de aparecer no runtime durante a execução.");
      project(runtime);
      const state = text(current.state);
      if (ACTIVE_STATES.has(state)) button.textContent = LABELS[state] || "Executando…";
      if (!TERMINAL_STATES.has(state)) continue;
      return current;
    }
    throw new Error("A execução continua além do tempo de acompanhamento desta tela. Consulte os detalhes do job.");
  }

  async function runIndividual(button) {
    if (!button || button.dataset.csIndividualBusy === "1") return;
    const row = button.closest(".update-queue-row");
    if (!row) return;

    const original = text(button.textContent) || "Executar";
    button.dataset.csIndividualBusy = "1";
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.classList.add("cs-update-individual-busy");

    try {
      let runtime = await runtimeSnapshot(true);
      let job = jobFromRow(row, runtime);
      if (!job) throw new Error("Não foi possível localizar este job para execução individual.");
      if (text(job.state) === "rollback_required") {
        throw new Error("Este item exige revisão/rollback manual antes de uma nova tentativa.");
      }
      if (text(job.state) === "completed") {
        button.textContent = "Concluído";
        return;
      }

      let plan = job.execution_plan || null;
      const mustReprepare = RETRYABLE_STATES.has(text(job.state)) || text(job.state) !== "plan_ready" || plan?.ready !== true;
      if (mustReprepare) {
        button.textContent = "Preparando…";
        const prepared = await postJson("/atualizacoes/preparar", {job_id: job.job_id});
        if (prepared?.preview?.ready !== true) {
          throw new Error(prepared?.preview?.message || "A preparação não ficou pronta para execução.");
        }

        button.textContent = "Gerando plano…";
        const planned = await postJson("/atualizacoes/plano", {job_id: job.job_id});
        plan = planned?.plan || null;
        if (plan?.ready !== true) throw new Error(plan?.message || "O plano não ficou pronto para execução.");

        runtime = await runtimeSnapshot(true);
        job = jobFromRow(row, runtime) || job;
        project(runtime);
        if (text(job.state) === "completed" || plan?.terminal === true || plan?.already_current === true) {
          button.textContent = "Concluído";
          notify(`${job.name || "Produto"}: já estava atualizado; ciclo concluído sem escrita.`);
          return;
        }
      }

      if (!plan?.plan_id) {
        runtime = await runtimeSnapshot(true);
        job = jobFromRow(row, runtime) || job;
        plan = job.execution_plan || plan;
      }
      if (!plan?.plan_id) throw new Error("Plano pronto sem identificador de execução.");

      button.textContent = "Executando…";
      await postJson("/atualizacoes/executar", {
        job_id: job.job_id,
        plan_id: plan.plan_id,
        confirmation: `EXECUTAR ${job.woo_product_id}`,
      });

      const current = await waitUntilTerminal(text(job.job_id), row, button);
      if (text(current.state) !== "completed") {
        throw new Error(current.execution_error || `A tentativa terminou em ${LABELS[text(current.state)] || current.state}.`);
      }

      button.textContent = "Concluído";
      notify(`${current.name || "Produto"}: atualização concluída.`);
    } catch (error) {
      const reason = text(error?.message || String(error)) || "Falha não identificada.";
      notify(reason, "error");
      button.disabled = false;
      button.textContent = /tentar novamente/i.test(original) ? "Tentar novamente" : original;
    } finally {
      delete button.dataset.csIndividualBusy;
      button.removeAttribute("aria-busy");
      button.classList.remove("cs-update-individual-busy");
      try {
        const runtime = await runtimeSnapshot(true);
        const current = jobFromRow(row, runtime);
        if (current) {
          project(runtime);
          if (text(current.state) === "completed") {
            button.disabled = true;
            button.textContent = "Concluído";
          } else if (ERROR_STATES.has(text(current.state))) {
            button.disabled = false;
            button.textContent = text(current.state) === "rollback_required" ? "Revisão necessária" : "Tentar novamente";
          } else if (!button.disabled) {
            button.textContent = original;
          }
        }
      } catch (_error) {}
    }
  }

  document.addEventListener("click", event => {
    const action = individualActionButton(event.target);
    if (action) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      runIndividual(action);
      return;
    }
    if (event.target?.closest?.("[data-update-detail]")) setTimeout(refresh, 80);
  }, true);
  document.addEventListener("change", event => {
    if (event.target?.id === "updates_queue_status_filter") setTimeout(refresh, 50);
  }, true);

  installStyles();
  setInterval(refresh, 950);
  setTimeout(refresh, 120);
})();
