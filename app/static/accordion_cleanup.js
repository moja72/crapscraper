(() => {
  "use strict";

  const STYLE_ID = "crapscraper-accordion-cleanup-style";
  const existingStyle = document.getElementById(STYLE_ID);
  if (existingStyle) existingStyle.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Resumo da comparação: apenas um triângulo, sem marcador nativo nem +/- legado. */
    #comparison_summary_card > .comparison-summary-header::-webkit-details-marker{
      display:none!important;
    }
    #comparison_summary_card > .comparison-summary-header::marker{
      content:""!important;
      display:none!important;
    }
    #comparison_summary_card .comparison-summary-toggle{
      font-size:13px!important;
      line-height:1!important;
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
    }
    #comparison_summary_card .comparison-summary-toggle::before,
    #comparison_summary_card .comparison-summary-toggle::after{
      content:none!important;
      display:none!important;
    }

    /* Ambiente: o resumo aparece somente no cabeçalho da sanfona. */
    .standard-update-environment-inline-meta{
      display:none!important;
    }

    /* Fila: o resumo operacional permanece apenas dentro do conteúdo da sanfona. */
    .standard-update-accordion-card[data-update-accordion-kind="queue"]
      > .standard-update-accordion-toggle .standard-update-accordion-meta{
      display:none!important;
    }
  `;
  document.head.appendChild(style);

  function normalizeComparisonSummary() {
    const card = document.getElementById("comparison_summary_card");
    if (!card) return;

    const toggle = card.querySelector(".comparison-summary-toggle");
    if (!toggle) return;

    if (toggle.textContent !== "▸") {
      toggle.textContent = "▸";
    }
    toggle.setAttribute("aria-label", "Alternar resumo da comparação");
  }

  function getEnvironmentCard() {
    return (
      document.querySelector('#tab_panel_atualizacoes .card[data-update-accordion-kind="environment"]') ||
      document.getElementById("updates_environment_details")?.closest(".card") ||
      null
    );
  }

  function hideEnvironmentDuplicateMeta() {
    const card = getEnvironmentCard();
    if (!card) return;

    const candidates = [...card.querySelectorAll(".small, div, span, p")];
    for (const node of candidates) {
      if (node.closest(".standard-update-accordion-toggle")) continue;

      const text = String(node.textContent || "").replace(/\s+/g, " ").trim();
      if (!/^\d+\s+requisito\(s\)\s+exigem\s+atenção$/i.test(text)) continue;

      node.classList.add("standard-update-environment-inline-meta");
    }
  }

  function collapseQueueByDefault() {
    const card =
      document.querySelector('#tab_panel_atualizacoes .card[data-update-accordion-kind="queue"]') ||
      document.getElementById("updates_queue_meta")?.closest(".card") ||
      null;

    if (!card || card.dataset.queueDefaultCollapsedApplied === "1") return;

    const toggle = card.querySelector(":scope > .standard-update-accordion-toggle");
    if (!toggle) return;

    card.dataset.queueDefaultCollapsedApplied = "1";
    card.classList.add("is-collapsed");
    toggle.setAttribute("aria-expanded", "false");
  }

  function refine() {
    normalizeComparisonSummary();
    hideEnvironmentDuplicateMeta();
    collapseQueueByDefault();
  }

  refine();

  let timer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(refine, 50);
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
