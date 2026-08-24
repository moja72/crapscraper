(() => {
  "use strict";

  if (window.__csListManagerVisualPolish) return;
  window.__csListManagerVisualPolish = true;

  const STYLE_ID = "cs-list-manager-visual-polish-style";

  function installStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      #cs_addition_list_manager_modal{
        padding:24px!important;
      }
      #cs_addition_list_manager_modal .cs-lm-modal{
        width:min(1480px,calc(100vw - 48px))!important;
        max-width:1480px!important;
        max-height:calc(100vh - 48px)!important;
        padding:62px 18px 18px!important;
        overflow:auto!important;
        overscroll-behavior:contain!important;
      }
      #cs_addition_list_manager_modal .cs-lm-x{
        top:14px!important;
        right:14px!important;
        width:38px!important;
        min-width:38px!important;
        max-width:38px!important;
        height:38px!important;
        min-height:38px!important;
        max-height:38px!important;
        padding:0!important;
        border-radius:50%!important;
        line-height:1!important;
      }
      #cs_addition_list_manager_modal .cs-lm-head{
        padding-right:0!important;
      }
      #cs_addition_list_manager_modal .cs-lm-actions [data-a="activate"]{
        background:var(--success,#10b981)!important;
        border-color:var(--success,#10b981)!important;
        color:#06150f!important;
      }
      #cs_addition_list_manager_modal .cs-lm-actions [data-a="activate"]:disabled{
        opacity:.78!important;
      }
      #cs_addition_list_manager_modal .cs-lm-move{
        display:none!important;
      }
      @media(max-width:760px){
        #cs_addition_list_manager_modal{
          padding:12px!important;
        }
        #cs_addition_list_manager_modal .cs-lm-modal{
          width:calc(100vw - 24px)!important;
          max-width:none!important;
          max-height:calc(100vh - 24px)!important;
          padding:56px 14px 14px!important;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function polishModal() {
    const modal = document.getElementById("cs_addition_list_manager_modal");
    if (!modal) return;

    modal.querySelectorAll(".cs-lm-move").forEach(node => node.remove());

    modal.querySelectorAll('[data-a="download"]').forEach(button => {
      if (button.textContent !== "⬇️ Baixar") button.textContent = "⬇️ Baixar";
    });

    const csv = modal.querySelector("#cs_lm_csv");
    if (csv && csv.textContent !== "⬇️ Baixar CSV") csv.textContent = "⬇️ Baixar CSV";

    modal.querySelectorAll('[data-a="activate"]').forEach(button => {
      button.classList.remove("btn-secondary");
      button.classList.add("btn-success");
    });
  }

  function start() {
    installStyle();
    polishModal();

    const observer = new MutationObserver(() => polishModal());
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
