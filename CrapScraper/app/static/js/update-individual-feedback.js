const $ = (selector, root = document) => root.querySelector(selector);
const pending = new Set();

function productName(button) {
  const card = button.closest("[data-update-card], .update-card, [data-job-id], .update-queue-item, .update-job-card");
  const heading = card?.querySelector("h3, h4, .update-product-name, .update-job-main > strong, strong");
  return String(heading?.textContent || "produto selecionado").trim();
}

function ensureStyles() {
  if ($("#update-individual-loading-style")) return;
  const style = document.createElement("style");
  style.id = "update-individual-loading-style";
  style.textContent = `
    [data-update-execute][data-update-submitting="1"]{pointer-events:none;opacity:.88;cursor:wait;display:inline-flex;align-items:center;justify-content:center;gap:7px}
    .update-inline-spinner{width:13px;height:13px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;display:inline-block;animation:update-inline-spin .7s linear infinite;flex:0 0 auto}
    @keyframes update-inline-spin{to{transform:rotate(360deg)}}
  `;
  document.head.appendChild(style);
}

function loadingMarkup() {
  return '<span class="update-inline-spinner" aria-hidden="true"></span><span>Executando...</span>';
}

function lock(button) {
  if (!button || button.dataset.updateSubmitting === "1") return false;
  button.dataset.updateSubmitting = "1";
  button.dataset.updateSubmitStarted = String(Date.now());
  button.dataset.updateOriginalLabel = button.textContent || "Executar";
  button.setAttribute("aria-busy", "true");
  button.innerHTML = loadingMarkup();
  pending.add(button);

  const band = $("#update-operation-status");
  if (band) {
    band.textContent = `Executando ${productName(button)}...`;
    band.className = "operation-band loading";
  }

  // Não marque disabled durante a captura: update.js ainda precisa receber este
  // primeiro clique. No próximo task o botão já fica bloqueado contra repetição.
  setTimeout(() => {
    if (button.isConnected && button.dataset.updateSubmitting === "1") button.disabled = true;
  }, 0);
  return true;
}

function unlock(button) {
  if (!button?.isConnected || button.dataset.updateSubmitting !== "1") return;
  const state = button.closest(".update-job-card")?.querySelector(".status-chip")?.dataset.status || "";
  if (["running", "success", "queued"].includes(state)) return;
  button.disabled = false;
  button.removeAttribute("aria-busy");
  button.textContent = button.dataset.updateOriginalLabel || "Executar";
  delete button.dataset.updateSubmitting;
  delete button.dataset.updateSubmitStarted;
  delete button.dataset.updateOriginalLabel;
  pending.delete(button);
}

ensureStyles();

document.addEventListener("click", event => {
  const button = event.target.closest?.("[data-update-execute]");
  if (!button) return;
  if (button.dataset.updateSubmitting === "1") {
    event.preventDefault();
    event.stopImmediatePropagation();
    return;
  }
  if (button.disabled) return;
  lock(button);
}, true);

const operation = $("#update-operation-status");
if (operation) {
  new MutationObserver(() => {
    const text = String(operation.textContent || "").toLowerCase();
    if (!operation.classList.contains("error") && !/\b(erro|falha|bloquead)/i.test(text)) return;
    setTimeout(() => [...pending].forEach(unlock), 250);
  }).observe(operation, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"]});
}

// Falha de rede silenciosa não pode deixar um botão órfão bloqueado para sempre.
setInterval(() => {
  for (const button of [...pending]) {
    if (!button.isConnected) {
      pending.delete(button);
      continue;
    }
    const state = button.closest(".update-job-card")?.querySelector(".status-chip")?.dataset.status || "";
    const started = Number(button.dataset.updateSubmitStarted || 0);
    if (["ready", "error"].includes(state) && started && Date.now() - started > 120000) unlock(button);
  }
}, 5000);
