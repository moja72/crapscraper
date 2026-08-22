(() => {
  "use strict";

  if (window.__crapScraperPreparationCanonicalV8CleanupInstalled) return;
  window.__crapScraperPreparationCanonicalV8CleanupInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function cleanUpdatePreparation() {
    const root = $("#tab_panel_atualizacoes .updates-working-card.cs-preparation-canonical");
    if (!root) return;

    const body = $("#cs_updates_preparation_body", root);
    const canonicalHeader = $(":scope > .standard-update-accordion-toggle.cs-preparation-header", root);

    /* O antigo cabeçalho interno deixa de participar do layout. */
    $$(":scope > .cs-preparation-header", root).forEach(node => {
      if (node !== canonicalHeader) node.hidden = true;
    });

    /* Só a descrição que foi movida para o body canônico permanece visível. */
    $$(":scope > .cs-preparation-description", root).forEach(node => {
      if (!body?.contains(node)) node.remove();
    });

    /* Evita a mensagem vazia duplicada que existia no renderer legado. */
    const list = $("#updates_jobs", root);
    if (list) {
      const seen = new Set();
      $$(":scope > .notice", list).forEach(node => {
        const key = text(node.textContent);
        if (!key) return;
        if (seen.has(key)) node.remove();
        else seen.add(key);
      });
    }
  }

  function cleanAdditionPreparation() {
    const root = $("#addition_preparation_accordion.cs-preparation-canonical");
    if (!root) return;
    $$(":scope > .addition-section-hint", root).forEach(node => node.remove());
    const tableHead = $(".addition-table-head", root);
    if (tableHead) tableHead.classList.add("cs-preparation-table-head");
  }

  function run() {
    cleanUpdatePreparation();
    cleanAdditionPreparation();
  }

  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(run, 0);
  }

  function start() {
    run();
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("#tab_btn_atualizacoes,#tab_btn_adicoes,#updates_refresh_btn,#addition_preparation_refresh")) schedule();
    }, true);
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes" || key === "adicoes") schedule();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
