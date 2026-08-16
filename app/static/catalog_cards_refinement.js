(() => {
  "use strict";

  const STYLE_ID = "crapscraper-catalog-cards-refinement";
  document.getElementById(STYLE_ID)?.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Modal Catálogos: filtro e ação na mesma linha. */
    .form-grid:has(#catalogos_filter_slot){
      grid-template-columns:minmax(0,1fr) minmax(260px,1fr)!important;
      align-items:end!important;
      gap:14px!important;
    }
    .form-grid:has(#catalogos_filter_slot) .catalogos-refresh-field .row{
      width:100%!important;
    }
    .form-grid:has(#catalogos_filter_slot) .catalogos-refresh-field button{
      width:100%!important;
      min-height:46px!important;
    }

    /* Cards: status sempre ocupa uma linha e nunca quebra no desktop. */
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
      white-space:nowrap!important;
    }

    /* Atalhos inferiores: indisponível fica claramente apagado. */
    .catalogo-summary-card .catalogo-availability-icon.is-unavailable{
      opacity:.12!important;
      filter:grayscale(1) saturate(0)!important;
    }

    /* Botão de download no grupo superior de ícones. */
    .catalogo-card-actions .catalogo-download-button{
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
    }

    /* Fila de atualização: checkpoint centralizado verticalmente com o select. */
    #updates_queue_checkpoint{
      display:flex!important;
      align-items:center!important;
      min-height:48px!important;
      margin:0!important;
      line-height:1.35!important;
    }

    @media(max-width:760px){
      .form-grid:has(#catalogos_filter_slot){
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

  function slotNameFromCard(card) {
    const loadButton = card?.querySelector(".catalogo-load-button");
    const source = String(loadButton?.getAttribute("onclick") || "");
    const match = source.match(/loadCatalogo\((.+)\)/);
    if (match) {
      try { return String(JSON.parse(match[1]) || "").trim(); } catch (_) {}
    }
    const aria = String(loadButton?.getAttribute("aria-label") || "");
    return aria.replace(/^Carregar catálogo\s+/i, "").trim();
  }

  function ensureStatusPlaceholder(card) {
    const small = card?.querySelector(".small");
    const details = small?.querySelector(".catalogo-context-accordion");
    if (!small || !details) return;
    let row = small.querySelector(".catalogo-status-row");
    if (!row) {
      row = document.createElement("span");
      row.className = "catalogo-status-row";
      row.setAttribute("aria-hidden", "true");
      small.insertBefore(row, details);
    }
  }

  function filenameFromResponse(response, fallback) {
    const disposition = String(response.headers.get("content-disposition") || "");
    let match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (match) {
      try { return decodeURIComponent(match[1].replace(/["']/g, "")); } catch (_) {}
    }
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
      const rows = Array.isArray(payload?.catalogos) ? payload.catalogos : [];
      const downloads = rows.filter(row => {
        const rowSlot = text(row?.slot_name || row?.catalogo_nome);
        return rowSlot === slotName && row?.csv_exists && row?.download_csv_url;
      });
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
    const slotName = slotNameFromCard(card);
    if (!slotName) return;
    const button = document.createElement("button");
    button.className = "catalogo-icon-button catalogo-download-button";
    button.type = "button";
    button.title = `Baixar catálogo ${slotName}`;
    button.setAttribute("aria-label", `Baixar catálogo ${slotName}`);
    button.textContent = "⬇️";
    button.addEventListener("click", () => downloadCatalogContexts(slotName, button));
    const view = actions.querySelector(".catalogo-view-button");
    if (view?.nextSibling) actions.insertBefore(button, view.nextSibling);
    else actions.appendChild(button);
  }

  function refine() {
    document.querySelectorAll(".catalogo-summary-card").forEach(card => {
      ensureStatusPlaceholder(card);
      ensureDownloadButton(card);
    });
  }

  refine();
  let timer = null;
  new MutationObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(refine, 50);
  }).observe(document.body, {childList:true, subtree:true});
})();
