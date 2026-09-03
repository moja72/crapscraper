import {get,post} from "./api.js";

const $ = selector => document.querySelector(selector);
const selected = new Set();
const jobCache = new Map();
const jobRequests = new Map();
const openedTerminalLogs = new Set();
let allFiltered = false;
let stickyOperation = null;
let restoringOperation = false;
let activeDetailJobId = "";

function listingTotal() {
  const text = $("#update-showing")?.textContent || "";
  const match = text.match(/\bde\s+(\d+)\s+itens?\b/i);
  return match ? Number(match[1]) : 0;
}

function batchRunning() {
  const toggle = $("#update-batch-toggle");
  return Boolean(toggle && !toggle.disabled);
}

function visibleCards() {
  return [...document.querySelectorAll("#update-list .update-job-card")];
}

function safe(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const formatted = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
  return formatted.replace(/\s+às\s+/i, " - ").replace(/,\s*/, " - ");
}

function statusTime(job) {
  const state = String(job?.state || "");
  if (state === "success") return {label: "Concluído em", value: job.finished_at || job.updated_at};
  if (state === "error") return {label: "Erro em", value: job.finished_at || job.updated_at};
  if (state === "running") return {label: "Iniciado em", value: job.started_at || job.updated_at};
  return {label: "Atualizado em", value: job.updated_at || job.created_at};
}

async function loadJob(jobId, expectedState = "") {
  const cached = jobCache.get(jobId);
  if (cached && (!expectedState || String(cached.state || "") === expectedState)) return cached;
  const pendingKey = `${jobId}:${expectedState}`;
  if (jobRequests.has(pendingKey)) return jobRequests.get(pendingKey);
  const request = get(`/api/updates/job?job_id=${encodeURIComponent(jobId)}`)
    .then(response => {
      const job = response.item || {};
      jobCache.set(jobId, job);
      return job;
    })
    .finally(() => jobRequests.delete(pendingKey));
  jobRequests.set(pendingKey, request);
  return request;
}

function copyIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"></path></svg>';
}

function terminalizeProgress(card) {
  const jobId = card.dataset.jobId || "";
  const state = card.querySelector(".update-job-state .status-chip")?.dataset.status || "";
  if (!jobId || state === "running") return;
  const progress = card.querySelector(".update-job-progress");
  if (!progress || progress.tagName === "DETAILS") return;

  const head = progress.querySelector(".update-job-progress-head");
  const label = head?.querySelector("strong")?.textContent?.trim() || "Detalhes da execução";
  const step = head?.querySelector("small")?.textContent?.trim() || "";
  const bar = progress.querySelector("progress");
  const log = progress.querySelector(".update-job-live-log");
  const details = document.createElement("details");
  details.className = `${progress.className} update-job-progress-terminal`;
  details.dataset.progressState = progress.dataset.progressState || "idle";
  details.dataset.updateTerminalLog = jobId;
  details.setAttribute("aria-label", progress.getAttribute("aria-label") || `Execução de ${jobId}`);
  details.innerHTML = `<summary><span class="update-terminal-summary-text"><strong>${safe(label)}</strong><small>${safe(step)}</small></span><span class="update-terminal-summary-actions"><button type="button" class="update-job-copy-log" data-update-copy-log="${safe(jobId)}" title="Copiar log" aria-label="Copiar log">${copyIcon()}</button><span class="update-terminal-chevron" aria-hidden="true">▸</span></span></summary>`;
  if (bar) details.appendChild(bar);
  if (log) details.appendChild(log);
  details.addEventListener("toggle", () => {
    if (details.open) openedTerminalLogs.add(jobId);
    else openedTerminalLogs.delete(jobId);
  });
  if (openedTerminalLogs.has(jobId)) details.open = true;
  progress.replaceWith(details);
}

async function decorateStatusTime(card) {
  const jobId = card.dataset.jobId || "";
  const stateNode = card.querySelector(".update-job-state");
  const expectedState = stateNode?.querySelector(".status-chip")?.dataset.status || "";
  if (!jobId || !stateNode || stateNode.querySelector("[data-update-status-time]")) return;
  try {
    const job = await loadJob(jobId, expectedState);
    if (!card.isConnected || card.dataset.jobId !== jobId || stateNode.querySelector("[data-update-status-time]")) return;
    const timing = statusTime(job);
    const formatted = formatDateTime(timing.value);
    if (!formatted) return;
    const line = document.createElement("small");
    line.dataset.updateStatusTime = "1";
    line.className = "update-status-time";
    line.textContent = `${timing.label}: ${formatted}`;
    stateNode.appendChild(line);
  } catch {
    // O card continua funcional mesmo que o enriquecimento visual falhe.
  }
}

function decorateCards() {
  for (const card of visibleCards()) {
    terminalizeProgress(card);
    void decorateStatusTime(card);
  }
}

async function decorateDetail() {
  const grid = $("#update-detail-content .details-grid");
  const jobId = activeDetailJobId;
  if (!grid || !jobId || grid.querySelector("[data-update-detail-time]")) return;
  try {
    const job = await loadJob(jobId);
    if (!grid.isConnected || grid.querySelector("[data-update-detail-time]")) return;
    const timing = statusTime(job);
    const formatted = formatDateTime(timing.value);
    if (!formatted) return;
    const item = document.createElement("div");
    item.dataset.updateDetailTime = "1";
    item.innerHTML = `<dt>Data/hora do status</dt><dd>${safe(timing.label)}: ${safe(formatted)}</dd>`;
    grid.appendChild(item);
  } catch {
    // O modal principal já mostra os dados essenciais; não o bloqueie por isso.
  }
}

async function copyJobLog(jobId, button) {
  try {
    const job = await loadJob(jobId);
    const text = (job.logs || []).map(line => String(line)).join("\n") || "Sem logs.";
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    button.dataset.copied = "1";
    button.title = "Log copiado";
    button.setAttribute("aria-label", "Log copiado");
    setTimeout(() => {
      if (!button.isConnected) return;
      delete button.dataset.copied;
      button.title = "Copiar log";
      button.setAttribute("aria-label", "Copiar log");
    }, 1400);
  } catch (error) {
    operation(`Não foi possível copiar o log: ${error.message}`, "error", 5000);
  }
}

function ensureTerminalStyles() {
  if ($("#update-terminal-progress-styles")) return;
  const style = document.createElement("style");
  style.id = "update-terminal-progress-styles";
  style.textContent = `
    .update-job-progress-terminal{display:block}
    .update-job-progress-terminal>summary{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:38px;list-style:none}
    .update-job-progress-terminal>summary::-webkit-details-marker{display:none}
    .update-terminal-summary-text{display:flex;min-width:0;align-items:center;justify-content:space-between;gap:10px;flex:1}
    .update-terminal-summary-text strong{min-width:0;font-size:13px;overflow-wrap:anywhere}
    .update-terminal-summary-text small{color:var(--muted);white-space:nowrap}
    .update-terminal-summary-actions{display:flex;align-items:center;gap:5px;flex:0 0 auto}
    .update-job-copy-log{display:grid;place-items:center;width:30px;min-width:30px;min-height:30px;padding:5px;border-radius:7px;background:var(--surface-2)}
    .update-job-copy-log svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    .update-job-copy-log[data-copied="1"]{border-color:var(--accent);color:#86efac}
    .update-terminal-chevron{color:var(--muted);transition:transform .16s ease}
    .update-job-progress-terminal[open] .update-terminal-chevron{transform:rotate(90deg)}
    .update-job-progress-terminal>progress{width:100%;margin:6px 0;height:7px}
    .update-job-progress-terminal>.update-job-live-log{margin-top:6px}
    .update-status-time{margin-top:2px;font-variant-numeric:tabular-nums}
  `;
  document.head.appendChild(style);
}

function syncUi() {
  for (const checkbox of document.querySelectorAll("#update-list [data-update-select-check]")) {
    const id = checkbox.dataset.updateSelectCheck || "";
    checkbox.checked = allFiltered || selected.has(id);
  }
  const count = allFiltered ? listingTotal() : selected.size;
  const output = $("#update-selected-count");
  if (output) output.textContent = `${count} selecionado(s)${allFiltered ? " no resultado filtrado" : ""}`;
  const start = $("#update-batch-start");
  if (start) {
    start.disabled = batchRunning() || count <= 0;
    start.title = batchRunning()
      ? "Já existe uma fila em execução."
      : count
        ? "Executar os produtos selecionados. Pré-requisitos e versão live da origem serão validados automaticamente."
        : "Selecione ao menos um produto preparado para executar a fila.";
  }
  decorateCards();
  void decorateDetail();
}

function clearSelection() {
  selected.clear();
  allFiltered = false;
  syncUi();
}

function selectionPayload() {
  const value = id => $(id)?.value || "";
  return {
    query: value("#update-query"),
    group: value("#update-group"),
    stage: value("#update-stage"),
    sort_by: value("#update-sort-by") || "date",
    sort_order: value("#update-sort-order") || "desc",
    page_size: Number(value("#update-page-size") || 5),
  };
}

async function selectedJobIds() {
  if (!allFiltered) return [...selected];
  const response = await post("/api/updates/selection", selectionPayload());
  return (response.items || []).map(item => String(item.job_id || "")).filter(Boolean);
}

function operation(message, kind = "info", stickyMs = 0) {
  const node = $("#update-operation-status");
  if (!node) return;
  stickyOperation = stickyMs > 0
    ? {message, kind, until: Date.now() + stickyMs}
    : null;
  node.textContent = message;
  node.className = `operation-band ${kind}`;
}

function preserveOperationError(node) {
  if (!node || restoringOperation) return;
  const text = (node.textContent || "").trim();
  const isError = node.classList.contains("error") && text.length > 0;
  if (isError) {
    stickyOperation = {message: text, kind: "error", until: Date.now() + 15000};
    return;
  }
  if (!stickyOperation || Date.now() >= stickyOperation.until) {
    stickyOperation = null;
    return;
  }
  if (text === stickyOperation.message && node.classList.contains(stickyOperation.kind)) return;
  restoringOperation = true;
  node.textContent = stickyOperation.message;
  node.className = `operation-band ${stickyOperation.kind}`;
  queueMicrotask(() => { restoringOperation = false; });
}

async function startBatch() {
  const button = $("#update-batch-start");
  if (!button || batchRunning()) return;
  const original = button.textContent;
  stickyOperation = null;
  button.disabled = true;
  button.textContent = "Preparando fila…";
  operation("Validando pré-requisitos e confirmando a versão atual das origens…", "loading");
  try {
    const ids = await selectedJobIds();
    if (!ids.length) throw new Error("Selecione ao menos um produto preparado para executar a fila.");
    const response = await post("/api/updates/batch/start", {job_ids: ids});
    const queued = Number(response.queued_count ?? response.batch?.total ?? ids.length);
    const skipped = Number(response.skipped_count ?? 0);
    operation(
      skipped
        ? `Fila iniciada com ${queued} produto(s). ${skipped} seleção(ões) obsoleta(s) ou bloqueada(s) foram ignoradas.`
        : `Fila iniciada com ${queued} produto(s).`,
      "success",
    );
    clearSelection();
    $("#update-refresh")?.click();
  } catch (error) {
    operation(`Fila bloqueada: ${error.message}`, "error", 15000);
  } finally {
    button.textContent = original;
    queueMicrotask(syncUi);
  }
}

document.addEventListener("change", event => {
  const checkbox = event.target.closest?.("[data-update-select-check]");
  if (checkbox) {
    event.stopImmediatePropagation();
    const id = checkbox.dataset.updateSelectCheck || "";
    if (checkbox.checked) selected.add(id); else selected.delete(id);
    allFiltered = false;
    syncUi();
    return;
  }
  if (event.target.matches?.("#update-group,#update-stage,#update-sort-by,#update-sort-order,#update-page-size")) {
    clearSelection();
  }
}, true);

document.addEventListener("input", event => {
  if (event.target?.id === "update-query") clearSelection();
}, true);

document.addEventListener("click", event => {
  const copy = event.target.closest?.("[data-update-copy-log]");
  if (copy) {
    event.preventDefault();
    event.stopImmediatePropagation();
    void copyJobLog(copy.dataset.updateCopyLog || "", copy);
    return;
  }

  const detailButton = event.target.closest?.("[data-update-select]");
  if (detailButton) activeDetailJobId = detailButton.dataset.updateSelect || "";

  const target = event.target.closest?.("button,[data-update-group]");
  if (!target) return;

  if (target.matches?.("[data-update-execute]")) {
    stickyOperation = null;
    return;
  }
  if (target.id === "update-select-page") {
    event.preventDefault();
    event.stopImmediatePropagation();
    const ids = visibleCards().map(card => card.querySelector("[data-update-select-check]")?.dataset.updateSelectCheck).filter(Boolean);
    const complete = ids.length > 0 && ids.every(id => selected.has(id));
    for (const id of ids) complete ? selected.delete(id) : selected.add(id);
    allFiltered = false;
    syncUi();
    return;
  }
  if (target.id === "update-select-all") {
    event.preventDefault();
    event.stopImmediatePropagation();
    selected.clear();
    allFiltered = true;
    syncUi();
    return;
  }
  if (target.id === "update-clear-selection") {
    event.preventDefault();
    event.stopImmediatePropagation();
    clearSelection();
    return;
  }
  if (target.id === "update-batch-start") {
    event.preventDefault();
    event.stopImmediatePropagation();
    void startBatch();
    return;
  }
  if (target.id === "update-filter-clear" || target.matches?.("[data-update-group]")) {
    clearSelection();
  }
}, true);

ensureTerminalStyles();
const list = $("#update-list");
if (list) new MutationObserver(syncUi).observe(list, {childList: true, subtree: true});
const detailContent = $("#update-detail-content");
if (detailContent) new MutationObserver(() => { void decorateDetail(); }).observe(detailContent, {childList: true, subtree: true});
const operationNode = $("#update-operation-status");
if (operationNode) new MutationObserver(() => {
  preserveOperationError(operationNode);
  syncUi();
}).observe(operationNode, {childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["class"]});

window.__crapscraperUpdateSelectionFix = true;
queueMicrotask(syncUi);
