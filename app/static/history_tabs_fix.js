(() => {
  "use strict";

  const STYLE_ID = "crapscraper-history-tabs-fix";
  document.getElementById(STYLE_ID)?.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    /* Histórico: tabs no mesmo padrão visual das Execuções Simultâneas. */
    #updates_history_controls .updates-history-tabs{
      display:flex!important;
      align-items:stretch!important;
      gap:4px!important;
      padding:0!important;
      margin:14px 0 0!important;
      border-bottom:0!important;
    }

    #updates_history_controls .updates-history-tab{
      position:relative!important;
      bottom:-1px!important;
      min-height:44px!important;
      padding:10px 18px!important;
      border:1px solid rgba(255,255,255,.10)!important;
      border-radius:10px 10px 0 0!important;
      background:rgba(255,255,255,.035)!important;
      color:var(--text-muted)!important;
      box-shadow:none!important;
      transition:background .16s ease,border-color .16s ease,color .16s ease!important;
    }

    #updates_history_controls .updates-history-tab.is-active{
      z-index:2!important;
      background:var(--bg-elev-1)!important;
      color:var(--text)!important;
      border-color:rgba(124,58,237,.72)!important;
      border-bottom:none!important;
      box-shadow:none!important;
    }

    #updates_history_controls .updates-history-tab:not(.is-active):hover{
      background:rgba(255,255,255,.05)!important;
      color:var(--text)!important;
    }

    #updates_history_controls + #updates_history,
    #updates_history_controls ~ #updates_history{
      background:var(--bg-elev-1)!important;
    }

    /* Histórico: mantém status + tentar novamente + detalhes na mesma linha. */
    #updates_history .update-queue-row{
      grid-template-columns:54px minmax(0,1fr) auto auto auto!important;
      align-items:start!important;
      column-gap:12px!important;
    }

    #updates_history .update-queue-row > .badge{
      grid-column:3!important;
      grid-row:1!important;
      align-self:start!important;
      white-space:nowrap!important;
    }

    #updates_history .update-queue-row > .update-retry-btn{
      grid-column:4!important;
      grid-row:1!important;
      align-self:start!important;
      white-space:nowrap!important;
    }

    #updates_history .update-queue-row > .update-history-details{
      grid-column:5!important;
      grid-row:1!important;
      align-self:start!important;
      white-space:nowrap!important;
    }

    #updates_history .update-queue-row > .update-operational-detail{
      grid-column:2 / -1!important;
      grid-row:2!important;
      width:100%!important;
      min-width:0!important;
    }

    @media (max-width:900px){
      #updates_history .update-queue-row{
        grid-template-columns:42px minmax(0,1fr)!important;
      }
      #updates_history .update-queue-row > .badge,
      #updates_history .update-queue-row > .update-retry-btn,
      #updates_history .update-queue-row > .update-history-details{
        grid-column:2!important;
        grid-row:auto!important;
        justify-self:start!important;
      }
      #updates_history .update-queue-row > .update-operational-detail{
        grid-column:1 / -1!important;
        grid-row:auto!important;
      }
    }
  `;
  document.head.appendChild(style);
})();
