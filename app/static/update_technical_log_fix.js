(() => {
  "use strict";

  if (window.__crapScraperUpdateTechnicalLogFixInstalled) return;
  window.__crapScraperUpdateTechnicalLogFixInstalled = true;

  const SELECTOR = "#tab_panel_atualizacoes details.updates-technical-log";
  const STATE_KEY = "crapscraper:update-technical-log:open:v3";
  const bound = new WeakSet();
  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  let lastJobId = "";
  let refreshTimer = null;
  let observer = null;

  async function requestJson(url, timeoutMs = 9000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.message || `HTTP ${response.status}`);
      }
      return payload;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function technicalDetails() {
    return $(SELECTOR);
  }

  function storedOpenState() {
    try {
      const value = sessionStorage.getItem(STATE_KEY);
      return value === "1" ? true : value === "0" ? false : null;
    } catch (_error) {
      return null;
    }
  }

  function persistOpenState(details) {
    try { sessionStorage.setItem(STATE_KEY, details.open ? "1" : "0"); } catch (_error) {}
  }

  function syncDisclosure(details) {
    if (!details) return;
    const summary = $(":scope > summary", details);
    if (!summary) return;
    const title = $(".section-title", summary);
    const chevron = $(".updates-disclosure-chevron", summary);
    if (title && clean(title.textContent) !== "Logs da atualização") {
      title.textContent = "Logs da atualização";
    }
    if (chevron) chevron.textContent = details.open ? "▾" : "▸";
    summary.setAttribute("aria-expanded", details.open ? "true" : "false");
  }

  function resolveBatchJobId(batch) {
    const current = clean(batch?.current_job_id);
    if (current) return current;
    const results = Array.isArray(batch?.results) ? batch.results : [];
    for (let index = results.length - 1; index >= 0; index -= 1) {
      const jobId = clean(results[index]?.job_id);
      if (jobId) return jobId;
    }
    return "";
  }

  async function refreshTechnicalLog() {
    const details = technicalDetails();
    const target = $("#updates_log");
    if (!details?.open || !target) return;

    try {
      const status = await requestJson("/operacoes/simples/status", 7000);
      const resolved = resolveBatchJobId(status?.update);
      if (resolved) lastJobId = resolved;
      if (!lastJobId) {
        if (!clean(target.textContent) || clean(target.textContent) === "Nenhum evento nesta sessão.") {
          target.textContent = "Execute ou selecione uma atualização para carregar o log técnico correspondente.";
        }
        return;
      }

      const payload = await requestJson(
        `/atualizacoes/logs?job_id=${encodeURIComponent(lastJobId)}`,
        7000,
      );
      const logs = Array.isArray(payload?.logs) ? payload.logs : [];
      target.textContent = logs.length ? logs.join("\n") : "Nenhum evento técnico registrado para esta atualização.";
      target.scrollTop = target.scrollHeight;
    } catch (_error) {
      /* O log é diagnóstico auxiliar; nunca deve interferir na atualização. */
    }
  }

  function bind(details = technicalDetails()) {
    if (!details) return false;

    if (!bound.has(details)) {
      bound.add(details);
      const preferred = storedOpenState();
      if (preferred !== null && details.open !== preferred) details.open = preferred;
      syncDisclosure(details);

      // ÚNICO controlador do estado: o evento nativo <details> toggle.
      // Não interceptamos click/keydown e nunca alternamos `open` manualmente.
      details.addEventListener("toggle", () => {
        persistOpenState(details);
        syncDisclosure(details);
        if (details.open) refreshTechnicalLog();
      });
    } else {
      syncDisclosure(details);
    }

    return true;
  }

  function nodeContainsTechnicalDetails(node) {
    if (!(node instanceof Element)) return false;
    if (node.matches?.("details.updates-technical-log")) return true;
    return Boolean(node.querySelector?.("details.updates-technical-log"));
  }

  function observeReplacement() {
    const panel = $("#tab_panel_atualizacoes");
    if (!panel || observer) return;
    observer = new MutationObserver(records => {
      // Observa somente substituição/adição de elementos. Mudanças de texto dos
      // logs/progresso não disparam rebind nem alteram o estado da sanfona.
      const replaced = records.some(record =>
        Array.from(record.addedNodes || []).some(nodeContainsTechnicalDetails)
      );
      if (replaced) bind();
    });
    observer.observe(panel, {childList: true, subtree: true});
  }

  function startLogPolling() {
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(() => {
      if (technicalDetails()?.open) refreshTechnicalLog();
    }, 1400);
  }

  function boot() {
    bind();
    observeReplacement();
    startLogPolling();

    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (String(event?.detail?.key || "") === "atualizacoes") bind();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once: true});
  } else {
    boot();
  }
})();
