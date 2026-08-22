(() => {
  "use strict";

  if (window.__crapScraperPanelLayoutStandardizationInstalled) return;
  window.__crapScraperPanelLayoutStandardizationInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const addClasses = (node, ...names) => {
    if (node) node.classList.add(...names.filter(Boolean));
    return node;
  };

  function installStyles() {
    if ($("#cs-panel-layout-standardization-style")) return;
    const style = document.createElement("style");
    style.id = "cs-panel-layout-standardization-style";
    style.textContent = `
      :root{--cs-operational-control-height:44px;--cs-operational-gap:12px;--cs-operational-section-gap:16px}
      #tab_panel_atualizacoes,#tab_panel_adicoes{--cs-operational-card-padding:18px}
      .cs-operational-stack{display:grid;gap:var(--cs-operational-section-gap)}
      .cs-operational-section.card{margin:0;padding:var(--cs-operational-card-padding);border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg-elev-1);overflow:visible}
      details.cs-operational-section>summary{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:48px;margin:calc(-1 * var(--cs-operational-card-padding));margin-bottom:0;padding:0 var(--cs-operational-card-padding);cursor:pointer;list-style:none}
      details.cs-operational-section>summary::-webkit-details-marker{display:none}
      details.cs-operational-section[open]>summary{margin-bottom:8px;border-bottom:1px solid var(--line)}
      .cs-operational-section-title{display:inline-flex;align-items:center;gap:8px;min-width:0}
      .cs-operational-section-title .section-title{margin:0;font-size:16px;line-height:1.3}
      .cs-operational-section-meta{margin-left:auto;text-align:right;font-size:11px;line-height:1.4}
      .cs-operational-section-hint{margin:0 0 14px;color:var(--text-muted);font-size:11px;line-height:1.55}
      .cs-operational-section[open]>summary .updates-disclosure-chevron{transform:rotate(90deg)}
      .cs-operational-heading-actions{display:flex;justify-content:flex-end;gap:8px;margin:0 0 12px}
      .cs-operational-heading-actions:empty{display:none}

      .cs-operational-filters{display:grid;grid-template-columns:minmax(260px,1fr) minmax(180px,240px) auto;gap:var(--cs-operational-gap);align-items:end;margin:12px 0}
      .cs-operational-filters--wide{grid-template-columns:minmax(260px,1.5fr) repeat(3,minmax(150px,.72fr)) auto}
      .cs-operational-filters--history{grid-template-columns:minmax(240px,1.35fr) minmax(170px,.65fr) minmax(220px,.9fr)}
      .cs-operational-filters label,.cs-operational-filters .field{display:grid;gap:6px;min-width:0;margin:0;color:var(--text-muted);font-size:12px;font-weight:700}
      .cs-operational-filters input,.cs-operational-filters select,.cs-operational-filters>button{width:100%;min-height:var(--cs-operational-control-height)}
      .cs-operational-filter-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px}
      .cs-operational-filter-actions button{min-height:var(--cs-operational-control-height)}

      .cs-operational-meta{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;margin:10px 0}
      .cs-operational-meta-left{display:flex;align-items:center;gap:12px;min-width:0;flex-wrap:wrap}
      .cs-operational-meta .small,.cs-operational-meta strong{margin:0;font-size:12px}
      .cs-operational-meta .listing-page-size{margin-left:auto}
      .cs-operational-meta .listing-page-size label{display:inline-flex;align-items:center;gap:6px;margin:0;color:var(--text-muted);font-size:12px;font-weight:700;white-space:nowrap}
      .cs-operational-meta .listing-page-size-input{width:58px;min-width:58px;min-height:32px;height:32px;padding:4px 6px;text-align:center}

      .cs-operational-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:10px 0 12px}
      .cs-operational-actions>button{min-height:40px;padding:8px 13px;border-radius:var(--radius-xs)}
      .cs-operational-actions>strong{margin-right:auto}
      .cs-operational-table-head{padding:9px 7px;border-top:1px solid var(--line);border-bottom:1px solid var(--line-strong);background:rgba(255,255,255,.018)}
      .cs-operational-list{min-width:0}
      .cs-operational-list>.notice,.cs-operational-list>.addition-empty{display:grid;place-items:center;min-height:88px;margin:0;padding:20px;border:1px dashed var(--line-strong);border-radius:var(--radius-xs);background:rgba(255,255,255,.015);color:var(--text-muted);text-align:center;font-size:12px}
      .cs-operational-list>.update-job,.cs-operational-list>.update-queue-row,.cs-operational-list>.addition-op-row,.cs-operational-list>.addition-history-row{min-height:58px;padding:12px 7px;border-bottom:1px solid var(--line)}

      .cs-operational-pagination{display:grid;grid-template-columns:minmax(150px,1fr) auto minmax(150px,1fr);align-items:center;gap:12px;margin:14px 0 0}
      .cs-operational-pagination>button{box-sizing:border-box;width:150px;min-height:40px;padding:8px 14px;border-radius:var(--radius-xs)}
      .cs-operational-pagination>button:first-child{justify-self:start}
      .cs-operational-pagination>button:last-child{justify-self:end}
      .cs-operational-pagination>.badge{display:inline-flex;align-items:center;justify-content:center;gap:6px;justify-self:center;min-width:150px;min-height:40px;padding:6px 10px;text-align:center;white-space:nowrap}
      .cs-operational-pagination input{box-sizing:border-box;width:58px;min-width:58px;min-height:30px;height:30px;padding:4px 6px;text-align:center;font:inherit;font-variant-numeric:tabular-nums}

      .cs-operational-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:8px;margin:14px 0}
      .cs-operational-stats>*{display:grid;align-content:center;gap:4px;min-height:72px;padding:11px 12px;border:1px solid var(--line);border-radius:var(--radius-xs);background:var(--bg-elev-2)}
      .cs-operational-stats strong{font-size:21px;line-height:1;font-variant-numeric:tabular-nums}
      .cs-operational-stats span{color:var(--text-muted);font-size:11px;font-weight:700}

      #tab_panel_adicoes .addition-operations-center{gap:var(--cs-operational-section-gap)}
      #tab_panel_adicoes .addition-intro-card{display:grid;gap:14px;padding:18px}
      #tab_panel_adicoes .addition-intro-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:22px;align-items:start}
      #tab_panel_adicoes .addition-intro-copy{min-width:0}
      #tab_panel_adicoes .addition-intro-copy .section-title{margin:0;font-size:16px}
      #tab_panel_adicoes .addition-intro-copy .small{max-width:920px;margin-top:7px;line-height:1.55}
      #tab_panel_adicoes .addition-intro-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
      #tab_panel_adicoes .addition-flow-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius-xs);background:rgba(255,255,255,.018);color:var(--text-muted);font-size:11px;font-weight:700}
      #tab_panel_adicoes .addition-flow-step{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
      #tab_panel_adicoes .addition-flow-step::after{content:"→";margin-left:2px;color:var(--text-faint)}
      #tab_panel_adicoes .addition-flow-step:last-child::after{display:none}
      #tab_panel_adicoes .addition-summary-title{align-items:flex-start;margin-bottom:12px}
      #tab_panel_adicoes .addition-summary-title>.addition-summary-heading{display:grid;gap:5px}
      #tab_panel_adicoes .addition-guidance{margin-top:8px}
      #tab_panel_adicoes .addition-toolbar{margin:12px 0}
      #tab_panel_adicoes .addition-list-meta{margin:10px 0}
      #tab_panel_adicoes .addition-bulk-actions{margin:10px 0 12px}
      #tab_panel_adicoes .addition-table-head{padding:9px 7px}
      #tab_panel_adicoes .addition-op-row{padding:12px 7px}
      #tab_panel_adicoes #addition_history_accordion:not([open])>:not(summary),
      #tab_panel_adicoes #addition_technical_accordion:not([open])>:not(summary){display:none}

      #tab_panel_atualizacoes .updates-overview-card{margin:0}
      #tab_panel_atualizacoes .updates-working-card>.standard-update-original-title{display:none}
      #tab_panel_atualizacoes .updates-conditional-controls{margin-top:0;padding:0;border:0;background:none}
      #tab_panel_atualizacoes .updates-subtitle{margin:12px 0 8px}
      #tab_panel_atualizacoes .updates-history-panel{padding:10px 0 0;border:0;background:transparent}
      #tab_panel_atualizacoes .updates-history-tabs{margin-top:10px}
      #tab_panel_atualizacoes .updates-technical-log.card{padding:18px}
      #tab_panel_atualizacoes .updates-summary{margin:14px 0}
      #tab_panel_atualizacoes .cs-update-operational-summary{margin:12px 0}
      #tab_panel_atualizacoes .updates-filters{margin:12px 0}
      #tab_panel_atualizacoes .updates-list-controls{margin:12px 0}

      @media(max-width:1050px){
        .cs-operational-filters--wide{grid-template-columns:repeat(2,minmax(0,1fr))}
        .cs-operational-filters--wide>button{width:100%}
      }
      @media(max-width:900px){
        .cs-operational-filters,.cs-operational-filters--history{grid-template-columns:1fr}
        .cs-operational-filter-actions{justify-content:stretch}
        .cs-operational-filter-actions>button{flex:1}
        #tab_panel_adicoes .addition-intro-head{grid-template-columns:1fr}
        #tab_panel_adicoes .addition-intro-actions{justify-content:flex-start}
        .cs-operational-stats{grid-template-columns:repeat(2,minmax(0,1fr))}
      }
      @media(max-width:620px){
        #tab_panel_atualizacoes,#tab_panel_adicoes{--cs-operational-card-padding:14px}
        .cs-operational-meta{align-items:stretch;flex-direction:column}
        .cs-operational-meta .listing-page-size{width:100%;justify-content:space-between;margin-left:0}
        .cs-operational-actions{align-items:stretch;flex-direction:column}
        .cs-operational-actions>button{width:100%}
        .cs-operational-pagination{grid-template-columns:1fr}
        .cs-operational-pagination>button,.cs-operational-pagination>.badge{width:100%;justify-self:stretch}
        .cs-operational-pagination>button:first-child,.cs-operational-pagination>button:last-child{justify-self:stretch}
        .cs-operational-stats{grid-template-columns:1fr}
        .cs-operational-section-meta{max-width:45%;white-space:normal}
        #tab_panel_adicoes .addition-intro-actions>*{width:100%}
      }
    `;
    document.head.appendChild(style);
  }

  function sectionHint(section, message) {
    if (!section || $(".cs-operational-section-hint", section)) return;
    const summary = section.matches("details") ? section.querySelector(":scope > summary") : null;
    const hint = document.createElement("div");
    hint.className = "cs-operational-section-hint";
    hint.textContent = message;
    if (summary) summary.insertAdjacentElement("afterend", hint);
    else section.prepend(hint);
  }

  function introMarkup() {
    const section = document.createElement("section");
    section.className = "card addition-intro-card cs-operational-section";
    section.id = "addition_intro_card";
    section.innerHTML = `
      <div class="addition-intro-head">
        <div class="addition-intro-copy">
          <div class="section-title">Adicionar produtos</div>
          <div class="small">Gerencie os produtos aprovados na Comparação, prepare conteúdo e arquivos, organize a fila e acompanhe a publicação no WooCommerce. As etapas concluídas são reaproveitadas para evitar trabalho duplicado.</div>
        </div>
        <div class="addition-intro-actions" id="addition_intro_actions"></div>
      </div>
      <div class="addition-flow-strip" aria-label="Fluxo de adição">
        <span class="addition-flow-step">Aprovação</span>
        <span class="addition-flow-step">Preparação</span>
        <span class="addition-flow-step">Fila</span>
        <span class="addition-flow-step">Publicação</span>
        <span class="addition-flow-step">Histórico</span>
      </div>`;
    return section;
  }

  function applySectionClasses(section) {
    if (!section) return;
    addClasses(section, "cs-operational-section");
    const summary = section.matches("details") ? section.querySelector(":scope > summary") : null;
    if (!summary) return;
    addClasses(summary, "cs-operational-section-summary");
    addClasses(summary.querySelector(".addition-accordion-title,.updates-history-title"), "cs-operational-section-title");
    addClasses(summary.querySelector(":scope > .small"), "cs-operational-section-meta");
  }

  function applyPagination(node) {
    if (!node) return;
    node.classList.remove("addition-pagination");
    addClasses(node, "listing-pagination", "cs-operational-pagination");
  }

  function applyMeta(node) {
    if (!node) return;
    addClasses(node, "listing-meta-row", "cs-operational-meta");
    addClasses(node.querySelector(".addition-list-meta-left"), "cs-operational-meta-left");
  }

  function makeUpdateAccordion(card, title, metaNode, hint) {
    if (!card || card.matches("details")) return card;
    const details = document.createElement("details");
    details.open = true;
    details.className = card.className;
    [...card.attributes].forEach(attribute => {
      if (!["class"].includes(attribute.name)) details.setAttribute(attribute.name, attribute.value);
    });
    const summary = document.createElement("summary");
    summary.className = "cs-operational-section-summary";
    const titleWrap = document.createElement("span");
    titleWrap.className = "cs-operational-section-title";
    titleWrap.innerHTML = '<span class="updates-disclosure-chevron" aria-hidden="true">▸</span>';
    const titleNode = document.createElement("span");
    titleNode.className = "section-title";
    titleNode.textContent = title;
    titleWrap.appendChild(titleNode);
    summary.appendChild(titleWrap);
    if (metaNode) {
      addClasses(metaNode, "small", "cs-operational-section-meta");
      summary.appendChild(metaNode);
    }
    details.appendChild(summary);
    while (card.firstChild) details.appendChild(card.firstChild);
    card.replaceWith(details);
    applySectionClasses(details);
    sectionHint(details, hint);
    return details;
  }

  function createQueueMeta(root) {
    if ($("#updates_queue_listing_meta", root)) return;
    const controls = $("#updates_queue_list_controls", root);
    const filters = $(".updates-list-controls", controls);
    const found = $("#updates_queue_found_count", controls);
    const pageSizeInput = $("#updates_queue_page_size", controls);
    const pageSizeLabel = pageSizeInput?.closest("label");
    if (!controls || !filters || !found || !pageSizeLabel) return;
    const meta = document.createElement("div");
    meta.id = "updates_queue_listing_meta";
    meta.className = "listing-meta-row cs-operational-meta";
    const left = document.createElement("div");
    left.className = "cs-operational-meta-left";
    left.appendChild(found);
    const pageSize = document.createElement("div");
    pageSize.className = "listing-page-size";
    pageSize.appendChild(pageSizeLabel);
    meta.append(left, pageSize);
    filters.insertAdjacentElement("afterend", meta);
  }

  function repairPageJump(label, key) {
    if (!label || label.dataset.csPageRepairing === "1") return;
    const match = label.textContent.match(/Página\s+(\d+)\s+de\s+(\d+)/i);
    const existing = label.querySelector("[data-cs-page-input]");
    if (existing) {
      label.classList.add("cs-page-jump");
      if (!existing.dataset.csPageBound) {
        existing.dataset.csPageBound = "1";
        const go = () => window.__crapscraperPagination?.[key]?.(existing.value);
        existing.addEventListener("change", go);
        existing.addEventListener("keydown", event => {
          if (event.key === "Enter") {
            event.preventDefault();
            existing.blur();
          }
        });
      }
      return;
    }
    if (!match) return;
    label.dataset.csPageRepairing = "1";
    const page = Math.max(1, Number(match[1] || 1));
    const pages = Math.max(1, Number(match[2] || 1));
    const input = document.createElement("input");
    input.type = "number";
    input.min = "1";
    input.max = String(pages);
    input.value = String(Math.min(page, pages));
    input.dataset.csPageInput = "";
    input.setAttribute("aria-label", "Ir para página");
    const total = document.createElement("span");
    total.textContent = String(pages);
    label.replaceChildren(document.createTextNode("Página "), input, document.createTextNode(" de "), total);
    label.classList.add("cs-page-jump");
    delete label.dataset.csPageRepairing;
    repairPageJump(label, key);
  }

  function keepUpdatePageJump(label, key) {
    if (!label || label.dataset.csPageObserver === "1") return;
    label.dataset.csPageObserver = "1";
    repairPageJump(label, key);
    const observer = new MutationObserver(() => {
      if (label.dataset.csPageRepairing === "1" || label.querySelector("[data-cs-page-input]")) return;
      queueMicrotask(() => repairPageJump(label, key));
    });
    observer.observe(label, {childList:true});
  }

  function standardizeUpdates() {
    const root = $("#tab_panel_atualizacoes");
    if (!root || root.dataset.layoutStandardized === "1") return false;
    root.dataset.layoutStandardized = "1";
    addClasses(root, "cs-operational-stack");

    const workingCard = $(".updates-working-card", root);
    const workingTitle = $("#updates_working_title", workingCard);
    const working = makeUpdateAccordion(
      workingCard,
      "Preparação",
      null,
      "Revise os itens aprovados, aplique os filtros e prepare downloads e planos antes de enviá-los para a fila."
    );
    workingTitle?.remove();

    const queueCard = $(".updates-queue-section", root);
    const queueHeading = $(".updates-section-heading", queueCard);
    const queueMeta = $("#updates_queue_meta", queueCard);
    const queue = makeUpdateAccordion(
      queueCard,
      "Fila de atualização",
      queueMeta,
      "Acompanhe a lista ativa, controle a execução sequencial e filtre os itens persistidos na fila."
    );
    const queueTitleGroup = $(".updates-section-heading>div", queue);
    queueTitleGroup?.remove();
    addClasses(queueHeading, "cs-operational-heading-actions");

    const history = $("#updates_history_accordion", root);
    const technical = $(".updates-technical-log", root);
    [working, queue, history, technical].forEach(applySectionClasses);
    sectionHint(history, "Consulte resultados concluídos ou com erro, filtre os registros e baixe o histórico persistido.");
    sectionHint(technical, "Eventos técnicos da atualização para diagnóstico quando uma operação exigir investigação.");

    const prepFilters = $(".updates-filters", working);
    addClasses(prepFilters, "cs-operational-filters", "cs-operational-filters--wide");
    const prepSearch = $("#updates_search_filter", prepFilters)?.closest("label");
    if (prepSearch) prepFilters.prepend(prepSearch);
    addClasses($("#updates_clear_filters", prepFilters), "cs-operational-filter-action");

    createQueueMeta(root);
    addClasses($(".updates-list-controls", queue), "cs-operational-filters");
    addClasses($(".updates-history-filter-group", history), "cs-operational-filters", "cs-operational-filters--history");
    addClasses($(".updates-history-actions", history), "cs-operational-filter-actions");

    $$(".listing-meta-row", root).forEach(applyMeta);
    addClasses($(".updates-bulkbar", working), "cs-operational-actions");
    addClasses($(".updates-queue-actions", queue), "cs-operational-actions");

    addClasses($("#updates_summary", root), "cs-operational-stats");
    addClasses($("#updates_jobs", root), "cs-operational-list");
    addClasses($("#updates_queue_jobs", root), "cs-operational-list");
    addClasses($("#updates_history", root), "cs-operational-list");
    addClasses($(".addition-table-head", root), "cs-operational-table-head");

    const prepPagination = $("#updates_prev_page", root)?.closest(".listing-pagination");
    const queuePagination = $("#updates_queue_prev", root)?.closest(".listing-pagination");
    const historyPagination = $("#updates_history_prev", root)?.closest(".listing-pagination");
    [prepPagination, queuePagination, historyPagination].forEach(applyPagination);
    $("#updates_jobs", root)?.insertAdjacentElement("afterend", prepPagination);
    $("#updates_queue_jobs", root)?.insertAdjacentElement("afterend", queuePagination);
    $("#updates_history", root)?.insertAdjacentElement("afterend", historyPagination);

    keepUpdatePageJump($("#updates_page_label", root), "updatesWaiting");
    keepUpdatePageJump($("#updates_queue_page", root), "updatesQueue");
    keepUpdatePageJump($("#updates_history_page", root), "updatesHistory");
    return true;
  }

  function standardizeAddition() {
    const root = $("#addition_operational_root");
    if (!root || root.dataset.layoutStandardized === "1") return false;
    const summary = $(".addition-summary-card", root);
    if (!summary) return false;

    root.dataset.layoutStandardized = "1";
    addClasses(root, "addition-layout-standard", "cs-operational-stack");
    addClasses(summary, "cs-operational-section");

    if (!$("#addition_intro_card", root)) {
      const intro = introMarkup();
      root.insertBefore(intro, summary);
      const sync = $("#addition_sync_approved", summary);
      const actions = $("#addition_intro_actions", intro);
      if (sync && actions) {
        sync.classList.remove("btn-sm");
        actions.appendChild(sync);
      }
    }

    const titleWrap = $(".addition-summary-title", summary);
    if (titleWrap) {
      const heading = titleWrap.firstElementChild;
      if (heading) {
        heading.classList.add("addition-summary-heading");
        const title = $(".section-title", heading);
        const subtitle = $(".small", heading);
        if (title) title.textContent = "Resumo das adições";
        if (subtitle) subtitle.textContent = "Visão geral dos produtos aprovados e do andamento da operação.";
      }
    }
    addClasses($(".addition-summary-grid", summary), "cs-operational-stats");

    const preparation = $("#addition_preparation_accordion", root);
    const queue = $("#addition_queue_accordion", root);
    const history = $("#addition_history_accordion", root);
    const technical = $("#addition_technical_accordion", root);
    [preparation, queue, history, technical].forEach(applySectionClasses);
    sectionHint(preparation, "Revise os itens aprovados e prepare conteúdo, imagem, categoria, preços e ZIP antes de enviá-los para a fila.");
    sectionHint(queue, "Acompanhe os produtos prontos, o estado persistido e controle o processamento sequencial da fila.");
    sectionHint(history, "Consulte tentativas anteriores, resultados, duração e registros persistidos de cada cadastro.");
    sectionHint(technical, "Eventos técnicos desta sessão para diagnóstico quando uma operação exigir investigação.");

    $$(".addition-toolbar", root).forEach(node => addClasses(node, "cs-operational-filters"));
    const historyFilters = $(".updates-history-filter-group", history);
    historyFilters?.removeAttribute("style");
    addClasses(historyFilters, "cs-operational-filters", "cs-operational-filters--history");
    addClasses($(".updates-history-actions", history), "cs-operational-filter-actions");

    $$(".addition-list-meta", root).forEach(applyMeta);
    $$(".addition-bulk-actions", root).forEach(node => addClasses(node, "cs-operational-actions"));
    $$(".addition-table-head", root).forEach(node => addClasses(node, "cs-operational-table-head"));
    ["preparation", "queue", "history"].forEach(scope => {
      addClasses($(`#addition_${scope}_rows`, root), "cs-operational-list");
      applyPagination($(`#addition_${scope}_prev`, root)?.closest(".addition-pagination,.listing-pagination"));
    });

    if (history) history.open = false;
    if (technical) technical.open = false;
    return true;
  }

  function scheduleAdditionStandardization() {
    [0, 50, 150, 350, 750].forEach(delay => window.setTimeout(standardizeAddition, delay));
  }

  function start() {
    installStyles();
    standardizeUpdates();
    $("#tab_btn_adicoes")?.addEventListener("click", scheduleAdditionStandardization);
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "adicoes") scheduleAdditionStandardization();
    });
    if (document.body?.dataset?.activeTab === "adicoes") scheduleAdditionStandardization();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();