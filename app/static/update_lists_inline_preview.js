(() => {
  "use strict";

  const STYLE_ID = "crapscraper-update-lists-inline-preview-style";
  document.getElementById(STYLE_ID)?.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .update-lists-inline-preview{
      margin-top:18px!important;
      padding-top:18px!important;
      border-top:1px solid var(--line-strong)!important;
    }
    .update-lists-inline-preview #update_list_preview_title{
      margin:0 0 12px!important;
    }
    .update-lists-inline-preview #update_list_preview_summary{
      margin:0 0 14px!important;
    }
    .update-lists-inline-preview .update-list-preview-toolbar{
      display:grid!important;
      grid-template-columns:minmax(0,1fr)!important;
      gap:12px!important;
      align-items:end!important;
      margin:0 0 10px!important;
      padding:14px!important;
      border:1px solid #292931!important;
      border-radius:14px!important;
      background:#111114!important;
    }
    .update-lists-inline-preview .update-list-preview-toolbar > label{
      width:100%!important;
      min-width:0!important;
      margin:0!important;
    }
    .update-lists-inline-preview #update_list_preview_search{
      width:100%!important;
    }
    .update-lists-inline-preview #update_list_preview_count{
      display:none!important;
    }
    .update-lists-inline-preview .update-list-preview-listing-meta{
      margin:8px 0 10px!important;
    }
    .update-lists-inline-preview .listing-pagination{
      margin:0 0 14px!important;
    }
    .update-lists-inline-preview .table-wrap{
      margin-top:0!important;
    }
    #update_list_preview_modal.cs-inline-preview-source{
      display:none!important;
      pointer-events:none!important;
    }
  `;
  document.head.appendChild(style);

  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function findManagerCard() {
    const headings = [...document.querySelectorAll("h1,h2,h3,h4,.section-title,strong")];
    const title = headings.find(node => /^Gerenciar Listas de Atualização$/i.test(normalize(node.textContent)));
    if (!title) return null;
    return title.closest(".configuration-modal-card,.modal-card,[role='dialog'],.comparison-link-modal-card")
      || title.parentElement;
  }

  function getPreviewParts() {
    const title = document.getElementById("update_list_preview_title");
    const summary = document.getElementById("update_list_preview_summary");
    const toolbar = document.querySelector(".update-list-preview-toolbar");
    const meta = document.querySelector(".update-list-preview-listing-meta")
      || document.getElementById("update_list_preview_result_meta")?.closest(".listing-meta-row");
    const pagination = document.getElementById("update_list_preview_page")?.closest(".listing-pagination");
    const rows = document.getElementById("update_list_preview_rows");
    const tableWrap = rows?.closest(".table-wrap");
    return {title, summary, toolbar, meta, pagination, tableWrap};
  }

  function ensureInlineHost() {
    const manager = findManagerCard();
    if (!manager) return null;
    let host = manager.querySelector(".update-lists-inline-preview");
    if (!host) {
      host = document.createElement("section");
      host.className = "update-lists-inline-preview cs-search-system";
      host.dataset.csSearchSystem = "update-list-preview-inline";
      host.hidden = true;
      manager.appendChild(host);
    }
    return host;
  }

  function movePreviewInline() {
    const modal = document.getElementById("update_list_preview_modal");
    const host = ensureInlineHost();
    if (!modal || !host) return false;

    const parts = getPreviewParts();
    if (!parts.title || !parts.toolbar || !parts.tableWrap) return false;

    const ordered = [
      parts.title,
      parts.summary,
      parts.toolbar,
      parts.meta,
      parts.pagination,
      parts.tableWrap,
    ].filter(Boolean);

    ordered.forEach(node => {
      if (node.parentElement !== host) host.appendChild(node);
    });

    host.hidden = false;
    modal.classList.add("hidden", "cs-inline-preview-source");
    modal.setAttribute("aria-hidden", "true");
    return true;
  }

  function keepNestedModalClosed() {
    const modal = document.getElementById("update_list_preview_modal");
    if (!modal) return;
    if (document.querySelector(".update-lists-inline-preview #update_list_preview_rows")) {
      modal.classList.add("hidden", "cs-inline-preview-source");
      modal.setAttribute("aria-hidden", "true");
    }
  }

  function scheduleInlinePreview() {
    [0, 50, 140, 320, 700].forEach(delay => {
      window.setTimeout(() => {
        movePreviewInline();
        keepNestedModalClosed();
      }, delay);
    });
  }

  document.addEventListener("click", event => {
    const button = event.target?.closest?.("button");
    if (!button || !/^Visualizar$/i.test(normalize(button.textContent))) return;
    const manager = findManagerCard();
    if (!manager || !manager.contains(button)) return;
    scheduleInlinePreview();
  }, true);

  let timer = null;
  const observer = new MutationObserver(() => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      if (!document.getElementById("update_list_preview_modal")) return;
      if (!document.querySelector(".update-lists-inline-preview #update_list_preview_rows")) {
        const modal = document.getElementById("update_list_preview_modal");
        if (modal && !modal.classList.contains("hidden")) movePreviewInline();
      }
      keepNestedModalClosed();
    }, 60);
  });

  function start() {
    observer.observe(document.body, {childList:true, subtree:true, attributes:true, attributeFilter:["class"]});
    keepNestedModalClosed();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
