(() => {
  "use strict";

  if (window.__crapScraperOperationalUiCardSizeParityV6Installed) return;
  window.__crapScraperOperationalUiCardSizeParityV6Installed = true;

  const style = document.createElement("style");
  style.id = "cs-operational-ui-card-size-parity-v6-style";
  style.textContent = `
    /*
     * Contrato visual único dos cards operacionais.
     * Desktop: todos os cards de Atualizar e Adicionar medem exatamente
     * 200px x 66px, independentemente das classes geradas por cada fluxo.
     */
    #updates_summary,
    #addition_summary_grid {
      display:flex!important;
      flex-wrap:wrap!important;
      align-items:stretch!important;
      justify-content:flex-start!important;
      gap:8px!important;
      width:100%!important;
      margin:12px 0 0!important;
      padding:0!important;
      border:0!important;
      background:transparent!important;
      grid-template-columns:none!important;
    }

    #updates_summary>.cs-v5-metric-card,
    #updates_summary>.cs-v4-metric-card,
    #addition_summary_grid>.addition-summary-chip,
    #addition_summary_grid>.cs-v5-metric-card,
    #addition_summary_grid>.cs-v4-metric-card {
      flex:0 0 200px!important;
      width:200px!important;
      min-width:200px!important;
      max-width:200px!important;
      height:66px!important;
      min-height:66px!important;
      max-height:66px!important;
      margin:0!important;
      padding:9px 10px!important;
      border:1px solid var(--line)!important;
      border-radius:10px!important;
      background:rgba(255,255,255,.022)!important;
      color:var(--text)!important;
      box-sizing:border-box!important;
      display:flex!important;
      flex-direction:column!important;
      justify-content:center!important;
      align-items:stretch!important;
      gap:4px!important;
      text-align:left!important;
      box-shadow:none!important;
      transform:none!important;
      appearance:none!important;
      font:inherit!important;
      overflow:visible!important;
    }

    #updates_summary>.cs-v5-metric-card:hover,
    #updates_summary>.cs-v4-metric-card:hover,
    #addition_summary_grid>.addition-summary-chip:hover,
    #addition_summary_grid>.cs-v5-metric-card:hover,
    #addition_summary_grid>.cs-v4-metric-card:hover {
      border-color:var(--line-accent)!important;
      background:var(--accent-soft)!important;
    }

    #updates_summary>.is-filter-active,
    #addition_summary_grid>.is-filter-active {
      border-color:rgba(124,58,237,.88)!important;
      background:linear-gradient(180deg,rgba(124,58,237,.20),rgba(124,58,237,.10))!important;
      box-shadow:inset 0 0 0 1px rgba(143,91,255,.20)!important;
    }

    #updates_summary>*>strong,
    #addition_summary_grid>*>strong {
      display:block!important;
      margin:0!important;
      color:var(--text)!important;
      font-size:18px!important;
      font-weight:800!important;
      line-height:1!important;
      font-variant-numeric:tabular-nums!important;
    }

    #updates_summary .cs-v5-metric-footer,
    #updates_summary .cs-v4-metric-footer,
    #updates_summary .operational-summary-footer,
    #addition_summary_grid .cs-v5-metric-footer,
    #addition_summary_grid .cs-v4-metric-footer,
    #addition_summary_grid .operational-summary-footer {
      display:flex!important;
      align-items:center!important;
      justify-content:flex-start!important;
      gap:5px!important;
      min-width:0!important;
      min-height:22px!important;
      margin:2px 0 0!important;
      color:var(--text-muted)!important;
      font-size:11px!important;
      font-weight:650!important;
      line-height:1.2!important;
    }

    #updates_summary .cs-v5-metric-label,
    #updates_summary .cs-v4-metric-label,
    #updates_summary .operational-summary-label,
    #addition_summary_grid .cs-v5-metric-label,
    #addition_summary_grid .cs-v4-metric-label,
    #addition_summary_grid .operational-summary-label {
      min-width:0!important;
      color:var(--text-muted)!important;
      font-size:11px!important;
      font-weight:650!important;
      line-height:1.2!important;
    }

    #updates_summary .comparison-help,
    #addition_summary_grid .comparison-help,
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
      align-self:center!important;
      font-size:10px!important;
      line-height:20px!important;
      box-sizing:border-box!important;
    }

    /* Responsividade: abaixo do desktop, os cards continuam iguais entre si. */
    @media(max-width:1180px){
      #updates_summary>.cs-v5-metric-card,
      #updates_summary>.cs-v4-metric-card,
      #addition_summary_grid>.addition-summary-chip,
      #addition_summary_grid>.cs-v5-metric-card,
      #addition_summary_grid>.cs-v4-metric-card {
        flex:1 1 calc(25% - 8px)!important;
        width:calc(25% - 8px)!important;
        min-width:180px!important;
        max-width:none!important;
      }
    }

    @media(max-width:760px){
      #updates_summary>.cs-v5-metric-card,
      #updates_summary>.cs-v4-metric-card,
      #addition_summary_grid>.addition-summary-chip,
      #addition_summary_grid>.cs-v5-metric-card,
      #addition_summary_grid>.cs-v4-metric-card {
        flex:1 1 calc(50% - 8px)!important;
        width:calc(50% - 8px)!important;
        min-width:0!important;
      }
    }

    @media(max-width:480px){
      #updates_summary>.cs-v5-metric-card,
      #updates_summary>.cs-v4-metric-card,
      #addition_summary_grid>.addition-summary-chip,
      #addition_summary_grid>.cs-v5-metric-card,
      #addition_summary_grid>.cs-v4-metric-card {
        flex:1 1 100%!important;
        width:100%!important;
        min-width:0!important;
      }
    }
  `;
  document.head.appendChild(style);
})();
