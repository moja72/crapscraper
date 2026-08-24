(() => {
  "use strict";

  const ENDPOINT = "/plugintema/catalogo/atualizar";
  const STATUS_ENDPOINT = "/plugintema/catalogo/atualizar/status";
  const active = new Map();

  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

  async function json(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || payload?.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  function ensureStyle() {
    if (document.getElementById("cs-plugintema-refresh-style")) return;
    const style = document.createElement("style");
    style.id = "cs-plugintema-refresh-style";
    style.textContent = `
      .cs-catalog-refresh{position:relative}
      .cs-catalog-refresh.is-busy{pointer-events:none;opacity:.78}
      .cs-catalog-refresh.is-busy::before{content:"";display:inline-block;width:10px;height:10px;margin-right:6px;border:2px solid rgba(255,255,255,.25);border-top-color:currentColor;border-radius:50%;vertical-align:-1px;animation:csCatalogSpin .75s linear infinite}
      .cs-catalog-refresh-status{margin-top:7px;color:#9ca3af;font-size:11px;line-height:1.35}
      .cs-catalog-refresh-status.is-ok{color:#34d399}
      .cs-catalog-refresh-status.is-error{color:#f87171}
      @keyframes csCatalogSpin{to{transform:rotate(360deg)}}
      @media(prefers-reduced-motion:reduce){.cs-catalog-refresh.is-busy::before{animation:none}}
    `;
    document.head.appendChild(style);
  }

  function catalogIdFromCard(card) {
    return text(card?.dataset?.plugintemaCatalogId);
  }

  function statusNode(card) {
    let node = card.querySelector(".cs-catalog-refresh-status");
    if (!node) {
      node = document.createElement("div");
      node.className = "cs-catalog-refresh-status";
      const actions = card.querySelector(".plugintema-catalog-actions");
      (actions?.parentElement || card).appendChild(node);
    }
    return node;
  }

  function setStatus(card, message, kind = "") {
    const node = statusNode(card);
    node.className = `cs-catalog-refresh-status${kind ? ` ${kind}` : ""}`;
    node.textContent = message;
  }

  function selectedCatalogId() {
    return text(document.getElementById("plugintema_manage_catalog")?.value);
  }

  function refreshManagedView(catalogId) {
    const select = document.getElementById("plugintema_manage_catalog");
    if (!select) return;
    if ([...select.options].some(option => option.value === catalogId)) select.value = catalogId;
    select.dispatchEvent(new Event("change", {bubbles: true}));
  }

  function resultMessage(result) {
    const cache = result?.cache || {};
    const mode = cache.mode === "incremental" ? "cache incremental" : "varredura completa";
    return `Atualizado: ${result.after ?? 0} itens · +${result.added ?? 0} novos · ${result.removed ?? 0} removidos · ${result.versions_updated ?? 0} versões alteradas · ${mode}.`;
  }

  async function runRefresh(catalogId, button, card, forceFull = false) {
    if (!catalogId || active.has(catalogId)) return;
    const original = button.textContent;
    active.set(catalogId, true);
    button.disabled = true;
    button.classList.add("is-busy");
    button.textContent = forceFull ? "Varredura completa..." : "Atualizando...";
    setStatus(card, "Consultando a loja e reaproveitando o cache local quando possível...");

    try {
      const started = await json(ENDPOINT, {
        method: "POST",
        body: JSON.stringify({catalog_id: catalogId, force_full: !!forceFull}),
      });
      const jobId = text(started.job_id);
      if (!jobId) throw new Error("A atualização não retornou um identificador de processo.");

      let snapshot = started;
      while (!["completed", "error"].includes(text(snapshot.status))) {
        await sleep(650);
        snapshot = await json(`${STATUS_ENDPOINT}?job_id=${encodeURIComponent(jobId)}`);
        const message = text(snapshot.message);
        if (message) setStatus(card, message);
      }
      if (snapshot.status === "error") throw new Error(snapshot.message || "Falha ao atualizar o catálogo.");

      const result = snapshot.result || {};
      setStatus(card, resultMessage(result), "is-ok");
      button.textContent = "✅ Atualizado";
      window.setTimeout(() => refreshManagedView(catalogId), 250);
      window.setTimeout(() => {
        if (document.body.contains(button)) button.textContent = original || "🔄 Atualizar";
      }, 2600);
    } catch (error) {
      setStatus(card, error?.message || String(error), "is-error");
      button.textContent = "Tentar novamente";
    } finally {
      active.delete(catalogId);
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }

  function decorateCard(card) {
    if (!card || card.dataset.csRefreshReady === "1") return;
    const catalogId = catalogIdFromCard(card);
    const actions = card.querySelector(".plugintema-catalog-actions");
    if (!catalogId || !actions) return;
    card.dataset.csRefreshReady = "1";

    const button = document.createElement("button");
    button.className = "btn-secondary btn-sm cs-catalog-refresh";
    button.type = "button";
    button.dataset.catalogRefreshId = catalogId;
    button.textContent = "🔄 Atualizar";
    button.title = "Atualiza versões, novos produtos, status e categorias usando a loja WooCommerce.";
    const download = actions.querySelector('[data-catalog-action="download"]');
    if (download) download.insertAdjacentElement("afterend", button);
    else actions.appendChild(button);
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      runRefresh(catalogId, button, card, event.shiftKey);
    });
  }

  function decorateCards() {
    document.querySelectorAll(".plugintema-catalog-card").forEach(decorateCard);
  }

  function ensureToolbarButton() {
    const toolbar = document.querySelector(".plugintema-manage-toolbar .listing-page-size");
    if (!toolbar || document.getElementById("plugintema_manage_refresh")) return;
    const button = document.createElement("button");
    button.id = "plugintema_manage_refresh";
    button.type = "button";
    button.className = "btn-secondary btn-sm cs-catalog-refresh";
    button.textContent = "🔄 Atualizar catálogo";
    const download = document.getElementById("plugintema_manage_download");
    if (download) download.insertAdjacentElement("beforebegin", button);
    else toolbar.appendChild(button);
    button.addEventListener("click", () => {
      const catalogId = selectedCatalogId();
      const card = document.querySelector(`.plugintema-catalog-card[data-plugintema-catalog-id="${CSS.escape(catalogId)}"]`);
      if (!catalogId || !card) return;
      runRefresh(catalogId, button, card, false);
    });
  }

  function decorate() {
    ensureStyle();
    decorateCards();
    ensureToolbarButton();
  }

  const observer = new MutationObserver(decorate);
  observer.observe(document.documentElement, {subtree: true, childList: true});
  document.addEventListener("DOMContentLoaded", decorate, {once: true});
  window.setTimeout(decorate, 100);
})();
