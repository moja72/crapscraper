(() => {
  "use strict";
  if (window.__crapScraperProcessModalStabilityInstalled) return;
  window.__crapScraperProcessModalStabilityInstalled = true;

  const HISTORY_KEY = "crapscraper.process.history.v1";
  const ABORT_RE = /(?:aborterror|signal is aborted|aborted without reason|the operation was aborted)/i;
  let guardInstalled = false;
  let lastBaseSignature = "";
  let cleanupTimer = 0;

  function findInnerHtmlDescriptor() {
    let proto = Element.prototype;
    while (proto) {
      const descriptor = Object.getOwnPropertyDescriptor(proto, "innerHTML");
      if (descriptor?.get && descriptor?.set) return descriptor;
      proto = Object.getPrototypeOf(proto);
    }
    return null;
  }

  function baseSignature(markup) {
    return String(markup || "")
      .replace(/Tempo:\s*[^<]*/gi, "Tempo: *")
      .replace(/\s+/g, " ")
      .trim();
  }

  function installBodyGuard() {
    if (guardInstalled) return true;
    const body = document.getElementById("cs_processes_body");
    const native = findInnerHtmlDescriptor();
    if (!body || !native) return false;

    try {
      Object.defineProperty(body, "innerHTML", {
        configurable: true,
        enumerable: false,
        get() { return native.get.call(this); },
        set(value) {
          const markup = String(value ?? "");
          const signature = baseSignature(markup);
          const hasNativeBase = !!this.querySelector(":scope > .cs-process-card, :scope > .cs-process-empty");

          // active_processes.js redraws the whole body every second only to
          // update elapsed time. Ignore those semantically identical paints so
          // history/addition cards and scrollbar are not destroyed/recreated.
          if (signature && signature === lastBaseSignature && hasNativeBase) return;

          const scrollTop = this.scrollTop;
          const history = this.querySelector(":scope > #cs_process_history_section");
          const activeEmpty = this.querySelector(":scope > #cs_process_active_empty");
          const additionCards = Array.from(this.querySelectorAll(":scope > .cs-addition-operational-process"));

          native.set.call(this, markup);
          lastBaseSignature = signature;

          if (activeEmpty && !this.querySelector("#cs_process_active_empty")) this.appendChild(activeEmpty);
          additionCards.forEach(card => {
            if (!this.contains(card)) this.appendChild(card);
          });
          if (history && !this.querySelector("#cs_process_history_section")) this.appendChild(history);

          this.scrollTop = scrollTop;
          requestAnimationFrame(() => {
            if (document.body.contains(this)) this.scrollTop = scrollTop;
          });
        },
      });
      guardInstalled = true;
      return true;
    } catch (_error) {
      return false;
    }
  }

  function cleanAbortHistoryStorage() {
    try {
      const rows = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      if (!Array.isArray(rows)) return;
      const filtered = rows.filter(row => !ABORT_RE.test(String(row?.detail || "")));
      if (filtered.length !== rows.length) {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(filtered.slice(0, 80)));
      }
    } catch (_error) {}
  }

  function cleanAbortHistoryDom() {
    const section = document.getElementById("cs_process_history_section");
    if (!section) return;
    let removed = 0;
    section.querySelectorAll(".cs-process-history-card").forEach(card => {
      const detail = card.querySelector(".cs-process-detail")?.textContent || "";
      if (!ABORT_RE.test(detail)) return;
      card.remove();
      removed += 1;
    });
    if (removed) {
      const count = section.querySelector(".cs-process-history-count");
      if (count) {
        const visible = section.querySelectorAll(".cs-process-history-card").length;
        count.textContent = `${visible} registro(s)`;
      }
    }
  }

  function maintain() {
    installBodyGuard();
    cleanAbortHistoryStorage();
    cleanAbortHistoryDom();
  }

  function start() {
    maintain();
    window.setTimeout(maintain, 250);
    window.setTimeout(maintain, 1000);
    // Lightweight maintenance only; it does not fetch or repaint the panel.
    cleanupTimer = window.setInterval(maintain, 3000);
  }

  window.addEventListener("pagehide", () => {
    if (cleanupTimer) window.clearInterval(cleanupTimer);
  }, {once: true});

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
