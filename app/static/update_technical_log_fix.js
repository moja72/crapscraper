(() => {
  "use strict";

  if (window.__crapScraperUpdateTechnicalLogFixInstalled) return;
  window.__crapScraperUpdateTechnicalLogFixInstalled = true;

  const STATE_KEY = "crapscraper:update-technical-log:open:v4";
  const MOUNT_ID = "updates_technical_log_mount";
  const STABLE_ATTR = "data-cs-stable-update-log";
  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();

  let stableDetails = null;
  let lastJobId = "";
  let polling = null;
  let refreshInFlight = false;

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

  function installStyles() {
    if ($("#cs-update-technical-log-stable-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-technical-log-stable-style";
    style.textContent = `
      #tab_panel_atualizacoes details.updates-technical-log:not([${STABLE_ATTR}="1"]){
        display:none!important
      }
      #${MOUNT_ID}{display:block!important;min-width:0}
      #${MOUNT_ID}>details.updates-technical-log{display:block!important}
    `;
    document.head.appendChild(style);
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
    try {
      sessionStorage.setItem(STATE_KEY, details.open ? "1" : "0");
    } catch (_error) {}
  }

  function syncDisclosure(details) {
    const summary = $(":scope > summary", details);
    if (!summary) return;
    const title = $(".section-title", summary);
    const chevron = $(".updates-disclosure-chevron", summary);
    if (title) title.textContent = "Logs da atualização";
    if (chevron) chevron.textContent = details.open ? "▾" : "▸";
    summary.setAttribute("aria-expanded", details.open ? "true" : "false");
  }

  function ensureStableDetails() {
    if (stableDetails?.isConnected) return stableDetails;

    const panel = $("#tab_panel_atualizacoes");
    if (!panel) return null;

    const original = $(`details.updates-technical-log[${STABLE_ATTR}="1"]`, panel)
      || $("details.updates-technical-log", panel);
    if (!original) return null;

    let mount = document.getElementById(MOUNT_ID);
    if (!mount) {
      mount = document.createElement("div");
      mount.id = MOUNT_ID;
      mount.dataset.csStableUpdateLogMount = "1";
      panel.appendChild(mount);
    }

    original.setAttribute(STABLE_ATTR, "1");
    if (original.parentElement !== mount) mount.appendChild(original);
    stableDetails = original;

    const preferred = storedOpenState();
    if (preferred !== null) stableDetails.open = preferred;
    syncDisclosure(stableDetails);

    if (stableDetails.dataset.csStableToggleBound !== "1") {
      stableDetails.dataset.csStableToggleBound = "1";
      stableDetails.addEventListener("toggle", () => {
        persistOpenState(stableDetails);
        syncDisclosure(stableDetails);
        if (stableDetails.open) refreshTechnicalLog();
      });
    }

    return stableDetails;
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
    const details = ensureStableDetails();
    const target = $("#updates_log", details);
    const panel = $("#tab_panel_atualizacoes");
    if (
      refreshInFlight || document.hidden || !details?.open || !target ||
      !panel || panel.classList.contains("hidden")
    ) {
      return;
    }

    refreshInFlight = true;
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
      const nextText = logs.length
        ? logs.join("\n")
        : "Nenhum evento técnico registrado para esta atualização.";

      // Polling altera SOMENTE o texto do <pre>. Nunca recria <details>,
      // nunca toca em `open` e nunca reescreve o card pai.
      if (target.textContent !== nextText) {
        const stayAtBottom =
          target.scrollHeight - target.scrollTop - target.clientHeight < 32;
        target.textContent = nextText;
        if (stayAtBottom) target.scrollTop = target.scrollHeight;
      }
    } catch (_error) {
      // O log é diagnóstico auxiliar; nunca interfere na atualização.
    } finally {
      refreshInFlight = false;
    }
  }

  function startPolling() {
    window.clearInterval(polling);
    polling = window.setInterval(refreshTechnicalLog, 1600);
  }

  function boot() {
    installStyles();
    const details = ensureStableDetails();
    if (!details) return;
    startPolling();

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && stableDetails?.open) refreshTechnicalLog();
    });
    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (String(event?.detail?.key || "") === "atualizacoes" && stableDetails?.open) {
        refreshTechnicalLog();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once: true});
  } else {
    boot();
  }
})();