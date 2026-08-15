(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);

  const STYLE_ID = "crapscraper-preparation-bulk-style";
  if (!document.getElementById(STYLE_ID)) {
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .cs-preparation-bulkbar{
        display:flex!important;
        align-items:center!important;
        gap:12px!important;
        flex-wrap:wrap!important;
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
        flex-wrap:wrap!important;
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
      .cs-preparation-bulkbar #updates_selected_count{
        margin-left:auto!important;
        white-space:nowrap!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions{
        display:flex!important;
        align-items:center!important;
        gap:10px!important;
        flex:0 0 auto!important;
      }
      .cs-preparation-bulkbar .cs-preparation-actions button{
        min-height:48px!important;
        padding:0 22px!important;
        border-color:#6d3bb5!important;
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
      .cs-preparation-bulkbar .cs-original-bulk-trigger{
        display:none!important;
      }
      .cs-preparation-bulkbar .updates-bulk-title,
      .cs-preparation-bulkbar .section-title{
        display:none!important;
      }
      @media(max-width:900px){
        .cs-preparation-bulkbar{align-items:stretch!important}
        .cs-preparation-bulkbar .cs-preparation-selection{flex-basis:100%!important}
        .cs-preparation-bulkbar .cs-preparation-actions{width:100%!important}
        .cs-preparation-bulkbar .cs-preparation-actions button{flex:1 1 0!important}
        .cs-preparation-bulkbar #updates_selected_count{margin-left:0!important}
      }
    `;
    document.head.appendChild(style);
  }

  function findPreparationRoot() {
    const anchor = byId("updates_status_filter") || byId("updates_page_size");
    return anchor?.closest?.(".updates-card-section,.card,section") || anchor?.parentElement || null;
  }

  function makeProxyCheckbox(originalButton, id, labelText) {
    let label = byId(id)?.closest("label");
    if (label) return {label, input: byId(id)};

    label = document.createElement("label");
    label.className = "cs-preparation-check";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.id = id;
    const text = document.createElement("span");
    text.textContent = labelText;
    label.append(input, text);

    input.addEventListener("change", () => {
      if (input.checked) {
        originalButton?.click();
      } else {
        byId("updates_clear_selection")?.click();
      }
      setTimeout(syncProxyState, 60);
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

    [pageProxy.label, allProxy.label, clear, count].forEach((node) => {
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
    [prepare, enqueue].forEach((node) => {
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

  let timer = null;
  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(standardizePreparationBulk, 60);
  };

  const start = () => {
    standardizePreparationBulk();
    new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true, characterData:true});
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
