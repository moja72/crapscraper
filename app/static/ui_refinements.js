(() => {
  "use strict";

  const STYLE_ID = "crapscraper-ui-refinements-style";
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Execuções simultâneas: um único plano visual, sem blocos internos mais escuros. */
    #runs_manager_card.collect-runs-accordion{
      background:rgba(255,255,255,.055)!important;
      border-color:rgba(255,255,255,.11)!important;
      overflow:visible!important;
    }
    #runs_manager_card .runs-manager-header,
    #runs_manager_card #runs_manager_content,
    #runs_manager_card .runs-tabs-wrap,
    #runs_manager_card .run-card-wrap,
    #runs_manager_card .form-grid,
    #runs_manager_card .runs-manager-create-actions{
      background:transparent!important;
    }
    #runs_manager_card #runs_manager_content{
      border:none!important;
      box-shadow:none!important;
    }
    #runs_manager_card .runs-manager-header:hover{
      background:rgba(255,255,255,.025)!important;
    }
    #runs_manager_card .runs-manager-header[aria-expanded="true"] + #runs_manager_content{
      background:transparent!important;
      border:none!important;
      box-shadow:none!important;
    }
    #runs_manager_card .run-tab-btn{
      background:rgba(255,255,255,.035)!important;
      border:1px solid rgba(255,255,255,.10)!important;
      box-shadow:none!important;
    }
    #runs_manager_card .run-tab-btn[aria-selected="true"]{
      background:rgba(255,255,255,.055)!important;
      border-color:rgba(124,58,237,.7)!important;
      box-shadow:inset 0 -2px 0 var(--accent)!important;
    }

    /* Cards de catálogo: status e atalhos estáveis. */
    .catalogo-summary-card{
      overflow:visible!important;
    }
    .catalogo-summary-card:has(.catalogo-availability-icon:hover),
    .catalogo-summary-card:has(.catalogo-availability-icon:focus-visible){
      z-index:80!important;
    }
    .catalogo-status-row{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      flex-wrap:wrap!important;
      min-height:24px;
      margin:6px 0 8px;
      color:var(--text-muted);
    }
    .catalogo-status-item{
      display:inline-flex;
      align-items:center;
      gap:5px;
      white-space:nowrap;
    }
    .catalogo-availability{
      position:relative!important;
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      overflow:visible!important;
      min-height:34px;
    }
    .catalogo-availability-icon{
      position:relative!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      min-width:28px;
      min-height:28px;
      border-radius:7px;
      cursor:help;
      opacity:1;
      overflow:visible!important;
    }
    .catalogo-availability-icon.is-unavailable{
      opacity:.60!important;
      filter:saturate(.45);
    }
    .catalogo-availability-icon::after{
      content:attr(data-tooltip)!important;
      position:absolute!important;
      left:50%!important;
      bottom:calc(100% + 8px)!important;
      transform:translateX(-50%) translateY(3px)!important;
      z-index:10000!important;
      width:max-content!important;
      max-width:180px!important;
      padding:6px 8px!important;
      border:1px solid var(--line-strong)!important;
      border-radius:7px!important;
      background:#19191d!important;
      color:var(--text)!important;
      font-size:11px!important;
      font-weight:700!important;
      line-height:1.2!important;
      white-space:nowrap!important;
      opacity:0!important;
      visibility:hidden!important;
      pointer-events:none!important;
      box-shadow:0 8px 24px rgba(0,0,0,.38)!important;
      transition:opacity .14s ease,transform .14s ease,visibility .14s ease!important;
    }
    .catalogo-availability-icon::before{
      display:none!important;
    }
    .catalogo-availability-icon:hover::after,
    .catalogo-availability-icon:focus-visible::after{
      opacity:1!important;
      visibility:visible!important;
      transform:translateX(-50%) translateY(0)!important;
    }
    .catalogo-availability-icon:first-child::after{
      left:0!important;
      transform:translateY(3px)!important;
    }
    .catalogo-availability-icon:first-child:hover::after,
    .catalogo-availability-icon:first-child:focus-visible::after{
      transform:translateY(0)!important;
    }
    .catalogo-availability-icon:last-child::after{
      left:auto!important;
      right:0!important;
      transform:translateY(3px)!important;
    }
    .catalogo-availability-icon:last-child:hover::after,
    .catalogo-availability-icon:last-child:focus-visible::after{
      transform:translateY(0)!important;
    }

    /* Histórico: tabs reais, conectadas ao painel ativo. */
    .updates-history-tabs{
      display:flex!important;
      align-items:flex-end!important;
      gap:4px!important;
      padding:0 10px!important;
      margin:10px 0 0!important;
      border-bottom:1px solid var(--line-strong)!important;
    }
    .updates-history-tab{
      position:relative!important;
      bottom:-1px!important;
      min-height:42px!important;
      padding:9px 18px!important;
      border:1px solid var(--line-strong)!important;
      border-bottom-color:var(--line-strong)!important;
      border-radius:10px 10px 0 0!important;
      background:var(--bg-elev-2)!important;
      color:var(--text-muted)!important;
      box-shadow:none!important;
    }
    .updates-history-tab.is-active{
      z-index:3!important;
      background:var(--bg-elev-1)!important;
      color:var(--text)!important;
      border-color:var(--line-strong)!important;
      border-bottom:none!important;
      box-shadow:none!important;
    }
    .updates-history-tab:not(.is-active):hover{
      background:var(--bg-elev-3)!important;
      color:var(--text)!important;
    }
    .updates-history-panel{
      margin-top:0!important;
      padding-top:14px!important;
      border:1px solid var(--line-strong)!important;
      border-top:0!important;
      border-radius:0 0 12px 12px!important;
      background:var(--bg-elev-1)!important;
    }

    /* Logs: todos seguem o padrão Log d... em sanfona fechada. */
    .standard-log-accordion{
      overflow:hidden!important;
    }
    .standard-log-accordion > summary{
      list-style:none!important;
      cursor:pointer!important;
      display:flex!important;
      align-items:center!important;
      gap:8px!important;
      user-select:none!important;
    }
    .standard-log-accordion > summary::-webkit-details-marker{display:none!important;}
    .standard-log-chevron{
      display:inline-flex!important;
      width:14px!important;
      align-items:center!important;
      justify-content:center!important;
      transition:transform .18s ease!important;
    }
    .standard-log-accordion[open] .standard-log-chevron{
      transform:rotate(90deg)!important;
    }
    .standard-log-content{
      margin-top:14px!important;
    }

    /* Atualizar: Ambiente, Preparação e Fila seguem o mesmo padrão de sanfona. */
    .standard-update-accordion{
      overflow:hidden!important;
      padding:0!important;
    }
    .standard-update-accordion > summary{
      list-style:none!important;
      cursor:pointer!important;
      display:flex!important;
      align-items:center!important;
      justify-content:space-between!important;
      gap:16px!important;
      min-height:64px!important;
      padding:16px 18px!important;
      user-select:none!important;
      background:transparent!important;
    }
    .standard-update-accordion > summary::-webkit-details-marker{display:none!important;}
    .standard-update-accordion > summary:hover{
      background:rgba(255,255,255,.025)!important;
    }
    .standard-update-accordion-summary-copy{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      min-width:0!important;
    }
    .standard-update-accordion-title{
      margin:0!important;
      font-size:18px!important;
      font-weight:800!important;
      line-height:1.2!important;
      color:var(--text)!important;
    }
    .standard-update-accordion-meta{
      margin-left:auto!important;
      color:var(--text-muted)!important;
      font-size:13px!important;
      white-space:nowrap!important;
      overflow:hidden!important;
      text-overflow:ellipsis!important;
    }
    .standard-update-accordion-chevron{
      display:inline-flex!important;
      width:16px!important;
      flex:0 0 16px!important;
      align-items:center!important;
      justify-content:center!important;
      color:var(--text-muted)!important;
      transition:transform .18s ease!important;
    }
    .standard-update-accordion[open] > summary .standard-update-accordion-chevron{
      transform:rotate(90deg)!important;
    }
    .standard-update-accordion-content{
      padding:0 18px 18px!important;
      background:transparent!important;
    }
    .standard-update-accordion-content > :first-child{
      margin-top:0!important;
    }
    @media(max-width:760px){
      .standard-update-accordion > summary{
        align-items:flex-start!important;
      }
      .standard-update-accordion-meta{
        white-space:normal!important;
      }
    }
  `;

  document.getElementById(STYLE_ID)?.remove();
  document.head.appendChild(style);

  function normalizeDefaultLabels(root = document) {
    root.querySelectorAll?.("option").forEach(option => {
      if (String(option.value || "").trim().toLowerCase() !== "default") return;
      const star = option.textContent.includes("⭐") ? " ⭐" : "";
      option.textContent = `Padrão${star}`;
    });

    const defaultButton = document.getElementById("slot_default_btn");
    if (defaultButton) {
      if (/default atual/i.test(defaultButton.textContent || "")) defaultButton.textContent = "⭐ Padrão atual";
      else if (/\bdefault\b/i.test(defaultButton.textContent || "")) defaultButton.textContent = "⭐ Padrão";
    }
  }

  function normalizeCatalogAvailability(root = document) {
    root.querySelectorAll?.(".catalogo-availability").forEach(container => {
      if (container.dataset.uiRefined === "1") return;
      const current = [...container.querySelectorAll(".catalogo-availability-icon")]
        .map(node => String(node.getAttribute("aria-label") || node.dataset.tooltip || "").toLowerCase());
      const hasCatalog = current.some(label => label.includes("catálogo"));
      const hasState = current.some(label => label.includes("estado"));
      const hasLog = current.some(label => label.includes("log"));
      const items = [
        ["📄", "Catálogo", hasCatalog],
        ["📝", "Estado", hasState],
        ["📋", "Log", hasLog],
      ];
      container.innerHTML = items.map(([icon,label,available]) =>
        `<span class="catalogo-availability-icon${available ? "" : " is-unavailable"}" tabindex="0" role="img" aria-label="${label}" aria-disabled="${available ? "false" : "true"}" data-tooltip="${label}">${icon}</span>`
      ).join("");
      container.dataset.uiRefined = "1";
    });
  }

  function normalizeCatalogStatusRows(root = document) {
    root.querySelectorAll?.(".catalogo-summary-card .small").forEach(small => {
      if (small.querySelector(".catalogo-status-row")) return;
      const details = small.querySelector(".catalogo-context-accordion");
      if (!details) return;
      const before = [];
      let node = small.firstChild;
      while (node && node !== details) {
        const next = node.nextSibling;
        if (node.nodeType === Node.TEXT_NODE || (node.nodeType === Node.ELEMENT_NODE && node.tagName === "BR")) {
          before.push(node);
        }
        node = next;
      }
      const text = before.map(item => item.textContent || "").join(" ").replace(/\s+/g," ");
      const isCurrent = /Atual/i.test(text);
      const isDefault = /Catálogo padrão/i.test(text);
      if (!isCurrent && !isDefault) return;
      before.forEach(item => item.remove());
      const row = document.createElement("span");
      row.className = "catalogo-status-row";
      row.innerHTML = `${isCurrent ? '<span class="catalogo-status-item">🟢 Atual</span>' : ""}${isDefault ? '<span class="catalogo-status-item">⭐ Catálogo padrão</span>' : ""}`;
      small.insertBefore(row, details);
    });
  }

  function standardizeCollectLog() {
    const log = document.getElementById("logs");
    if (!log) return;
    const currentDetails = log.closest("details.standard-log-accordion");
    if (currentDetails) return;
    const card = log.closest(".card");
    if (!card) return;

    const copyRow = card.querySelector(".log-copy-row");
    const details = document.createElement("details");
    details.className = `${card.className} standard-log-accordion`;
    details.dataset.standardLog = "collect";

    const summary = document.createElement("summary");
    summary.innerHTML = '<span class="standard-log-chevron" aria-hidden="true">▸</span><span class="section-title" style="margin:0;">Log da coleta</span>';

    const content = document.createElement("div");
    content.className = "standard-log-content";
    content.appendChild(log);
    if (copyRow) content.appendChild(copyRow);

    details.appendChild(summary);
    details.appendChild(content);
    card.replaceWith(details);
  }

  function standardizeUpdateLog() {
    const log = document.getElementById("updates_log");
    if (!log) return;
    const details = log.closest("details");
    if (!details) return;
    details.classList.add("standard-log-accordion");
    details.removeAttribute("open");
    const title = details.querySelector("summary .section-title");
    if (title) title.textContent = "Logs da atualização";
    const chevron = details.querySelector("summary .updates-disclosure-chevron");
    if (chevron) {
      chevron.classList.add("standard-log-chevron");
      chevron.textContent = "▸";
    }
  }

  function findCardByTitle(titlePattern) {
    const candidates = [...document.querySelectorAll("#tab_panel_atualizacoes .card")];
    return candidates.find(card => {
      if (card.matches("details.standard-update-accordion")) return false;
      const title = [...card.querySelectorAll(":scope > .section-title, :scope > div > .section-title, :scope > header .section-title")]
        .find(node => titlePattern.test(String(node.textContent || "").trim()));
      return Boolean(title);
    }) || null;
  }

  function extractAccordionMeta(card, kind) {
    if (kind === "environment") {
      const title = [...card.querySelectorAll(".section-title")].find(node => /^Ambiente$/i.test(String(node.textContent || "").trim()));
      const sibling = title?.nextElementSibling;
      return sibling?.classList?.contains("small") ? String(sibling.textContent || "").trim() : "";
    }
    if (kind === "queue") {
      return String(document.getElementById("updates_queue_meta")?.textContent || "").trim();
    }
    return "";
  }

  function convertCardToAccordion(card, {kind, title, open = true}) {
    if (!card || card.matches("details.standard-update-accordion")) return;

    const details = document.createElement("details");
    details.className = `${card.className} standard-update-accordion`;
    details.dataset.updateAccordion = kind;
    if (open) details.open = true;

    const summary = document.createElement("summary");
    const summaryCopy = document.createElement("span");
    summaryCopy.className = "standard-update-accordion-summary-copy";
    summaryCopy.innerHTML = `<span class="standard-update-accordion-chevron" aria-hidden="true">▸</span><span class="standard-update-accordion-title">${title}</span>`;
    summary.appendChild(summaryCopy);

    const metaText = extractAccordionMeta(card, kind);
    if (metaText) {
      const meta = document.createElement("span");
      meta.className = "standard-update-accordion-meta";
      meta.textContent = metaText;
      summary.appendChild(meta);
    }

    const content = document.createElement("div");
    content.className = "standard-update-accordion-content";

    const titleNodes = [...card.querySelectorAll(".section-title")].filter(node => {
      const text = String(node.textContent || "").trim();
      return text === title || (kind === "preparation" && /^Aguardando\s*\/\s*prepara/i.test(text));
    });
    titleNodes.forEach(node => node.remove());

    if (kind === "environment") {
      const diagnosticButton = card.querySelector("#updates_environment_toggle");
      diagnosticButton?.remove();
      const diagnosticDetails = card.querySelector("#updates_environment_details");
      diagnosticDetails?.classList.remove("hidden");
      const duplicateMeta = [...card.querySelectorAll(".small")].find(node => String(node.textContent || "").trim() === metaText);
      duplicateMeta?.remove();
    }

    if (kind === "queue") {
      const duplicateMeta = card.querySelector("#updates_queue_meta");
      duplicateMeta?.classList.add("standard-update-accordion-live-meta");
    }

    while (card.firstChild) content.appendChild(card.firstChild);
    details.appendChild(summary);
    details.appendChild(content);
    card.replaceWith(details);

    if (kind === "queue") {
      const liveMeta = details.querySelector("#updates_queue_meta");
      const summaryMeta = details.querySelector(".standard-update-accordion-meta");
      if (liveMeta && summaryMeta) {
        const sync = () => { summaryMeta.textContent = String(liveMeta.textContent || "").trim(); };
        sync();
        new MutationObserver(sync).observe(liveMeta, {childList:true, subtree:true, characterData:true});
      }
    }
  }

  function standardizeUpdateSections() {
    const environmentButton = document.getElementById("updates_environment_toggle");
    const environmentCard = environmentButton?.closest(".card") || findCardByTitle(/^Ambiente$/i);
    convertCardToAccordion(environmentCard, {kind:"environment", title:"Ambiente", open:true});

    const preparationTitle = document.getElementById("updates_working_title");
    const preparationCard = preparationTitle?.closest(".card") || findCardByTitle(/^(Preparação|Aguardando\s*\/\s*preparação)$/i);
    convertCardToAccordion(preparationCard, {kind:"preparation", title:"Preparação", open:true});

    const queueMeta = document.getElementById("updates_queue_meta");
    const queueCard = queueMeta?.closest(".card") || findCardByTitle(/^Fila de atualização$/i);
    convertCardToAccordion(queueCard, {kind:"queue", title:"Fila de atualização", open:true});
  }

  function refine(root = document) {
    normalizeDefaultLabels(root);
    normalizeCatalogStatusRows(root);
    normalizeCatalogAvailability(root);
    standardizeCollectLog();
    standardizeUpdateLog();
    standardizeUpdateSections();
  }

  refine(document);
  let timer = null;
  const observer = new MutationObserver(mutations => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const roots = new Set(mutations.map(item => item.target?.nodeType === Node.ELEMENT_NODE ? item.target : item.target?.parentElement).filter(Boolean));
      if (!roots.size) refine(document);
      else roots.forEach(root => refine(root));
    }, 40);
  });
  observer.observe(document.body, {childList:true, subtree:true});
})();
