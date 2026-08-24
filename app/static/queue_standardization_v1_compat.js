(() => {
  "use strict";
  if (window.__crapScraperQueueStandardizationV1CompatInstalled) return;
  window.__crapScraperQueueStandardizationV1CompatInstalled = true;

  function ensureUpdateQueueMetaContract() {
    const card = document.querySelector("#tab_panel_atualizacoes .updates-queue-section");
    if (!card) return;
    let meta = document.getElementById("updates_queue_meta");
    if (!meta) {
      meta = document.createElement("span");
      meta.id = "updates_queue_meta";
      card.appendChild(meta);
    }
    meta.hidden = true;
    meta.setAttribute("aria-hidden", "true");
    meta.style.display = "none";
  }

  function start() {
    ensureUpdateQueueMetaContract();
    const panel = document.getElementById("tab_panel_atualizacoes");
    if (panel) {
      new MutationObserver(ensureUpdateQueueMetaContract).observe(panel, {childList:true, subtree:true});
    }
    [60,180,420,900,1800,3200].forEach(delay => setTimeout(ensureUpdateQueueMetaContract, delay));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
