import {get} from "./api.js";

const $ = (selector, root = document) => root.querySelector(selector);
let syncing = false;
let scheduled = 0;

function ensureQueuedOption() {
  const select = $("#update-group");
  if (!select || select.querySelector('option[value="queued"]')) return;
  const option = document.createElement("option");
  option.value = "queued";
  option.textContent = "Na fila";
  const prepared = select.querySelector('option[value="prepared"]');
  if (prepared?.nextSibling) select.insertBefore(option, prepared.nextSibling);
  else select.appendChild(option);
}

function queuedCard(count) {
  return `<div class="card metric-card" data-update-queued-card>
    <button class="metric-filter" data-update-queued-filter aria-pressed="false"><small>Na fila</small><strong>${Number(count || 0)}</strong></button>
    <button type="button" class="help-tip" data-tooltip="Produtos já enviados para a fila e que aguardam sua vez; o item ativo aparece em Em andamento." aria-label="Ajuda sobre Na fila">?</button>
  </div>`;
}

async function syncCards() {
  if (syncing) return;
  syncing = true;
  try {
    ensureQueuedOption();
    const cards = $("#update-cards");
    if (!cards) return;
    const response = await get("/api/updates/jobs?page=1&page_size=1");
    const count = Number(response?.counts?.queued || 0);
    let card = cards.querySelector("[data-update-queued-card]");
    if (!card) {
      const preparedButton = cards.querySelector('[data-update-group="prepared"]');
      const preparedCard = preparedButton?.closest(".metric-card");
      if (preparedCard) preparedCard.insertAdjacentHTML("afterend", queuedCard(count));
      else cards.insertAdjacentHTML("beforeend", queuedCard(count));
      card = cards.querySelector("[data-update-queued-card]");
    }
    const strong = card?.querySelector("strong");
    if (strong) strong.textContent = String(count);
    const active = $("#update-group")?.value === "queued";
    card?.querySelector("[data-update-queued-filter]")?.setAttribute("aria-pressed", String(active));
  } catch {
    // A UI base continua funcional se a projeção auxiliar falhar.
  } finally {
    syncing = false;
  }
}

function decorateQueuedRows() {
  for (const chip of document.querySelectorAll('#update-list .status-chip[data-status="queued"]')) {
    chip.textContent = "Na fila";
    const state = chip.closest(".update-job-state");
    const detail = state?.querySelector("small");
    if (detail && /^queued\b/i.test(detail.textContent || "")) {
      detail.textContent = (detail.textContent || "").replace(/^queued/i, "Aguardando execução");
    }
  }
}

function scheduleSync() {
  decorateQueuedRows();
  ensureQueuedOption();
  clearTimeout(scheduled);
  scheduled = setTimeout(syncCards, 40);
}

document.addEventListener("click", event => {
  const button = event.target.closest?.("[data-update-queued-filter]");
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const select = $("#update-group");
  if (!select) return;
  select.value = "queued";
  select.dispatchEvent(new Event("change", {bubbles: true}));
  $("#update-filter-apply")?.click();
}, true);

document.addEventListener("change", event => {
  if (event.target?.id === "update-group") scheduleSync();
});

document.addEventListener("app:tab", event => {
  if (event.detail === "update") scheduleSync();
});

ensureQueuedOption();
const cards = $("#update-cards");
if (cards) new MutationObserver(scheduleSync).observe(cards, {childList: true, subtree: true});
const list = $("#update-list");
if (list) new MutationObserver(decorateQueuedRows).observe(list, {childList: true, subtree: true});
scheduleSync();
