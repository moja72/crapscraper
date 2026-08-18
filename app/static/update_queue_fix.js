(() => {
  "use strict";

  const PREPARATION_STATES = new Set(["approved", "validating", "preparing", "downloading", "prepared"]);
  const ACTIVE_LIST_STATES = new Set(["plan_ready", "queued", "executing", "error", "failed", "blocked", "rollback_required"]);
  const COMPLETED_STATES = new Set(["completed", "rolled_back"]);
  let projectionBusy = false;

  function normalizeQueueName(value) {
    return String(value || "").trim() || "default";
  }

  function queueLabel(value) {
    const name = normalizeQueueName(value);
    return name === "default" ? "Padrão" : name;
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

  function projectRuntime(runtime) {
    const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
    const queue = runtime?.queue || {};
    const activeName = normalizeQueueName(queue.active_queue);
    const byId = new Map(jobs.map(job => [String(job?.job_id || ""), job]));
    const belongsToActiveList = job => String(job?.queue_name || "").trim() === activeName;

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

    const activeJobs = jobs.filter(belongsToActiveList);
    const activeVisibleJobs = activeJobs.filter(job => ACTIVE_LIST_STATES.has(String(job?.state || "")));
    const queueWrap = document.getElementById("updates_queue_jobs");
    if (queueWrap) {
      let visibleRows = 0;
      queueWrap.querySelectorAll(".update-queue-row").forEach(row => {
        const detail = row.querySelector("[data-update-detail]");
        const job = byId.get(String(detail?.dataset?.updateDetail || ""));
        const show = !!job && belongsToActiveList(job) && ACTIVE_LIST_STATES.has(String(job.state || ""));
        row.style.display = show ? "" : "none";
        if (show) visibleRows += 1;
      });
      ensureNotice(queueWrap, "cs-active-queue-empty", "Nenhum item pronto ou aguardando execução nesta lista.", visibleRows === 0);
    }

    const statusLabel = {running: "Executando", paused: "Pausada", stopped: "Fila parada"}[queue.status] || "Fila parada";
    const meta = document.getElementById("updates_queue_meta");
    if (meta) meta.textContent = `${activeVisibleJobs.length} produtos · ${statusLabel} · ${queueLabel(activeName)}`;
    document.getElementById("updates_queue_list_controls")?.classList.toggle("hidden", activeVisibleJobs.length === 0);

    const select = document.getElementById("updates_queue_select");
    if (select) {
      Array.from(select.options).forEach(option => {
        const name = normalizeQueueName(option.value);
        const listJobs = jobs.filter(job => String(job?.queue_name || "").trim() === name);
        const completed = listJobs.filter(job => COMPLETED_STATES.has(String(job?.state || ""))).length;
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
      // O painel principal já possui tratamento de indisponibilidade; este complemento é somente visual.
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
      const belongsToActive = job => String(job?.queue_name || "").trim() === activeName;
      const belongsToPreparationContext = job => normalizeQueueName(job?.queue_name) === activeName;

      const ready = jobs.filter(job => belongsToActive(job) && job?.state === "plan_ready" && job?.execution_eligible === true);
      if (ready.length) {
        button.textContent = "Adicionando planos prontos...";
        await post("/atualizacoes/fila/adicionar", {job_ids: ready.map(job => job.job_id)});
        runtime = await json("/atualizacoes/jobs");
        queue = runtime?.queue || queue;
        jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : jobs;
      }

      const queued = jobs.filter(job => belongsToActive(job) && job?.state === "queued");
      const executing = jobs.filter(job => belongsToActive(job) && job?.state === "executing");

      if (!queued.length && !executing.length) {
        const preparing = jobs.filter(job => belongsToPreparationContext(job) && PREPARATION_STATES.has(String(job?.state || "")));
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

  document.addEventListener("click", event => {
    const button = event.target?.closest?.("#updates_queue_start");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    executeQueue(button);
  }, true);

  window.setInterval(refreshProjection, 1200);
  window.setTimeout(refreshProjection, 100);
})();
