(() => {
  "use strict";

  if (window.__crapScraperPreparationStandardizationV12Installed) return;
  window.__crapScraperPreparationStandardizationV12Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const additionSelection = {ids:new Set(), allResults:false, allIds:new Set(), busy:false};
  let normalizing = false;
  let scheduled = 0;

  function installStyles() {
    if ($("#cs-preparation-standardization-v12-style")) return;
    const style = document.createElement("style");
    style.id = "cs-preparation-standardization-v12-style";
    style.textContent = `
      /* Preparação v12: um único contrato visual para Atualizar e Adicionar. */
      #tab_panel_atualizacoes .cs-prep-v12,
      #tab_panel_adicoes .cs-prep-v12{
        width:100%!important;min-width:0!important;padding:16px 18px!important;
        border:1px solid var(--line)!important;border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;overflow:visible!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12>.cs-prep-v12-header,
      #tab_panel_adicoes .cs-prep-v12>.cs-prep-v12-header{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-height:30px!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;box-shadow:none!important;list-style:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12>.cs-prep-v12-header::-webkit-details-marker,
      #tab_panel_adicoes .cs-prep-v12>.cs-prep-v12-header::-webkit-details-marker{display:none!important}
      #tab_panel_atualizacoes .cs-prep-v12-header .standard-update-accordion-toggle-copy,
      #tab_panel_adicoes .cs-prep-v12-header .cs-op-summary-left{
        display:inline-flex!important;align-items:center!important;gap:8px!important;min-width:0!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-header .standard-update-accordion-title,
      #tab_panel_adicoes .cs-prep-v12-header .section-title{
        margin:0!important;color:var(--text)!important;font-size:16px!important;font-weight:850!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-summary,
      #tab_panel_adicoes .cs-prep-v12-summary{
        margin-left:auto!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12.is-collapsed>.cs-prep-v12-body{display:none!important}
      #tab_panel_adicoes .cs-prep-v12:not([open])>.cs-prep-v12-body{display:none!important}
      #tab_panel_atualizacoes .cs-prep-v12-body,
      #tab_panel_adicoes .cs-prep-v12-body{display:grid!important;gap:10px!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important}
      #tab_panel_atualizacoes .cs-prep-v12-description,
      #tab_panel_adicoes .cs-prep-v12-description{
        margin:10px 0 2px!important;padding:0!important;color:var(--text-muted)!important;font-size:11px!important;line-height:1.5!important;
      }

      /* Linha 1: Buscar | Estado | Atualizar. */
      #tab_panel_atualizacoes .cs-prep-v12-toolbar,
      #tab_panel_adicoes .cs-prep-v12-toolbar{
        display:grid!important;grid-template-columns:minmax(280px,1fr) minmax(180px,230px) auto!important;
        gap:10px!important;align-items:end!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-field,
      #tab_panel_adicoes .cs-prep-v12-field{
        display:grid!important;gap:6px!important;min-width:0!important;margin:0!important;color:var(--text-muted)!important;
        font-size:11px!important;font-weight:750!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-field>label,
      #tab_panel_adicoes .cs-prep-v12-field>label{margin:0!important;color:inherit!important;font:inherit!important}
      #tab_panel_atualizacoes .cs-prep-v12-field input,
      #tab_panel_atualizacoes .cs-prep-v12-field select,
      #tab_panel_adicoes .cs-prep-v12-field input,
      #tab_panel_adicoes .cs-prep-v12-field select{
        width:100%!important;min-width:0!important;min-height:46px!important;margin:0!important;padding:8px 13px!important;
        border:1px solid var(--line-strong)!important;border-radius:9px!important;background:var(--bg-input)!important;
        color:var(--text)!important;box-shadow:none!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-refresh,
      #tab_panel_adicoes .cs-prep-v12-refresh{
        min-width:108px!important;min-height:46px!important;margin:0!important;padding:0 16px!important;border-radius:9px!important;
      }

      /* Linha 2: Versão | Relacionamento | Limpar filtros. */
      #tab_panel_atualizacoes .cs-prep-v12-advanced,
      #tab_panel_adicoes .cs-prep-v12-advanced{
        display:grid!important;grid-template-columns:repeat(2,minmax(190px,1fr)) auto!important;gap:10px!important;align-items:end!important;
        width:100%!important;min-width:0!important;margin:0!important;padding:10px!important;
        border:1px solid var(--line)!important;border-radius:10px!important;background:rgba(255,255,255,.015)!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-advanced>button,
      #tab_panel_adicoes .cs-prep-v12-advanced>button{min-height:46px!important;margin:0!important;padding:0 16px!important;border-radius:9px!important}

      /* Linha 3: seleção à esquerda e ações à direita. */
      #tab_panel_atualizacoes .cs-prep-v12-bulk,
      #tab_panel_adicoes .cs-prep-v12-bulk{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-width:0!important;min-height:60px!important;margin:0!important;padding:10px 12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.022)!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-selection,
      #tab_panel_adicoes .cs-prep-v12-selection{
        display:flex!important;align-items:center!important;gap:12px!important;flex:1 1 auto!important;min-width:0!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-check,
      #tab_panel_adicoes .cs-prep-v12-check{
        display:inline-flex!important;align-items:center!important;gap:7px!important;margin:0!important;color:var(--text-soft)!important;
        font-size:11px!important;font-weight:750!important;white-space:nowrap!important;cursor:pointer!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-check input[type=checkbox],
      #tab_panel_adicoes .cs-prep-v12-check input[type=checkbox]{
        width:17px!important;height:17px!important;min-height:0!important;margin:0!important;accent-color:#7c3aed!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-actions,
      #tab_panel_adicoes .cs-prep-v12-actions{
        display:flex!important;align-items:center!important;justify-content:flex-end!important;gap:8px!important;flex:0 0 auto!important;
        margin-left:auto!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-selected-count,
      #tab_panel_adicoes .cs-prep-v12-selected-count{
        margin-right:2px!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-actions button,
      #tab_panel_adicoes .cs-prep-v12-actions button{min-height:40px!important;padding:0 14px!important;border-radius:9px!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-preparation-original-bulk-triggers{display:none!important}

      /* Linha 4: total encontrado | itens por página. */
      #tab_panel_atualizacoes .cs-prep-v12-meta,
      #tab_panel_adicoes .cs-prep-v12-meta{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;
        width:100%!important;min-height:34px!important;margin:0!important;padding:0 2px!important;border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-found,
      #tab_panel_adicoes .cs-prep-v12-found{
        margin:0!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-meta .listing-page-size,
      #tab_panel_adicoes .cs-prep-v12-meta .listing-page-size{
        display:inline-flex!important;align-items:center!important;gap:8px!important;margin-left:auto!important;color:var(--text-soft)!important;
        font-size:11px!important;font-weight:700!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-meta .listing-page-size input,
      #tab_panel_adicoes .cs-prep-v12-meta .listing-page-size input{
        width:58px!important;min-width:58px!important;min-height:32px!important;margin:0!important;padding:4px 7px!important;text-align:center!important;
      }

      /* Jobs: mesma moldura, conteúdo interno específico de cada fluxo. */
      #tab_panel_atualizacoes .cs-prep-v12-list,
      #tab_panel_adicoes .cs-prep-v12-list{display:grid!important;gap:8px!important;width:100%!important;min-width:0!important;margin:0!important}
      #tab_panel_atualizacoes .cs-prep-v12-list>.update-job,
      #tab_panel_adicoes .cs-prep-v12-list>.addition-op-row{
        width:100%!important;min-width:0!important;margin:0!important;padding:12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.014)!important;box-shadow:none!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-list>.update-job{
        display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(140px,180px) minmax(220px,auto)!important;gap:12px!important;align-items:center!important;
      }
      #tab_panel_adicoes .cs-prep-v12-list>.addition-op-row{
        display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(180px,.8fr) minmax(155px,.7fr) minmax(210px,auto)!important;gap:12px!important;align-items:center!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-empty,
      #tab_panel_adicoes .cs-prep-v12-empty,
      #tab_panel_atualizacoes .cs-prep-v12-list>.notice,
      #tab_panel_adicoes .cs-prep-v12-list>.addition-empty,
      #tab_panel_adicoes .cs-prep-v12-list>.addition-loading{
        display:grid!important;place-items:center!important;width:100%!important;min-height:88px!important;margin:0!important;padding:18px!important;
        border:1px dashed var(--line-strong)!important;border-radius:11px!important;background:rgba(255,255,255,.012)!important;
        color:var(--text-muted)!important;text-align:center!important;box-sizing:border-box!important;
      }
      #tab_panel_adicoes .cs-prep-v12-table-head{display:none!important}

      /* Paginação comum. */
      #tab_panel_atualizacoes .cs-prep-v12-pagination,
      #tab_panel_adicoes .cs-prep-v12-pagination{
        display:grid!important;grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
        gap:10px!important;align-items:center!important;width:100%!important;min-width:0!important;margin:2px 0 0!important;padding:0!important;
      }
      #tab_panel_atualizacoes .cs-prep-v12-pagination>button,
      #tab_panel_adicoes .cs-prep-v12-pagination>button{width:100%!important;min-height:42px!important;margin:0!important}
      #tab_panel_atualizacoes .cs-prep-v12-pagination .badge,
      #tab_panel_adicoes .cs-prep-v12-pagination .badge{justify-self:center!important;white-space:nowrap!important}

      #cs_addition_preparation_feedback:empty{display:none!important}
      #cs_addition_preparation_feedback{margin:0!important;padding:8px 10px!important;border:1px solid var(--line)!important;border-radius:8px!important;color:var(--text-muted)!important;font-size:11px!important}

      @media(max-width:900px){
        #tab_panel_atualizacoes .cs-prep-v12-toolbar,#tab_panel_adicoes .cs-prep-v12-toolbar,
        #tab_panel_atualizacoes .cs-prep-v12-advanced,#tab_panel_adicoes .cs-prep-v12-advanced{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-prep-v12-refresh,#tab_panel_adicoes .cs-prep-v12-refresh,
        #tab_panel_atualizacoes .cs-prep-v12-advanced>button,#tab_panel_adicoes .cs-prep-v12-advanced>button{width:100%!important}
        #tab_panel_atualizacoes .cs-prep-v12-bulk,#tab_panel_adicoes .cs-prep-v12-bulk{align-items:stretch!important;flex-direction:column!important}
        #tab_panel_atualizacoes .cs-prep-v12-actions,#tab_panel_adicoes .cs-prep-v12-actions{width:100%!important;margin-left:0!important;justify-content:flex-start!important}
        #tab_panel_atualizacoes .cs-prep-v12-list>.update-job,#tab_panel_adicoes .cs-prep-v12-list>.addition-op-row{grid-template-columns:30px minmax(0,1fr)!important;align-items:start!important}
      }
      @media(max-width:620px){
        #tab_panel_atualizacoes .cs-prep-v12-pagination,#tab_panel_adicoes .cs-prep-v12-pagination{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-prep-v12-meta,#tab_panel_adicoes .cs-prep-v12-meta{align-items:flex-start!important;flex-direction:column!important}
        #tab_panel_atualizacoes .cs-prep-v12-meta .listing-page-size,#tab_panel_adicoes .cs-prep-v12-meta .listing-page-size{margin-left:0!important}
      }
    `;
    document.head.appendChild(style);
  }

  function fieldFor(control) {
    if (!control) return null;
    const field = control.closest("label,.field") || control.parentElement;
    if (field) field.classList.add("cs-prep-v12-field");
    return field;
  }

  function ensureBody(root, id) {
    let body = $(`#${id}`, root);
    if (!body) {
      body = document.createElement("div");
      body.id = id;
      root.appendChild(body);
    }
    body.className = `${body.className || ""} cs-prep-v12-body`.trim();
    body.removeAttribute("hidden");
    return body;
  }

  function canonicalDescription(root, body, value) {
    $$(".cs-preparation-description,.cs-v4-preparation-hint,.addition-section-hint,.cs-op-section-hint", root)
      .filter(node => node !== body && !node.closest("#updates_history_accordion,#addition_history_accordion"))
      .forEach(node => node.remove());
    let description = $(":scope > .cs-prep-v12-description", body);
    if (!description) {
      description = document.createElement("div");
      description.className = "cs-prep-v12-description";
      body.prepend(description);
    }
    description.textContent = value;
    return description;
  }

  function removeDuplicateUpdateEmpty(list) {
    if (!list) return;
    const seen = new Set();
    $$(":scope > .notice", list).forEach(node => {
      const key = text(node.textContent).toLowerCase();
      if (!key) return;
      if (seen.has(key)) node.remove();
      else {
        seen.add(key);
        node.classList.add("cs-prep-v12-empty");
        node.hidden = false;
      }
    });
  }

  function normalizeMetaText(node) {
    if (!node) return;
    const match = text(node.textContent).match(/^(\d+)\s+itens?$/i);
    if (!match) return;
    const count = Number(match[1]);
    const next = `${count} ${count === 1 ? "item encontrado" : "itens encontrados"}`;
    if (node.textContent !== next) node.textContent = next;
  }

  function normalizeUpdate() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root) return false;
    root.classList.add("cs-prep-v12");

    const header = $(":scope > .standard-update-accordion-toggle", root);
    if (header) header.classList.add("cs-prep-v12-header");
    $("#cs_v4_update_preparation_summary", root)?.classList.add("cs-prep-v12-summary");

    const body = ensureBody(root, "cs_updates_preparation_v12_body");
    const description = canonicalDescription(
      root, body,
      "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os planos antes de enviá-los para a fila de atualização."
    );

    const toolbar = $(".updates-filters", root);
    toolbar?.classList.add("cs-prep-v12-toolbar");
    fieldFor($("#updates_search_filter", root));
    fieldFor($("#updates_status_filter", root));
    const refresh = $(".cs-v4-preparation-refresh", toolbar || root) || toolbar?.querySelector("button");
    refresh?.classList.add("cs-prep-v12-refresh");

    const advanced = $(".cs-v4-preparation-advanced", root) || $(".cs-preparation-advanced", root);
    advanced?.classList.add("cs-prep-v12-advanced");
    fieldFor($("#updates_version_filter", root));
    fieldFor($("#updates_relationship_filter", root));

    const bulk = $(".updates-bulkbar", root);
    bulk?.classList.add("cs-prep-v12-bulk");
    const selection = $(".cs-preparation-selection", bulk || root);
    selection?.classList.add("cs-prep-v12-selection");
    $$(`label`, selection || document).forEach(label => label.classList.add("cs-prep-v12-check"));
    const actions = $(".cs-preparation-actions", bulk || root);
    actions?.classList.add("cs-prep-v12-actions");
    $("#updates_selected_count", root)?.classList.add("cs-prep-v12-selected-count");

    const meta = $(".listing-meta-row", root);
    meta?.classList.add("cs-prep-v12-meta");
    $("#updates_found_count", root)?.classList.add("cs-prep-v12-found");

    const progress = $("#updates_batch_progress", root);
    const list = $("#updates_jobs", root);
    list?.classList.add("cs-prep-v12-list");
    removeDuplicateUpdateEmpty(list);
    const pagination = $(".listing-pagination", root);
    pagination?.classList.add("cs-prep-v12-pagination");

    [description, toolbar, advanced, bulk, meta, progress, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });

    const legacyControls = $("#updates_working_controls", root);
    if (legacyControls && legacyControls !== body) legacyControls.hidden = true;
    $(".cs-v4-preparation-head", root)?.setAttribute("hidden", "");
    return true;
  }

  function ensureAdditionAdvanced(root) {
    let advanced = $("#addition_preparation_advanced_v12", root);
    if (!advanced) {
      advanced = document.createElement("div");
      advanced.id = "addition_preparation_advanced_v12";
      advanced.className = "cs-prep-v12-advanced";
      advanced.innerHTML = `
        <label class="cs-prep-v12-field">Versão
          <select id="addition_preparation_version">
            <option value="">Todas</option>
            <option value="has_version">Com versão informada</option>
            <option value="missing_version">Sem versão informada</option>
          </select>
        </label>
        <label class="cs-prep-v12-field">Relacionamento
          <select id="addition_preparation_relationship">
            <option value="">Todos</option>
            <option value="new_product">Novo produto</option>
            <option value="woo_linked">Com WooCommerce ID</option>
          </select>
        </label>
        <button class="btn-secondary" id="addition_preparation_clear_filters_v12" type="button">Limpar filtros</button>`;
    }
    $("#addition_preparation_advanced", root)?.remove();
    return advanced;
  }

  function ensureAdditionBulk(root) {
    let bulk = $(".addition-bulk-actions", root);
    if (!bulk) {
      bulk = document.createElement("div");
      root.appendChild(bulk);
    }
    bulk.classList.add("cs-prep-v12-bulk");

    let selection = $(":scope > .cs-prep-v12-selection", bulk);
    if (!selection) {
      selection = document.createElement("div");
      selection.className = "cs-prep-v12-selection";
      bulk.prepend(selection);
    }

    const pageBox = $("#addition_preparation_select_all", root);
    let pageLabel = pageBox?.closest("label");
    if (pageBox && !pageLabel) {
      pageLabel = document.createElement("label");
      pageBox.replaceWith(pageLabel);
      pageLabel.append(pageBox, document.createTextNode(" Selecionar página"));
    }
    if (pageLabel) {
      pageLabel.classList.add("cs-prep-v12-check");
      const labelText = Array.from(pageLabel.childNodes).find(node => node.nodeType === Node.TEXT_NODE);
      if (labelText) labelText.textContent = " Selecionar página";
      if (pageLabel.parentElement !== selection) selection.appendChild(pageLabel);
    }

    let allLabel = $("#cs_addition_select_all_results", root)?.closest("label");
    if (!allLabel) {
      allLabel = document.createElement("label");
      allLabel.className = "cs-prep-v12-check";
      allLabel.innerHTML = '<input id="cs_addition_select_all_results" type="checkbox"><span>Selecionar todo resultado</span>';
    }
    if (allLabel.parentElement !== selection) selection.appendChild(allLabel);

    let clear = $("#addition_preparation_clear_selection_v12", root);
    if (!clear) {
      clear = document.createElement("button");
      clear.id = "addition_preparation_clear_selection_v12";
      clear.type = "button";
      clear.className = "btn-secondary";
      clear.textContent = "Limpar seleção";
    }
    if (clear.parentElement !== selection) selection.appendChild(clear);

    let actions = $(":scope > .cs-prep-v12-actions", bulk);
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "cs-prep-v12-actions";
      bulk.appendChild(actions);
    }

    let count = $("#addition_preparation_selected_count", root);
    if (!count) {
      count = document.createElement("strong");
      count.id = "addition_preparation_selected_count";
      count.textContent = "0 selecionados";
    }
    count.classList.add("cs-prep-v12-selected-count");
    if (count.parentElement !== actions) actions.prepend(count);

    [$("#addition_prepare_selected", root), $("#addition_add_selected_from_prep", root)].filter(Boolean).forEach(button => {
      button.classList.remove("btn-secondary");
      button.classList.add("btn-success");
      if (button.id === "addition_add_selected_from_prep") button.textContent = "Adicionar selecionados à fila";
      if (button.parentElement !== actions) actions.appendChild(button);
    });
    return bulk;
  }

  function normalizeAddition() {
    const root = $("#addition_preparation_accordion");
    if (!root) return false;
    root.classList.add("cs-prep-v12");

    const header = $(":scope > summary", root);
    header?.classList.add("cs-prep-v12-header");
    $("#addition_preparation_summary", root)?.classList.add("cs-prep-v12-summary");

    const body = ensureBody(root, "cs_addition_preparation_v12_body");
    const description = canonicalDescription(
      root, body,
      "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os dados antes de enviá-los para a fila de adição."
    );

    const toolbar = $(".addition-toolbar", root);
    toolbar?.classList.add("cs-prep-v12-toolbar");
    const search = $("#addition_preparation_search", root);
    if (search) search.placeholder = "Nome ou WooCommerce ID";
    fieldFor(search);
    fieldFor($("#addition_preparation_state", root));
    $("#addition_preparation_refresh", root)?.classList.add("cs-prep-v12-refresh");

    const advanced = ensureAdditionAdvanced(root);
    const bulk = ensureAdditionBulk(root);

    const meta = $(".addition-list-meta", root);
    meta?.classList.add("cs-prep-v12-meta");
    const found = $("#addition_preparation_meta", root);
    found?.classList.add("cs-prep-v12-found");
    normalizeMetaText(found);
    const oldMetaLeft = $(".addition-list-meta-left", meta || root);
    if (found && meta && found.parentElement !== meta) meta.prepend(found);
    if (oldMetaLeft && !oldMetaLeft.children.length) oldMetaLeft.remove();

    const tableHead = $(".addition-table-head", root);
    tableHead?.classList.add("cs-prep-v12-table-head");
    const list = $("#addition_preparation_rows", root);
    list?.classList.add("cs-prep-v12-list");
    $(".addition-empty", list || root)?.classList.add("cs-prep-v12-empty");
    const pagination = $(".addition-pagination", root);
    pagination?.classList.add("cs-prep-v12-pagination");

    let feedback = $("#cs_addition_preparation_feedback", root);
    if (!feedback) {
      feedback = document.createElement("div");
      feedback.id = "cs_addition_preparation_feedback";
      feedback.setAttribute("aria-live", "polite");
    }

    [description, toolbar, advanced, bulk, meta, feedback, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });
    tableHead?.remove();
    syncAdditionRows();
    updateAdditionCount();
    return true;
  }

  function currentAdditionFilters() {
    return {
      q: $("#addition_preparation_search")?.value || "",
      state: $("#addition_preparation_state")?.value || "",
      version: $("#addition_preparation_version")?.value || "",
      relationship: $("#addition_preparation_relationship")?.value || "",
    };
  }

  function installFetchBridge() {
    if (window.__csPreparationV12FetchBridgeInstalled) return;
    window.__csPreparationV12FetchBridgeInstalled = true;
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      if (typeof input !== "string") return nativeFetch(input, init);
      try {
        const url = new URL(input, window.location.href);
        if (url.origin === window.location.origin && url.pathname === "/adicoes/operacoes" && url.searchParams.get("scope") === "preparation") {
          const filters = currentAdditionFilters();
          if (filters.version) url.searchParams.set("version", filters.version); else url.searchParams.delete("version");
          if (filters.relationship) url.searchParams.set("relationship", filters.relationship); else url.searchParams.delete("relationship");
          const next = input.startsWith("http") ? url.href : `${url.pathname}${url.search}`;
          return nativeFetch(next, init);
        }
      } catch (_error) {}
      return nativeFetch(input, init);
    };
  }

  function updateAdditionCount() {
    const count = additionSelection.ids.size;
    const node = $("#addition_preparation_selected_count");
    if (node) node.textContent = `${count} selecionado${count === 1 ? "" : "s"}`;
  }

  function syncAdditionRows() {
    const rows = $("#addition_preparation_rows");
    if (!rows) return;
    $$("[data-add-select=\"preparation\"]", rows).forEach(box => {
      const id = text(box.dataset.job);
      if (!id) return;
      const should = additionSelection.ids.has(id);
      if (box.checked !== should) {
        box.checked = should;
        box.dispatchEvent(new Event("change", {bubbles:true}));
      }
    });
    $(".addition-empty", rows)?.classList.add("cs-prep-v12-empty");
  }

  function clearAdditionSelection() {
    additionSelection.ids.clear();
    additionSelection.allIds.clear();
    additionSelection.allResults = false;
    const all = $("#cs_addition_select_all_results");
    if (all) all.checked = false;
    const page = $("#addition_preparation_select_all");
    if (page?.checked || page?.indeterminate) {
      page.checked = false;
      page.indeterminate = false;
      page.dispatchEvent(new Event("change", {bubbles:true}));
    }
    $$("#addition_preparation_rows [data-add-select=\"preparation\"]:checked").forEach(box => {
      box.checked = false;
      box.dispatchEvent(new Event("change", {bubbles:true}));
    });
    updateAdditionCount();
  }

  async function fetchAllAdditionIds() {
    const filters = currentAdditionFilters();
    const base = new URLSearchParams({scope:"preparation", q:filters.q, state:filters.state, page:"1", page_size:"100"});
    if (filters.version) base.set("version", filters.version);
    if (filters.relationship) base.set("relationship", filters.relationship);
    const first = await fetch(`/adicoes/operacoes?${base.toString()}`, {cache:"no-store", credentials:"same-origin"}).then(r => r.json());
    if (first?.ok === false) throw new Error(first.message || "Falha ao selecionar resultados.");
    const items = [...(Array.isArray(first?.items) ? first.items : [])];
    const pages = Math.max(1, Number(first?.pages || 1));
    if (pages > 1) {
      const calls = [];
      for (let page = 2; page <= pages; page += 1) {
        const params = new URLSearchParams(base); params.set("page", String(page));
        calls.push(fetch(`/adicoes/operacoes?${params.toString()}`, {cache:"no-store", credentials:"same-origin"}).then(r => r.json()));
      }
      const rest = await Promise.all(calls);
      rest.forEach(payload => items.push(...(Array.isArray(payload?.items) ? payload.items : [])));
    }
    return new Set(items.map(item => text(item?.job_id)).filter(Boolean));
  }

  function feedback(message, error = false) {
    const node = $("#cs_addition_preparation_feedback");
    if (!node) return;
    node.textContent = text(message);
    node.style.borderColor = error ? "rgba(239,68,68,.45)" : "";
    node.style.color = error ? "#fecaca" : "";
  }

  async function runAdditionBulk(endpoint, successMessage) {
    const ids = [...additionSelection.ids];
    if (!ids.length || additionSelection.busy) {
      if (!ids.length) feedback("Selecione ao menos um produto.", true);
      return;
    }
    additionSelection.busy = true;
    feedback(`Processando ${ids.length} produto(s)…`);
    try {
      const response = await fetch(endpoint, {
        method:"POST", credentials:"same-origin", cache:"no-store",
        headers:{"Content-Type":"application/json"}, body:JSON.stringify({job_ids:ids}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      feedback(payload?.message || successMessage);
      clearAdditionSelection();
      window.setTimeout(() => $("#addition_preparation_refresh")?.click(), 80);
    } catch (error) {
      feedback(error?.message || "Falha ao executar a operação.", true);
    } finally {
      additionSelection.busy = false;
    }
  }

  function resetAdditionAdvancedAndReload() {
    const search = $("#addition_preparation_search");
    const state = $("#addition_preparation_state");
    const version = $("#addition_preparation_version");
    const relationship = $("#addition_preparation_relationship");
    if (search) search.value = "";
    if (state) state.value = "";
    if (version) version.value = "";
    if (relationship) relationship.value = "";
    clearAdditionSelection();
    if (search) search.dispatchEvent(new Event("input", {bubbles:true}));
    if (state) state.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function bindEvents() {
    document.addEventListener("change", async event => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (!target) return;

      if (target.matches("#addition_preparation_rows [data-add-select=\"preparation\"]")) {
        const id = text(target.dataset.job);
        if (id) target.checked ? additionSelection.ids.add(id) : additionSelection.ids.delete(id);
        if (!target.checked && additionSelection.allResults) {
          additionSelection.allResults = false;
          $("#cs_addition_select_all_results")?.removeAttribute("checked");
        }
        updateAdditionCount();
        return;
      }

      if (target.id === "cs_addition_select_all_results") {
        if (!target.checked) {
          clearAdditionSelection();
          return;
        }
        feedback("Selecionando todos os resultados…");
        try {
          const ids = await fetchAllAdditionIds();
          additionSelection.ids = new Set(ids);
          additionSelection.allIds = new Set(ids);
          additionSelection.allResults = true;
          syncAdditionRows();
          updateAdditionCount();
          feedback(ids.size ? `${ids.size} resultado(s) selecionado(s).` : "Nenhum resultado disponível.");
        } catch (error) {
          target.checked = false;
          feedback(error?.message || "Falha ao selecionar resultados.", true);
        }
        return;
      }

      if (["addition_preparation_version", "addition_preparation_relationship"].includes(target.id)) {
        clearAdditionSelection();
        const search = $("#addition_preparation_search");
        search?.dispatchEvent(new Event("input", {bubbles:true}));
      }
      if (["addition_preparation_search", "addition_preparation_state"].includes(target.id)) clearAdditionSelection();
    }, true);

    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#addition_preparation_clear_filters_v12")) {
        event.preventDefault(); event.stopImmediatePropagation();
        resetAdditionAdvancedAndReload();
        return;
      }
      if (target.closest("#addition_preparation_clear_selection_v12")) {
        event.preventDefault(); event.stopImmediatePropagation();
        clearAdditionSelection();
        return;
      }
      if (target.closest("#addition_prepare_selected")) {
        event.preventDefault(); event.stopImmediatePropagation();
        runAdditionBulk("/adicoes/operacoes/preparar", "Preparação iniciada.");
        return;
      }
      if (target.closest("#addition_add_selected_from_prep")) {
        event.preventDefault(); event.stopImmediatePropagation();
        runAdditionBulk("/adicoes/fila/adicionar", "Produtos enviados à fila.");
      }
    }, true);
  }

  function observeLists() {
    const updateList = $("#updates_jobs");
    if (updateList && updateList.dataset.prepV12Observed !== "1") {
      updateList.dataset.prepV12Observed = "1";
      new MutationObserver(() => removeDuplicateUpdateEmpty(updateList)).observe(updateList, {childList:true});
    }
    const additionList = $("#addition_preparation_rows");
    if (additionList && additionList.dataset.prepV12Observed !== "1") {
      additionList.dataset.prepV12Observed = "1";
      new MutationObserver(() => {
        syncAdditionRows();
        updateAdditionCount();
        $(".addition-empty", additionList)?.classList.add("cs-prep-v12-empty");
        normalizeMetaText($("#addition_preparation_meta"));
      }).observe(additionList, {childList:true});
    }
  }

  function normalizeAll() {
    if (normalizing) return;
    normalizing = true;
    try {
      installStyles();
      normalizeUpdate();
      normalizeAddition();
      observeLists();
    } finally {
      normalizing = false;
    }
  }

  function schedule(delays = [0, 60, 180, 480, 1000]) {
    window.clearTimeout(scheduled);
    delays.forEach(delay => { scheduled = window.setTimeout(normalizeAll, delay); });
  }

  function start() {
    installFetchBridge();
    installStyles();
    bindEvents();
    normalizeAll();
    [80, 250, 700, 1600].forEach(delay => window.setTimeout(normalizeAll, delay));
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "adicoes") schedule();
    });
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => schedule());
    $("#tab_btn_adicoes")?.addEventListener("click", () => schedule());
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
