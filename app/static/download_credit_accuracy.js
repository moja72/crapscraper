(() => {
  "use strict";
  if (window.__crapScraperCreditAccuracyInstalled) return;
  window.__crapScraperCreditAccuracyInstalled = true;

  const $ = (selector) => document.querySelector(selector);
  const text = (value) => String(value ?? "").replace(/\s+/g, " ").trim();
  let loading = false;
  let timer = null;

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
    node.innerHTML = `${label}: <b>${value}</b>`;
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
    renderOne("#cs_credit_ultrapack", "UltraPackV2", payload?.ultrapackv2 || {});
    renderOne("#cs_credit_plugintheme", "PluginTheme", payload?.plugintheme || {});
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
      if (response.ok) render(payload);
    } catch (_error) {
      // O contador principal continua funcional mesmo se esta camada auxiliar falhar.
    } finally {
      loading = false;
    }
  }

  function start() {
    window.setTimeout(refresh, 1500);
    timer = window.setInterval(refresh, 10000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
