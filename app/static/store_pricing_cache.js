(function () {
  "use strict";

  const PLAN_HTML_KEY = "crapscraper:store-pricing-html:v1";
  const PACK_HTML_KEY = "crapscraper:store-pack-html:v1";
  const endpoint = "/loja/precos/cache/atualizar";
  const statusEndpoint = "/loja/precos/cache/status";
  let allowPackReload = false;

  const byId = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function selectedKinds() {
    return Array.from(document.querySelectorAll('input[name="store_kind"]:checked'))
      .map((node) => String(node.value || "").trim())
      .filter((value) => value === "plugin" || value === "theme");
  }

  async function json(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
    return data;
  }

  function saveHtml(root, key, kind) {
    if (!root || root.getAttribute("aria-busy") === "true") return;
    const html = root.innerHTML || "";
    if (!html || /inline-loading-spinner|updates-error/.test(html)) return;
    if (kind === "plans" && !root.querySelector(".store-kind-price-grid")) return;
    if (kind === "packs" && !root.querySelector("[data-store-pack-id]") && !/Nenhum produto pacote/.test(html)) return;
    try {
      localStorage.setItem(key, JSON.stringify({ saved_at: new Date().toISOString(), html }));
    } catch (_error) {}
  }

  function restoreHtml(root, key) {
    if (!root) return false;
    try {
      const cached = JSON.parse(localStorage.getItem(key) || "null");
      if (!cached?.html) return false;
      root.innerHTML = cached.html;
      root.setAttribute("aria-busy", "false");
      return true;
    } catch (_error) {
      return false;
    }
  }

  function observeSavedHtml() {
    const plans = byId("store_preview");
    const packs = byId("store_pack_prices");
    if (plans) {
      restoreHtml(plans, PLAN_HTML_KEY);
      new MutationObserver(() => saveHtml(plans, PLAN_HTML_KEY, "plans"))
        .observe(plans, { childList: true, subtree: true, attributes: true });
    }
    if (packs) {
      restoreHtml(packs, PACK_HTML_KEY);
      new MutationObserver(() => saveHtml(packs, PACK_HTML_KEY, "packs"))
        .observe(packs, { childList: true, subtree: true, attributes: true });
    }
  }

  function formatCacheTime(value) {
    if (!value) return "Ainda não salvo";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Salvo localmente" : `Salvo em ${date.toLocaleString("pt-BR")}`;
  }

  function ensurePlanRefreshUi() {
    const preview = byId("store_preview");
    if (!preview || byId("store_plan_refresh")) return;
    const toolbar = document.createElement("div");
    toolbar.className = "store-section-head store-pricing-cache-toolbar";
    toolbar.innerHTML = '<div><strong>Valores atuais dos planos</strong><div class="small" id="store_plan_cache_meta">Carregando dados salvos...</div></div><button class="btn-secondary btn-sm" id="store_plan_refresh" type="button">Atualizar preços</button>';
    preview.parentNode?.insertBefore(toolbar, preview);
    byId("store_plan_refresh")?.addEventListener("click", () => refreshRemote("plans"));
  }

  function ensurePackMeta() {
    const button = byId("store_pack_refresh");
    if (!button) return;
    button.textContent = "Atualizar preços";
    const head = button.closest(".store-section-head");
    if (head && !byId("store_pack_cache_meta")) {
      const meta = document.createElement("div");
      meta.id = "store_pack_cache_meta";
      meta.className = "small";
      meta.textContent = "Carregando dados salvos...";
      button.parentNode?.insertBefore(meta, button);
    }
    button.addEventListener("click", (event) => {
      if (allowPackReload) {
        allowPackReload = false;
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      refreshRemote("packs");
    }, true);
  }

  async function cacheMeta(target) {
    const kinds = selectedKinds();
    const params = new URLSearchParams({ target });
    if (target === "plans") kinds.forEach((kind) => params.append("tipo", kind));
    try {
      const data = await json(`${statusEndpoint}?${params}`);
      const node = byId(target === "plans" ? "store_plan_cache_meta" : "store_pack_cache_meta");
      if (node) node.textContent = data.cached ? formatCacheTime(data.cache?.cached_at) : "Ainda não há dados salvos";
      return !!data.cached;
    } catch (_error) {
      return false;
    }
  }

  async function pollJob(jobId, target, button) {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      await sleep(800);
      const data = await json(`${statusEndpoint}?job_id=${encodeURIComponent(jobId)}`);
      if (button) button.textContent = data.message || "Atualizando...";
      if (data.status === "completed") return data;
      if (data.status === "error") throw new Error(data.message || "Falha ao atualizar preços.");
    }
    throw new Error("A atualização ultrapassou o tempo esperado.");
  }

  function reloadFromServer(target) {
    if (target === "plans") {
      const first = document.querySelector('input[name="store_kind"]:checked') || document.querySelector('input[name="store_kind"]');
      first?.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    const button = byId("store_pack_refresh");
    if (button) {
      allowPackReload = true;
      button.click();
    }
  }

  async function refreshRemote(target) {
    const button = byId(target === "plans" ? "store_plan_refresh" : "store_pack_refresh");
    const original = button?.textContent || "Atualizar preços";
    if (button) {
      button.disabled = true;
      button.textContent = "Atualizando...";
    }
    try {
      const started = await json(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, kinds: target === "plans" ? selectedKinds() : [] }),
      });
      await pollJob(started.job_id, target, button);
      reloadFromServer(target);
      await sleep(250);
      await cacheMeta(target);
    } catch (error) {
      const meta = byId(target === "plans" ? "store_plan_cache_meta" : "store_pack_cache_meta");
      if (meta) meta.textContent = `Falha ao atualizar: ${error.message || error}`;
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = original.includes("Atualizar") ? original : "Atualizar preços";
      }
    }
  }

  function restoreWhileOpeningStore() {
    const button = byId("tab_btn_loja");
    if (!button) return;
    button.addEventListener("click", () => {
      setTimeout(() => {
        const plans = byId("store_preview");
        const packs = byId("store_pack_prices");
        if (plans?.getAttribute("aria-busy") === "true") restoreHtml(plans, PLAN_HTML_KEY);
        if (packs?.getAttribute("aria-busy") === "true") restoreHtml(packs, PACK_HTML_KEY);
        cacheMeta("plans");
        cacheMeta("packs");
      }, 40);
    }, true);
  }

  function watchFirstWarmup() {
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      const planReady = await cacheMeta("plans");
      const packReady = await cacheMeta("packs");
      if (planReady) reloadFromServer("plans");
      if (packReady) reloadFromServer("packs");
      if ((planReady && packReady) || attempts >= 20) clearInterval(timer);
    }, 2000);
  }

  function init() {
    observeSavedHtml();
    ensurePlanRefreshUi();
    ensurePackMeta();
    restoreWhileOpeningStore();
    cacheMeta("plans");
    cacheMeta("packs");
    watchFirstWarmup();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
})();
