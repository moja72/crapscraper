(() => {
  "use strict";
  if (window.__crapScraperSharedEnvironmentPanelInstalled) return;
  window.__crapScraperSharedEnvironmentPanelInstalled = true;

  const byId = id => document.getElementById(id);
  const REFRESH_COOLDOWN_MS = 15000;
  let placementFrame = 0;
  let summaryFrame = 0;
  let refreshTimer = 0;
  let lastRefreshRequestAt = 0;

  function normalize(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function environmentCard() {
    return document.querySelector(".updates-environment-card");
  }

  function panelVisible(panel) {
    return !!panel && !panel.classList.contains("hidden");
  }

  function targetPanel() {
    const store = byId("tab_panel_loja");
    const additions = byId("tab_panel_adicoes");
    const updates = byId("tab_panel_atualizacoes");
    if (panelVisible(store)) return store;
    if (panelVisible(additions)) return additions;
    return updates;
  }

  function headerSummaryNode() {
    return environmentCard()?.querySelector(
      ":scope > .standard-update-accordion-toggle .standard-update-accordion-meta"
    ) || null;
  }

  function setSummaryText(value) {
    const next = normalize(value);
    [byId("updates_environment_summary"), headerSummaryNode()].forEach(node => {
      if (node && normalize(node.textContent) !== next) node.textContent = next;
    });
  }

  function cookieState() {
    const node = byId("plugintheme_cookie_status");
    if (!node) return {known: false, blocked: false};

    const value = normalize(node.textContent).toLowerCase();
    if (!value || value.includes("verificando")) return {known: false, blocked: false};

    const blockedByText = [
      "não validada", "nao validada", "ausente", "pendente",
      "expirada", "expirado", "inválida", "invalida", "inválido", "invalido",
    ].some(token => value.includes(token));

    if (blockedByText) return {known: true, blocked: true};
    if (node.classList.contains("is-blocked")) return {known: true, blocked: true};
    if (node.classList.contains("is-ok")) return {known: true, blocked: false};
    return {known: false, blocked: false};
  }

  function syncEnvironmentSummary() {
    summaryFrame = 0;
    const chips = Array.from(document.querySelectorAll("#updates_environment_chips .environment-chip"));
    const cookie = cookieState();

    if (!chips.length || !cookie.known) {
      setSummaryText("Verificando pré-requisitos...");
      return;
    }

    const blockedChips = chips.filter(node => node.classList.contains("is-blocked")).length;
    const blockedTotal = blockedChips + (cookie.blocked ? 1 : 0);
    if (!blockedTotal) {
      setSummaryText("Todos os pré-requisitos estão OK");
      return;
    }

    setSummaryText(
      blockedTotal === 1
        ? "1 requisito exige atenção"
        : `${blockedTotal} requisitos exigem atenção`
    );
  }

  function scheduleSummarySync() {
    if (summaryFrame) cancelAnimationFrame(summaryFrame);
    summaryFrame = requestAnimationFrame(syncEnvironmentSummary);
  }

  function environmentStatusPending() {
    const chips = byId("updates_environment_chips");
    const summary = normalize(byId("updates_environment_summary")?.textContent).toLowerCase();
    const cookie = normalize(byId("plugintheme_cookie_status")?.textContent).toLowerCase();
    return !chips?.children.length || summary.includes("verificando") || cookie.includes("verificando");
  }

  function requestEnvironmentRefresh(force = false) {
    const button = byId("updates_prerequisites_btn");
    if (!button || button.disabled) return false;

    const now = Date.now();
    if (!force && !environmentStatusPending() && now - lastRefreshRequestAt < REFRESH_COOLDOWN_MS) {
      return false;
    }

    lastRefreshRequestAt = now;
    button.click();
    return true;
  }

  function scheduleEnvironmentRefresh(force = false) {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => requestEnvironmentRefresh(force), 0);
  }

  function warmEnvironment() {
    // O listener do painel principal pode ser registrado no mesmo DOMContentLoaded.
    // Pequenas tentativas evitam deixar a aba Adicionar presa no placeholder se a
    // primeira chamada ocorrer antes de o botão receber seu handler.
    [0, 80, 240, 700].forEach((delay, index) => {
      window.setTimeout(() => {
        if (environmentStatusPending()) requestEnvironmentRefresh(index > 0);
      }, delay);
    });
  }

  function observeEnvironment() {
    const card = environmentCard();
    if (!card || card.dataset.sharedEnvironmentObserved === "1") return;
    card.dataset.sharedEnvironmentObserved = "1";

    const observer = new MutationObserver(scheduleSummarySync);
    observer.observe(card, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  function placeEnvironment() {
    placementFrame = 0;
    const card = environmentCard();
    const target = targetPanel();
    if (!card || !target) return;

    card.classList.add("shared-environment-card");
    if (target.firstElementChild !== card) {
      target.insertBefore(card, target.firstElementChild);
    }

    observeEnvironment();
    scheduleSummarySync();
    scheduleEnvironmentRefresh(false);
  }

  function schedulePlacement() {
    if (placementFrame) cancelAnimationFrame(placementFrame);
    placementFrame = requestAnimationFrame(placeEnvironment);
  }

  function handleOperationalTabChange() {
    schedulePlacement();
    scheduleEnvironmentRefresh(false);
  }

  function start() {
    placeEnvironment();
    observeEnvironment();
    scheduleSummarySync();
    warmEnvironment();

    // Ambiente é um componente único compartilhado pelas três abas. Toda entrada
    // em Atualizar, Adicionar ou Loja deve usar o mesmo diagnóstico já aquecido e,
    // quando necessário, pedir revalidação sem depender do handler de Atualizar.
    ["tab_btn_atualizacoes", "tab_btn_adicoes", "tab_btn_loja"].forEach(id => {
      byId(id)?.addEventListener("click", handleOperationalTabChange);
    });

    document.addEventListener("crapscraper:main-tab-changed", handleOperationalTabChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();
