(() => {
  "use strict";

  const STYLE_ID = "crapscraper-catalog-cards-refinement";
  document.getElementById(STYLE_ID)?.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .catalogos-top-controls-row{
      display:grid!important;
      grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;
      align-items:end!important;
      gap:14px!important;
      width:100%!important;
      max-width:none!important;
      flex:1 1 100%!important;
    }
    .catalogos-top-controls-row > .field{
      min-width:0!important;
      width:100%!important;
      max-width:none!important;
    }
    .catalogos-top-controls-row .catalogos-refresh-field .row{
      width:100%!important;
    }
    .catalogos-top-controls-row .catalogos-refresh-field button{
      width:100%!important;
      min-height:46px!important;
    }

    .catalogo-summary-card .catalogo-card-actions{
      display:flex!important;
      align-items:center!important;
      justify-content:flex-end!important;
      flex-wrap:nowrap!important;
      gap:8px!important;
      overflow:visible!important;
      max-width:none!important;
    }
    .catalogo-summary-card .catalogo-status-row{
      display:flex!important;
      align-items:center!important;
      flex-wrap:nowrap!important;
      gap:12px!important;
      min-height:24px!important;
      height:24px!important;
      margin:6px 0 8px!important;
      overflow:hidden!important;
    }
    .catalogo-summary-card .catalogo-status-item{
      display:inline-flex!important;
      align-items:center!important;
      gap:4px!important;
      white-space:nowrap!important;
    }

    .catalogo-summary-card .catalogo-availability{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      min-height:34px!important;
    }
    .catalogo-summary-card .catalogo-availability-icon.is-unavailable{
      opacity:.12!important;
      filter:grayscale(1) saturate(0)!important;
    }

    .catalogo-card-actions .catalogo-download-button{
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
    }

    #updates_queue_checkpoint{
      display:flex!important;
      align-items:center!important;
      align-self:center!important;
      min-height:48px!important;
      margin:0!important;
      line-height:1.35!important;
    }

    @media(max-width:760px){
      .catalogos-top-controls-row{
        grid-template-columns:1fr!important;
      }
      .catalogo-summary-card .catalogo-status-row{
        flex-wrap:wrap!important;
        height:auto!important;
        min-height:24px!important;
      }
    }
  `;
  document.head.appendChild(style);

  const text = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  function ensureTopControlsRow() {
    const select = document.getElementById("catalogos_filter_slot");
    const selectField = select?.closest(".field");
    const actionField = document.querySelector(".catalogos-refresh-field")
      || [...document.querySelectorAll(".field")].find(field => /^Ações$/i.test(text(field.querySelector("label")?.textContent)) && field.querySelector("#catalogos_refresh_btn,button"));
    if (!selectField || !actionField) return;

    const container = selectField.closest(".form-grid") || selectField.parentElement;
    if (!container) return;
    if (actionField.parentElement !== container) container.appendChild(actionField);

    container.classList.add("catalogos-top-controls-row");
    container.style.setProperty("display", "grid", "important");
    container.style.setProperty("grid-template-columns", "minmax(0,1fr) minmax(0,1fr)", "important");
    container.style.setProperty("align-items", "end", "important");
    container.style.setProperty("gap", "14px", "important");
    container.style.setProperty("width", "100%", "important");
    container.style.setProperty("max-width", "none", "important");
  }

  function slotNameFromCard(card) {
    const loadButton = card?.querySelector(".catalogo-load-button");
    const source = String(loadButton?.getAttribute("onclick") || "");
    const match = source.match(/loadCatalogo\((.+)\)/);
    if (match) {
      try { return String(JSON.parse(match[1]) || "").trim(); } catch (_) {}
    }
    const aria = String(loadButton?.getAttribute("aria-label") || "");
    const fromAria = aria.replace(/^Carregar catálogo\s+/i, "").trim();
    if (fromAria) return fromAria;
    const heading = card?.querySelector(".section-title,h3,h4,strong");
    const visible = text(heading?.textContent);
    return /^Padrão$/i.test(visible) ? "default" : visible;
  }

  function normalizeStatusRow(card) {
    const small = card?.querySelector(".small");
    const details = small?.querySelector(".catalogo-context-accordion");
    if (!small || !details) return;

    let row = small.querySelector(":scope > .catalogo-status-row");
    if (row) return;

    let isCurrent = false;
    let isDefault = false;
    const removable = [];
    let node = small.firstChild;
    while (node && node !== details) {
      const next = node.nextSibling;
      const value = text(node.textContent);
      if (/^(?:🟢\s*)?Atual$/i.test(value)) isCurrent = true;
      if (/^(?:⭐\s*)?Catálogo padrão$/i.test(value)) isDefault = true;
      if (node.nodeType === Node.TEXT_NODE && (isCurrent || isDefault)) removable.push(node);
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName === "BR") removable.push(node);
      node = next;
    }

    if (!isCurrent) isCurrent = !!card.querySelector(".catalogo-load-button:disabled");
    if (!isDefault) isDefault = !!card.querySelector(".catalogo-default-button:disabled");
    removable.forEach(item => item.remove());

    row = document.createElement("span");
    row.className = "catalogo-status-row";
    row.setAttribute("aria-label", "Status do catálogo");
    row.innerHTML = `${isCurrent ? '<span class="catalogo-status-item">🟢 Atual</span>' : ""}${isDefault ? '<span class="catalogo-status-item">⭐ Catálogo padrão</span>' : ""}`;
    if (!isCurrent && !isDefault) row.setAttribute("aria-hidden", "true");
    small.insertBefore(row, details);
  }

  function normalizeAvailability(card) {
    const container = card?.querySelector(".catalogo-availability");
    if (!container) return;
    const labels = [...container.querySelectorAll(".catalogo-availability-icon")]
      .map(node => text(node.getAttribute("aria-label") || node.dataset.tooltip).toLowerCase());
    const raw = text(container.textContent).toLowerCase();
    const hasCatalog = labels.some(label => label.includes("catálogo")) || raw.includes("📄");
    const hasState = labels.some(label => label.includes("estado")) || raw.includes("📝");
    const hasLog = labels.some(label => label.includes("log")) || raw.includes("📋");
    const items = [["📄","Catálogo",hasCatalog],["📝","Estado",hasState],["📋","Log",hasLog]];
    container.innerHTML = items.map(([icon,label,available]) =>
      `<span class="catalogo-availability-icon${available ? "" : " is-unavailable"}" tabindex="0" role="img" aria-label="${label}" aria-disabled="${available ? "false" : "true"}" data-tooltip="${label}">${icon}</span>`
    ).join("");
  }

  function filenameFromResponse(response, fallback) {
    const disposition = String(response.headers.get("content-disposition") || "");
    let match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (match) { try { return decodeURIComponent(match[1].replace(/["']/g, "")); } catch (_) {} }
    match = disposition.match(/filename=["']?([^;"']+)/i);
    return match ? match[1].trim() : fallback;
  }

  async function downloadCatalogContexts(slotName, button) {
    if (!slotName || !button) return;
    const oldLabel = button.textContent;
    button.disabled = true;
    button.textContent = "…";
    try {
      const response = await fetch("/catalogos/data", {cache:"no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const rows = Array.isArray(payload?.catalogos) ? payload.catalogos : Array.isArray(payload?.rows) ? payload.rows : [];
      const downloads = rows.filter(row => text(row?.slot_name || row?.catalogo_nome) === slotName && row?.download_csv_url);
      if (!downloads.length) {
        window.alert("Nenhum arquivo de catálogo disponível para este catálogo.");
        return;
      }
      for (let index = 0; index < downloads.length; index += 1) {
        const item = downloads[index];
        const fileResponse = await fetch(item.download_csv_url, {cache:"no-store"});
        if (!fileResponse.ok) throw new Error(`Falha ao baixar catálogo (${fileResponse.status})`);
        const blob = await fileResponse.blob();
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        const suffix = downloads.length > 1 ? `-${index + 1}` : "";
        anchor.href = url;
        anchor.download = filenameFromResponse(fileResponse, `${slotName}${suffix}.csv`);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
      }
    } catch (error) {
      window.alert(`Não foi possível baixar o catálogo: ${text(error?.message || error)}`);
    } finally {
      button.disabled = false;
      button.textContent = oldLabel;
    }
  }

  function ensureDownloadButton(card) {
    const actions = card?.querySelector(".catalogo-card-actions");
    if (!actions || actions.querySelector(".catalogo-download-button")) return;
    const slotName = slotNameFromCard(card) || (card.querySelector(".catalogo-default-button:disabled") ? "default" : "");
    if (!slotName) return;

    const button = document.createElement("button");
    button.className = "catalogo-icon-button catalogo-download-button";
    button.type = "button";
    button.title = `Baixar catálogo ${slotName}`;
    button.setAttribute("aria-label", `Baixar catálogo ${slotName}`);
    button.textContent = "⬇️";
    button.addEventListener("click", () => downloadCatalogContexts(slotName, button));
    const view = actions.querySelector(".catalogo-view-button");
    if (view) view.insertAdjacentElement("afterend", button);
    else actions.prepend(button);
  }

  function refine() {
    ensureTopControlsRow();
    document.querySelectorAll(".catalogo-summary-card").forEach(card => {
      normalizeStatusRow(card);
      normalizeAvailability(card);
      ensureDownloadButton(card);
    });
  }

  const run = () => window.requestAnimationFrame(refine);
  run();
  [100,300,800,1600].forEach(delay => window.setTimeout(refine, delay));
  let timer = null;
  new MutationObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(refine, 60);
  }).observe(document.body, {childList:true, subtree:true});
})();
