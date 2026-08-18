(() => {
  "use strict";

  function normalize(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function ensureStyle() {
    if (document.getElementById("cs-passive-accordion-style")) return;
    const style = document.createElement("style");
    style.id = "cs-passive-accordion-style";
    style.textContent = `
      details.cs-passive-details:hover,
      details.cs-passive-details:has(> summary.cs-passive-summary:hover) {
        border-color: var(--line) !important;
        box-shadow: none !important;
        transform: none !important;
      }
      summary.cs-passive-summary:hover,
      summary.cs-passive-summary:focus-visible {
        background: inherit !important;
        border-color: inherit !important;
        box-shadow: none !important;
        transform: none !important;
        color: inherit !important;
      }
      .cs-price-footer {
        display: flex !important;
        align-items: center !important;
        justify-content: flex-end !important;
        width: 100% !important;
        max-width: 100% !important;
        padding: 14px 16px 4px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
        overflow: visible !important;
      }
      .cs-price-footer > button {
        flex: 0 0 auto !important;
        width: auto !important;
        min-width: 160px !important;
        max-width: calc(100% - 2px) !important;
        white-space: nowrap !important;
      }
    `;
    document.head.appendChild(style);
  }

  function markPassiveAccordions() {
    document.querySelectorAll("details > summary").forEach((summary) => {
      const text = normalize(summary.textContent);
      if (text.includes("Execuções Simultâneas") || text === "Fila" || text.startsWith("Fila ")) {
        summary.classList.add("cs-passive-summary");
        summary.closest("details")?.classList.add("cs-passive-details");
      }
    });
  }

  function ensureCategoryFooter() {
    const button = document.getElementById("store_category_save_all");
    if (!button) return;
    button.textContent = "Salvar preços";
    const footer = button.parentElement;
    if (footer) footer.classList.add("cs-price-footer");
  }

  function ensurePackFooter() {
    const root = document.getElementById("store_pack_prices");
    if (!root) return;
    const card = root.closest(".card");
    if (!card) return;

    let button = document.getElementById("store_pack_save_all");
    if (!button) return;
    button.textContent = "Salvar preços";

    let footer = button.parentElement;
    if (!footer) return;
    footer.classList.add("cs-price-footer");

    if (footer.parentElement !== card) {
      footer.remove();
      card.appendChild(footer);
    }
  }

  function apply() {
    markPassiveAccordions();
    ensureCategoryFooter();
    ensurePackFooter();
  }

  const start = () => {
    ensureStyle();
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
