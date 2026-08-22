(() => {
  "use strict";

  if (window.__crapScraperOperationalUiCardSizeParityV6Installed) return;
  window.__crapScraperOperationalUiCardSizeParityV6Installed = true;

  const style = document.createElement("style");
  style.id = "cs-operational-ui-card-size-parity-v6-style";
  style.textContent = `
    /*
     * Igualdade real de tamanho entre os cards de Atualizar e Adicionar.
     * A referência é a largura compacta atualmente exibida em Atualizar.
     * Mantemos a lógica/click/tooltip da v5 e ajustamos somente geometria.
     */
    #updates_summary,
    #addition_summary_grid {
      display:grid!important;
      grid-template-columns:repeat(7,minmax(0,1fr))!important;
      gap:8px!important;
      width:100%!important;
      align-items:stretch!important;
    }

    #updates_summary>.cs-v5-metric-card,
    #addition_summary_grid>.cs-v5-metric-card {
      grid-column:auto!important;
      width:100%!important;
      min-width:0!important;
      min-height:66px!important;
      height:auto!important;
      padding:9px 10px!important;
      border-radius:10px!important;
      box-sizing:border-box!important;
    }

    #updates_summary .cs-v5-metric-footer,
    #addition_summary_grid .cs-v5-metric-footer {
      min-height:22px!important;
      margin-top:2px!important;
    }

    #updates_summary .operational-summary-help,
    #addition_summary_grid .operational-summary-help {
      flex:0 0 22px!important;
      width:22px!important;
      min-width:22px!important;
      max-width:22px!important;
      height:22px!important;
      min-height:22px!important;
      max-height:22px!important;
      margin:0!important;
      padding:0!important;
    }

    @media(max-width:1180px){
      #updates_summary,
      #addition_summary_grid {
        grid-template-columns:repeat(4,minmax(0,1fr))!important;
      }
    }

    @media(max-width:760px){
      #updates_summary,
      #addition_summary_grid {
        grid-template-columns:repeat(2,minmax(0,1fr))!important;
      }
    }

    @media(max-width:480px){
      #updates_summary,
      #addition_summary_grid {
        grid-template-columns:1fr!important;
      }
    }
  `;
  document.head.appendChild(style);
})();
