(() => {
  "use strict";

  const DEBOUNCE_MS = 700;
  const SCAN_DELAY_MS = 50;
  const FALLBACK_SCAN_MS = 500;
  const DEFAULT_PAGE_SIZE = 5;
  const normalize = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  const timers = new WeakMap();

  const KNOWN_SETTERS = new Map([
    ["catalogos_page_label", "catalogs"],
    ["comparison_page_label", "comparison"],
    ["updates_page_label", "updatesWaiting"],
    ["updates_queue_page", "updatesQueue"],
    ["updates_history_page", "updatesHistory"],
    ["plugintema_manage_page_status", "pluginTemaManager"],
    ["update_list_preview_page", "updateListPreview"],
    ["catalog_preview_page", "catalogPreview"],
  ]);

  const PAGE_SIZE_IDS = [
    "catalogos_page_size",
    "comparison_page_size",
    "plugintema_manage_page_size",
    "updates_page_size",
    "updates_queue_page_size",
    "updates_history_page_size",
    "update_list_preview_page_size",
    "catalog_preview_page_size",
  ];

  function clampPage(value, total, fallback) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(1, Math.min(total, parsed));
  }

  function parseLabel(label) {
    if (!label) return null;
    const match = normalize(label.textContent).match(/P[aá]gina\s+(\d+)\s+de\s+(\d+)/i);
    if (match) return { current: Number(match[1]), total: Number(match[2]) };
    const current = Number(label.dataset.csCurrent || 0);
    const total = Number(label.dataset.csTotal || 0);
    if (current > 0 && total > 0) return { current, total };
    return null;
  }

  function paginationButtons(label) {
    const row = label?.closest?.(".listing-pagination") || label?.parentElement;
    if (!row) return { prev: null, next: null };
    const buttons = [...row.querySelectorAll("button")];
    return { prev: buttons[0] || null, next: buttons.at(-1) || null };
  }

  function fallbackJump(label, target, current) {
    const { prev, next } = paginationButtons(label);
    const direction = target > current ? "next" : "prev";
    let remaining = Math.abs(target - current);
    const step = () => {
      if (remaining <= 0) return;
      const liveLabel = label.id ? document.getElementById(label.id) : label;
      const buttons = paginationButtons(liveLabel);
      const button = direction === "next" ? buttons.next || next : buttons.prev || prev;
      if (!button || button.disabled) return;
      button.click();
      remaining -= 1;
      if (remaining > 0) window.setTimeout(step, 55);
    };
    step();
  }

  function goToPage(label, input) {
    const info = parseLabel(label);
    if (!info) return;
    const target = clampPage(input.value, info.total, info.current);
    input.value = String(target);
    if (target === info.current) return;

    const setterName = KNOWN_SETTERS.get(label.id) || label.dataset.csSetter || "";
    const api = window.__crapscraperPagination;
    if (setterName && api && typeof api[setterName] === "function") {
      api[setterName](target);
      return;
    }
    fallbackJump(label, target, info.current);
  }

  function bindInput(label, input) {
    if (!label || !input || input.dataset.csAutoJumpBound === "1") return;
    input.dataset.csAutoJumpBound = "1";
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("autocomplete", "off");
    input.title = "Digite o número da página";

    input.addEventListener("input", () => {
      const oldTimer = timers.get(input);
      if (oldTimer) window.clearTimeout(oldTimer);
      const timer = window.setTimeout(() => goToPage(label, input), DEBOUNCE_MS);
      timers.set(input, timer);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const oldTimer = timers.get(input);
      if (oldTimer) window.clearTimeout(oldTimer);
      goToPage(label, input);
    });
  }

  function makeEditable(label) {
    if (!label) return;
    const existing = label.querySelector("input[data-cs-page-input]");
    if (existing) {
      bindInput(label, existing);
      return;
    }

    const info = parseLabel(label);
    if (!info || !Number.isFinite(info.current) || !Number.isFinite(info.total) || info.total < 1) return;

    label.dataset.csCurrent = String(info.current);
    label.dataset.csTotal = String(info.total);
    label.classList.add("cs-page-jump");
    label.innerHTML = `Página <input data-cs-page-input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;
    bindInput(label, label.querySelector("input[data-cs-page-input]"));
  }

  function ensureFiveOption(select) {
    if (!select || select.tagName !== "SELECT") return false;
    const numericOptions = [...select.options].filter(option => /^\d+$/.test(normalize(option.value)));
    if (!numericOptions.length || numericOptions.length !== select.options.length) return false;

    if (![...select.options].some(option => Number(option.value) === DEFAULT_PAGE_SIZE)) {
      const option = document.createElement("option");
      option.value = String(DEFAULT_PAGE_SIZE);
      option.textContent = String(DEFAULT_PAGE_SIZE);
      select.appendChild(option);
    }
    [...select.options]
      .sort((a, b) => Number(a.value) - Number(b.value))
      .forEach(option => select.appendChild(option));
    return true;
  }

  function enforceDefaultPageSize(select) {
    if (!ensureFiveOption(select)) return;
    if (select.dataset.csFiveDefaultApplied === "1") return;
    select.dataset.csFiveDefaultApplied = "1";
    if (String(select.value) === String(DEFAULT_PAGE_SIZE)) return;
    select.value = String(DEFAULT_PAGE_SIZE);
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function scanPageSizes() {
    PAGE_SIZE_IDS.forEach(id => enforceDefaultPageSize(document.getElementById(id)));
    document.querySelectorAll("select").forEach(select => {
      const nearby = normalize(select.closest("label,.listing-page-size,.cs-page-size-wrap")?.textContent);
      if (/itens por página|linhas por página/i.test(nearby)) enforceDefaultPageSize(select);
    });
  }

  function scanKnownLabels() {
    KNOWN_SETTERS.forEach((_setter, id) => {
      const label = document.getElementById(id);
      if (label) makeEditable(label);
    });
  }

  function scanGenericPagination() {
    const rows = document.querySelectorAll(".listing-pagination,.pagination,[class*='pagination']");
    rows.forEach((row) => {
      const candidates = [...row.querySelectorAll("span,div,strong,b")];
      const label = candidates.find((node) =>
        node.querySelector("input[data-cs-page-input]") ||
        /^P[aá]gina\s+\d+\s+de\s+\d+$/i.test(normalize(node.textContent))
      );
      if (label) makeEditable(label);
    });

    document.querySelectorAll("span[id],div[id]").forEach(node => {
      if (/page|pagina/i.test(node.id) && /^P[aá]gina\s+\d+\s+de\s+\d+$/i.test(normalize(node.textContent))) makeEditable(node);
    });
  }

  function scan() {
    scanPageSizes();
    document.querySelectorAll("input[data-cs-page-input]").forEach((input) => {
      const label = input.closest(".cs-page-jump") || input.parentElement;
      bindInput(label, input);
    });
    scanKnownLabels();
    scanGenericPagination();
  }

  let scanTimer = null;
  function scheduleScan() {
    if (scanTimer !== null) return;
    scanTimer = window.setTimeout(() => {
      scanTimer = null;
      scan();
    }, SCAN_DELAY_MS);
  }

  function start() {
    scan();
    new MutationObserver(scheduleScan).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    window.setInterval(scan, FALLBACK_SCAN_MS);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
