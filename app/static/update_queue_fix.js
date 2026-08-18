(() => {
  "use strict";

  const PREPARATION_STATES = new Set(["approved", "validating", "preparing", "downloading", "staging", "prepared", "planned"]);
  const ACTIVE_EXECUTION_STATES = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "dry_run_ready", "rolling_back"
  ]);
  const DEFAULT_QUEUE_STATES = new Set([
    "plan_ready", "queued", ...ACTIVE_EXECUTION_STATES,
    "error", "failed", "blocked", "rollback_required", "interrupted"
  ]);
  const COMPLETED_STATES = new Set(["completed", "rolled_back"]);
  let projectionBusy = false;

  function normalizeQueueName(value) {
    return String(value || "").trim() || "default";
  }

  function queueLabel(value) {
    const name = normalizeQueueName(value);
    return name === "default" ? "Padrão" : name;
  }

  function text(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  function installLiveLogStyles() {
    if (document.getElementById("cs-update-queue-live-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-queue-live-style";
    style.textContent = `
      #updates_queue_jobs .cs-update-live-log{margin-top:9px;padding:9px 11px;border:1px solid #2b2b33;border-radius:10px;background:#0d0d10;display:grid;gap:7px;max-width:760px}
      #updates_queue_jobs .cs-update-live-head{display:flex;align-items:center;gap:8px;color:#c7cbd4;font-size:11px;font-weight:800;line-height:1.25}
      #updates_queue_jobs .cs-update-live-spinner{width:11px;height:11px;flex:0 0 11px;border:2px solid rgba(255,255,255,.16);border-top-color:#10b981;border-radius:50%;animation:csUpdateQueueSpin .75s linear infinite}
      #updates_queue_jobs .cs-update-live-lines{color:#9da7b5;font:10.5px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
      #updates_queue_jobs .cs-update-live-step{color:#7f8794;font-size:10px}
      #updates_queue_jobs .cs-update-history-pending{color:#fbbf24}
      @keyframes csUpdateQueueSpin{to{transform:rotate(360deg)}}
      @media(prefers-reduced-motion:reduce){#updates_queue_jobs .cs-update-live-spinner{animation:none!important}}
    `;
    document.head.appendChild(style);
  }

  function toast(message, kind = "ok") {
    document.querySelector(".cs-update-queue-fix-toast")?.remove();
    const node = document.createElement("div");
    node.className = "cs-update-queue-fix-toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = String(message || "");
    const palette = kind === "error"
      ? {border: "#ef4444", background: "#451a1a"}
      : kind === "warning"
        ? {border: "#f59e0b", background: "#3b2a05"}
        : {border: "#10b981", background: "#063d2b"};
    Object.assign(node.style, {
      position: "fixed", right: "18px", bottom: "18px", zIndex: "100000",
      maxWidth: "560px", padding: "12px 14px", borderRadius: "12px",
      border: `1px solid ${palette.border}`,
      background: palette.background, color: "#fff",
      fontWeight: "700", boxShadow: "0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  async function json(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (_error) {}
    if (!response.ok || data?.ok === false) {
      const error = new Error(data?.message || data?.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  const post = (url, payload = {}) => json(url, {method: "POST", body: JSON.stringify(payload)});

  function ensureNotice(container, className, message, show) {
    if (!container) return;
    let notice = container.querySelector(`.${className}`);
    if (!show) {
      notice?.remove();
      return;
    }
    if (!notice) {
      notice = document.createElement("div");
      notice.className = `notice ${className}`;
      container.appendChild(notice);
    }
    notice.textContent = message;
  }

  function currentStateFilter() {
    return text(document.getElementById("updates_queue_status_filter")?.value);
  }

  function belongsToQueue(job, activeName) {
    return normalizeQueueName(job?.queue_name) === activeName;
  }

  function queueJobVisible(job, activeName, stateFilter) {
    if (!job || !belongsToQueue(job, activeName)) return false;
    const state = text(job.state);
    if (stateFilter) return state === stateFilter;
    if (COMPLETED_STATES.has(state)) return job.history_ready !== true;
    return DEFAULT_QUEUE_STATES.has(state);
  }

  function liveLogs(job) {
    const live = Array.isArray(job?.live_execution_logs) ? job.live_execution_logs : [];
    const persisted = Array.isArray(job?.execution_logs) ? job.execution_logs : [];
    return (live.length ? live : persisted).map(String);
  }

  function liveStatus(job) {
    const state = text(job?.state);
    const labels = {
      executing: "Executando atualização",
      installing: "Instalando atualização",
      filesystem_validated: "Sistema de arquivos validado",
      updating_wordpress: "Atualizando WordPress",
      validating_wordpress: "Validando WordPress",
      validated: "Validação concluída",
      dry_run_ready: "Simulação pronta",
      rolling_back: "Executando rollback",
      completed: "Finalizando registro no histórico",
      rolled_back: "Finalizando registro do rollback"
    };
    return labels[state] || "Processando atualização";
  }

  function annotateLiveRow(row, job) {
    row.querySelector(".cs-update-live-log")?.remove();
    const state = text(job?.state);
    const logs = liveLogs(job);
    const completionPending = COMPLETED_STATES.has(state) && job?.history_ready !== true;
    if (!ACTIVE_EXECUTION_STATES.has(state) && !completionPending && !logs.length) return;

    const main = row.children?.[1] || row.querySelector("div:nth-child(2)") || row;
    if (!main) return;
    const tail = logs.slice(-4);
    const step = text(job?.last_completed_step);
    const block = document.createElement("div");
    block.className = "cs-update-live-log";
    block.setAttribute("aria-live", "polite");
    block.innerHTML = `
      <div class="cs-update-live-head ${completionPending ? "cs-update-history-pending" : ""}">
        <span class="cs-update-live-spinner" aria-hidden="true"></span>
        <span>${escapeHtml(liveStatus(job))}</span>
      </div>
      ${tail.length ? `<div class="cs-update-live-lines">${tail.map(escapeHtml).join("\n")}</div>` : ""}
      ${step ? `<div class="cs-update-live-step">Última etapa concluída: ${escapeHtml(step)}</div>` : ""}
    `;
    main.appendChild(block);
  }

  function projectRuntime(runtime) {
    installLiveLogStyles();
    const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
    const queue = runtime?.queue || {};
    const activeName = normalizeQueueName(queue.active_queue);
    const byId = new Map(jobs.map(job => [String(job?.job_id || ""), job]));

    const prepWrap = document.getElementById("updates_jobs");
    if (prepWrap) {
      let visiblePrep = 0;
      prepWrap.querySelectorAll("[data-update-job-id]").forEach(card => {
        const job = byId.get(String(card.dataset.updateJobId || ""));
        const show = !!job && PREPARATION_STATES.has(String(job.state || ""));
        card.style.display = show ? "" : "none";
        if (show) visiblePrep += 1;
      });
      document.getElementById("updates_working_controls")?.classList.toggle("hidden", visiblePrep === 0);
      const found = document.getElementById("updates_found_count");
      if (found && visiblePrep === 0) found.textContent = "0 itens encontrados";
      ensureNotice(prepWrap, "cs-preparation-empty", "Nenhum job aguardando preparação.", visiblePrep === 0);
    }

    const activeJobs = jobs.filter(job => belongsToQueue(job, activeName));
    const stateFilter = currentStateFilter();
    const projectedJobs = activeJobs.filter(job => queueJobVisible(job, activeName, stateFilter));
    const defaultPending = activeJobs.filter(job => queueJobVisible(job, activeName, ""));
    const queueWrap = document.getElementById("updates_queue_jobs");
    if (queueWrap) {
      let visibleRows = 0;
      queueWrap.querySelectorAll(".update-queue-row").forEach(row => {
        const detail = row.querySelector("[data-update-detail]");
        const job = byId.get(String(detail?.dataset?.updateDetail || ""));
        const show = queueJobVisible(job, activeName, stateFilter);
        row.style.display = show ? "" : "none";
        if (show) {
          visibleRows += 1;
          annotateLiveRow(row, job);
        } else {
          row.querySelector(".cs-update-live-log")?.remove();
        }
      });
      const emptyMessage = stateFilter === "completed"
        ? "Nenhum item concluído nesta lista."
        : "Nenhum item pendente de execução nesta lista.";
      ensureNotice(queueWrap, "cs-active-queue-empty", emptyMessage, visibleRows === 0 && projectedJobs.length === 0);
    }

    const statusLabel = {running: "Executando", paused: "Pausada", stopped: "Fila parada"}[queue.status] || "Fila parada";
    const meta = document.getElementById("updates_queue_meta");
    if (meta) {
      const completed = activeJobs.filter(job => text(job.state) === "completed" && job.history_ready === true).length;
      meta.textContent = `${defaultPending.length} pendentes · ${completed} concluídos · ${statusLabel} · ${queueLabel(activeName)}`;
    }
    document.getElementById("updates_queue_list_controls")?.classList.toggle("hidden", activeJobs.length === 0);

    const select = document.getElementById("updates_queue_select");
    if (select) {
      Array.from(select.options).forEach(option => {
        const name = normalizeQueueName(option.value);
        const listJobs = jobs.filter(job => belongsToQueue(job, name));
        const completed = listJobs.filter(job => COMPLETED_STATES.has(String(job?.state || "")) && job.history_ready === true).length;
        option.textContent = `${queueLabel(name)} (${completed}/${listJobs.length})`;
      });
    }
  }

  async function refreshProjection() {
    if (projectionBusy || document.hidden || !document.getElementById("updates_queue_jobs")) return;
    projectionBusy = true;
    try {
      projectRuntime(await json("/atualizacoes/jobs"));
    } catch (_error) {
      // O painel principal continua funcional mesmo se esta projeção visual falhar.
    } finally {
      projectionBusy = false;
    }
  }

  async function executeQueue(button) {
    if (!button || button.dataset.csQueueBusy === "1") return;
    button.dataset.csQueueBusy = "1";
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Verificando fila...";
    try {
      let runtime = await json("/atualizacoes/jobs");
      let queue = runtime?.queue || {};
      const activeName = normalizeQueueName(queue.active_queue);
      let jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
      const belongsToActive = job => belongsToQueue(job, activeName);

      const ready = jobs.filter(job => belongsToActive(job) && job?.state === "plan_ready" && job?.execution_eligible === true);
      if (ready.length) {
        button.textContent = "Adicionando planos prontos...";
        await post("/atualizacoes/fila/adicionar", {job_ids: ready.map(job => job.job_id)});
        runtime = await json("/atualizacoes/jobs");
        queue = runtime?.queue || queue;
        jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : jobs;
      }

      const queued = jobs.filter(job => belongsToActive(job) && job?.state === "queued");
      const executing = jobs.filter(job => belongsToActive(job) && ACTIVE_EXECUTION_STATES.has(text(job?.state)));

      if (!queued.length && !executing.length) {
        const preparing = jobs.filter(job => belongsToActive(job) && PREPARATION_STATES.has(String(job?.state || "")));
        if (preparing.length) {
          toast(`${preparing.length} item(ns) ainda está(ão) em preparação. Quando o plano ficar pronto, ele aparecerá na lista ${queueLabel(activeName)}.`, "warning");
          return;
        }
        toast(`A lista ${queueLabel(activeName)} não possui itens prontos para execução.`, "error");
        return;
      }
      if (executing.length && queue.status === "running") {
        toast("A fila já está em execução.", "ok");
        return;
      }

      button.textContent = queue.status === "paused" ? "Retomando..." : "Iniciando...";
      const path = queue.status === "paused" ? "/atualizacoes/fila/continuar" : "/atualizacoes/fila/iniciar";
      const result = await post(path, {});
      const status = result?.queue?.status || "running";
      toast(result?.started === false && status === "running" ? "A fila já estava em execução." : "Fila iniciada com sucesso.", "ok");
      window.setTimeout(refreshProjection, 250);
    } catch (error) {
      let message = error?.message || String(error);
      if (error?.status === 403 && /bloquead|configura/i.test(message)) {
        message += " Ative SCRAPER_UPDATE_EXECUTION_ENABLED=1 no ambiente do Windows e reinicie o CrapScraper.";
      }
      toast(message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original || "Executar fila";
      delete button.dataset.csQueueBusy;
    }
  }

  document.addEventListener("change", event => {
    if (event.target?.id === "updates_queue_status_filter") window.setTimeout(refreshProjection, 30);
  }, true);

  document.addEventListener("click", event => {
    const button = event.target?.closest?.("#updates_queue_start");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    executeQueue(button);
  }, true);

  installLiveLogStyles();
  window.setInterval(refreshProjection, 900);
  window.setTimeout(refreshProjection, 100);
})();
