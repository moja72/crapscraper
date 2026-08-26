(() => {
  "use strict";

  if (window.__crapScraperUpdateFlowFinalInstalled) return;
  window.__crapScraperUpdateFlowFinalInstalled = true;

  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  let observer = null;

  function removeRedundantWaitingCard() {
    const summary = document.getElementById("updates_summary");
    if (!summary) return false;
    const cards = Array.from(summary.children || []);
    const labelOf = card => clean(card.querySelector("span")?.textContent).replace(/\s*\?\s*$/, "");
    const hasPrepared = cards.some(card => labelOf(card) === "Preparados");
    if (!hasPrepared) return false;
    const waiting = cards.find(card => labelOf(card) === "Aguardando");
    if (!waiting) return false;
    waiting.remove();
    return true;
  }

  function bindSummary() {
    const summary = document.getElementById("updates_summary");
    if (!summary) return false;
    removeRedundantWaitingCard();
    if (summary.dataset.csFinalSummaryBound === "1") return true;
    summary.dataset.csFinalSummaryBound = "1";
    observer = new MutationObserver(() => removeRedundantWaitingCard());
    observer.observe(summary, {childList: true});
    return true;
  }

  function boot() {
    bindSummary();
    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (clean(event?.detail?.key) === "atualizacoes") window.setTimeout(bindSummary, 0);
    });
    document.getElementById("tab_btn_atualizacoes")?.addEventListener("click", () => window.setTimeout(bindSummary, 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
  else boot();
})();
