(() => {
  "use strict";
  if (window.__crapScraperCreditAccuracyInstalled) return;
  window.__crapScraperCreditAccuracyInstalled = true;

  const $ = (selector) => document.querySelector(selector);
  const text = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  let loading = false;
  let timer = null;
  let lastPayload = null;
  let reapplying = false;

  function creditText(payload) {
    const remaining = Number(payload?.remaining);
    const limit = Number(payload?.limit);
    if (!payload?.ok || !Number.isFinite(remaining) || !Number.isFinite(limit) || limit <= 0) return "—";
    const prefix = payload?.estimated ? "≈" : "";
    return `${prefix}${Math.max(0, remaining)}/${Math.max(0, limit)}`;
  }

  function renderOne(id, label, payload) {
    const node = $(id);
    if (!node) return;
    const value = creditText(payload);
    const markup = `${label}: <b>${value}</b>`;
    if (node.innerHTML !== markup) node.innerHTML = markup;
    if (payload?.estimated) {
      node.title = text(payload?.message || "Estimativa local; o saldo remoto ainda está sendo consultado.");
      node.dataset.creditAccuracy = "estimated";
    } else if (payload?.ok) {
      node.title = `Saldo remoto confirmado. Fonte: ${text(payload?.source || "remota")}.`;
      node.dataset.creditAccuracy = "remote";
    } else {
      node.title = text(payload?.message || "Saldo indisponível.");
      node.dataset.creditAccuracy = "unavailable";
    }
  }

  function render(payload) {
    if (!payload) return;
    reapplying = true;
    try {
      renderOne("#cs_credit_ultrapack", "UltraPackV2", payload?.ultrapackv2 || {});
      renderOne("#cs_credit_plugintheme", "PluginTheme", payload?.plugintheme || {});
    } finally {
      reapplying = false;
    }
  }

  function payloadScore(payload) {
    if (!payload) return -1;
    const sites = [payload?.ultrapackv2, payload?.plugintheme];
    return sites.reduce((score, site) => {
      if (!site?.ok) return score;
      return score + (site?.estimated ? 1 : 10);
    }, 0);
  }

  function remember(payload) {
    // Nunca deixa uma resposta estimada substituir um saldo remoto já confirmado.
    if (!lastPayload || payloadScore(payload) >= payloadScore(lastPayload)) lastPayload = payload;
    render(lastPayload);
  }

  async function refresh() {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const response = await fetch("/processos/creditos", {
        cache: "no-store",
        credentials: "same-origin",
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok) remember(payload);
    } catch (_error) {
      // O contador principal continua funcional mesmo se esta camada auxiliar falhar.
    } finally {
      loading = false;
    }
  }

  function protectRenderedValue() {
    const root = $("#cs_download_credits");
    if (!root || root.dataset.creditAccuracyObserver === "1") return;
    root.dataset.creditAccuracyObserver = "1";
    const observer = new MutationObserver(() => {
      if (reapplying || !lastPayload) return;
      window.setTimeout(() => render(lastPayload), 0);
    });
    observer.observe(root, { childList: true, subtree: true, characterData: true });
  }

  function start() {
    protectRenderedValue();
    window.setTimeout(refresh, 1500);
    timer = window.setInterval(refresh, 10000);
    window.setInterval(protectRenderedValue, 1500);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
