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
  let refreshTimer = 0;
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
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      return payload;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function technicalDetails() {
    return $(SELECTOR);
  }

  function savedOpenState() {
    try {
      const raw = sessionStorage.getItem(STATE_KEY);
      if (raw === "1") return true;
      if (raw === "0") return false;
    } catch (_error) {}
    return null;
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
    if (title && clean(title.textContent) !== "Logs da atualização") title.textContent = "Logs da atualização";
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
      const payload = await requestJson(`/atualizacoes/logs?job_id=${encodeURIComponent(lastJobId)}`, 7000);
      const logs = Array.isArray(payload?.logs) ? payload.logs : [];
      const next = logs.length ? logs.join("\n") : "Nenhum evento técnico registrado para esta atualização.";
      if (target.textContent !== next) {
        const wasAtBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 16;
        target.textContent = next;
        if (wasAtBottom) target.scrollTop = target.scrollHeight;
      }
    } catch (_error) {
      // O log é diagnóstico auxiliar; nunca interfere no executor nem no estado open.
    }
  }

  function bindTechnicalAccordion() {
    const details = technicalDetails();
    if (!details) return false;
    if (bound.has(details)) {
      syncDisclosure(details);
      return true;
    }

    // O navegador é o único responsável por abrir/fechar <details>. Esta policy
    // observa o evento nativo toggle; não intercepta click/keydown e não inverte open.
    const saved = savedOpenState();
    if (saved !== null && details.open !== saved) details.open = saved;
    syncDisclosure(details);

    details.addEventListener("toggle", () => {
      persistOpenState(details);
      syncDisclosure(details);
      if (details.open) refreshTechnicalLog();
    });
    bound.add(details);
    details.dataset.csTechnicalLogFixed = "1";
    if (details.open) refreshTechnicalLog();
    return true;
  }

  function observeReplacement() {
    const panel = $("#tab_panel_atualizacoes");
    if (!panel || observer) return;
    observer = new MutationObserver(() => bindTechnicalAccordion());
    observer.observe(panel, {childList: true, subtree: true});
  }

  function startLogRefresh() {
    window.clearInterval(refreshTimer);
    refreshTimer = window.setInterval(() => {
      if (technicalDetails()?.open) refreshTechnicalLog();
    }, 1600);
  }

  function boot() {
    bindTechnicalAccordion();
    observeReplacement();
    startLogRefresh();
    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (clean(event?.detail?.key) === "atualizacoes") window.setTimeout(bindTechnicalAccordion, 0);
    });
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => window.setTimeout(bindTechnicalAccordion, 0));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once: true});
  else boot();
})();
