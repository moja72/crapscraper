(() => {
  "use strict";

  if (window.__crapScraperUpdateTechnicalLogFixInstalled) return;
  window.__crapScraperUpdateTechnicalLogFixInstalled = true;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  let lastJobId = "";
  let refreshTimer = null;

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
    return $("#tab_panel_atualizacoes details.updates-technical-log");
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
    const chevronText = details.open ? "▾" : "▸";
    const expanded = details.open ? "true" : "false";
    if (chevron && chevron.textContent !== chevronText) chevron.textContent = chevronText;
    if (summary.getAttribute("aria-expanded") !== expanded) {
      summary.setAttribute("aria-expanded", expanded);
    }
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

  function startLogPolling() {
    window.clearInterval(refreshTimer);
    refreshTechnicalLog();
    refreshTimer = window.setInterval(() => {
      const details = technicalDetails();
      if (details?.open) refreshTechnicalLog();
    }, 1400);
  }

  function bindTechnicalAccordion() {
    const details = technicalDetails();
    if (!details) return false;
    const summary = $(":scope > summary", details);
    if (!summary) return false;

    syncDisclosure(details);
    if (details.dataset.csTechnicalLogFixed === "1") return true;
    details.dataset.csTechnicalLogFixed = "1";

    // Algumas camadas de padronização antigas interceptam/reconstroem accordions.
    // O listener em captura torna esta sanfona determinística: um clique = um toggle.
    summary.addEventListener("click", event => {
      event.preventDefault();
      event.stopImmediatePropagation();
      details.open = !details.open;
      syncDisclosure(details);
      if (details.open) refreshTechnicalLog();
    }, true);

    summary.addEventListener("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      details.open = !details.open;
      syncDisclosure(details);
      if (details.open) refreshTechnicalLog();
    }, true);

    details.addEventListener("toggle", () => {
      syncDisclosure(details);
      if (details.open) refreshTechnicalLog();
    });

    return true;
  }

  function boot() {
    bindTechnicalAccordion();
    startLogPolling();

    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (String(event?.detail?.key || "") === "atualizacoes") bindTechnicalAccordion();
    });
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => {
      window.setTimeout(bindTechnicalAccordion, 0);
    });
    window.setInterval(bindTechnicalAccordion, 1200);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once: true});
  } else {
    boot();
  }
})();
