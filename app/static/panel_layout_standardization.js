(() => {
  "use strict";

  if (window.__crapScraperPanelLayoutStandardizationInstalled) return;
  window.__crapScraperPanelLayoutStandardizationInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);

  function installStyles() {
    if ($("#cs-panel-layout-standardization-style")) return;
    const style = document.createElement("style");
    style.id = "cs-panel-layout-standardization-style";
    style.textContent = `
      #tab_panel_adicoes .addition-operations-center.addition-layout-standard{gap:12px}
      #tab_panel_adicoes .addition-intro-card{display:grid;gap:14px;padding:18px 20px}
      #tab_panel_adicoes .addition-intro-head{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:22px;align-items:start}
      #tab_panel_adicoes .addition-intro-copy{min-width:0}
      #tab_panel_adicoes .addition-intro-copy .section-title{margin:0;font-size:16px}
      #tab_panel_adicoes .addition-intro-copy .small{max-width:920px;margin-top:7px;line-height:1.55}
      #tab_panel_adicoes .addition-intro-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
      #tab_panel_adicoes .addition-flow-strip{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.018);color:var(--text-muted);font-size:11px;font-weight:700}
      #tab_panel_adicoes .addition-flow-step{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
      #tab_panel_adicoes .addition-flow-step::after{content:"→";margin-left:2px;color:var(--text-faint)}
      #tab_panel_adicoes .addition-flow-step:last-child::after{display:none}
      #tab_panel_adicoes .addition-summary-card{padding:16px 18px}
      #tab_panel_adicoes .addition-summary-title{align-items:flex-start;margin-bottom:12px}
      #tab_panel_adicoes .addition-summary-title>.addition-summary-heading{display:grid;gap:5px}
      #tab_panel_adicoes .addition-summary-title .section-title{font-size:15px}
      #tab_panel_adicoes .addition-summary-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important}
      #tab_panel_adicoes .addition-summary-chip{min-height:70px!important;padding:11px 12px!important}
      #tab_panel_adicoes .addition-summary-chip strong{font-size:21px!important}
      #tab_panel_adicoes .addition-guidance{margin-top:8px!important}
      #tab_panel_adicoes .addition-section-hint{margin:0 0 10px;padding:0 2px;color:var(--text-muted);font-size:11px;line-height:1.5}
      #tab_panel_adicoes .addition-accordion{overflow:visible}
      #tab_panel_adicoes .addition-accordion>summary{padding-bottom:3px}
      #tab_panel_adicoes .addition-toolbar{grid-template-columns:minmax(260px,1fr) minmax(180px,250px) 150px!important;gap:10px!important;margin:12px 0 10px!important}
      #tab_panel_adicoes .addition-bulk-actions{padding-top:2px;margin:8px 0 13px!important}
      #tab_panel_adicoes .addition-list-meta{margin:8px 0!important}
      #tab_panel_adicoes .addition-table-head{background:rgba(255,255,255,.012);border-top:1px solid var(--line);padding:8px 7px!important}
      #tab_panel_adicoes .addition-op-row{padding:12px 7px!important}
      #tab_panel_adicoes .addition-pagination{padding-top:2px}
      #tab_panel_adicoes .updates-section-heading{margin-top:6px}
      #tab_panel_adicoes #addition_history_accordion:not([open]) .updates-history-toolbar,
      #tab_panel_adicoes #addition_history_accordion:not([open]) .addition-list-meta,
      #tab_panel_adicoes #addition_history_accordion:not([open]) #addition_history_rows,
      #tab_panel_adicoes #addition_history_accordion:not([open]) .addition-pagination{display:none}
      #tab_panel_adicoes #addition_technical_accordion:not([open]) #addition_technical_log,
      #tab_panel_adicoes #addition_technical_accordion:not([open]) .log-copy-row{display:none}
      @media(max-width:900px){
        #tab_panel_adicoes .addition-intro-head{grid-template-columns:1fr}
        #tab_panel_adicoes .addition-intro-actions{justify-content:flex-start}
        #tab_panel_adicoes .addition-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}
        #tab_panel_adicoes .addition-toolbar{grid-template-columns:1fr!important}
      }
      @media(max-width:560px){
        #tab_panel_adicoes .addition-summary-grid{grid-template-columns:1fr!important}
        #tab_panel_adicoes .addition-intro-actions>*{width:100%}
      }
    `;
    document.head.appendChild(style);
  }

  function sectionHint(details, message) {
    if (!details || $(".addition-section-hint", details)) return;
    const summary = details.querySelector(":scope > summary");
    if (!summary) return;
    const hint = document.createElement("div");
    hint.className = "addition-section-hint";
    hint.textContent = message;
    summary.insertAdjacentElement("afterend", hint);
  }

  function introMarkup() {
    const section = document.createElement("section");
    section.className = "card addition-intro-card";
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

  function standardizeAddition() {
    const root = $("#addition_operational_root");
    if (!root || root.dataset.layoutStandardized === "1") return false;
    const summary = $(".addition-summary-card", root);
    if (!summary) return false;

    root.dataset.layoutStandardized = "1";
    root.classList.add("addition-layout-standard");

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

    sectionHint($("#addition_preparation_accordion", root), "Revise os itens aprovados, confira dados essenciais e prepare conteúdo, imagem, categoria, preços e ZIP antes de enviá-los para a fila.");
    sectionHint($("#addition_queue_accordion", root), "Acompanhe os produtos prontos para execução, o estado persistido de cada item e controle o processamento sequencial da fila.");
    sectionHint($("#addition_history_accordion", root), "Consulte tentativas anteriores, resultados, duração e registros persistidos de cada cadastro.");
    sectionHint($("#addition_technical_accordion", root), "Eventos técnicos desta sessão para diagnóstico. Use apenas quando precisar investigar uma operação.");

    const history = $("#addition_history_accordion", root);
    const technical = $("#addition_technical_accordion", root);
    if (history) history.open = false;
    if (technical) technical.open = false;
    return true;
  }

  function scheduleAdditionStandardization() {
    [0, 40, 120, 300, 700].forEach(delay => window.setTimeout(standardizeAddition, delay));
  }

  installStyles();
  $("#tab_btn_adicoes")?.addEventListener("click", scheduleAdditionStandardization);
  document.addEventListener("crapscraper:main-tab-changed", event => {
    const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
    if (key === "adicoes") scheduleAdditionStandardization();
  });
  if (document.body?.dataset?.activeTab === "adicoes") scheduleAdditionStandardization();
})();
