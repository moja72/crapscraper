(() => {
  "use strict";
  if (window.__crapScraperAdditionProcessesBridgeInstalled) return;
  window.__crapScraperAdditionProcessesBridgeInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const escapeHtml = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const HISTORY_KEY = "crapscraper.process.history.v1";
  const HISTORY_LIMIT = 80;
  let active = new Map();
  let seen = new Map();
  let polling = false;
  let renderedSignature = "";

  function parsedTime(value, fallback = Date.now()) {
    const parsed = Date.parse(text(value));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function loadHistory() {
    try {
      const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter(Boolean).slice(0, HISTORY_LIMIT) : [];
    } catch (_error) { return []; }
  }

  function recordFinished(process) {
    const history = loadHistory();
    const finishedAt = Date.now();
    const row = {
      historyId: `${text(process.id || process.job_id || "addition")}:${finishedAt}`,
      processId: text(process.id || process.job_id || ""),
      title: text(process.title || "Cadastro de novo produto"),
      detail: text(process.detail || ""),
      status: "Finalizado",
      error: false,
      kind: "addition",
      startedAt: Number(process.startedAt || 0) || finishedAt,
      finishedAt,
    };
    const duplicate = history.find(item => item.processId === row.processId && Math.abs(Number(item.finishedAt || 0) - finishedAt) < 1500);
    if (duplicate) return;
    history.unshift(row);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, HISTORY_LIMIT))); } catch (_error) {}
  }

  function stateSignature() {
    return JSON.stringify([...active.values()].map(process => ({
      id: text(process.id),
      status: text(process.status),
      detail: text(process.detail),
      progress: Number.isFinite(Number(process.progress)) ? Number(process.progress) : null,
      latest_log: text(process.latest_log),
      meta: text(process.meta),
    })));
  }

  async function poll() {
    if (polling || document.hidden) return;
    polling = true;
    try {
      const response = await fetch("/adicoes/operacoes?scope=processes", {cache:"no-store", credentials:"same-origin"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const next = new Map();
      for (const raw of Array.isArray(payload?.processes) ? payload.processes : []) {
        const id = text(raw?.id || raw?.job_id);
        if (!id) continue;
        const previous = seen.get(id);
        next.set(id, {
          ...raw,
          id,
          startedAt: previous?.startedAt || parsedTime(raw?.started_at),
        });
      }
      for (const [id, previous] of seen) {
        if (!next.has(id)) recordFinished(previous);
      }
      active = next;
      seen = next;
      syncButtonCount();
      decorate(false);
    } catch (_error) {
      syncButtonCount();
    } finally { polling = false; }
  }

  function elapsed(process) {
    const start = Number(process?.startedAt || 0);
    if (!start) return "";
    const seconds = Math.max(0, Math.floor((Date.now() - start) / 1000));
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }

  function card(process) {
    const pctRaw = Number(process?.progress);
    const hasProgress = Number.isFinite(pctRaw) && pctRaw >= 0;
    const pct = hasProgress ? Math.max(0, Math.min(100, Math.round(pctRaw))) : 0;
    return `<article class="cs-process-card cs-addition-operational-process" data-addition-process="${escapeHtml(process.id)}">
      <div class="cs-process-row"><div><div class="cs-process-name">${escapeHtml(process.title || "Cadastro de novo produto")}</div><div class="cs-process-detail">${escapeHtml(process.detail || "")}</div></div><span class="cs-process-status is-active">${escapeHtml(process.status || "Executando")}</span></div>
      <div class="cs-process-progress ${hasProgress ? "" : "is-indeterminate"}"><span style="${hasProgress ? `width:${pct}%` : ""}"></span></div>
      <div class="cs-process-meta"><span>${hasProgress ? `${pct}%` : "Progresso em andamento"}</span>${process.meta ? `<span>${escapeHtml(process.meta)}</span>` : ""}<span>Tempo: ${escapeHtml(elapsed(process))}</span></div>
      ${process.latest_log ? `<div class="cs-process-log">${escapeHtml(process.latest_log)}</div>` : ""}
    </article>`;
  }

  function syncButtonCount() {
    const button = $("#cs_processes_button");
    const count = $(".cs-process-count", button);
    if (!button || !count) return;
    const previousExtra = Number(button.dataset.additionOperationalCount || 0);
    const displayed = Math.max(0, Number.parseInt(count.textContent || "0", 10) || 0);
    const nativeCount = Math.max(0, displayed - previousExtra);
    const extra = active.size;
    const total = nativeCount + extra;
    if (count.textContent !== String(total)) count.textContent = String(total);
    button.dataset.additionOperationalCount = String(extra);
    button.classList.toggle("has-active", total > 0);
  }

  function modalVisible() {
    const overlay = $("#cs_processes_overlay");
    return !!overlay && !overlay.classList.contains("hidden");
  }

  function decorate(force = false) {
    if (!modalVisible()) return;
    const body = $("#cs_processes_body");
    if (!body) return;
    const signature = stateSignature();
    if (!force && signature === renderedSignature) return;
    renderedSignature = signature;

    body.querySelectorAll(".cs-addition-operational-process").forEach(node => node.remove());
    if (!active.size) return;
    body.querySelectorAll(":scope > .cs-process-empty, :scope > #cs_process_active_empty").forEach(node => node.remove());
    const history = $("#cs_process_history_section", body);
    const fragment = document.createRange().createContextualFragment([...active.values()].map(card).join(""));
    if (history) body.insertBefore(fragment, history);
    else body.prepend(fragment);
  }

  function start() {
    setTimeout(poll, 900);
    setInterval(poll, 4000);
    $("#cs_processes_button")?.addEventListener("click", () => setTimeout(() => decorate(true), 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
