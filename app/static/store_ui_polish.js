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

  const start = () => {
    ensureStyle();
    markPassiveAccordions();
    const observer = new MutationObserver(markPassiveAccordions);
    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
