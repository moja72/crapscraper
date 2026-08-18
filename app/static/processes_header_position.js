(() => {
  "use strict";

  const HEADER_TEXT = "Coletar • Comparar • Atualizar • Adicionar • Loja";
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function findHeaderTextNode() {
    const matches = Array.from(document.body?.querySelectorAll("*") || [])
      .filter(node => !["SCRIPT", "STYLE", "BUTTON"].includes(node.tagName))
      .filter(node => normalize(node.textContent) === HEADER_TEXT);
    if (!matches.length) return null;
    matches.sort((a, b) => a.querySelectorAll("*").length - b.querySelectorAll("*").length);
    return matches[0];
  }

  function moveProcessesButton() {
    const button = document.getElementById("cs_processes_button");
    const target = findHeaderTextNode();
    if (!button || !target) return false;
    if (button.parentElement === target) return true;

    target.replaceChildren(button);
    return true;
  }

  function scheduleMove() {
    [0, 60, 180, 450, 900, 1800].forEach(delay => setTimeout(moveProcessesButton, delay));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleMove, {once: true});
  } else {
    scheduleMove();
  }
  window.addEventListener("load", scheduleMove, {once: true});
})();
