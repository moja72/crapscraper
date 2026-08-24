(() => {
  "use strict";
  if (window.__crapScraperQueueHelpCleanupV2Installed) return;
  window.__crapScraperQueueHelpCleanupV2Installed = true;

  const ROOTS = "#updates_queue_accordion,#addition_queue_accordion,.updates-queue-section,#addition_queue_accordion";
  let timer = 0;

  function cleanupRoot(root) {
    if (!root) return;

    root.querySelectorAll(".operational-action-control").forEach(wrapper => {
      const realButton = wrapper.querySelector("button:not(.comparison-help)");
      if (!realButton) wrapper.remove();
    });

    root.querySelectorAll(".comparison-help.operational-action-help").forEach(help => {
      const wrapper = help.closest(".operational-action-control");
      const realButton = wrapper?.querySelector?.("button:not(.comparison-help)");
      if (!wrapper || !realButton) help.remove();
    });

    root.querySelectorAll(".comparison-help.operational-field-help").forEach(help => {
      const label = help.closest("label");
      if (!label || !label.querySelector("input,select,textarea")) help.remove();
    });

    root.querySelectorAll(".comparison-help").forEach(help => {
      const validAction = help.classList.contains("operational-action-help") && !!help.closest(".operational-action-control")?.querySelector("button:not(.comparison-help)");
      const validField = help.classList.contains("operational-field-help") && !!help.closest("label")?.querySelector("input,select,textarea");
      const validSummary = help.classList.contains("operational-summary-help") && !!help.closest(".operational-summary-footer,.cs-queue-v1-chip");
      if (!validAction && !validField && !validSummary) help.remove();
    });
  }

  function cleanup() {
    document.querySelectorAll(ROOTS).forEach(cleanupRoot);
  }
  function schedule(delay = 25) {
    clearTimeout(timer);
    timer = window.setTimeout(cleanup, delay);
  }

  function start() {
    cleanup();
    const observer = new MutationObserver(() => schedule(20));
    observer.observe(document.body, {childList:true, subtree:true});
    document.addEventListener("click", event => {
      const id = event.target?.closest?.("button")?.id || "";
      if (["tab_btn_atualizacoes","tab_btn_adicoes","updates_refresh_btn","addition_queue_refresh"].includes(id)) schedule(40);
    }, true);
    [100,300,800,1600,3000].forEach(delay => window.setTimeout(cleanup, delay));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
