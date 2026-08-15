(() => {
  "use strict";

  const DEBOUNCE_MS = 700;
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
  ]);

  function clampPage(value, total, fallback) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(1, Math.min(total, parsed));
  }

  function parseLabel(label) {
    if (!label) return null;
    const current = Number(label.dataset.csCurrent || 0);
    const total = Number(label.dataset.csTotal || 0);
    if (current > 0 && total > 0) return { current, total };

    const match = normalize(label.textContent).match(/P[aá]gina\s+(\d+)\s+de\s+(\d+)/i);
    if (!match) return null;
    return { current: Number(match[1]), total: Number(match[2]) };
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
  }

  function makeEditable(label) {
    if (!label) return;
    const existing = label.querySelector("input[data-cs-page-input]");
    if (existing) {
      bindInput(label, existing);
      return;
    }

    const info = parseLabel(label);
    if (!info) return;
    label.dataset.csCurrent = String(info.current);
    label.dataset.csTotal = String(info.total);
    label.classList.add("cs-page-jump");
    label.innerHTML = `Página <input data-cs-page-input type="number" min="1" max="${info.total}" value="${info.current}" aria-label="Ir para página"> de <span>${info.total}</span>`;
    bindInput(label, label.querySelector("input[data-cs-page-input]"));
  }

  function scan() {
    document.querySelectorAll("input[data-cs-page-input]").forEach((input) => {
      const label = input.closest(".cs-page-jump") || input.parentElement;
      bindInput(label, input);
    });

    document.querySelectorAll(".listing-pagination").forEach((row) => {
      const candidates = [...row.querySelectorAll("span,div,strong,b")];
      const label = candidates.find((node) =>
        node.querySelector("input[data-cs-page-input]") ||
        /^P[aá]gina\s+\d+\s+de\s+\d+$/i.test(normalize(node.textContent))
      );
      if (label) makeEditable(label);
    });
  }

  let scanTimer = null;
  function scheduleScan() {
    window.clearTimeout(scanTimer);
    scanTimer = window.setTimeout(scan, 60);
  }

  function start() {
    scan();
    new MutationObserver(scheduleScan).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
