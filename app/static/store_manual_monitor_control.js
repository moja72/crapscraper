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
      .cs-store-monitor-control{display:flex;align-items:center;justify-content:space-between;gap:14px;margin:12px 0 2px;padding:12px 14px;border:1px solid #2b2b33;border-radius:10px;background:#0d0d10}
      .cs-store-monitor-copy{min-width:0;display:grid;gap:4px}.cs-store-monitor-title{font-weight:800;color:#f4f4f7;font-size:12px}.cs-store-monitor-state{color:#9da3b2;font-size:11px;line-height:1.35}
      .cs-store-monitor-actions{display:flex;align-items:center;gap:9px;flex:0 0 auto}.cs-store-monitor-dot{width:9px;height:9px;border-radius:50%;background:#6b7280;box-shadow:0 0 0 3px rgba(107,114,128,.10)}
      .cs-store-monitor-dot.is-on{background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.12)}.cs-store-monitor-dot.is-error{background:#ef4444;box-shadow:0 0 0 3px rgba(239,68,68,.12)}
      .cs-store-monitor-toggle{min-height:34px;padding:0 13px;border:1px solid #383842;border-radius:8px;background:#1b1b21;color:#fff;font-weight:800;font-size:11px;cursor:pointer}
      .cs-store-monitor-toggle:hover{border-color:#6d3bb5}.cs-store-monitor-toggle.is-on{background:#123321;border-color:#246b43;color:#c9f7dc}.cs-store-monitor-toggle:disabled{opacity:.55;cursor:wait}
      @media(max-width:720px){.cs-store-monitor-control{align-items:stretch;flex-direction:column}.cs-store-monitor-actions{justify-content:space-between}.cs-store-monitor-toggle{flex:1}}
    `;
    document.head.appendChild(style);
  }

  function findMonitorCard() {
    const headings = [...document.querySelectorAll("#tab_panel_loja h2, #tab_panel_loja h3, #tab_panel_loja h4, #tab_panel_loja strong")];
    const heading = headings.find(node => text(node.textContent).toLowerCase().includes("atualizações solicitadas pelo wordpress"));
    if (!heading) return null;
    return heading.closest("section, article, details, .panel-card, .store-card, .card") || heading.parentElement?.parentElement || heading.parentElement;
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
        <button type="button" class="cs-store-monitor-toggle" aria-pressed="false">Ativar monitor</button>
      </div>`;

    const heading = [...card.querySelectorAll("h2,h3,h4,strong")].find(node => text(node.textContent).toLowerCase().includes("atualizações solicitadas pelo wordpress"));
    const anchor = heading?.parentElement || heading;
    if (anchor?.nextSibling) anchor.parentNode.insertBefore(root, anchor.nextSibling);
    else card.prepend(root);

    root.querySelector(".cs-store-monitor-toggle")?.addEventListener("click", toggle);
    return root;
  }

  function render() {
    const root = ensureControl();
    if (!root || !state) return;
    const enabled = !!state.enabled;
    const configured = state.configured !== false;
    const button = root.querySelector(".cs-store-monitor-toggle");
    const dot = root.querySelector(".cs-store-monitor-dot");
    const copy = root.querySelector(".cs-store-monitor-state");

    dot?.classList.toggle("is-on", enabled && configured);
    dot?.classList.toggle("is-error", !configured);
    if (button) {
      button.disabled = busy || (!configured && !enabled);
      button.classList.toggle("is-on", enabled);
      button.setAttribute("aria-pressed", enabled ? "true" : "false");
      button.textContent = busy ? "Salvando…" : (enabled ? "Desativar monitor" : "Ativar monitor");
    }
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
    if (busy) return;
    busy = true;
    render();
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({enabled: !state?.enabled}),
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
