(() => {
  "use strict";

  const HEADER_TEXT = "Coletar • Comparar • Atualizar • Adicionar • Loja";
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if (document.getElementById("cs-processes-header-position-style")) return;
    const style = document.createElement("style");
    style.id = "cs-processes-header-position-style";
    style.textContent = `
      #cs_processes_header_group{display:inline-flex;align-items:center;gap:10px;flex-wrap:nowrap;white-space:nowrap;max-width:100%}
      #cs_processes_header_group #cs_processes_button{flex:0 0 auto;margin:0}
      #cs_processes_header_group #cs_download_credits{display:inline-flex!important;align-items:center!important;gap:10px!important;margin:0!important;color:#8f99a8;font-size:10px;line-height:1.2;white-space:nowrap}
      #cs_processes_header_group #cs_download_credits>div{display:inline-flex;align-items:center;gap:3px;margin:0!important;white-space:nowrap}
      #cs_processes_header_group #cs_download_credits b{display:inline;font-weight:750}
      @media(max-width:760px){
        #cs_processes_header_group{align-items:flex-start;flex-wrap:wrap}
        #cs_processes_header_group #cs_download_credits{flex-wrap:wrap;gap:6px 10px!important}
      }
    `;
    document.head.appendChild(style);
  }

  function findHeaderTextNode() {
    const existingGroup = document.getElementById("cs_processes_header_group");
    if (existingGroup?.parentElement) return existingGroup.parentElement;
    const matches = Array.from(document.body?.querySelectorAll("*") || [])
      .filter(node => !["SCRIPT", "STYLE", "BUTTON"].includes(node.tagName))
      .filter(node => normalize(node.textContent) === HEADER_TEXT);
    if (!matches.length) return null;
    matches.sort((a, b) => a.querySelectorAll("*").length - b.querySelectorAll("*").length);
    return matches[0];
  }

  function moveProcessesButton() {
    installStyles();
    const button = document.getElementById("cs_processes_button");
    const credits = document.getElementById("cs_download_credits");
    const target = findHeaderTextNode();
    if (!button || !target) return false;

    let group = document.getElementById("cs_processes_header_group");
    if (!group) {
      group = document.createElement("div");
      group.id = "cs_processes_header_group";
    }

    if (button.parentElement !== group) group.appendChild(button);
    if (credits && credits.parentElement !== group) group.appendChild(credits);
    if (group.parentElement !== target || target.childNodes.length !== 1 || target.firstChild !== group) {
      target.replaceChildren(group);
    }
    return true;
  }

  function scheduleMove() {
    [0, 60, 180, 450, 900, 1800, 2600].forEach(delay => setTimeout(moveProcessesButton, delay));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleMove, {once: true});
  } else {
    scheduleMove();
  }
  window.addEventListener("load", scheduleMove, {once: true});
})();
