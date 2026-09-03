import {post} from "./api.js";

const $ = selector => document.querySelector(selector);
const selected = new Set();
let allFiltered = false;

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
        ? "Executar os produtos selecionados; itens que deixaram de ser elegíveis serão ignorados com diagnóstico."
        : "Selecione ao menos um produto preparado para executar a fila.";
  }
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

function operation(message, kind = "info") {
  const node = $("#update-operation-status");
  if (!node) return;
  node.textContent = message;
  node.className = `operation-band ${kind}`;
}

async function startBatch() {
  const button = $("#update-batch-start");
  if (!button || batchRunning()) return;
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Preparando fila…";
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
    operation(`Fila bloqueada: ${error.message}`, "error");
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
  const target = event.target.closest?.("button,[data-update-group]");
  if (!target) return;

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

const list = $("#update-list");
if (list) new MutationObserver(syncUi).observe(list, {childList: true, subtree: true});
const operationNode = $("#update-operation-status");
if (operationNode) new MutationObserver(syncUi).observe(operationNode, {childList: true, characterData: true, subtree: true});

window.__crapscraperUpdateSelectionFix = true;
queueMicrotask(syncUi);
