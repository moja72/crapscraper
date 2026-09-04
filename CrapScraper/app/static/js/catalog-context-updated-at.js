const $ = (selector, root = document) => root.querySelector(selector);

function formatContextUpdatedAt(value) {
  const timestamp = Number(value || 0);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "Sem atualização";
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) return "Sem atualização";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function rowPayload(row) {
  const source = $("[data-row]", row);
  if (!source?.dataset.row) return null;
  try {
    return JSON.parse(decodeURIComponent(source.dataset.row));
  } catch (_error) {
    return null;
  }
}

function patchHeader(table) {
  const header = $("thead tr", table);
  if (!header || $("[data-context-updated-at-header]", header)) return;
  const actions = header.lastElementChild;
  const cell = document.createElement("th");
  cell.dataset.contextUpdatedAtHeader = "1";
  cell.textContent = "Última atualização";
  header.insertBefore(cell, actions || null);
}

function patchRows(table) {
  const body = $("#catalog-context-rows", table);
  if (!body) return;
  for (const row of body.querySelectorAll("tr")) {
    if (row.querySelector("[data-context-updated-at-cell]")) continue;
    const payload = rowPayload(row);
    if (!payload) {
      const onlyCell = row.cells.length === 1 ? row.cells[0] : null;
      if (onlyCell?.colSpan) onlyCell.colSpan = 8;
      continue;
    }
    const actions = row.lastElementChild;
    const cell = document.createElement("td");
    cell.dataset.contextUpdatedAtCell = "1";
    cell.textContent = formatContextUpdatedAt(payload.updated_at);
    cell.title = payload.updated_at ? `Última atualização deste contexto: ${cell.textContent}` : "Este contexto ainda não possui data de atualização.";
    row.insertBefore(cell, actions || null);
  }
}

function patchContextTable() {
  const body = $("#catalog-context-rows");
  const table = body?.closest("table");
  if (!table) return;
  patchHeader(table);
  patchRows(table);
}

queueMicrotask(() => {
  patchContextTable();
  const body = $("#catalog-context-rows");
  if (!body) return;
  new MutationObserver(patchContextTable).observe(body, {childList: true, subtree: true});
});

export {formatContextUpdatedAt};
