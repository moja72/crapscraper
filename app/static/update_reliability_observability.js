(() => {
  "use strict";

  if (window.__crapScraperUpdateReliabilityObservabilityInstalled) return;
  window.__crapScraperUpdateReliabilityObservabilityInstalled = true;

  const TERMINAL_ERRORS = new Set(["error", "failed", "blocked", "rollback_required", "rolled_back", "canceled", "interrupted"]);
  const RETRYABLE = new Set(["error", "failed", "blocked", "interrupted"]);
  const RETRY_SELECTOR = ".update-retry-btn,[data-update-history-retry]";
  const POLL_MS = 900;
  const TIMEOUT_MS = 30 * 60 * 1000;
  let refreshTimer = 0;
  let refreshing = false;

  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const escapeHtml = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

  function installStyles() {
    if (document.getElementById("cs-update-reliability-observability-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-reliability-observability-style";
    style.textContent = `
      .cs-update-status-stack{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:3px;min-width:160px}
      .cs-update-status-stack>.badge{margin:0}
      .cs-update-status-line{color:var(--text-muted,#9ca3af);font-size:11px;line-height:1.35;white-space:nowrap}
      .cs-update-success-count{color:var(--text-muted,#9ca3af);font-size:11px;line-height:1.35;white-space:nowrap}
      .cs-update-success-count strong{color:var(--text,#e5e7eb);font-weight:800}
      .cs-update-failure-summary{margin-top:5px;color:#cbd5e1;font-size:11px;line-height:1.45}
      .cs-update-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}
      .update-retry-btn.cs-retry-running,[data-update-history-retry].cs-retry-running{opacity:.78;cursor:wait}
    `;
    document.head.appendChild(style);
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
      headers: options.body ? {"Content-Type": "application/json", ...(options.headers || {})} : (options.headers || {}),
      ...options,
    });
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    if (!response.ok || payload?.ok === false) {
      throw new Error(clean(payload?.message || payload?.error) || `HTTP ${response.status}`);
    }
    return payload;
  }

  function toast(message, kind = "ok") {
    document.querySelector(".cs-update-reliability-toast")?.remove();
    const node = document.createElement("div");
    node.className = "cs-update-reliability-toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = clean(message);
    Object.assign(node.style, {
      position: "fixed", right: "18px", bottom: "18px", zIndex: "100001",
      maxWidth: "580px", padding: "12px 14px", borderRadius: "12px", color: "#fff",
      background: kind === "error" ? "#451a1a" : "#063d2b",
      border: `1px solid ${kind === "error" ? "#ef4444" : "#10b981"}`,
      boxShadow: "0 12px 34px rgba(0,0,0,.38)", fontWeight: "700",
    });
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  function rowJobId(row) {
    if (!row) return "";
    const detail = row.querySelector("[data-update-detail],[data-cs-stage1-detail]");
    if (detail) return clean(detail.dataset.updateDetail || detail.dataset.csStage1Detail);
    return clean(row.dataset.ohRow || row.dataset.csStage1Job || row.dataset.updateJobId);
  }

  function formatDate(value) {
    const raw = clean(value);
    if (!raw) return "—";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw;
    return new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    }).format(date).replace(",", " -");
  }

  function ensureStatusStack(row, job) {
    let stack = row.querySelector(".cs-update-status-stack");
    if (!stack) {
      const badge = row.querySelector(":scope > .badge") || row.querySelector(".badge");
      if (!badge) return null;
      if (badge.parentElement !== row && badge.parentElement?.classList.contains("cs-update-status-stack")) {
        stack = badge.parentElement;
      } else if (badge.parentElement === row) {
        stack = document.createElement("div");
        stack.className = "cs-update-status-stack";
        badge.insertAdjacentElement("beforebegin", stack);
        stack.appendChild(badge);
      } else {
        stack = badge.parentElement;
        stack.classList.add("cs-update-status-stack");
      }
    }
    if (!stack) return null;

    let attempts = stack.querySelector(".cs-update-attempts");
    if (!attempts) {
      attempts = document.createElement("div");
      attempts.className = "cs-update-status-line cs-update-attempts";
      stack.appendChild(attempts);
    }
    attempts.textContent = `${clean(job.state) || "estado"} · ${Math.max(0, Number(job.attempts || 0))} tentativa(s)`;

    let date = stack.querySelector(".cs-update-date");
    if (!date) {
      date = document.createElement("div");
      date.className = "cs-update-status-line cs-update-date";
      stack.appendChild(date);
    }
    const state = clean(job.state).toLowerCase();
    date.textContent = `${state === "completed" ? "Concluído" : "Atualizado"} em: ${formatDate(job.status_at || job.completed_at || job.updated_at)}`;

    let count = stack.querySelector(".cs-update-success-count");
    if (!count) {
      count = document.createElement("div");
      count.className = "cs-update-success-count";
      stack.appendChild(count);
    }
    const value = Math.max(0, Number.parseInt(String(job.updates_count ?? 0), 10) || 0);
    count.innerHTML = `Atualizações: <strong>${escapeHtml(value)}</strong>`;
    return stack;
  }

  function ensureRetry(row, job) {
    const state = clean(job.state).toLowerCase();
    if (!RETRYABLE.has(state)) return;
    if (row.querySelector(RETRY_SELECTOR)) return;
    const detail = row.querySelector("[data-update-detail],[data-cs-stage1-detail]");
    if (!detail) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-success update-retry-btn";
    button.textContent = "Tentar novamente";
    if (detail.parentElement?.classList.contains("cs-update-actions")) {
      detail.parentElement.appendChild(button);
      return;
    }
    const actions = document.createElement("div");
    actions.className = "cs-update-actions";
    detail.insertAdjacentElement("beforebegin", actions);
    actions.appendChild(detail);
    actions.appendChild(button);
  }

  function decorateRow(row, job) {
    if (!row || !job) return;
    const summary = clean(job.failure_summary);
    const rawError = clean(job.execution_error);
    const errorNode = row.querySelector(".updates-error");
    if (summary && errorNode) {
      if (clean(errorNode.textContent) !== summary) errorNode.textContent = summary;
      if (rawError && rawError !== summary) errorNode.title = rawError;
    } else if (summary && !row.querySelector(".cs-update-failure-summary")) {
      const main = row.children?.[1] || row.querySelector("div");
      if (main) {
        const note = document.createElement("div");
        note.className = "cs-update-failure-summary";
        note.textContent = summary;
        if (rawError && rawError !== summary) note.title = rawError;
        main.appendChild(note);
      }
    }
    ensureStatusStack(row, job);
    ensureRetry(row, job);
  }

  function decorateAll(jobs) {
    const byId = new Map((jobs || []).map(job => [clean(job?.job_id), job]));
    document.querySelectorAll(".update-queue-row,.op-history-row").forEach(row => {
      const job = byId.get(rowJobId(row));
      if (job) decorateRow(row, job);
    });
  }

  async function refreshDecorations() {
    if (refreshing || !document.querySelector("#tab_panel_atualizacoes,#updates_queue_jobs,#updates_history")) return;
    refreshing = true;
    try {
      const payload = await request("/atualizacoes/jobs");
      decorateAll(Array.isArray(payload?.jobs) ? payload.jobs : []);
    } catch (_error) {
    } finally {
      refreshing = false;
    }
  }

  function scheduleRefresh(delay = 80) {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refreshDecorations, delay);
  }

  async function waitForJob(jobId) {
    const deadline = Date.now() + TIMEOUT_MS;
    const graceUntil = Date.now() + 4500;
    let sawProgress = false;
    while (Date.now() < deadline) {
      const payload = await request("/atualizacoes/jobs");
      const job = (Array.isArray(payload?.jobs) ? payload.jobs : []).find(item => clean(item?.job_id) === jobId);
      if (!job) throw new Error("A atualização não foi encontrada após iniciar a nova tentativa.");
      const state = clean(job.state).toLowerCase();
      if (!TERMINAL_ERRORS.has(state)) sawProgress = true;
      if (state === "completed") return job;
      if (TERMINAL_ERRORS.has(state) && (sawProgress || Date.now() >= graceUntil)) {
        throw new Error(clean(job.failure_summary || job.execution_error) || "A nova tentativa terminou com erro.");
      }
      await sleep(POLL_MS);
    }
    throw new Error("A nova tentativa continua em execução além do tempo de acompanhamento da tela. Consulte Processos antes de repetir.");
  }

  async function retryEndToEnd(button, jobId) {
    const original = clean(button.textContent) || "Tentar novamente";
    button.disabled = true;
    button.classList.add("cs-retry-running");
    button.textContent = "Revalidando e atualizando…";
    document.body.dataset.updateRecoveryBusy = "1";
    try {
      const started = await request("/operacoes/simples/retry-update", {
        method: "POST", body: JSON.stringify({job_id: jobId}),
      });
      if (started?.already_completed === true) {
        toast("Este produto já consta como atualizado.");
        scheduleRefresh(50);
        return;
      }
      const completed = await waitForJob(jobId);
      button.textContent = "Atualizado";
      toast(`${clean(completed?.name) || "Produto"}: atualização concluída com sucesso.`);
      scheduleRefresh(20);
      window.setTimeout(() => location.reload(), 850);
    } catch (error) {
      button.disabled = false;
      button.textContent = original;
      toast(clean(error?.message || error) || "Não foi possível concluir a nova tentativa.", "error");
      scheduleRefresh(20);
    } finally {
      button.classList.remove("cs-retry-running");
      delete document.body.dataset.updateRecoveryBusy;
    }
  }

  document.addEventListener("click", event => {
    const button = event.target?.closest?.(RETRY_SELECTOR);
    if (!button || button.dataset.csEndToEndRetry === "1") return;
    const row = button.closest(".update-queue-row,.op-history-row");
    const jobId = rowJobId(row);
    if (!jobId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    button.dataset.csEndToEndRetry = "1";
    retryEndToEnd(button, jobId).finally(() => { delete button.dataset.csEndToEndRetry; });
  }, true);

  const observer = new MutationObserver(mutations => {
    if (mutations.some(item => item.addedNodes?.length || item.removedNodes?.length)) scheduleRefresh(70);
  });

  function start() {
    installStyles();
    observer.observe(document.body, {childList: true, subtree: true});
    scheduleRefresh(0);
    window.setInterval(() => { if (!document.hidden) scheduleRefresh(0); }, 2200);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
