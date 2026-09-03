const jobsById = new Map();
const nativeFetch = window.fetch.bind(window);

const style = document.createElement("style");
style.textContent = `
.update-status-time{margin-top:2px;color:#a7b4c6!important;font-size:11px!important;font-variant-numeric:tabular-nums}
.update-job-progress-accordion{display:block!important;padding:0!important;overflow:hidden}
.update-job-progress-accordion>summary{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;align-items:center;gap:7px;min-height:38px;padding:7px 8px;list-style:none;cursor:pointer}
.update-job-progress-accordion>summary::-webkit-details-marker{display:none}
.update-job-progress-accordion>summary::before{content:"▸";color:#a7b4c6;font-size:13px;transition:transform .15s ease}
.update-job-progress-accordion[open]>summary::before{transform:rotate(90deg)}
.update-job-progress-summary-label{min-width:0;font-size:12px;font-weight:600;overflow-wrap:anywhere}
.update-job-progress-summary-stage{color:#a7b4c6;font-size:11px;font-weight:400;white-space:nowrap}
.update-job-progress-body{display:grid;gap:6px;padding:0 8px 8px}
.update-job-copy-log{display:grid;place-items:center;width:30px;min-width:30px;min-height:30px;padding:0;border-radius:6px;color:#cbd5e1;background:#0f172a}
.update-job-copy-log svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.update-job-copy-log[data-copied="1"]{color:#86efac;border-color:#22c55e}
.update-job-progress-accordion .update-job-live-log{height:min(220px,32vh)}
`;
document.head.appendChild(style);

function requestPath(input) {
  try {
    const raw = typeof input === "string" ? input : input?.url || "";
    return new URL(raw, window.location.href).pathname;
  } catch {
    return "";
  }
}

function remember(payload) {
  const rows = Array.isArray(payload?.items)
    ? payload.items
    : payload?.item
      ? [payload.item]
      : [];
  for (const job of rows) {
    if (job?.job_id) jobsById.set(String(job.job_id), job);
  }
  queueMicrotask(decorateCards);
}

window.fetch = async (...args) => {
  const response = await nativeFetch(...args);
  const path = requestPath(args[0]);
  if (response.ok && (path === "/api/updates/jobs" || path === "/api/updates/job")) {
    response.clone().json().then(remember).catch(() => {});
  }
  return response;
};

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "";
  const datePart = date.toLocaleDateString("pt-BR");
  const timePart = date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return `${datePart} - ${timePart}`;
}

function stateTimestamp(job) {
  if (job.state === "success") return ["Concluído", job.finished_at || job.updated_at];
  if (job.state === "error") return ["Erro", job.finished_at || job.error?.timestamp || job.updated_at];
  if (job.state === "running") return ["Iniciado", job.started_at || job.updated_at];
  return ["Preparado", job.updated_at || job.created_at];
}

function logLines(job) {
  const lines = Array.isArray(job.logs) ? job.logs.map(String) : [];
  const error = String(job.error?.message || "").trim();
  if (error && !lines.some(line => line.includes(error))) lines.push(`ERRO: ${error}`);
  return lines.length ? lines : ["Nenhuma mensagem registrada nesta atualização."];
}

function copyIcon() {
  return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"></path></svg>';
}

function buildTerminalProgress(job, oldNode) {
  const p = job.progress || {};
  const total = Math.max(1, Number(p.total || 1));
  const value = Math.max(0, Math.min(total, Number(p.step || 0)));
  const details = document.createElement("details");
  details.className = "update-job-progress update-job-progress-accordion";
  details.dataset.progressState = p.failed ? "error" : p.complete ? "complete" : "idle";
  details.setAttribute("aria-label", `Log da atualização de ${job.product_name || "produto"}`);

  const summary = document.createElement("summary");
  const label = document.createElement("strong");
  label.className = "update-job-progress-summary-label";
  label.textContent = p.label || (job.state === "success" ? "Atualização concluída" : "Atualização com erro");
  const stage = document.createElement("small");
  stage.className = "update-job-progress-summary-stage";
  stage.textContent = `Etapa ${value} de ${total}`;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "update-job-copy-log";
  copy.dataset.updateCopyJobLog = String(job.job_id || "");
  copy.setAttribute("aria-label", "Copiar log da atualização");
  copy.title = "Copiar log";
  copy.innerHTML = copyIcon();
  summary.append(label, stage, copy);

  const body = document.createElement("div");
  body.className = "update-job-progress-body";
  const progress = document.createElement("progress");
  progress.max = total;
  progress.value = value;
  progress.setAttribute("aria-label", p.label || job.stage || "Progresso da atualização");
  const list = document.createElement("ol");
  list.className = "update-job-live-log";
  list.setAttribute("role", "log");
  for (const line of logLines(job)) {
    const li = document.createElement("li");
    li.textContent = line;
    list.appendChild(li);
  }
  body.append(progress, list);
  details.append(summary, body);
  oldNode.replaceWith(details);
}

function decorateCard(card) {
  const id = String(card.dataset.jobId || "");
  const job = jobsById.get(id);
  if (!job) return;

  const state = card.querySelector(".update-job-state");
  if (state) {
    const [label, raw] = stateTimestamp(job);
    const formatted = formatDate(raw);
    let stamp = state.querySelector(".update-status-time");
    if (!stamp) {
      stamp = document.createElement("small");
      stamp.className = "update-status-time";
      state.appendChild(stamp);
    }
    stamp.textContent = formatted ? `${label} em ${formatted}` : "";
    stamp.hidden = !formatted;
  }

  if (!['success', 'error'].includes(String(job.state || ""))) return;
  const progress = card.querySelector(".update-job-progress");
  if (!progress || progress.matches("details.update-job-progress-accordion")) return;
  buildTerminalProgress(job, progress);
}

function decorateCards() {
  document.querySelectorAll("#update-list .update-job-card").forEach(decorateCard);
}

document.addEventListener("click", async event => {
  const button = event.target.closest?.("[data-update-copy-job-log]");
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const job = jobsById.get(String(button.dataset.updateCopyJobLog || ""));
  if (!job) return;
  const text = logLines(job).join("\n");
  try {
    await navigator.clipboard.writeText(text);
    button.dataset.copied = "1";
    button.title = "Log copiado";
    setTimeout(() => {
      button.dataset.copied = "0";
      button.title = "Copiar log";
    }, 1400);
  } catch {
    button.title = "Não foi possível copiar o log";
  }
}, true);

const list = document.querySelector("#update-list");
if (list) new MutationObserver(decorateCards).observe(list, {childList: true, subtree: true});
document.addEventListener("app:tab", event => {
  if (event.detail === "update") queueMicrotask(decorateCards);
});

window.__crapscraperUpdateTerminalUi = true;
