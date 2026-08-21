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
    const additions = byId("tab_panel_adicoes");
    const updates = byId("tab_panel_atualizacoes");
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

    const updateButton = byId("tab_btn_atualizacoes");
    const additionButton = byId("tab_btn_adicoes");
    updateButton?.addEventListener("click", schedulePlacement);
    additionButton?.addEventListener("click", schedulePlacement);

    const updatePanel = byId("tab_panel_atualizacoes");
    const additionPanel = byId("tab_panel_adicoes");
    const observer = new MutationObserver(placeEnvironment);
    [updatePanel, additionPanel].forEach(panel => {
      if (panel) observer.observe(panel, {attributes: true, attributeFilter: ["class"]});
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();
