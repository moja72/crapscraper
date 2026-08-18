(() => {
  "use strict";

  const clean = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  function findButton(label) {
    return [...document.querySelectorAll("button")].find(
      (button) => clean(button.textContent).toLowerCase() === label.toLowerCase()
    ) || null;
  }

  function findComparisonCard() {
    const source = document.getElementById("comparison_source_catalog");
    const target = document.getElementById("comparison_target_catalog");
    if (!source || !target) return null;
    const candidates = [...document.querySelectorAll(".card")];
    return candidates.find((card) => card.contains(source) && card.contains(target)) || source.closest(".card");
  }

  function install() {
    const card = findComparisonCard();
    const compareButton = findButton("Comparar agora");
    const refreshButton = findButton("Atualizar lista");
    if (!card || !compareButton || !refreshButton) return false;

    let actions = document.getElementById("comparison_catalog_actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.id = "comparison_catalog_actions";
      actions.className = "comparison-catalog-actions";

      const filesBox = [...card.children].find((node) =>
        clean(node.textContent).startsWith("Arquivos carregados:")
      );
      if (filesBox) filesBox.insertAdjacentElement("afterend", actions);
      else card.appendChild(actions);
    }

    compareButton.classList.add("comparison-catalog-action-primary");
    refreshButton.classList.add("comparison-catalog-action-secondary");
    actions.append(compareButton, refreshButton);
    return true;
  }

  function start() {
    if (install()) return;
    const observer = new MutationObserver(() => {
      if (install()) observer.disconnect();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
