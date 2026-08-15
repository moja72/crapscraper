(() => {
  "use strict";

  const STYLE_ID = "crapscraper-run-tabs-history-style";
  document.getElementById(STYLE_ID)?.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Execuções Simultâneas: replica o padrão visual das abas do Histórico. */
    #runs_tabs_wrap,
    #runs_manager_card .runs-tabs-wrap{
      display:flex!important;
      align-items:stretch!important;
      gap:4px!important;
      padding:0!important;
      margin:0!important;
      border-bottom:0!important;
      overflow:visible!important;
    }

    #runs_manager_card .run-card-wrap{
      position:relative!important;
      flex:1 1 320px!important;
      min-width:260px!important;
      background:transparent!important;
    }

    #runs_manager_card .run-tab-btn{
      position:relative!important;
      bottom:-1px!important;
      width:100%!important;
      min-height:72px!important;
      padding:10px 18px!important;
      border:1px solid rgba(255,255,255,.10)!important;
      border-radius:10px 10px 0 0!important;
      background:rgba(255,255,255,.035)!important;
      color:var(--text-muted)!important;
      box-shadow:none!important;
      transition:background .16s ease,border-color .16s ease,color .16s ease!important;
    }

    #runs_manager_card .run-tab-btn[aria-selected="true"]{
      z-index:2!important;
      background:transparent!important;
      color:var(--text)!important;
      border-color:rgba(124,58,237,.72)!important;
      border-bottom:none!important;
      box-shadow:none!important;
    }

    #runs_manager_card .run-tab-btn[aria-selected="false"]:hover{
      background:rgba(255,255,255,.05)!important;
      color:var(--text)!important;
    }

    #runs_manager_card .run-card-wrap > .run-close-btn,
    #runs_manager_card .run-card-wrap > button[aria-label*="Fechar"],
    #runs_manager_card .run-card-wrap > button[title*="Fechar"]{
      z-index:5!important;
    }

    /* O gerenciador integrado mantém a troca explícita entre listas. */
    html body #update_lists_modal .update-list-row [data-update-list-action="preview"]{
      display:inline-flex!important;
    }
  `;

  document.head.appendChild(style);
})();
