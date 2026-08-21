(() => {
  "use strict";
  if (window.__crapScraperSharedEnvironmentPanelInstalled) return;
  window.__crapScraperSharedEnvironmentPanelInstalled = true;

  const byId = id => document.getElementById(id);

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

  function placeEnvironment() {
    const card = environmentCard();
    const target = targetPanel();
    if (!card || !target) return;

    card.classList.add("shared-environment-card");
    if (target.firstElementChild !== card) {
      target.insertBefore(card, target.firstElementChild);
    }
  }

  function schedulePlacement() {
    window.requestAnimationFrame(placeEnvironment);
  }

  function start() {
    placeEnvironment();

    ["tab_btn_atualizacoes", "tab_btn_adicoes", "tab_btn_loja"].forEach(id => {
      byId(id)?.addEventListener("click", schedulePlacement);
    });

    const observer = new MutationObserver(placeEnvironment);
    ["tab_panel_atualizacoes", "tab_panel_adicoes", "tab_panel_loja"].forEach(id => {
      const panel = byId(id);
      if (panel) observer.observe(panel, {attributes: true, attributeFilter: ["class"]});
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();
