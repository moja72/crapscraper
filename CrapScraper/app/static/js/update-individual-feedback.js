const $ = (selector, root = document) => root.querySelector(selector);

function productName(button) {
  const card = button.closest("[data-update-card], .update-card, [data-job-id], .update-queue-item");
  const heading = card?.querySelector("h3, h4, strong, .update-product-name");
  return String(heading?.textContent || "produto selecionado").trim();
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-update-execute]");
  if (!button || button.disabled) return;

  const startedAt = Date.now();
  const band = $("#update-operation-status");
  if (band) {
    band.textContent = `Preparando ${productName(button)} para execução individual…`;
    band.className = "operation-band info";
  }

  // update.js continua sendo o único proprietário da chamada execute/retry.
  // Esta camada só preserva o feedback de preflight por um instante; não toca
  // em seleção, lote, pausa, cancelamento ou no contrato transacional.
  const observer = new MutationObserver(() => {
    if (!button.isConnected || Date.now() - startedAt >= 650) return;
    if (button.textContent !== "Preparando…") button.textContent = "Preparando…";
  });

  try {
    observer.observe(button, {childList: true, subtree: true, characterData: true});
  } catch (_) {}
  button.textContent = "Preparando…";

  window.setTimeout(() => {
    observer.disconnect();
    if (button.isConnected && button.disabled) button.textContent = "Executando…";
  }, 650);
}, true);
