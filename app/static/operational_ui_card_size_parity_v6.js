(() => {
  "use strict";

  if (window.__crapScraperOperationalUiCardSizeParityV6Installed) return;
  window.__crapScraperOperationalUiCardSizeParityV6Installed = true;

  const style = document.createElement("style");
  style.id = "cs-operational-ui-card-size-parity-v6-style";
  style.textContent = `
    /*
     * Contrato visual único dos cards operacionais.
     * A especificidade é deliberadamente maior que as camadas legadas v4/v5,
     * para impedir que Adicionar volte a distribuir o espaço livre entre cards.
     */
    #tab_panel_atualizacoes #updates_summary,
    #addition_intro_card #addition_summary_grid {
      display:grid!important;
      grid-template-columns:repeat(auto-fill,200px)!important;
      grid-auto-columns:200px!important;
      column-gap:8px!important;
      row-gap:8px!important;
      justify-content:start!important;
      justify-items:start!important;
      align-content:start!important;
      align-items:stretch!important;
      width:100%!important;
      margin:12px 0 0!important;
      padding:0!important;
      border:0!important;
      background:transparent!important;
    }

    #tab_panel_atualizacoes #updates_summary>.cs-v5-metric-card,
    #tab_panel_atualizacoes #updates_summary>.cs-v4-metric-card,
    #addition_intro_card #addition_summary_grid>.addition-summary-chip,
    #addition_intro_card #addition_summary_grid>.cs-v5-metric-card,
    #addition_intro_card #addition_summary_grid>.cs-v4-metric-card {
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
      flex:0 0 200px!important;
      flex-direction:column!important;
      justify-content:center!important;
      align-items:stretch!important;
      justify-self:start!important;
      gap:4px!important;
      text-align:left!important;
      box-shadow:none!important;
      transform:none!important;
      appearance:none!important;
      font:inherit!important;
      overflow:visible!important;
    }

    #tab_panel_atualizacoes #updates_summary>.cs-v5-metric-card:hover,
    #tab_panel_atualizacoes #updates_summary>.cs-v4-metric-card:hover,
    #addition_intro_card #addition_summary_grid>.addition-summary-chip:hover,
    #addition_intro_card #addition_summary_grid>.cs-v5-metric-card:hover,
    #addition_intro_card #addition_summary_grid>.cs-v4-metric-card:hover {
      border-color:var(--line-accent)!important;
      background:var(--accent-soft)!important;
    }

    #tab_panel_atualizacoes #updates_summary>.is-filter-active,
    #addition_intro_card #addition_summary_grid>.is-filter-active,
    #tab_panel_atualizacoes #updates_summary>[aria-pressed="true"] {
      border-color:rgba(124,58,237,.88)!important;
      background:linear-gradient(180deg,rgba(124,58,237,.20),rgba(124,58,237,.10))!important;
      box-shadow:inset 0 0 0 1px rgba(143,91,255,.20)!important;
    }

    #tab_panel_atualizacoes #updates_summary>*>strong,
    #addition_intro_card #addition_summary_grid>*>strong {
      display:block!important;
      margin:0!important;
      color:var(--text)!important;
      font-size:18px!important;
      font-weight:800!important;
      line-height:1!important;
      font-variant-numeric:tabular-nums!important;
    }

    #tab_panel_atualizacoes #updates_summary .cs-v5-metric-footer,
    #tab_panel_atualizacoes #updates_summary .cs-v4-metric-footer,
    #tab_panel_atualizacoes #updates_summary .operational-summary-footer,
    #addition_intro_card #addition_summary_grid .cs-v5-metric-footer,
    #addition_intro_card #addition_summary_grid .cs-v4-metric-footer,
    #addition_intro_card #addition_summary_grid .operational-summary-footer {
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

    #tab_panel_atualizacoes #updates_summary .cs-v5-metric-label,
    #tab_panel_atualizacoes #updates_summary .cs-v4-metric-label,
    #tab_panel_atualizacoes #updates_summary .operational-summary-label,
    #addition_intro_card #addition_summary_grid .cs-v5-metric-label,
    #addition_intro_card #addition_summary_grid .cs-v4-metric-label,
    #addition_intro_card #addition_summary_grid .operational-summary-label {
      min-width:0!important;
      color:var(--text-muted)!important;
      font-size:11px!important;
      font-weight:650!important;
      line-height:1.2!important;
    }

    #tab_panel_atualizacoes #updates_summary .comparison-help,
    #addition_intro_card #addition_summary_grid .comparison-help,
    #tab_panel_atualizacoes #updates_summary .operational-summary-help,
    #addition_intro_card #addition_summary_grid .operational-summary-help {
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

    /*
     * Histórico: a aba ativa usa somente a borda roxa.
     * O fundo permanece transparente para conservar exatamente o fundo do painel.
     */
    #tab_panel_atualizacoes .updates-history-tab.is-active,
    #tab_panel_adicoes #addition_history_tabs .updates-history-tab.is-active,
    #tab_panel_atualizacoes .updates-history-tab.is-active:hover,
    #tab_panel_adicoes #addition_history_tabs .updates-history-tab.is-active:hover {
      border-color:var(--accent)!important;
      border-bottom-color:var(--accent)!important;
      background:transparent!important;
      box-shadow:none!important;
      color:var(--text)!important;
    }

    @media(max-width:1200px){
      #tab_panel_atualizacoes #updates_summary,
      #addition_intro_card #addition_summary_grid {
        grid-template-columns:repeat(auto-fill,180px)!important;
        grid-auto-columns:180px!important;
      }
      #tab_panel_atualizacoes #updates_summary>.cs-v5-metric-card,
      #tab_panel_atualizacoes #updates_summary>.cs-v4-metric-card,
      #addition_intro_card #addition_summary_grid>.addition-summary-chip,
      #addition_intro_card #addition_summary_grid>.cs-v5-metric-card,
      #addition_intro_card #addition_summary_grid>.cs-v4-metric-card {
        width:180px!important;
        min-width:180px!important;
        max-width:180px!important;
        flex-basis:180px!important;
      }
    }

    @media(max-width:760px){
      #tab_panel_atualizacoes #updates_summary,
      #addition_intro_card #addition_summary_grid {
        grid-template-columns:repeat(2,minmax(0,1fr))!important;
        grid-auto-columns:auto!important;
      }
      #tab_panel_atualizacoes #updates_summary>.cs-v5-metric-card,
      #tab_panel_atualizacoes #updates_summary>.cs-v4-metric-card,
      #addition_intro_card #addition_summary_grid>.addition-summary-chip,
      #addition_intro_card #addition_summary_grid>.cs-v5-metric-card,
      #addition_intro_card #addition_summary_grid>.cs-v4-metric-card {
        width:100%!important;
        min-width:0!important;
        max-width:none!important;
        flex-basis:auto!important;
      }
    }

    @media(max-width:480px){
      #tab_panel_atualizacoes #updates_summary,
      #addition_intro_card #addition_summary_grid {
        grid-template-columns:1fr!important;
      }
    }
  `;
  document.head.appendChild(style);
})();
