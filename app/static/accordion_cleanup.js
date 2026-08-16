(() => {
  "use strict";

  const STYLE_ID = "crapscraper-accordion-cleanup-style";
  const existingStyle = document.getElementById(STYLE_ID);
  if (existingStyle) existingStyle.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Resumo da comparação: apenas um triângulo, sem marcador nativo nem +/- legado. */
    #comparison_summary_card > .comparison-summary-header::-webkit-details-marker{
      display:none!important;
    }
    #comparison_summary_card > .comparison-summary-header::marker{
      content:""!important;
      display:none!important;
    }
    #comparison_summary_card .comparison-summary-toggle{
      font-size:13px!important;
      line-height:1!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
    }
    #comparison_summary_card .comparison-summary-toggle::before,
    #comparison_summary_card .comparison-summary-toggle::after{
      content:none!important;
      display:none!important;
    }

    /* Ambiente: o resumo aparece somente no cabeçalho da sanfona. */
    #updates_environment_summary,
    .standard-update-environment-inline-meta{
      display:none!important;
    }

    /* Fila: o resumo operacional permanece apenas dentro do conteúdo da sanfona. */
    .standard-update-accordion-card[data-update-accordion-kind="queue"]
      > .standard-update-accordion-toggle .standard-update-accordion-meta{
      display:none!important;
    }

    /* Carregamento da aba Atualizar: skeleton + cache visual do último estado válido. */
    #tab_panel_atualizacoes .cs-update-skeleton{
      position:relative!important;
      overflow:hidden!important;
      min-width:72px!important;
      min-height:14px!important;
      border-radius:7px!important;
      color:transparent!important;
      text-shadow:none!important;
      background:rgba(255,255,255,.055)!important;
      user-select:none!important;
    }
    #tab_panel_atualizacoes .cs-update-skeleton::after{
      content:""!important;
      position:absolute!important;
      inset:0!important;
      transform:translateX(-100%);
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.11),transparent)!important;
      animation:csUpdateSkeletonSweep 1.15s ease-in-out infinite!important;
      pointer-events:none!important;
    }
    #tab_panel_atualizacoes .cs-update-cached{
      transition:opacity .18s ease!important;
      opacity:.88!important;
    }
    #tab_panel_atualizacoes .cs-update-refresh-indicator{
      display:inline-flex!important;
      align-items:center!important;
      gap:8px!important;
      margin-left:12px!important;
      color:var(--text-muted)!important;
      font-size:12px!important;
      line-height:1!important;
      opacity:.85!important;
    }
    #tab_panel_atualizacoes .cs-update-refresh-indicator::before{
      content:"";
      width:10px;
      height:10px;
      border:2px solid rgba(255,255,255,.18);
      border-top-color:var(--accent,#7c3aed);
      border-radius:50%;
      animation:csUpdateSpinner .8s linear infinite;
    }
    @keyframes csUpdateSkeletonSweep{100%{transform:translateX(100%);}}
    @keyframes csUpdateSpinner{to{transform:rotate(360deg);}}
    @media (prefers-reduced-motion:reduce){
      #tab_panel_atualizacoes .cs-update-skeleton::after,
      #tab_panel_atualizacoes .cs-update-refresh-indicator::before{animation:none!important;}
    }
  `;
  document.head.appendChild(style);

  function normalizeComparisonSummary() {
    const card = document.getElementById("comparison_summary_card");
    if (!card) return;

    const toggle = card.querySelector(".comparison-summary-toggle");
    if (!toggle) return;

    if (toggle.textContent !== "▸") toggle.textContent = "▸";
    toggle.setAttribute("aria-label", "Alternar resumo da comparação");
  }

  function getEnvironmentCard() {
    return (
      document.querySelector('#tab_panel_atualizacoes .card[data-update-accordion-kind="environment"]') ||
      document.getElementById("updates_environment_details")?.closest(".card") ||
      null
    );
  }

  function hideEnvironmentDuplicateMeta() {
    const summary = document.getElementById("updates_environment_summary");
    if (summary) summary.classList.add("standard-update-environment-inline-meta");

    const card = getEnvironmentCard();
    if (!card) return;

    const candidates = [...card.querySelectorAll(".small, div, span, p")];
    for (const node of candidates) {
      if (node.closest(".standard-update-accordion-toggle")) continue;
      const text = String(node.textContent || "").replace(/\s+/g, " ").trim();
      if (!/^\d+\s+requisito\(s\)\s+exigem\s+atenção$/i.test(text)) continue;
      node.classList.add("standard-update-environment-inline-meta");
    }
  }

  function collapseQueueByDefault() {
    const card =
      document.querySelector('#tab_panel_atualizacoes .card[data-update-accordion-kind="queue"]') ||
      document.getElementById("updates_queue_meta")?.closest(".card") ||
      null;

    if (!card || card.dataset.queueDefaultCollapsedApplied === "1") return;
    const toggle = card.querySelector(":scope > .standard-update-accordion-toggle");
    if (!toggle) return;

    card.dataset.queueDefaultCollapsedApplied = "1";
    card.classList.add("is-collapsed");
    toggle.setAttribute("aria-expanded", "false");
  }

  const UPDATE_CACHE_KEY = "crapscraper:update-ui-cache:v1";
  const UPDATE_CACHE_MAX_AGE = 24 * 60 * 60 * 1000;
  const transientPattern = /^(?:0%|0\s+de\s+0\s+processados|verificando(?:\s+pré-requisitos)?\.{0,3}|carregando\.{0,3}|abra\s+a\s+aba\b|nenhuma\s+atualização\s+em\s+execução|nenhum\s+progresso\s+registrado|conteúdo\s+recolhido)$/i;
  let updateCacheApplied = false;
  let updateCacheWriteTimer = null;

  function getUpdatesPanel() {
    return document.getElementById("tab_panel_atualizacoes");
  }

  function normalizeText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function isTransientText(value) {
    const text = normalizeText(value);
    return !text || transientPattern.test(text);
  }

  function readUpdateCache() {
    try {
      const parsed = JSON.parse(localStorage.getItem(UPDATE_CACHE_KEY) || "null");
      if (!parsed || !parsed.savedAt || Date.now() - Number(parsed.savedAt) > UPDATE_CACHE_MAX_AGE) return null;
      return parsed;
    } catch (_) {
      return null;
    }
  }

  function snapshotUpdateLeaves(panel) {
    const values = {};
    panel.querySelectorAll("[id]").forEach(node => {
      if (!(node instanceof HTMLElement)) return;
      if (node.childElementCount !== 0) return;
      if (["INPUT", "SELECT", "TEXTAREA", "BUTTON", "OPTION", "SCRIPT", "STYLE"].includes(node.tagName)) return;
      const text = normalizeText(node.textContent);
      if (!text || text.length > 240 || isTransientText(text)) return;
      values[node.id] = text;
    });

    const accordions = {};
    panel.querySelectorAll('.standard-update-accordion-card[data-update-accordion-kind]').forEach(card => {
      const kind = card.dataset.updateAccordionKind;
      if (kind) accordions[kind] = !card.classList.contains("is-collapsed");
    });

    return {savedAt:Date.now(), values, accordions};
  }

  function writeUpdateCache() {
    const panel = getUpdatesPanel();
    if (!panel) return;
    const snapshot = snapshotUpdateLeaves(panel);
    if (Object.keys(snapshot.values).length < 3) return;
    try {
      localStorage.setItem(UPDATE_CACHE_KEY, JSON.stringify(snapshot));
    } catch (_) {
      /* Cache é apenas uma melhoria de UX. */
    }
  }

  function scheduleUpdateCacheWrite() {
    window.clearTimeout(updateCacheWriteTimer);
    updateCacheWriteTimer = window.setTimeout(writeUpdateCache, 900);
  }

  function restoreAccordionState(panel, cache) {
    const states = cache?.accordions || {};
    panel.querySelectorAll('.standard-update-accordion-card[data-update-accordion-kind]').forEach(card => {
      const kind = card.dataset.updateAccordionKind;
      if (!(kind in states)) return;
      const open = Boolean(states[kind]);
      card.classList.toggle("is-collapsed", !open);
      card.querySelector(":scope > .standard-update-accordion-toggle")?.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  function markUpdateSkeletons(panel) {
    panel.querySelectorAll("[id]").forEach(node => {
      if (!(node instanceof HTMLElement) || node.childElementCount !== 0) return;
      if (["BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(node.tagName)) return;
      if (node.classList.contains("cs-update-cached")) return;
      if (isTransientText(node.textContent)) node.classList.add("cs-update-skeleton");
    });
  }

  function clearUpdateSkeletons(panel) {
    panel.querySelectorAll(".cs-update-skeleton").forEach(node => node.classList.remove("cs-update-skeleton"));
  }

  function installRefreshIndicator(panel, hasCache) {
    if (panel.querySelector(".cs-update-refresh-indicator")) return;
    const heading = [...panel.querySelectorAll(".section-title, h2, h3")].find(node => /atualiza/i.test(normalizeText(node.textContent)));
    if (!heading?.parentElement) return;
    const indicator = document.createElement("span");
    indicator.className = "cs-update-refresh-indicator";
    indicator.textContent = hasCache ? "Atualizando dados em segundo plano" : "Carregando dados";
    indicator.setAttribute("aria-live", "polite");
    heading.parentElement.appendChild(indicator);
  }

  function removeRefreshIndicator(panel) {
    panel.querySelector(".cs-update-refresh-indicator")?.remove();
  }

  function applyCachedUpdateState() {
    if (updateCacheApplied) return;
    const panel = getUpdatesPanel();
    if (!panel) return;
    updateCacheApplied = true;

    const cache = readUpdateCache();
    if (cache) {
      restoreAccordionState(panel, cache);
      Object.entries(cache.values || {}).forEach(([id, cachedText]) => {
        const node = document.getElementById(id);
        if (!node || !panel.contains(node) || node.childElementCount !== 0) return;
        const current = normalizeText(node.textContent);
        if (!isTransientText(current)) return;
        node.dataset.csUpdateOriginal = current;
        node.dataset.csUpdateCachedText = String(cachedText);
        node.textContent = String(cachedText);
        node.classList.add("cs-update-cached");
      });
    }

    markUpdateSkeletons(panel);
    installRefreshIndicator(panel, Boolean(cache));

    window.setTimeout(() => {
      panel.querySelectorAll(".cs-update-cached").forEach(node => {
        if (normalizeText(node.textContent) === normalizeText(node.dataset.csUpdateCachedText)) {
          node.textContent = node.dataset.csUpdateOriginal || "";
        }
        node.classList.remove("cs-update-cached");
        delete node.dataset.csUpdateOriginal;
        delete node.dataset.csUpdateCachedText;
      });
      clearUpdateSkeletons(panel);
      removeRefreshIndicator(panel);
    }, 8000);
  }

  function reconcileCachedNodes(panel) {
    panel.querySelectorAll(".cs-update-cached").forEach(node => {
      const cached = normalizeText(node.dataset.csUpdateCachedText);
      if (normalizeText(node.textContent) !== cached) {
        node.classList.remove("cs-update-cached");
        delete node.dataset.csUpdateOriginal;
        delete node.dataset.csUpdateCachedText;
      }
    });

    panel.querySelectorAll(".cs-update-skeleton").forEach(node => {
      if (!isTransientText(node.textContent)) node.classList.remove("cs-update-skeleton");
    });

    const stillLoading = [...panel.querySelectorAll("[id]")].some(node =>
      node instanceof HTMLElement && node.childElementCount === 0 && /^(?:verificando|carregando)/i.test(normalizeText(node.textContent))
    );
    if (!stillLoading) removeRefreshIndicator(panel);
  }

  function bindAccordionCache(panel) {
    if (panel.dataset.csAccordionCacheBound === "1") return;
    panel.dataset.csAccordionCacheBound = "1";
    panel.addEventListener("click", event => {
      const toggle = event.target.closest?.(".standard-update-accordion-toggle");
      if (!toggle || !panel.contains(toggle)) return;
      window.setTimeout(scheduleUpdateCacheWrite, 80);
    });
  }

  function enhanceUpdateLoading() {
    const panel = getUpdatesPanel();
    if (!panel) return;
    applyCachedUpdateState();
    bindAccordionCache(panel);
    reconcileCachedNodes(panel);
    scheduleUpdateCacheWrite();
  }

  function refine() {
    normalizeComparisonSummary();
    hideEnvironmentDuplicateMeta();
    collapseQueueByDefault();
    enhanceUpdateLoading();
  }

  refine();

  let timer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(refine, 70);
  });
  observer.observe(document.body, {childList:true, subtree:true, characterData:true});
})();
