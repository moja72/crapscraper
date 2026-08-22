(() => {
  "use strict";
  if (window.__crapScraperSharedEnvironmentPanelInstalled) return;
  window.__crapScraperSharedEnvironmentPanelInstalled = true;

  const byId = id => document.getElementById(id);
  let placementFrame = 0;

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
    placementFrame = 0;
    const card = environmentCard();
    const target = targetPanel();
    if (!card || !target) return;

    card.classList.add("shared-environment-card");
    if (target.firstElementChild !== card) {
      target.insertBefore(card, target.firstElementChild);
    }
  }

  function schedulePlacement() {
    if (placementFrame) cancelAnimationFrame(placementFrame);
    placementFrame = requestAnimationFrame(placeEnvironment);
  }

  function start() {
    placeEnvironment();

    // A troca de aba e uma acao explicita. Nao precisamos observar continuamente
    // mudancas de classe e realimentar o DOM a cada alteracao feita por outras UIs.
    ["tab_btn_atualizacoes", "tab_btn_adicoes", "tab_btn_loja"].forEach(id => {
      byId(id)?.addEventListener("click", schedulePlacement);
    });

    // Permite que futuras trocas programaticas avisem o portal sem MutationObserver.
    document.addEventListener("crapscraper:main-tab-changed", schedulePlacement);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }
})();
