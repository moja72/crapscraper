(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const normalize = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  const STYLE_ID = "crapscraper-preparation-bulk-style";
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .cs-search-system .updates-bulkbar.cs-preparation-bulkbar,
      .cs-preparation-bulkbar{
        display:flex!important;
        flex-direction:row!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:16px!important;
        flex-wrap:nowrap!important;
        padding:12px!important;
        margin:12px 0!important;
        border:1px solid #292931!important;
        border-radius:12px!important;
        background:#151519!important;
      }
      .cs-preparation-bulkbar .cs-preparation-selection{
        display:flex!important;
        align-items:center!important;
        gap:12px!important;
        flex:1 1 auto!important;
        min-width:0!important;
        flex-wrap:nowrap!important;
      }
      .cs-preparation-bulkbar .cs-preparation-check{
        display:inline-flex!important;
        align-items:center!important;
        gap:7px!important;
        white-space:nowrap!important;
        cursor:pointer!important;
        font-size:13px!important;
        font-weight:700!important;
        color:#f3f4f6!important;
      }
      .cs-preparation-bulkbar .cs-preparation-check input{
        width:17px!important;
        height:17px!important;
        min-height:0!important;
        accent-color:#7c3aed!important;
      }
      .cs-preparation-bulkbar #updates_clear_selection{
        min-height:46px!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions{
        display:flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:10px!important;
        flex:0 0 auto!important;
        margin-left:auto!important;
        white-space:nowrap!important;
      }
      .cs-preparation-bulkbar > .cs-bulk-action-line{
        display:none!important;
        border:0!important;
        padding:0!important;
        margin:0!important;
        width:0!important;
        min-width:0!important;
        flex:0 0 0!important;
      }
      .cs-search-system #comparison_selected_count,
      .cs-search-system #updates_selected_count,
      .cs-preparation-bulkbar #updates_selected_count{
        margin:0!important;
        padding:0!important;
        border:0!important;
        border-radius:0!important;
        background:transparent!important;
        box-shadow:none!important;
        min-height:0!important;
        height:auto!important;
        white-space:nowrap!important;
        color:#f3f4f6!important;
        font-size:13px!important;
        font-weight:700!important;
        line-height:1.2!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions button{
        min-height:46px!important;
        padding:0 22px!important;
        border:1px solid #6d3bb5!important;
        background:#6732a6!important;
        color:#fff!important;
        box-shadow:none!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions button:hover:not(:disabled){
        background:#7c3aed!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions button:disabled{
        opacity:.55!important;
      }
      .cs-preparation-bulkbar .cs-original-bulk-trigger,
      .cs-hide-bulk-heading{
        display:none!important;
      }

      .cs-context-download{
        white-space:nowrap!important;
      }

      @media(max-width:1050px){
        .cs-search-system .updates-bulkbar.cs-preparation-bulkbar,
        .cs-preparation-bulkbar{
          flex-wrap:wrap!important;
          align-items:stretch!important;
        }
        .cs-preparation-bulkbar .cs-preparation-selection{
          flex-basis:100%!important;
          flex-wrap:wrap!important;
        }
        .cs-preparation-bulkbar .cs-preparation-actions{
          width:100%!important;
          margin-left:0!important;
          justify-content:flex-start!important;
        }
      }
      @media(max-width:720px){
        .cs-preparation-bulkbar .cs-preparation-actions{
          flex-wrap:wrap!important;
        }
        .cs-preparation-bulkbar .cs-preparation-actions button{
          flex:1 1 180px!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function findPreparationRoot() {
    const anchor = byId("updates_status_filter") || byId("updates_page_size");
    return anchor?.closest?.(".updates-card-section,.card,section") || anchor?.parentElement || null;
  }

  function makeProxyCheckbox(originalButton, id, labelText) {
    let input = byId(id);
    let label = input?.closest("label");
    if (label && input) return {label, input};

    label = document.createElement("label");
    label.className = "cs-preparation-check";
    input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    const text = document.createElement("span");
    text.textContent = labelText;
    label.append(input, text);

    input.addEventListener("change", () => {
      if (input.checked) originalButton?.click();
      else byId("updates_clear_selection")?.click();
      setTimeout(syncProxyState, 80);
    });
    return {label, input};
  }

  function syncProxyState() {
    const countText = byId("updates_selected_count")?.textContent || "";
    const count = Number.parseInt(countText, 10) || 0;
    const page = byId("cs_updates_select_page");
    const all = byId("cs_updates_select_all");
    if (count === 0) {
      if (page) page.checked = false;
      if (all) all.checked = false;
    }
  }

  function hideBulkHeading(root) {
    if (!root) return;
    [...root.querySelectorAll(".section-title,.updates-bulk-title,h3,h4,strong,div")]
      .filter((node) => node.childElementCount === 0 && normalize(node.textContent).toUpperCase() === "OPERAÇÕES EM LOTE")
      .forEach((node) => node.classList.add("cs-hide-bulk-heading"));
  }

  function standardizePreparationBulk() {
    const root = findPreparationRoot();
    const bar = root?.querySelector(".updates-bulkbar");
    if (!root || !bar) return;

    const selectPage = byId("updates_select_page");
    const selectAll = byId("updates_select_filtered");
    const clear = byId("updates_clear_selection");
    const count = byId("updates_selected_count");
    const prepare = byId("updates_prepare_selected");
    const enqueue = byId("updates_enqueue_selected");
    if (!selectPage || !selectAll || !clear || !count || !prepare || !enqueue) return;

    hideBulkHeading(root);
    bar.classList.add("cs-preparation-bulkbar");
    selectPage.classList.add("cs-original-bulk-trigger");
    selectAll.classList.add("cs-original-bulk-trigger");

    let selection = bar.querySelector(".cs-preparation-selection");
    if (!selection) {
      selection = document.createElement("div");
      selection.className = "cs-preparation-selection";
      bar.prepend(selection);
    }

    const pageProxy = makeProxyCheckbox(selectPage, "cs_updates_select_page", "Selecionar página");
    const allProxy = makeProxyCheckbox(selectAll, "cs_updates_select_all", "Selecionar todo resultado");
    [pageProxy.label, allProxy.label, clear].forEach((node) => {
      if (node && node.parentElement !== selection) selection.appendChild(node);
    });

    let actions = bar.querySelector(".cs-preparation-actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "cs-preparation-actions";
      bar.appendChild(actions);
    }

    prepare.textContent = "Preparar planos";
    enqueue.textContent = "Adicionar à fila";
    [count, prepare, enqueue].forEach((node) => {
      if (node.parentElement !== actions) actions.appendChild(node);
    });

    const meta = byId("updates_result_meta")?.closest(".listing-meta-row")
      || byId("updates_page_size")?.closest(".listing-meta-row")
      || byId("updates_page_size")?.parentElement;
    if (meta && bar.parentElement === meta.parentElement && bar.nextElementSibling !== meta) {
      meta.parentElement.insertBefore(bar, meta);
    }

    syncProxyState();
  }

  function moveContextListingControls() {
    const body = byId("catalogos_table_body");
    if (!body) return;
    const tableWrap = body.closest(".table-wrap") || body.closest("table")?.parentElement;
    if (!tableWrap || !tableWrap.parentElement) return;

    const meta = byId("catalogos_result_meta")?.closest(".listing-meta-row")
      || byId("catalogos_page_size")?.closest(".listing-meta-row")
      || byId("catalogos_result_meta")?.parentElement;
    const pagination = byId("catalogos_prev_page")?.closest(".listing-pagination")
      || byId("catalogos_page_label")?.parentElement;

    if (meta && meta.parentElement === tableWrap.parentElement) {
      tableWrap.parentElement.insertBefore(meta, tableWrap);
    }
    if (pagination && pagination.parentElement === tableWrap.parentElement) {
      tableWrap.parentElement.insertBefore(pagination, tableWrap);
    }
  }

  function addContextDownloadButtons() {
    const body = byId("catalogos_table_body");
    if (!body) return;
    [...body.querySelectorAll("tr")].forEach((row) => {
      const actionWrap = row.querySelector(".table-actions") || row.lastElementChild;
      if (!actionWrap || actionWrap.querySelector(".cs-context-download")) return;
      const previewButton = [...actionWrap.querySelectorAll("button")]
        .find((button) => normalize(button.textContent) === "Catálogo" && !button.disabled);
      if (!previewButton) return;
      const onclick = previewButton.getAttribute("onclick") || "";
      if (!onclick.includes("showCatalogoCsvPreview(")) return;

      const downloadButton = previewButton.cloneNode(true);
      downloadButton.classList.add("cs-context-download");
      downloadButton.textContent = "Baixar";
      downloadButton.setAttribute("aria-label", "Baixar contexto");
      downloadButton.setAttribute("title", "Baixar contexto");
      downloadButton.setAttribute("onclick", onclick.replace("showCatalogoCsvPreview(", "downloadCatalogoArquivo("));
      previewButton.insertAdjacentElement("afterend", downloadButton);
    });
  }

  function hideStandaloneCatalogDownload() {
    const preview = byId("catalogos_status_preview");
    if (!preview) return;
    const container = preview.closest(".card,section,.catalogos-preview,.catalog-preview") || preview.parentElement;
    if (!container) return;
    [...container.querySelectorAll("button")]
      .filter((button) => normalize(button.textContent) === "Baixar" && !button.classList.contains("cs-context-download"))
      .forEach((button) => {
        button.style.display = "none";
        button.setAttribute("aria-hidden", "true");
      });
  }

  function standardizeCatalogContexts() {
    moveContextListingControls();
    addContextDownloadButtons();
    hideStandaloneCatalogDownload();
  }

  function standardizeAll() {
    standardizePreparationBulk();
    standardizeCatalogContexts();
  }

  let timer = null;
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(standardizeAll, 0);
  };

  const start = () => {
    standardizeAll();

    /* Sem observer global: a preparação só é reajustada em eventos reais de UI. */
    document.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest(
        "#tab_btn_atualizacoes,#updates_refresh_btn,#updates_prepare_selected,#updates_enqueue_selected,#updates_clear_selection,#updates_select_page,#updates_select_filtered,#catalogos_refresh_btn"
      )) schedule();
    }, true);

    document.addEventListener("crapscraper:main-tab-changed", (event) => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "principal") schedule();
    });

    /* Catálogo é a única área dinâmica deste arquivo que ainda precisa observar
       inserções de linhas. O observer fica estritamente escopado ao tbody. */
    const catalogBody = byId("catalogos_table_body");
    if (catalogBody) {
      let catalogTimer = null;
      new MutationObserver(() => {
        clearTimeout(catalogTimer);
        catalogTimer = setTimeout(standardizeCatalogContexts, 40);
      }).observe(catalogBody, {childList:true, subtree:true});
    }
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
