(() => {
  "use strict";

  const STYLE_ID = "crapscraper-update-lists-manager-ui";
  const DEFAULT_PAGE_SIZE = 25;
  const state = {
    selectedName: "",
    items: [],
    metadata: null,
    query: "",
    page: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    loading: false,
    requestToken: 0,
  };

  const byId = id => document.getElementById(id);
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #update_lists_modal .update-lists-modal-card{
      width:min(1480px,calc(100vw - 48px))!important;
      max-width:1480px!important;
      max-height:calc(100vh - 48px)!important;
      overflow:auto!important;
      overscroll-behavior:contain!important;
    }
    #update_lists_modal .update-list-row{
      gap:16px!important;
    }
    #update_lists_modal .update-list-row > .row{
      flex-wrap:wrap!important;
      justify-content:flex-end!important;
    }
    #update_lists_modal .update-list-row.cs-preview-selected{
      border-color:rgba(124,58,237,.82)!important;
      box-shadow:inset 0 0 0 1px rgba(124,58,237,.20)!important;
    }
    #update_lists_modal .update-list-row [data-update-list-action="preview"]{
      display:none!important;
    }
    #update_lists_modal .cs-update-list-download{
      white-space:nowrap!important;
    }
    .update-lists-integrated-preview{
      margin-top:18px!important;
      padding-top:18px!important;
      border-top:1px solid var(--line-strong)!important;
      min-width:0!important;
    }
    .update-lists-preview-head{
      display:flex!important;
      align-items:flex-start!important;
      justify-content:space-between!important;
      gap:16px!important;
      flex-wrap:wrap!important;
      margin-bottom:12px!important;
    }
    .update-lists-preview-head-copy{
      min-width:0!important;
      flex:1 1 480px!important;
    }
    .update-lists-preview-title{
      margin:0 0 7px!important;
      font-size:18px!important;
      font-weight:800!important;
    }
    .update-lists-preview-summary{
      display:flex!important;
      flex-wrap:wrap!important;
      gap:8px!important;
      color:var(--text-muted)!important;
      font-size:13px!important;
    }
    .update-lists-preview-summary > span{
      display:inline-flex!important;
      align-items:center!important;
      min-height:34px!important;
      padding:6px 10px!important;
      border:1px solid var(--line)!important;
      border-radius:9px!important;
      background:rgba(255,255,255,.025)!important;
    }
    .update-lists-preview-search{
      display:grid!important;
      grid-template-columns:1fr!important;
      gap:12px!important;
      padding:14px!important;
      margin:0 0 10px!important;
      border:1px solid #292931!important;
      border-radius:14px!important;
      background:#111114!important;
    }
    .update-lists-preview-search label{
      display:grid!important;
      gap:7px!important;
      margin:0!important;
      font-size:12px!important;
      font-weight:700!important;
      color:#d7d7df!important;
    }
    .update-lists-preview-search input{
      width:100%!important;
      min-width:0!important;
      min-height:46px!important;
      border:1px solid #292931!important;
      border-radius:10px!important;
      background:#09090b!important;
      color:#fff!important;
      padding:0 14px!important;
    }
    .update-lists-preview-meta{
      display:flex!important;
      align-items:center!important;
      justify-content:space-between!important;
      gap:14px!important;
      min-height:48px!important;
      margin:8px 0 10px!important;
      color:var(--text-muted)!important;
    }
    .update-lists-preview-page-size{
      display:flex!important;
      align-items:center!important;
      gap:10px!important;
      margin-left:auto!important;
      white-space:nowrap!important;
      font-size:13px!important;
    }
    .update-lists-preview-page-size select{
      width:92px!important;
      min-width:92px!important;
      height:42px!important;
      min-height:42px!important;
      border:1px solid #292931!important;
      border-radius:10px!important;
      background:#09090b!important;
      color:#fff!important;
      padding:0 30px 0 12px!important;
    }
    .update-lists-preview-pagination{
      display:grid!important;
      grid-template-columns:minmax(160px,1fr) auto minmax(160px,1fr)!important;
      gap:12px!important;
      align-items:center!important;
      width:100%!important;
      margin:0 0 14px!important;
    }
    .update-lists-preview-pagination > button{
      width:100%!important;
      min-height:48px!important;
    }
    .update-lists-preview-page-jump{
      display:inline-flex!important;
      align-items:center!important;
      justify-content:center!important;
      gap:6px!important;
      min-height:36px!important;
      padding:4px 10px!important;
      border:1px solid #292931!important;
      border-radius:999px!important;
      background:#17171b!important;
      color:#fff!important;
      font-size:12px!important;
      font-weight:800!important;
      white-space:nowrap!important;
    }
    .update-lists-preview-page-jump input{
      width:58px!important;
      min-width:58px!important;
      height:28px!important;
      min-height:28px!important;
      padding:0 6px!important;
      text-align:center!important;
      border:1px solid #41414b!important;
      border-radius:7px!important;
      background:#09090b!important;
      color:#fff!important;
      font-size:12px!important;
      font-weight:800!important;
    }
    .update-lists-preview-table-wrap{
      width:100%!important;
      overflow:auto!important;
      border:1px solid var(--line)!important;
      border-radius:12px!important;
    }
    .update-lists-preview-table{
      width:100%!important;
      min-width:1050px!important;
      border-collapse:collapse!important;
    }
    .update-lists-preview-table th,
    .update-lists-preview-table td{
      padding:12px 14px!important;
      border-bottom:1px solid var(--line)!important;
      text-align:left!important;
      vertical-align:top!important;
    }
    .update-lists-preview-table tbody tr:last-child td{
      border-bottom:0!important;
    }
    .update-lists-preview-empty,
    .update-lists-preview-loading,
    .update-lists-preview-error{
      padding:22px!important;
      color:var(--text-muted)!important;
    }
    .update-lists-preview-error{color:#fca5a5!important;}
    #update_list_preview_modal{
      display:none!important;
    }
    @media(max-width:760px){
      #update_lists_modal .update-lists-modal-card{
        width:calc(100vw - 20px)!important;
        max-height:calc(100vh - 20px)!important;
      }
      .update-lists-preview-meta{
        align-items:flex-start!important;
        flex-direction:column!important;
      }
      .update-lists-preview-page-size{margin-left:0!important;}
      .update-lists-preview-pagination{
        grid-template-columns:1fr 1fr!important;
      }
      .update-lists-preview-page-jump{
        grid-column:1/-1!important;
        grid-row:1!important;
      }
    }
  `;
  document.getElementById(STYLE_ID)?.remove();
  document.head.appendChild(style);

  function managerCard() {
    return byId("update_lists_modal")?.querySelector(".update-lists-modal-card") || null;
  }

  function ensurePreviewHost() {
    const card = managerCard();
    if (!card) return null;
    let host = byId("update_lists_integrated_preview");
    if (host && card.contains(host)) return host;
    host = document.createElement("section");
    host.id = "update_lists_integrated_preview";
    host.className = "update-lists-integrated-preview";
    host.setAttribute("aria-live", "polite");
    card.appendChild(host);
    return host;
  }

  function queueRows() {
    return [...document.querySelectorAll("#update_lists_rows [data-update-list-name]")];
  }

  function queueNames() {
    return queueRows().map(row => normalize(row.dataset.updateListName)).filter(Boolean);
  }

  function activeQueueName() {
    const select = byId("updates_queue_select");
    const selected = normalize(select?.value);
    if (selected) return selected;
    const activeButton = document.querySelector("#update_lists_rows [data-update-list-action='activate']:disabled");
    return normalize(activeButton?.closest("[data-update-list-name]")?.dataset.updateListName);
  }

  function preferredQueueName() {
    const names = queueNames();
    if (state.selectedName && names.includes(state.selectedName)) return state.selectedName;
    const active = activeQueueName();
    if (active && names.includes(active)) return active;
    if (names.includes("default")) return "default";
    return names[0] || "";
  }

  async function requestDetails(name) {
    const response = await fetch(`/atualizacoes/filas/detalhes?name=${encodeURIComponent(name)}`, {
      credentials: "same-origin",
      cache: "no-store",
    });
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || payload?.error || `HTTP ${response.status}`);
    }
    return payload;
  }

  function statusLabel(value) {
    const labels = {
      approved: "Aprovado",
      waiting: "Aguardando",
      preparing: "Preparando",
      prepared: "Preparado",
      plan_ready: "Plano pronto",
      queued: "Na fila",
      executing: "Executando",
      completed: "Concluído",
      rolled_back: "Rollback concluído",
      blocked: "Bloqueado",
      error: "Erro",
      failed: "Falhou",
      canceled: "Cancelado",
      interrupted: "Interrompido",
      rollback_required: "Rollback necessário",
    };
    const key = normalize(value).toLowerCase();
    return labels[key] || normalize(value) || "-";
  }

  function filteredItems() {
    const query = normalize(state.query).toLowerCase();
    if (!query) return state.items;
    return state.items.filter(item => `${item.name || ""} ${item.woo_product_id || ""} ${item.state || ""} ${item.job_id || ""}`.toLowerCase().includes(query));
  }

  function pageInfo() {
    const items = filteredItems();
    const requested = Number.parseInt(String(state.pageSize || ""), 10);
    const size = Number.isFinite(requested) && requested > 0 ? Math.min(requested, 10000) : DEFAULT_PAGE_SIZE;
    const pages = Math.max(1, Math.ceil(items.length / size));
    state.page = Math.max(1, Math.min(Number(state.page) || 1, pages));
    const start = (state.page - 1) * size;
    return {items, size, pages, start, visible: items.slice(start, start + size)};
  }

  function rangeText(total, page, size) {
    if (!total) return "Mostrando 0 de 0 itens";
    const start = ((page - 1) * size) + 1;
    const end = Math.min(page * size, total);
    return `Mostrando ${start}–${end} de ${total} itens`;
  }

  function renderSelectedRows() {
    queueRows().forEach(row => {
      row.classList.toggle("cs-preview-selected", normalize(row.dataset.updateListName) === state.selectedName);
    });
  }

  function ensureDownloadButtons() {
    queueRows().forEach(row => {
      const actions = row.querySelector(":scope > .row") || row.querySelector(".row");
      if (!actions || actions.querySelector(".cs-update-list-download")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn-secondary btn-sm cs-update-list-download";
      button.dataset.updateListDownload = normalize(row.dataset.updateListName);
      button.textContent = "⬇️ Baixar";
      const preview = actions.querySelector("[data-update-list-action='preview']");
      if (preview) preview.insertAdjacentElement("afterend", button);
      else actions.prepend(button);
    });
    renderSelectedRows();
  }

  function summaryHtml(meta) {
    return [
      `<span><strong>${escapeHtml(meta?.total || 0)}</strong>&nbsp;itens</span>`,
      `<span><strong>${escapeHtml(meta?.completed || 0)}</strong>&nbsp;concluídos</span>`,
      `<span><strong>${escapeHtml(meta?.pending || 0)}</strong>&nbsp;pendentes</span>`,
      `<span>Arquivo:&nbsp;<strong>${escapeHtml(meta?.file || "-")}</strong></span>`,
      `<span>Última conclusão:&nbsp;<strong>${escapeHtml(meta?.last_completed_at || "Não registrada")}</strong></span>`,
    ].join("");
  }

  function renderPreview() {
    const host = ensurePreviewHost();
    if (!host) return;
    renderSelectedRows();

    if (state.loading) {
      host.innerHTML = `<div class="update-lists-preview-loading">Carregando a lista selecionada...</div>`;
      return;
    }
    if (!state.selectedName) {
      host.innerHTML = `<div class="update-lists-preview-empty">Nenhuma lista disponível para visualizar.</div>`;
      return;
    }

    const info = pageInfo();
    const displayName = state.selectedName === "default" ? "Padrão" : state.selectedName;
    const rows = info.visible.map(item => `
      <tr>
        <td>${escapeHtml(item.position || "-")}</td>
        <td>#${escapeHtml(item.woo_product_id || "-")}</td>
        <td><strong>${escapeHtml(item.name || "-")}</strong>${item.execution_error ? `<div class="updates-error">${escapeHtml(item.execution_error)}</div>` : ""}</td>
        <td>${escapeHtml(statusLabel(item.state))}</td>
        <td>${escapeHtml(item.plugintema_version || "-")} → ${escapeHtml(item.source_version || "-")}</td>
        <td>${escapeHtml(item.completed_at || item.updated_at || item.queued_at || "-")}</td>
        <td>${escapeHtml(item.last_completed_step || "-")}</td>
      </tr>`).join("") || `<tr><td colspan="7">Nenhum item encontrado nesta lista.</td></tr>`;

    host.innerHTML = `
      <div class="update-lists-preview-head">
        <div class="update-lists-preview-head-copy">
          <div class="update-lists-preview-title">Lista: ${escapeHtml(displayName)}</div>
          <div class="update-lists-preview-summary">${summaryHtml(state.metadata)}</div>
        </div>
        <button class="btn-secondary cs-update-list-download" type="button" data-update-list-download="${escapeHtml(state.selectedName)}">⬇️ Baixar CSV</button>
      </div>
      <div class="update-lists-preview-search">
        <label>Pesquisar na lista
          <input id="update_lists_inline_search" type="search" value="${escapeHtml(state.query)}" placeholder="Produto, WooCommerce ID ou estado">
        </label>
      </div>
      <div class="update-lists-preview-meta">
        <div class="small">${escapeHtml(rangeText(info.items.length, state.page, info.size))}</div>
        <label class="update-lists-preview-page-size">Itens por página
          <input id="update_lists_inline_page_size" class="listing-page-size-input" type="number" min="1" step="1" value="${info.size}" inputmode="numeric">
        </label>
      </div>
      <div class="update-lists-preview-pagination">
        <button class="btn-secondary" id="update_lists_inline_prev" type="button" ${state.page <= 1 ? "disabled" : ""}>← Anterior</button>
        <label class="update-lists-preview-page-jump">Página
          <input id="update_lists_inline_page" type="number" min="1" max="${info.pages}" value="${state.page}" inputmode="numeric" aria-label="Ir para página">
          de <span>${info.pages}</span>
        </label>
        <button class="btn-secondary" id="update_lists_inline_next" type="button" ${state.page >= info.pages ? "disabled" : ""}>Próxima →</button>
      </div>
      <div class="update-lists-preview-table-wrap">
        <table class="catalogos-table update-lists-preview-table">
          <thead><tr><th>Posição</th><th>Woo ID</th><th>Produto</th><th>Estado</th><th>Versões</th><th>Atualização</th><th>Última etapa</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  async function loadPreview(name, {resetQuery = true} = {}) {
    const normalizedName = normalize(name);
    if (!normalizedName) return;
    const token = ++state.requestToken;
    state.selectedName = normalizedName;
    state.page = 1;
    if (resetQuery) state.query = "";
    state.loading = true;
    renderPreview();
    try {
      const result = await requestDetails(normalizedName);
      if (token !== state.requestToken) return;
      state.items = Array.isArray(result.items) ? result.items : [];
      state.metadata = result.queue || {name: normalizedName, total: state.items.length};
      state.loading = false;
      renderPreview();
    } catch (error) {
      if (token !== state.requestToken) return;
      state.items = [];
      state.metadata = null;
      state.loading = false;
      const host = ensurePreviewHost();
      if (host) host.innerHTML = `<div class="update-lists-preview-error">Não foi possível carregar a lista: ${escapeHtml(error?.message || error)}</div>`;
    }
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return `"${text.replaceAll('"', '""')}"`;
  }

  async function downloadQueue(name) {
    const normalizedName = normalize(name);
    if (!normalizedName) return;
    let result;
    if (state.selectedName === normalizedName && state.metadata) {
      result = {items: state.items, queue: state.metadata};
    } else {
      result = await requestDetails(normalizedName);
    }
    const items = Array.isArray(result.items) ? result.items : [];
    const meta = result.queue || {};
    const headers = ["queue_name", "position", "job_id", "woocommerce_id", "product", "state", "queued_at", "updated_at", "completed_at", "last_completed_step"];
    const lines = [headers.join(",")];
    items.forEach(item => {
      lines.push([
        normalizedName,
        item.position || "",
        item.job_id || "",
        item.woo_product_id || "",
        item.name || "",
        item.state || "",
        item.queued_at || "",
        item.updated_at || "",
        item.completed_at || "",
        item.last_completed_step || "",
      ].map(csvCell).join(","));
    });
    const blob = new Blob(["\ufeff", lines.join("\r\n"), "\r\n"], {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = normalize(meta.file) || `${normalizedName.replace(/[^a-z0-9_-]+/gi, "-") || "lista"}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function loadDefaultPreview() {
    ensureDownloadButtons();
    const name = preferredQueueName();
    if (!name) {
      state.selectedName = "";
      state.items = [];
      state.metadata = null;
      state.loading = false;
      renderPreview();
      return;
    }
    if (state.selectedName === name && state.metadata) {
      renderPreview();
      return;
    }
    loadPreview(name).catch(() => {});
  }

  function scheduleDefaultPreview() {
    [0, 60, 160, 360].forEach(delay => window.setTimeout(loadDefaultPreview, delay));
  }

  document.addEventListener("click", event => {
    const previewButton = event.target?.closest?.("#update_lists_rows [data-update-list-action='preview']");
    if (previewButton) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const name = normalize(previewButton.closest("[data-update-list-name]")?.dataset.updateListName);
      if (name) loadPreview(name).catch(() => {});
      return;
    }

    const downloadButton = event.target?.closest?.("[data-update-list-download]");
    if (downloadButton && byId("update_lists_modal")?.contains(downloadButton)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      downloadButton.disabled = true;
      downloadQueue(downloadButton.dataset.updateListDownload)
        .catch(error => {
          const host = ensurePreviewHost();
          if (host) host.insertAdjacentHTML("afterbegin", `<div class="update-lists-preview-error">Falha ao baixar CSV: ${escapeHtml(error?.message || error)}</div>`);
        })
        .finally(() => { if (document.contains(downloadButton)) downloadButton.disabled = false; });
      return;
    }

    if (event.target?.closest?.("#open_update_lists_modal")) {
      scheduleDefaultPreview();
    }
  }, true);

  document.addEventListener("input", event => {
    if (event.target?.id === "update_lists_inline_search") {
      state.query = event.target.value;
      state.page = 1;
      renderPreview();
      byId("update_lists_inline_search")?.focus();
    }
  });

  document.addEventListener("change", event => {
    if (event.target?.id === "update_lists_inline_page_size") {
      const requested = Number.parseInt(event.target.value, 10);
      state.pageSize = Number.isFinite(requested) && requested > 0 ? Math.min(requested, 10000) : DEFAULT_PAGE_SIZE;
      state.page = 1;
      renderPreview();
    }
  });

  document.addEventListener("click", event => {
    if (event.target?.id === "update_lists_inline_prev") {
      state.page = Math.max(1, state.page - 1);
      renderPreview();
    } else if (event.target?.id === "update_lists_inline_next") {
      state.page += 1;
      renderPreview();
    }
  });

  let pageTimer = null;
  document.addEventListener("input", event => {
    if (event.target?.id !== "update_lists_inline_page") return;
    window.clearTimeout(pageTimer);
    pageTimer = window.setTimeout(() => {
      const info = pageInfo();
      state.page = Math.max(1, Math.min(Number(event.target.value) || state.page, info.pages));
      renderPreview();
    }, 500);
  });

  let mutationTimer = null;
  const observer = new MutationObserver(mutations => {
    const relevant = mutations.some(mutation => {
      const target = mutation.target?.nodeType === Node.ELEMENT_NODE ? mutation.target : mutation.target?.parentElement;
      return target?.id === "update_lists_rows" || target?.closest?.("#update_lists_rows");
    });
    if (!relevant) return;
    window.clearTimeout(mutationTimer);
    mutationTimer = window.setTimeout(() => {
      ensureDownloadButtons();
      renderSelectedRows();
      if (!byId("update_lists_modal")?.classList.contains("hidden")) {
        const names = queueNames();
        if (!state.selectedName || !names.includes(state.selectedName)) loadDefaultPreview();
      }
    }, 60);
  });

  function start() {
    observer.observe(document.body, {childList:true, subtree:true});
    ensureDownloadButtons();
    if (!byId("update_lists_modal")?.classList.contains("hidden")) scheduleDefaultPreview();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
