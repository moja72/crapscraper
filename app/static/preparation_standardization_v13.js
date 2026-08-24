(() => {
  "use strict";

  if (window.__crapScraperPreparationV13Installed) return;
  window.__crapScraperPreparationV13Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const additionSelection = {ids:new Set(), allResults:false, busy:false};
  let normalizing = false;

  function installStyles() {
    if ($("#cs-preparation-v13-style")) return;
    const style = document.createElement("style");
    style.id = "cs-preparation-v13-style";
    style.textContent = `
      /* Preparação v13: Atualizar e Adicionar compartilham a mesma estrutura visual. */
      #tab_panel_atualizacoes .cs-prep-v13,
      #tab_panel_adicoes .cs-prep-v13{
        width:100%!important;min-width:0!important;padding:16px 18px!important;
        border:1px solid var(--line)!important;border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;box-sizing:border-box!important;overflow:visible!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13>.cs-prep-v13-header,
      #tab_panel_adicoes .cs-prep-v13>.cs-prep-v13-header{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-height:32px!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;box-shadow:none!important;list-style:none!important;cursor:pointer!important;
      }
      #tab_panel_adicoes .cs-prep-v13>.cs-prep-v13-header::-webkit-details-marker{display:none!important}
      #tab_panel_atualizacoes .cs-prep-v13-header .standard-update-accordion-toggle-copy,
      #tab_panel_adicoes .cs-prep-v13-header .cs-op-summary-left{
        display:inline-flex!important;align-items:center!important;gap:8px!important;min-width:0!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-header .standard-update-accordion-title,
      #tab_panel_adicoes .cs-prep-v13-header .section-title{
        margin:0!important;color:var(--text)!important;font-size:16px!important;font-weight:850!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-summary,
      #tab_panel_adicoes .cs-prep-v13-summary{
        margin-left:auto!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13.is-collapsed>.cs-prep-v13-body{display:none!important}
      #tab_panel_adicoes .cs-prep-v13:not([open])>.cs-prep-v13-body{display:none!important}
      #tab_panel_atualizacoes .cs-prep-v13-body,
      #tab_panel_adicoes .cs-prep-v13-body{
        display:grid!important;gap:10px!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-description,
      #tab_panel_adicoes .cs-prep-v13-description{
        margin:10px 0 2px!important;padding:0!important;color:var(--text-muted)!important;font-size:11px!important;line-height:1.5!important;
      }

      /* 1. Buscar | Estado | Atualizar */
      #tab_panel_atualizacoes .cs-prep-v13-toolbar,
      #tab_panel_adicoes .cs-prep-v13-toolbar{
        display:grid!important;grid-template-columns:minmax(280px,1fr) minmax(180px,230px) auto!important;
        gap:10px!important;align-items:end!important;width:100%!important;min-width:0!important;margin:0!important;padding:0!important;
        border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-field,
      #tab_panel_adicoes .cs-prep-v13-field{
        display:grid!important;gap:6px!important;min-width:0!important;margin:0!important;color:var(--text-muted)!important;
        font-size:11px!important;font-weight:750!important;line-height:1.2!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-field>label,
      #tab_panel_adicoes .cs-prep-v13-field>label{margin:0!important;color:inherit!important;font:inherit!important}
      #tab_panel_atualizacoes .cs-prep-v13-field input,
      #tab_panel_atualizacoes .cs-prep-v13-field select,
      #tab_panel_adicoes .cs-prep-v13-field input,
      #tab_panel_adicoes .cs-prep-v13-field select{
        width:100%!important;min-width:0!important;min-height:46px!important;margin:0!important;padding:8px 13px!important;
        border:1px solid var(--line-strong)!important;border-radius:9px!important;background:var(--bg-input)!important;
        color:var(--text)!important;box-shadow:none!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-refresh,
      #tab_panel_adicoes .cs-prep-v13-refresh{
        min-width:108px!important;min-height:46px!important;margin:0!important;padding:0 16px!important;border-radius:9px!important;
      }

      /* 2. Versão | Relacionamento | Limpar filtros */
      #tab_panel_atualizacoes .cs-prep-v13-advanced,
      #tab_panel_adicoes .cs-prep-v13-advanced{
        display:grid!important;grid-template-columns:repeat(2,minmax(190px,1fr)) auto!important;gap:10px!important;align-items:end!important;
        width:100%!important;min-width:0!important;margin:0!important;padding:10px!important;
        border:1px solid var(--line)!important;border-radius:10px!important;background:rgba(255,255,255,.015)!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-advanced>button,
      #tab_panel_adicoes .cs-prep-v13-advanced>button{min-height:46px!important;margin:0!important;padding:0 16px!important;border-radius:9px!important}

      /* 3. Metadados */
      #tab_panel_atualizacoes .cs-prep-v13-meta,
      #tab_panel_adicoes .cs-prep-v13-meta{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;
        width:100%!important;min-height:34px!important;margin:0!important;padding:0 2px!important;border:0!important;background:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-found,
      #tab_panel_adicoes .cs-prep-v13-found{margin:0!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:700!important}
      #tab_panel_atualizacoes .cs-prep-v13-meta .listing-page-size,
      #tab_panel_adicoes .cs-prep-v13-meta .listing-page-size{
        display:inline-flex!important;align-items:center!important;gap:8px!important;margin-left:auto!important;color:var(--text-soft)!important;
        font-size:11px!important;font-weight:700!important;white-space:nowrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-meta .listing-page-size input,
      #tab_panel_adicoes .cs-prep-v13-meta .listing-page-size input{
        width:58px!important;min-width:58px!important;min-height:32px!important;margin:0!important;padding:4px 7px!important;text-align:center!important;
      }

      /* 4. Seleção e ações */
      #tab_panel_atualizacoes .cs-prep-v13-bulk,
      #tab_panel_adicoes .cs-prep-v13-bulk{
        display:flex!important;align-items:center!important;justify-content:space-between!important;gap:14px!important;
        width:100%!important;min-width:0!important;min-height:60px!important;margin:0!important;padding:10px 12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.022)!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-selection,
      #tab_panel_adicoes .cs-prep-v13-selection{
        display:flex!important;align-items:center!important;gap:12px!important;flex:1 1 auto!important;min-width:0!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-check,
      #tab_panel_adicoes .cs-prep-v13-check{
        display:inline-flex!important;align-items:center!important;gap:7px!important;margin:0!important;color:var(--text-soft)!important;
        font-size:11px!important;font-weight:750!important;white-space:nowrap!important;cursor:pointer!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-check input[type=checkbox],
      #tab_panel_adicoes .cs-prep-v13-check input[type=checkbox]{width:17px!important;height:17px!important;min-height:0!important;margin:0!important;accent-color:#7c3aed!important}
      #tab_panel_atualizacoes .cs-prep-v13-actions,
      #tab_panel_adicoes .cs-prep-v13-actions{
        display:flex!important;align-items:center!important;justify-content:flex-end!important;gap:8px!important;flex:0 0 auto!important;
        margin-left:auto!important;flex-wrap:wrap!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-selected-count,
      #tab_panel_adicoes .cs-prep-v13-selected-count{margin-right:2px!important;color:var(--text-muted)!important;font-size:11px!important;font-weight:750!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-prep-v13-actions button,
      #tab_panel_adicoes .cs-prep-v13-actions button{min-height:40px!important;padding:0 14px!important;border-radius:9px!important;white-space:nowrap!important}
      #tab_panel_atualizacoes .cs-prep-v13-actions .btn-success,
      #tab_panel_adicoes .cs-prep-v13-actions .btn-success{
        background:linear-gradient(135deg,#7c3aed,#6d28d9)!important;border-color:#8b5cf6!important;color:#fff!important;box-shadow:0 0 22px rgba(124,58,237,.15)!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-actions .btn-success:hover:not(:disabled),
      #tab_panel_adicoes .cs-prep-v13-actions .btn-success:hover:not(:disabled){filter:brightness(1.08)!important}
      #tab_panel_atualizacoes .cs-prep-v13-actions .btn-success:disabled,
      #tab_panel_adicoes .cs-prep-v13-actions .btn-success:disabled{opacity:.45!important;filter:saturate(.7)!important;box-shadow:none!important}
      #tab_panel_atualizacoes .cs-preparation-original-bulk-triggers{display:none!important}

      /* Jobs: mesma moldura; ação individual continua verde. */
      #tab_panel_atualizacoes .cs-prep-v13-list,
      #tab_panel_adicoes .cs-prep-v13-list{display:grid!important;gap:8px!important;width:100%!important;min-width:0!important;margin:0!important}
      #tab_panel_atualizacoes .cs-prep-v13-list>.update-job,
      #tab_panel_adicoes .cs-prep-v13-list>.addition-op-row{
        width:100%!important;min-width:0!important;margin:0!important;padding:12px!important;
        border:1px solid var(--line)!important;border-radius:11px!important;background:rgba(255,255,255,.014)!important;box-shadow:none!important;box-sizing:border-box!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-list>.update-job{display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(140px,180px) minmax(220px,auto)!important;gap:12px!important;align-items:center!important}
      #tab_panel_adicoes .cs-prep-v13-list>.addition-op-row{display:grid!important;grid-template-columns:30px minmax(280px,1fr) minmax(180px,.8fr) minmax(155px,.7fr) minmax(210px,auto)!important;gap:12px!important;align-items:center!important}
      #tab_panel_atualizacoes .cs-prep-v13-list .update-prepare.btn-success,
      #tab_panel_adicoes .cs-prep-v13-list .addition-op-actions .btn-success{background:var(--success)!important;border-color:rgba(16,185,129,.55)!important;color:#04130e!important;box-shadow:0 0 24px rgba(16,185,129,.12)!important}
      #tab_panel_atualizacoes .cs-prep-v13-empty,
      #tab_panel_adicoes .cs-prep-v13-empty,
      #tab_panel_atualizacoes .cs-prep-v13-list>.notice,
      #tab_panel_adicoes .cs-prep-v13-list>.addition-empty,
      #tab_panel_adicoes .cs-prep-v13-list>.addition-loading{
        display:grid!important;place-items:center!important;width:100%!important;min-height:88px!important;margin:0!important;padding:18px!important;
        border:1px dashed var(--line-strong)!important;border-radius:11px!important;background:rgba(255,255,255,.012)!important;
        color:var(--text-muted)!important;text-align:center!important;box-sizing:border-box!important;
      }
      #tab_panel_adicoes .addition-table-head{display:none!important}

      /* Paginação */
      #tab_panel_atualizacoes .cs-prep-v13-pagination,
      #tab_panel_adicoes .cs-prep-v13-pagination{
        display:grid!important;grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
        gap:10px!important;align-items:center!important;width:100%!important;min-width:0!important;margin:2px 0 0!important;padding:0!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-pagination>button,
      #tab_panel_adicoes .cs-prep-v13-pagination>button{width:100%!important;min-height:42px!important;margin:0!important}
      #tab_panel_atualizacoes .cs-prep-v13-pagination .badge,
      #tab_panel_adicoes .cs-prep-v13-pagination .badge{justify-self:center!important;white-space:nowrap!important}
      #cs_addition_preparation_feedback_v13:empty{display:none!important}
      #cs_addition_preparation_feedback_v13{margin:0!important;padding:8px 10px!important;border:1px solid var(--line)!important;border-radius:8px!important;color:var(--text-muted)!important;font-size:11px!important}

      @media(max-width:900px){
        #tab_panel_atualizacoes .cs-prep-v13-toolbar,#tab_panel_adicoes .cs-prep-v13-toolbar,
        #tab_panel_atualizacoes .cs-prep-v13-advanced,#tab_panel_adicoes .cs-prep-v13-advanced{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-prep-v13-refresh,#tab_panel_adicoes .cs-prep-v13-refresh,
        #tab_panel_atualizacoes .cs-prep-v13-advanced>button,#tab_panel_adicoes .cs-prep-v13-advanced>button{width:100%!important}
        #tab_panel_atualizacoes .cs-prep-v13-bulk,#tab_panel_adicoes .cs-prep-v13-bulk{align-items:stretch!important;flex-direction:column!important}
        #tab_panel_atualizacoes .cs-prep-v13-actions,#tab_panel_adicoes .cs-prep-v13-actions{width:100%!important;margin-left:0!important;justify-content:flex-start!important}
        #tab_panel_atualizacoes .cs-prep-v13-list>.update-job,#tab_panel_adicoes .cs-prep-v13-list>.addition-op-row{grid-template-columns:30px minmax(0,1fr)!important;align-items:start!important}
      }
      @media(max-width:620px){
        #tab_panel_atualizacoes .cs-prep-v13-pagination,#tab_panel_adicoes .cs-prep-v13-pagination{grid-template-columns:1fr!important}
        #tab_panel_atualizacoes .cs-prep-v13-meta,#tab_panel_adicoes .cs-prep-v13-meta{align-items:flex-start!important;flex-direction:column!important}
        #tab_panel_atualizacoes .cs-prep-v13-meta .listing-page-size,#tab_panel_adicoes .cs-prep-v13-meta .listing-page-size{margin-left:0!important}
      }
    `;
    document.head.appendChild(style);
  }

  function addFieldClass(control) {
    if (!control) return null;
    const field = control.closest("label,.field") || control.parentElement;
    if (field) field.classList.add("cs-prep-v13-field");
    return field;
  }

  function removeLegacyBodies(root, keep) {
    $$('[id^="cs_updates_preparation_v12_body"],[id^="cs_addition_preparation_v12_body"],#cs_addition_preparation_body', root).forEach(node => {
      if (node === keep) return;
      Array.from(node.children).forEach(child => {
        if (!keep.contains(child)) keep.appendChild(child);
      });
      node.remove();
    });
  }

  function ensureBody(root, id) {
    let body = $(`#${id}`, root);
    if (!body) {
      body = document.createElement("div");
      body.id = id;
      root.appendChild(body);
    }
    body.className = "cs-prep-v13-body";
    body.removeAttribute("hidden");
    removeLegacyBodies(root, body);
    return body;
  }

  function ensureDescription(root, body, value) {
    $$(".cs-preparation-description,.cs-v4-preparation-hint,.addition-section-hint,.cs-op-section-hint,.cs-prep-v12-description,.cs-prep-v13-description", root)
      .filter(node => node.parentElement !== body || !node.classList.contains("cs-prep-v13-description"))
      .forEach(node => node.remove());
    let description = $(":scope > .cs-prep-v13-description", body);
    if (!description) {
      description = document.createElement("div");
      description.className = "cs-prep-v13-description";
      body.prepend(description);
    }
    description.textContent = value;
    return description;
  }

  function removeDuplicateEmpty(list) {
    if (!list) return;
    const seen = new Set();
    $$(":scope > .notice,:scope > .addition-empty", list).forEach(node => {
      const key = clean(node.textContent).toLowerCase();
      if (!key) return;
      if (seen.has(key)) node.remove();
      else {
        seen.add(key);
        node.classList.add("cs-prep-v13-empty");
        node.hidden = false;
      }
    });
  }

  function normalizeFoundText(node) {
    if (!node) return;
    const raw = clean(node.textContent);
    if (/^Mostrando\s+\d+[–-]\d+\s+de\s+\d+\s+itens?$/i.test(raw)) return;
    const simple = raw.match(/^(\d+)\s+itens?(?:\s+encontrados?)?$/i);
    if (!simple) return;
    const total = Number(simple[1]);
    node.textContent = total ? `Mostrando 1–${total} de ${total} itens` : "0 itens encontrados";
  }

  function normalizeHeader(root, header, summary) {
    root.classList.add("cs-prep-v13");
    root.classList.remove("cs-prep-v12");
    header?.classList.add("cs-prep-v13-header");
    summary?.classList.add("cs-prep-v13-summary");
  }

  function normalizeUpdate() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root) return false;
    const header = $(":scope > .standard-update-accordion-toggle", root);
    normalizeHeader(root, header, $("#cs_v4_update_preparation_summary", root));
    const body = ensureBody(root, "cs_updates_preparation_v13_body");
    const description = ensureDescription(root, body, "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os planos antes de enviá-los para a fila de atualização.");

    const toolbar = $(".updates-filters", root);
    toolbar?.classList.add("cs-prep-v13-toolbar");
    addFieldClass($("#updates_search_filter", root));
    addFieldClass($("#updates_status_filter", root));
    const refresh = $(".cs-v4-preparation-refresh", toolbar || root) || toolbar?.querySelector("button");
    refresh?.classList.add("cs-prep-v13-refresh");

    const advanced = $(".cs-v4-preparation-advanced", root) || $(".cs-preparation-advanced", root);
    advanced?.classList.add("cs-prep-v13-advanced");
    addFieldClass($("#updates_version_filter", root));
    addFieldClass($("#updates_relationship_filter", root));

    const meta = $(".listing-meta-row", root);
    meta?.classList.add("cs-prep-v13-meta");
    $("#updates_found_count", root)?.classList.add("cs-prep-v13-found");

    const bulk = $(".updates-bulkbar", root);
    bulk?.classList.add("cs-prep-v13-bulk");
    const selection = $(".cs-preparation-selection", bulk || root);
    selection?.classList.add("cs-prep-v13-selection");
    $$("label", selection || document).forEach(label => label.classList.add("cs-prep-v13-check"));
    const actions = $(".cs-preparation-actions", bulk || root);
    actions?.classList.add("cs-prep-v13-actions");
    $("#updates_selected_count", root)?.classList.add("cs-prep-v13-selected-count");

    const progress = $("#updates_batch_progress", root);
    const list = $("#updates_jobs", root);
    list?.classList.add("cs-prep-v13-list");
    removeDuplicateEmpty(list);
    const pagination = $(".listing-pagination", root);
    pagination?.classList.add("cs-prep-v13-pagination");

    [description, toolbar, advanced, meta, bulk, progress, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });

    $("#updates_working_controls", root)?.setAttribute("hidden", "");
    $(".cs-v4-preparation-head", root)?.setAttribute("hidden", "");
    $$(':scope > .cs-prep-v12-body', root).forEach(node => node.remove());
    return true;
  }

  function ensureAdditionAdvanced(root) {
    let advanced = $("#addition_preparation_advanced_v13", root) || $("#addition_preparation_advanced_v12", root);
    if (!advanced) {
      advanced = document.createElement("div");
      advanced.innerHTML = `
        <label>Versão<select id="addition_preparation_version"><option value="">Todas</option><option value="has_version">Com versão informada</option><option value="missing_version">Sem versão informada</option></select></label>
        <label>Relacionamento<select id="addition_preparation_relationship"><option value="">Todos</option><option value="new_product">Novo produto</option><option value="woo_linked">Com WooCommerce ID</option></select></label>
        <button class="btn-secondary" id="addition_preparation_clear_filters_v13" type="button">Limpar filtros</button>`;
    }
    advanced.id = "addition_preparation_advanced_v13";
    advanced.className = "cs-prep-v13-advanced";
    addFieldClass($("#addition_preparation_version", advanced));
    addFieldClass($("#addition_preparation_relationship", advanced));
    return advanced;
  }

  function canonicalAdditionBulk(root) {
    let bulk = $(".addition-bulk-actions", root);
    if (!bulk) {
      bulk = document.createElement("div");
      root.appendChild(bulk);
    }
    bulk.className = "addition-bulk-actions cs-prep-v13-bulk";

    $$("button", bulk).filter(button => clean(button.textContent).toLowerCase() === "limpar seleção").forEach(button => button.remove());
    $$(".cs-preparation-selection,.cs-prep-v12-selection,.cs-prep-v12-actions,.cs-preparation-actions", bulk).forEach(wrapper => {
      Array.from(wrapper.children).forEach(child => bulk.appendChild(child));
      wrapper.remove();
    });

    let selection = $(":scope > .cs-prep-v13-selection", bulk);
    if (!selection) {
      selection = document.createElement("div");
      selection.className = "cs-prep-v13-selection";
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
      pageLabel.className = "cs-prep-v13-check";
      const textNode = Array.from(pageLabel.childNodes).find(node => node.nodeType === Node.TEXT_NODE);
      if (textNode) textNode.textContent = " Selecionar página";
      selection.appendChild(pageLabel);
    }

    let all = $("#cs_addition_select_all_results", root);
    let allLabel = all?.closest("label");
    if (!all) {
      all = document.createElement("input");
      all.type = "checkbox";
      all.id = "cs_addition_select_all_results";
    }
    if (!allLabel) {
      allLabel = document.createElement("label");
      allLabel.append(all, document.createElement("span"));
      allLabel.lastElementChild.textContent = "Selecionar todo resultado";
    }
    allLabel.className = "cs-prep-v13-check";
    selection.appendChild(allLabel);

    let clear = $("#addition_preparation_clear_selection_v13", root);
    if (!clear) {
      clear = document.createElement("button");
      clear.id = "addition_preparation_clear_selection_v13";
      clear.type = "button";
      clear.className = "btn-secondary";
      clear.textContent = "Limpar seleção";
    }
    selection.appendChild(clear);

    let actions = $(":scope > .cs-prep-v13-actions", bulk);
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "cs-prep-v13-actions";
      bulk.appendChild(actions);
    }
    let count = $("#addition_preparation_selected_count", root);
    if (!count) {
      count = document.createElement("strong");
      count.id = "addition_preparation_selected_count";
      count.textContent = "0 selecionados";
    }
    count.className = "cs-prep-v13-selected-count";
    actions.appendChild(count);

    const prepare = $("#addition_prepare_selected", root);
    const enqueue = $("#addition_add_selected_from_prep", root);
    [prepare, enqueue].filter(Boolean).forEach(button => {
      button.classList.remove("btn-secondary");
      button.classList.add("btn-success");
      actions.appendChild(button);
    });
    if (enqueue) enqueue.textContent = "Adicionar selecionados à fila";
    return bulk;
  }

  function normalizeAddition() {
    const root = $("#addition_preparation_accordion");
    if (!root) return false;
    const header = $(":scope > summary", root);
    normalizeHeader(root, header, $("#addition_preparation_summary", root));
    const body = ensureBody(root, "cs_addition_preparation_v13_body");
    const description = ensureDescription(root, body, "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os dados antes de enviá-los para a fila de adição.");

    const toolbar = $(".addition-toolbar", root);
    toolbar?.classList.add("cs-prep-v13-toolbar");
    const search = $("#addition_preparation_search", root);
    if (search) search.placeholder = "Nome ou WooCommerce ID";
    addFieldClass(search);
    addFieldClass($("#addition_preparation_state", root));
    $("#addition_preparation_refresh", root)?.classList.add("cs-prep-v13-refresh");

    const advanced = ensureAdditionAdvanced(root);

    const meta = $(".addition-list-meta", root);
    meta?.classList.add("cs-prep-v13-meta");
    const found = $("#addition_preparation_meta", root);
    found?.classList.add("cs-prep-v13-found");
    normalizeFoundText(found);
    if (found && meta && found.parentElement !== meta) meta.prepend(found);
    const metaLeft = $(".addition-list-meta-left", meta || root);
    if (metaLeft) {
      Array.from(metaLeft.children).forEach(child => {
        if (child !== found && child.id !== "addition_preparation_select_all") return;
      });
      if (!metaLeft.children.length) metaLeft.remove();
    }

    const bulk = canonicalAdditionBulk(root);
    const tableHead = $(".addition-table-head", root);
    tableHead?.remove();
    const list = $("#addition_preparation_rows", root);
    list?.classList.add("cs-prep-v13-list");
    removeDuplicateEmpty(list);
    const pagination = $(".addition-pagination", root);
    pagination?.classList.add("cs-prep-v13-pagination");

    let feedback = $("#cs_addition_preparation_feedback_v13", root);
    if (!feedback) {
      feedback = document.createElement("div");
      feedback.id = "cs_addition_preparation_feedback_v13";
      feedback.setAttribute("aria-live", "polite");
    }

    [description, toolbar, advanced, meta, bulk, feedback, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });
    $$(':scope > .cs-prep-v12-body,#cs_addition_preparation_body', root).forEach(node => node.remove());
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
    if (window.__csPreparationV13FetchBridgeInstalled) return;
    window.__csPreparationV13FetchBridgeInstalled = true;
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
      const id = clean(box.dataset.job);
      if (!id) return;
      const desired = additionSelection.ids.has(id);
      if (box.checked !== desired) {
        box.checked = desired;
        box.dispatchEvent(new Event("change", {bubbles:true}));
      }
    });
    removeDuplicateEmpty(rows);
  }

  function clearAdditionSelection() {
    additionSelection.ids.clear();
    additionSelection.allResults = false;
    const all = $("#cs_addition_select_all_results");
    if (all) all.checked = false;
    const page = $("#addition_preparation_select_all");
    if (page) { page.checked = false; page.indeterminate = false; }
    $$("#addition_preparation_rows [data-add-select=\"preparation\"]:checked").forEach(box => {
      box.checked = false;
      box.dispatchEvent(new Event("change", {bubbles:true}));
    });
    updateAdditionCount();
  }

  async function fetchAllAdditionIds() {
    const filters = currentAdditionFilters();
    const base = new URLSearchParams({scope:"preparation",q:filters.q,state:filters.state,page:"1",page_size:"100"});
    if (filters.version) base.set("version", filters.version);
    if (filters.relationship) base.set("relationship", filters.relationship);
    const first = await fetch(`/adicoes/operacoes?${base}`, {cache:"no-store",credentials:"same-origin"}).then(r => r.json());
    if (first?.ok === false) throw new Error(first.message || "Falha ao selecionar resultados.");
    const items = [...(Array.isArray(first?.items) ? first.items : [])];
    const pages = Math.max(1, Number(first?.pages || 1));
    for (let page = 2; page <= pages; page += 1) {
      const params = new URLSearchParams(base); params.set("page", String(page));
      const payload = await fetch(`/adicoes/operacoes?${params}`, {cache:"no-store",credentials:"same-origin"}).then(r => r.json());
      items.push(...(Array.isArray(payload?.items) ? payload.items : []));
    }
    return new Set(items.map(item => clean(item?.job_id)).filter(Boolean));
  }

  function feedback(message, error = false) {
    const node = $("#cs_addition_preparation_feedback_v13");
    if (!node) return;
    node.textContent = clean(message);
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
      const response = await fetch(endpoint, {method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({job_ids:ids})});
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

  function resetAdditionFilters() {
    ["addition_preparation_search","addition_preparation_state","addition_preparation_version","addition_preparation_relationship"].forEach(id => {
      const control = $(`#${id}`); if (control) control.value = "";
    });
    clearAdditionSelection();
    $("#addition_preparation_search")?.dispatchEvent(new Event("input", {bubbles:true}));
    $("#addition_preparation_state")?.dispatchEvent(new Event("change", {bubbles:true}));
  }

  function bindEvents() {
    document.addEventListener("change", async event => {
      const target = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement ? event.target : null;
      if (!target) return;
      if (target.matches('#addition_preparation_rows [data-add-select="preparation"]')) {
        const id = clean(target.dataset.job);
        if (id) target.checked ? additionSelection.ids.add(id) : additionSelection.ids.delete(id);
        if (!target.checked) {
          additionSelection.allResults = false;
          const all = $("#cs_addition_select_all_results"); if (all) all.checked = false;
        }
        updateAdditionCount();
        return;
      }
      if (target.id === "addition_preparation_select_all") {
        $$('#addition_preparation_rows [data-add-select="preparation"]').forEach(box => {
          box.checked = target.checked;
          const id = clean(box.dataset.job);
          if (id) target.checked ? additionSelection.ids.add(id) : additionSelection.ids.delete(id);
          box.dispatchEvent(new Event("change", {bubbles:true}));
        });
        updateAdditionCount();
        return;
      }
      if (target.id === "cs_addition_select_all_results") {
        if (!target.checked) { clearAdditionSelection(); return; }
        feedback("Selecionando todos os resultados…");
        try {
          additionSelection.ids = await fetchAllAdditionIds();
          additionSelection.allResults = true;
          syncAdditionRows(); updateAdditionCount();
          feedback(additionSelection.ids.size ? `${additionSelection.ids.size} resultado(s) selecionado(s).` : "Nenhum resultado disponível.");
        } catch (error) {
          target.checked = false;
          feedback(error?.message || "Falha ao selecionar resultados.", true);
        }
        return;
      }
      if (["addition_preparation_version","addition_preparation_relationship"].includes(target.id)) {
        clearAdditionSelection();
        $("#addition_preparation_search")?.dispatchEvent(new Event("input", {bubbles:true}));
      }
      if (["addition_preparation_search","addition_preparation_state"].includes(target.id)) clearAdditionSelection();
    }, true);

    document.addEventListener("input", event => {
      if (event.target?.id === "addition_preparation_search") clearAdditionSelection();
    }, true);

    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#addition_preparation_clear_filters_v13")) {
        event.preventDefault(); event.stopImmediatePropagation(); resetAdditionFilters(); return;
      }
      if (target.closest("#addition_preparation_clear_selection_v13")) {
        event.preventDefault(); event.stopImmediatePropagation(); clearAdditionSelection(); return;
      }
      if (target.closest("#addition_prepare_selected")) {
        event.preventDefault(); event.stopImmediatePropagation(); runAdditionBulk("/adicoes/operacoes/preparar", "Preparação iniciada."); return;
      }
      if (target.closest("#addition_add_selected_from_prep")) {
        event.preventDefault(); event.stopImmediatePropagation(); runAdditionBulk("/adicoes/fila/adicionar", "Produtos enviados à fila.");
      }
    }, true);
  }

  function observeDynamicAreas() {
    const updateList = $("#updates_jobs");
    if (updateList && updateList.dataset.prepV13Observed !== "1") {
      updateList.dataset.prepV13Observed = "1";
      new MutationObserver(() => removeDuplicateEmpty(updateList)).observe(updateList, {childList:true});
    }
    const additionList = $("#addition_preparation_rows");
    if (additionList && additionList.dataset.prepV13Observed !== "1") {
      additionList.dataset.prepV13Observed = "1";
      new MutationObserver(() => { syncAdditionRows(); normalizeFoundText($("#addition_preparation_meta")); }).observe(additionList, {childList:true});
    }
  }

  function normalizeAll() {
    if (normalizing) return;
    normalizing = true;
    try {
      installStyles();
      normalizeUpdate();
      normalizeAddition();
      observeDynamicAreas();
    } finally { normalizing = false; }
  }

  function schedule() {
    [0,60,180,480].forEach(delay => window.setTimeout(normalizeAll, delay));
  }

  function start() {
    installFetchBridge(); installStyles(); bindEvents(); normalizeAll();
    [80,250,700].forEach(delay => window.setTimeout(normalizeAll, delay));
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "adicoes") schedule();
    });
    $("#tab_btn_atualizacoes")?.addEventListener("click", schedule);
    $("#tab_btn_adicoes")?.addEventListener("click", schedule);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
