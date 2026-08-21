(() => {
  "use strict";
  if (window.__crapScraperStoreManualMonitorControlInstalled) return;
  window.__crapScraperStoreManualMonitorControlInstalled = true;

  const ENDPOINT = "/loja/wordpress-manual/control";
  let state = null;
  let busy = false;
  let timer = null;

  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyle() {
    if (document.getElementById("cs-store-monitor-control-style")) return;
    const style = document.createElement("style");
    style.id = "cs-store-monitor-control-style";
    style.textContent = `
      .cs-store-monitor-control{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:12px 0;padding:12px 14px;border:1px solid #2b2b33;border-radius:10px;background:#0d0d10}
      .cs-store-monitor-copy{min-width:0;display:grid;gap:4px}.cs-store-monitor-title{font-weight:800;color:#f4f4f7;font-size:12px}.cs-store-monitor-state{color:#9da3b2;font-size:11px;line-height:1.35}
      .cs-store-monitor-actions{display:flex;align-items:center;gap:9px;flex:0 0 auto}.cs-store-monitor-dot{width:9px;height:9px;border-radius:50%;background:#6b7280;box-shadow:0 0 0 3px rgba(107,114,128,.10)}
      .cs-store-monitor-dot.is-on{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.12)}.cs-store-monitor-dot.is-error{background:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.12)}
      .cs-store-monitor-toggle{display:inline-flex;align-items:center;gap:9px;min-height:34px;padding:5px 9px;border:1px solid #383842;border-radius:999px;background:#15151a;color:#fff;font-weight:800;font-size:11px;cursor:pointer}
      .cs-store-monitor-toggle:hover{border-color:#6d3bb5}.cs-store-monitor-toggle:disabled{opacity:.55;cursor:wait}
      .cs-store-monitor-switch{position:relative;width:38px;height:20px;border-radius:999px;background:#3b3b44;transition:background .18s ease;box-shadow:inset 0 0 0 1px rgba(255,255,255,.05)}
      .cs-store-monitor-switch::after{content:"";position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#fff;transition:transform .18s ease;box-shadow:0 1px 4px rgba(0,0,0,.45)}
      .cs-store-monitor-toggle.is-on .cs-store-monitor-switch{background:#22c55e}.cs-store-monitor-toggle.is-on .cs-store-monitor-switch::after{transform:translateX(18px)}
      .cs-store-monitor-toggle.is-error .cs-store-monitor-switch{background:#7f1d1d}.cs-store-monitor-toggle-label{min-width:68px;text-align:left}
      @media(max-width:720px){.cs-store-monitor-control{align-items:stretch;flex-direction:column}.cs-store-monitor-actions{justify-content:space-between}.cs-store-monitor-toggle{justify-content:center}}
    `;
    document.head.appendChild(style);
  }

  function findMonitorCard() {
    const grid = document.getElementById("wp_manual_monitor");
    if (grid) return grid.closest(".wp-manual-monitor, section.card, .card") || grid.parentElement;
    const title = document.getElementById("wp_manual_monitor_title");
    if (title) return title.closest(".wp-manual-monitor, section.card, .card") || title.parentElement;
    return document.querySelector("#tab_panel_loja .wp-manual-monitor");
  }

  function ensureControl() {
    installStyle();
    const card = findMonitorCard();
    if (!card) return null;

    let root = card.querySelector("#cs_store_manual_monitor_control");
    if (root) return root;

    root = document.createElement("div");
    root.id = "cs_store_manual_monitor_control";
    root.className = "cs-store-monitor-control";
    root.innerHTML = `
      <div class="cs-store-monitor-copy">
        <div class="cs-store-monitor-title">Monitoramento automático</div>
        <div class="cs-store-monitor-state">Carregando estado do monitor…</div>
      </div>
      <div class="cs-store-monitor-actions">
        <span class="cs-store-monitor-dot" aria-hidden="true"></span>
        <button type="button" class="cs-store-monitor-toggle" role="switch" aria-checked="false" aria-label="Ativar ou desativar monitoramento automático">
          <span class="cs-store-monitor-switch" aria-hidden="true"></span>
          <span class="cs-store-monitor-toggle-label">Desativado</span>
        </button>
      </div>`;

    const grid = card.querySelector("#wp_manual_monitor");
    if (grid?.parentNode === card) card.insertBefore(root, grid);
    else {
      const title = card.querySelector("#wp_manual_monitor_title");
      if (title?.nextSibling) title.parentNode.insertBefore(root, title.nextSibling);
      else card.prepend(root);
    }

    root.querySelector(".cs-store-monitor-toggle")?.addEventListener("click", toggle);
    return root;
  }

  function render() {
    const root = ensureControl();
    if (!root || !state) return;
    const enabled = !!state.enabled;
    const configured = state.configured !== false;
    const button = root.querySelector(".cs-store-monitor-toggle");
    const label = root.querySelector(".cs-store-monitor-toggle-label");
    const dot = root.querySelector(".cs-store-monitor-dot");
    const copy = root.querySelector(".cs-store-monitor-state");

    dot?.classList.toggle("is-on", enabled && configured);
    dot?.classList.toggle("is-error", !configured);
    if (button) {
      button.disabled = busy || (!configured && !enabled);
      button.classList.toggle("is-on", enabled);
      button.classList.toggle("is-error", !configured);
      button.setAttribute("aria-checked", enabled ? "true" : "false");
      button.setAttribute("title", enabled ? "Desativar monitor" : "Ativar monitor");
    }
    if (label) label.textContent = busy ? "Salvando…" : (enabled ? "Ativado" : "Desativado");
    if (copy) {
      if (!configured) copy.textContent = "Configuração incompleta: URL ou segredo do WordPress não estão disponíveis.";
      else if (enabled) copy.textContent = state.worker_alive ? "Ativo · consultando novos pedidos a cada 5 segundos." : "Ativo · iniciando o monitor…";
      else copy.textContent = "Desativado · nenhum novo pedido do WordPress será consultado.";
    }
  }

  async function load() {
    try {
      const response = await fetch(ENDPOINT, {cache: "no-store", credentials: "same-origin"});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      state = payload;
      render();
    } catch (_error) {
      const root = ensureControl();
      const copy = root?.querySelector(".cs-store-monitor-state");
      if (copy) copy.textContent = "Não foi possível consultar o estado do monitor.";
    }
  }

  async function toggle() {
    if (busy || !state) return;
    busy = true;
    render();
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({enabled: !state.enabled}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      state = payload;
    } catch (error) {
      window.alert(`Não foi possível alterar o monitor: ${text(error?.message)}`);
    } finally {
      busy = false;
      render();
    }
  }

  function visibleStore() {
    const panel = document.getElementById("tab_panel_loja");
    return !!panel && !panel.classList.contains("hidden");
  }

  function start() {
    ensureControl();
    load();
    const observer = new MutationObserver(() => {
      ensureControl();
      if (visibleStore()) render();
    });
    observer.observe(document.body, {childList: true, subtree: true});
    timer = window.setInterval(() => {
      if (visibleStore()) load();
    }, 5000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true});
  else start();
})();
