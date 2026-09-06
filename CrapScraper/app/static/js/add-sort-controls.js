const $ = (selector, root = document) => root.querySelector(selector);

function sortValues() {
  return {
    sortBy: $("#add-sort-by")?.value || "date",
    sortOrder: $("#add-sort-order")?.value || "desc",
  };
}

function withSort(url) {
  const text = String(url || "");
  if (!/^\/api\/additions(?:\/jobs)?(?:\?|$)/.test(text)) return text;
  const [path, rawQuery = ""] = text.split("?", 2);
  const query = new URLSearchParams(rawQuery);
  const {sortBy, sortOrder} = sortValues();
  query.set("sort_by", sortBy);
  query.set("sort_order", sortOrder);
  return `${path}?${query}`;
}

if (!window.__crapscraperAdditionSortFetch) {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const method = String(init?.method || (input instanceof Request ? input.method : "GET") || "GET").toUpperCase();
    if (method !== "GET") return originalFetch(input, init);
    if (typeof input === "string") return originalFetch(withSort(input), init);
    if (input instanceof Request && /^\/api\/additions(?:\/jobs)?(?:\?|$)/.test(new URL(input.url).pathname + new URL(input.url).search)) {
      const target = new URL(input.url);
      const {sortBy, sortOrder} = sortValues();
      target.searchParams.set("sort_by", sortBy);
      target.searchParams.set("sort_order", sortOrder);
      return originalFetch(new Request(target, input), init);
    }
    return originalFetch(input, init);
  };
  window.__crapscraperAdditionSortFetch = true;
}

function ensureControls() {
  const grid = $("#add-queue .update-filter-grid");
  if (!grid || $("#add-sort-by")) return false;
  const actions = grid.querySelector(".filter-actions");
  const wrapper = document.createElement("div");
  wrapper.dataset.addSortControls = "1";
  wrapper.style.display = "contents";
  wrapper.innerHTML = `
    <label>Ordenar por<select id="add-sort-by">
      <option value="date">Data de entrada na fila</option>
      <option value="name">Nome do produto</option>
    </select></label>
    <label>Ordem<select id="add-sort-order">
      <option value="desc">Mais recentes primeiro</option>
      <option value="asc">Mais antigos primeiro</option>
    </select></label>`;
  if (actions) grid.insertBefore(wrapper, actions);
  else grid.appendChild(wrapper);
  return true;
}

function refresh() {
  $("#add-refresh")?.click();
}

function boot() {
  const inserted = ensureControls();
  if (inserted) setTimeout(refresh, 0);
}

document.addEventListener("change", event => {
  if (!event.target?.matches?.("#add-sort-by,#add-sort-order")) return;
  refresh();
});

document.addEventListener("click", event => {
  if (event.target?.id !== "add-filter-clear") return;
  setTimeout(() => {
    const by = $("#add-sort-by");
    const order = $("#add-sort-order");
    if (by) by.value = "date";
    if (order) order.value = "desc";
    refresh();
  }, 0);
});

document.addEventListener("app:tab", event => {
  if (event.detail === "add") boot();
});

boot();
if (!$("#add-queue")) {
  new MutationObserver((_, observer) => {
    if (!$("#add-queue")) return;
    observer.disconnect();
    boot();
  }).observe(document.body, {childList: true, subtree: true});
}
