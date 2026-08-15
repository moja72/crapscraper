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

  function hideEnvironmentDuplicateMeta() {
    const card =
      document.querySelector('#tab_panel_atualizacoes .card[data-update-accordion-kind="environment"]') ||
      document.getElementById("updates_environment_details")?.closest(".card");

    if (!card) return;

    const originalTitle = [...card.querySelectorAll(".section-title")]
      .find(node => /^Ambiente$/i.test(String(node.textContent || "").trim()));
    const inlineMeta = originalTitle?.nextElementSibling;

    if (
      inlineMeta?.classList?.contains("small") &&
      /requisito\(s\).*atenção/i.test(String(inlineMeta.textContent || "").trim())
    ) {
      inlineMeta.classList.add("standard-update-environment-inline-meta");
    }
  }

  function refine() {
    normalizeComparisonSummary();
    hideEnvironmentDuplicateMeta();
  }

  refine();

  let timer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(refine, 50);
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
