(() => {
  "use strict";

  if (window.__crapScraperPreparationFlowGateV10Installed) return;
  window.__crapScraperPreparationFlowGateV10Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if ($("#cs-preparation-flow-gate-v10-style")) return;
    const style = document.createElement("style");
    style.id = "cs-preparation-flow-gate-v10-style";
    style.textContent = `
      /* V10: Atualizar e Adicionar compartilham o mesmo casco de Preparação. */
      #tab_panel_atualizacoes .cs-preparation-unified,
      #tab_panel_adicoes .cs-preparation-unified{
        box-sizing:border-box!important;
        width:100%!important;
      }
      #tab_panel_atualizacoes .cs-preparation-unified>[data-cs-preparation-role="body"],
      #tab_panel_adicoes .cs-preparation-unified>[data-cs-preparation-role="body"]{
        width:100%!important;
      }
      #tab_panel_atualizacoes .cs-preparation-unified [data-cs-preparation-role="actions"],
      #tab_panel_adicoes .cs-preparation-unified [data-cs-preparation-role="actions"]{
        margin-left:auto!important;
      }
      #addition_preparation_rows .addition-op-row[data-cs-preparation-ready="0"] [data-add-action="add"]{
        display:none!important;
      }
    `;
    document.head.appendChild(style);
  }

  function markRole(root, selector, role) {
    const node = $(selector, root);
    if (node) node.dataset.csPreparationRole = role;
    return node;
  }

  function normalizeRoot(root, kind) {
    if (!root) return;
    root.classList.add(
      "cs-preparation-canonical",
      "cs-preparation-unified",
      "cs-preparation-flow-v10",
      `cs-preparation-flow-v10-${kind}`,
    );
    root.dataset.csPreparationComponent = "preparation";
    root.dataset.csPreparationContext = kind;

    markRole(root, ":scope > .cs-preparation-header, :scope > summary, :scope > .standard-update-accordion-toggle", "header");
    markRole(root, ":scope > .cs-preparation-canonical-body", "body");
    markRole(root, ".cs-preparation-toolbar", "toolbar");
    markRole(root, ".cs-preparation-advanced", "advanced");
    markRole(root, ".cs-preparation-meta", "meta");
    markRole(root, ".cs-preparation-bulk", "bulk");
    markRole(root, ".cs-preparation-actions", "actions");
    markRole(root, ".cs-preparation-list", "list");
    markRole(root, ".cs-preparation-pagination", "pagination");
  }

  function setButton(id, label, title = "") {
    const button = $(`#${id}`);
    if (!button) return;
    if (button.textContent !== label) button.textContent = label;
    if (title) button.title = title;
  }

  function normalizeButtons() {
    setButton("updates_prepare_selected", "Preparar selecionados",
      "Valida os itens e gera os planos. Não adiciona à fila e não executa alterações.");
    setButton("updates_enqueue_selected", "Adicionar selecionados à fila",
      "Move somente itens com plano pronto para a fila. A execução continua separada.");
    setButton("addition_prepare_selected", "Preparar selecionados",
      "Prepara conteúdo, imagem, categoria, preços e ZIP. Não cadastra no WooCommerce.");
    setButton("addition_add_selected_from_prep", "Adicionar selecionados à fila",
      "Move somente produtos já preparados para a fila. A execução continua separada.");
    setButton("addition_queue_add_selected", "Adicionar selecionados à fila",
      "Move somente produtos preparados para a fila.");
  }

  function normalizeAdditionRows() {
    $$("#addition_preparation_rows .addition-op-row").forEach(row => {
      const state = text($(".addition-state-badge", row)?.textContent).toLowerCase();
      const ready = state === "pronto";
      row.dataset.csPreparationReady = ready ? "1" : "0";
      const add = $("[data-add-action=\"add\"]", row);
      if (add) {
        add.textContent = "Adicionar à fila";
        add.title = ready
          ? "Produto preparado: adicionar à fila sem iniciar a execução."
          : "Conclua a Preparação antes de adicionar à fila.";
        add.disabled = !ready;
        add.hidden = !ready;
      }
    });
  }

  function sync() {
    normalizeRoot($("#tab_panel_atualizacoes .updates-working-card"), "update");
    normalizeRoot($("#addition_preparation_accordion"), "addition");
    normalizeButtons();
    normalizeAdditionRows();
  }

  let timers = [];
  function burst(delays = [0, 80, 250, 700, 1500, 3000]) {
    timers.forEach(id => window.clearTimeout(id));
    timers = delays.map(delay => window.setTimeout(sync, delay));
  }

  function bindHooks() {
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest(
        "#tab_btn_atualizacoes,#tab_btn_adicoes," +
        "#updates_refresh_btn,#updates_prepare_selected,#updates_enqueue_selected," +
        "#addition_preparation_refresh,#addition_prepare_selected,#addition_add_selected_from_prep"
      )) burst();
    }, true);

    document.addEventListener("change", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.matches("#updates_status_filter,#addition_preparation_state,#addition_preparation_select_all,[data-add-select=\"preparation\"]")) {
        burst([0, 120, 500]);
      }
    }, true);

    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "adicoes") burst();
    });
  }

  function start() {
    installStyles();
    bindHooks();
    burst();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
