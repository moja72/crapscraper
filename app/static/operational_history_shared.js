(() => {
  "use strict";

  if (window.__crapScraperOperationalHistorySharedInstalled) return;
  window.__crapScraperOperationalHistorySharedInstalled = true;

  const SHELL_VERSION = "3";
  const CONFIG = {
    update: { root: "#updates_history_accordion", label: "Atualizar" },
    addition: { root: "#addition_history_accordion", label: "Adicionar" },
  };
  const STATUS_OPTIONS = [
    ["", "Todos"], ["completed", "Concluído"], ["rolled_back", "Rollback concluído"],
    ["error", "Erro"], ["failed", "Falhou"], ["blocked", "Bloqueado"],
    ["rollback_required", "Rollback necessário"], ["interrupted", "Interrompido"],
    ["canceled", "Cancelado"], ["running", "Em andamento"],
  ];
  const SORT_OPTIONS = [
    ["recent", "Mais recente"], ["old", "Mais antigo"],
    ["az", "Alfabética (A–Z)"], ["za", "Alfabética inversa (Z–A)"],
  ];

  const state = { update: freshState(), addition: freshState() };
  let ensureTimer = 0;
  let observer = null;

  function freshState() {
    return {
      items: [], counts: {completed: 0, errors: 0}, mode: "completed",
      query: "", status: "", origin: "", dateFrom: "", dateTo: "", lastDays: "",
      sort: "recent", page: 1, pageSize: 5, loading: false, loaded: false,
    };
  }

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const $$ = (selector, root = document) => Array.from(root?.querySelectorAll?.(selector) || []);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  function options(rows, selected = "") {
    return rows.map(([value, label]) => `<option value="${esc(value)}"${value === selected ? " selected" : ""}>${esc(label)}</option>`).join("");
  }

  function compatibilityMarkup(kind) {
    if (kind === "update") {
      return `<div class="op-history-compat" aria-hidden="true">
        <span id="updates_history_summary"></span><div id="updates_history_controls" class="hidden">
          <input id="updates_history_search"><select id="updates_history_status_filter"><option value=""></option></select>
          <button id="updates_history_download" type="button"></button><button id="updates_history_delete" type="button"></button>
          <button id="updates_history_completed" type="button"></button><button id="updates_history_errors" type="button"></button>
          <span id="updates_history_result_meta"></span><input id="updates_history_page_size" value="5">
          <button id="updates_history_prev" type="button"></button><span id="updates_history_page"></span><button id="updates_history_next" type="button"></button>
        </div><div id="updates_history"></div></div>`;
    }
    return `<div class="op-history-compat" aria-hidden="true">
      <span id="addition_history_summary"></span><input id="addition_history_search"><input id="addition_history_origin">
      <select id="addition_history_state"><option value=""></option></select>
      <button id="addition_history_download" type="button"></button><button id="addition_history_refresh" type="button"></button>
      <span id="addition_history_meta"></span><input id="addition_history_page_size" value="5">
      <button id="addition_history_prev" type="button"></button><span id="addition_history_page"></span><button id="addition_history_next" type="button"></button>
      <div id="addition_history_rows"></div></div>`;
  }

  function shell(kind) {
    const s = state[kind];
    return `
      <summary class="op-history-summary">
        <span class="op-history-title"><span class="updates-disclosure-chevron" aria-hidden="true">▸</span><span class="section-title">Histórico</span></span>
        <span class="small op-history-summary-count" data-oh-summary>0 registro(s)</span>
      </summary>
      <div class="op-history-body" data-oh-body data-oh-shell-version="${SHELL_VERSION}">
        <div class="op-history-toolbar">
          <div class="op-history-filter-grid">
            <label>Buscar no histórico<input data-oh-filter="query" type="search" placeholder="Nome ou WooCommerce ID"></label>
            <label>Estado<select data-oh-filter="status">${options(STATUS_OPTIONS, s.status)}</select></label>
            <label>Origem<input data-oh-filter="origin" type="search" placeholder="UltraPack, PluginTheme ou domínio"></label>
            <label>Ordenar<select data-oh-filter="sort">${options(SORT_OPTIONS, s.sort)}</select></label>
          </div>
          <div class="op-history-actions">
            <button class="btn-secondary" data-oh-action="download" type="button">Baixar histórico</button>
            <button class="btn-danger" data-oh-action="delete" type="button">Apagar histórico</button>
          </div>
        </div>
        <div class="op-history-period" aria-label="Filtro por período">
          <label>Data inicial<input data-oh-filter="date-from" type="date"></label>
          <label>Data final<input data-oh-filter="date-to" type="date"></label>
          <label>Últimos X dias<div class="op-history-last-days"><input data-oh-filter="last-days" type="number" min="1" max="3650" step="1" inputmode="numeric" placeholder="30"><button class="btn-secondary" data-oh-action="last-days" type="button">Aplicar</button></div></label>
          <button class="btn-secondary op-history-clear-period" data-oh-action="clear-period" type="button">Limpar período</button>
        </div>
        <div class="op-history-tabs" role="tablist" aria-label="Tipo de histórico">
          <button class="op-history-tab is-active" data-oh-mode="completed" role="tab" aria-selected="true" type="button">Concluídos (0)</button>
          <button class="op-history-tab" data-oh-mode="errors" role="tab" aria-selected="false" type="button">Erros (0)</button>
        </div>
        <div class="op-history-listing-meta">
          <div class="small" data-oh-meta>Mostrando 0–0 de 0 registros</div>
          <div class="listing-page-size"><label class="small">Itens por página</label><input data-oh-filter="page-size" class="listing-page-size-input" type="number" min="1" max="500" step="1" value="5" inputmode="numeric"></div>
        </div>
        <div class="op-history-pagination">
          <button class="btn-secondary" data-oh-action="prev" type="button">← Anterior</button>
          <span class="badge op-history-page">Página <input data-oh-filter="page" type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span data-oh-pages>1</span></span>
          <button class="btn-secondary" data-oh-action="next" type="button">Próxima →</button>
        </div>
        <div class="op-history-panel" data-oh-rows role="tabpanel" aria-live="polite"><div class="notice">Abra o histórico para carregar os registros.</div></div>
      </div>${compatibilityMarkup(kind)}`;
  }

  function syncControls(kind, root) {
    const s = state[kind];
    const values = {
      query: s.query, status: s.status, origin: s.origin, sort: s.sort,
      "date-from": s.dateFrom, "date-to": s.dateTo, "last-days": s.lastDays,
      "page-size": s.pageSize, page: s.page,
    };
    Object.entries(values).forEach(([key, value]) => {
      const control = $(`[data-oh-filter="${key}"]`, root);
      if (control && String(control.value) !== String(value ?? "")) control.value = String(value ?? "");
    });
  }

  function canonicalPresent(root) {
    const body = $("[data-oh-body]", root);
    return !!body && body.dataset.ohShellVersion === SHELL_VERSION && !!$("[data-oh-filter='sort']", root) && !!$(".op-history-period", root);
  }

  function ensureMounted(kind) {
    const root = $(CONFIG[kind].root);
    if (!root) return false;
    if (!canonicalPresent(root)) {
      const wasOpen = typeof root.open === "boolean" ? root.open : true;
      root.dataset.operationalHistoryShared = "1";
      root.dataset.historyKind = kind;
      root.classList.add("operational-history-shared");
      root.innerHTML = shell(kind);
      if (typeof root.open === "boolean") root.open = wasOpen;
      if (root.dataset.operationalHistoryBound !== "1") {
        bind(kind, root);
        root.addEventListener("toggle", () => { if (root.open) load(kind, true); });
        root.dataset.operationalHistoryBound = "1";
      }
      render(kind);
      if (wasOpen && !state[kind].loaded && !state[kind].loading) load(kind, true);
      return true;
    }
    root.dataset.operationalHistoryShared = "1";
    root.classList.add("operational-history-shared");
    syncControls(kind, root);
    return false;
  }

  function ensureAll() {
    ensureMounted("update");
    ensureMounted("addition");
  }

  function scheduleEnsure(delay = 24) {
    clearTimeout(ensureTimer);
    ensureTimer = window.setTimeout(ensureAll, delay);
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {
      cache: "no-store", credentials: "same-origin",
      headers: options.body ? {"Content-Type": "application/json", ...(options.headers || {})} : (options.headers || {}),
      ...options,
    });
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
    return payload;
  }

  async function load(kind, force = false) {
    const s = state[kind];
    if (s.loading || (s.loaded && !force)) return;
    s.loading = true; render(kind);
    try {
      const payload = await request(`/operacoes/historico?kind=${encodeURIComponent(kind)}`);
      s.items = Array.isArray(payload.items) ? payload.items : [];
      s.counts = payload.counts || {completed: 0, errors: 0};
      s.loaded = true; s.page = 1;
    } catch (error) {
      const root = $(CONFIG[kind].root); const rows = root && $("[data-oh-rows]", root);
      if (rows) rows.innerHTML = `<div class="notice is-error">${esc(error?.message || String(error))}</div>`;
    } finally { s.loading = false; render(kind); }
  }

  function itemTime(item) {
    const raw = text(item?.date || item?.finished_at || item?.started_at);
    const parsed = raw ? new Date(raw) : null;
    return parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : 0;
  }

  function filtered(kind) {
    const s = state[kind];
    const q = text(s.query).toLocaleLowerCase("pt-BR");
    const origin = text(s.origin).toLocaleLowerCase("pt-BR");
    const status = text(s.status);
    let from = null, to = null;
    if (s.lastDays) {
      const days = Math.max(1, Number.parseInt(s.lastDays, 10) || 0);
      if (days) from = Date.now() - days * 86400000;
    } else {
      if (s.dateFrom) { const parsed = new Date(`${s.dateFrom}T00:00:00`); if (!Number.isNaN(parsed.getTime())) from = parsed.getTime(); }
      if (s.dateTo) { const parsed = new Date(`${s.dateTo}T23:59:59.999`); if (!Number.isNaN(parsed.getTime())) to = parsed.getTime(); }
    }
    const items = s.items.filter(item => {
      if (item.bucket !== s.mode) return false;
      if (status && text(item.status) !== status) return false;
      if (q && !`${text(item.name)} ${text(item.woo_product_id)} ${text(item.job_id)}`.toLocaleLowerCase("pt-BR").includes(q)) return false;
      if (origin && !`${text(item.origin)} ${text(item.source_url)}`.toLocaleLowerCase("pt-BR").includes(origin)) return false;
      const time = itemTime(item);
      if (from !== null && (!time || time < from)) return false;
      if (to !== null && (!time || time > to)) return false;
      return true;
    });
    items.sort((a, b) => {
      if (s.sort === "old") return itemTime(a) - itemTime(b);
      if (s.sort === "az") return text(a.name).localeCompare(text(b.name), "pt-BR", {sensitivity:"base"});
      if (s.sort === "za") return text(b.name).localeCompare(text(a.name), "pt-BR", {sensitivity:"base"});
      return itemTime(b) - itemTime(a);
    });
    return items;
  }

  function formatDate(value) {
    const raw = text(value); if (!raw) return "—";
    const date = new Date(raw); if (Number.isNaN(date.getTime())) return raw;
    return new Intl.DateTimeFormat("pt-BR", {day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(date).replace(",", "");
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Number.parseInt(seconds, 10) || 0); if (!total) return "—";
    const days = Math.floor(total / 86400), hours = Math.floor((total % 86400) / 3600), minutes = Math.floor((total % 3600) / 60);
    const parts = []; if (days) parts.push(`${days}d`); if (hours || days) parts.push(`${hours}h`); parts.push(`${minutes}m`); return parts.join(" ");
  }

  function statusClass(status) {
    if (["completed","rolled_back"].includes(status)) return "is-success";
    if (["error","failed","blocked","rollback_required","interrupted","canceled"].includes(status)) return "is-danger";
    return "is-active";
  }

  function rowMarkup(item) {
    const from = text(item.version_from), to = text(item.version_to);
    const version = from && to ? `${from} → ${to}` : (to || from || "—");
    const woo = Number(item.woo_product_id || 0) > 0 ? `Woo #${esc(item.woo_product_id)} · ` : "";
    const attempt = Number(item.attempt_no || 0) > 0 ? ` · Tentativa ${esc(item.attempt_no)}` : "";
    const refs = [
      item.source_url ? `<a href="${esc(item.source_url)}" target="_blank" rel="noopener">origem</a>` : "",
      item.official_url ? `<a href="${esc(item.official_url)}" target="_blank" rel="noopener">link oficial</a>` : "",
    ].filter(Boolean).join(" · ");
    const logs = Array.isArray(item.logs) ? item.logs : [];
    const details = [
      item.product_type ? `<span><b>Tipo:</b> ${esc(item.product_type)}</span>` : "",
      item.category ? `<span><b>Categoria:</b> ${esc(item.category)}</span>` : "",
      item.developer ? `<span><b>Desenvolvedor:</b> ${esc(item.developer)}</span>` : "",
      item.current_step ? `<span><b>Etapa final:</b> ${esc(item.current_step)}</span>` : "",
      `<span><b>Progresso:</b> ${esc(item.progress || 0)}%</span>`,
      `<span><b>Estado final:</b> ${esc(item.final_state || item.status || "—")}</span>`,
      refs ? `<span><b>Referências:</b> ${refs}</span>` : "",
    ].filter(Boolean).join("");
    const technical = `${item.error ? `<div class="op-history-error">${esc(item.error)}</div>` : ""}${logs.length ? `<pre class="op-history-log">${logs.slice(-10).map(esc).join("\n")}</pre>` : ""}`;
    return `<article class="op-history-row" data-oh-row="${esc(item.job_id)}">
      <div class="op-history-main"><strong class="op-history-name">${esc(item.name || item.job_id)}</strong><div class="op-history-meta">${woo}${esc(version)}</div><div class="op-history-meta">Origem: ${esc(item.origin || "—")}${attempt}</div></div>
      <div class="op-history-state"><span class="op-history-badge ${statusClass(text(item.status))}">${esc(item.status_label || item.status || "—")}</span><span class="op-history-result">${esc(item.result || "")}</span></div>
      <div class="op-history-times"><span><b>Início:</b> ${esc(formatDate(item.started_at))}</span><span><b>Fim:</b> ${esc(formatDate(item.finished_at))}</span><span><b>Duração:</b> ${esc(formatDuration(item.duration_seconds))}</span></div>
      <div class="op-history-row-actions"><button class="btn-secondary" data-oh-detail type="button" aria-expanded="false">Detalhes</button></div>
      <div class="op-history-detail hidden" data-oh-detail-panel><div class="op-history-detail-grid">${details}</div>${technical}</div></article>`;
  }

  function render(kind) {
    const root = $(CONFIG[kind].root); if (!root || !canonicalPresent(root)) return;
    const s = state[kind], summary = $("[data-oh-summary]", root), rows = $("[data-oh-rows]", root); if (!summary || !rows) return;
    syncControls(kind, root);
    const completedCount = Number(s.counts?.completed || 0), errorCount = Number(s.counts?.errors || 0);
    summary.textContent = `${completedCount + errorCount} registro(s)`;
    $$('[data-oh-mode]', root).forEach(button => {
      const active = button.dataset.ohMode === s.mode; button.classList.toggle("is-active", active); button.setAttribute("aria-selected", String(active));
      const count = button.dataset.ohMode === "completed" ? completedCount : errorCount;
      button.textContent = `${button.dataset.ohMode === "completed" ? "Concluídos" : "Erros"} (${count})`;
    });
    if (s.loading) { rows.innerHTML = '<div class="op-history-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando histórico persistido…</span></div>'; return; }
    const items = filtered(kind); s.pageSize = Math.max(1, Math.min(500, Number.parseInt(s.pageSize, 10) || 5));
    const pages = Math.max(1, Math.ceil(items.length / s.pageSize)); s.page = Math.min(Math.max(1, Number.parseInt(s.page, 10) || 1), pages);
    const start = (s.page - 1) * s.pageSize, visible = items.slice(start, start + s.pageSize);
    rows.innerHTML = visible.length ? visible.map(rowMarkup).join("") : '<div class="op-history-empty">Nenhum registro corresponde aos filtros.</div>';
    const meta = $("[data-oh-meta]", root); if (meta) meta.textContent = `Mostrando ${items.length ? start + 1 : 0}–${Math.min(start + s.pageSize, items.length)} de ${items.length} registros`;
    const pageInput = $('[data-oh-filter="page"]', root); if (pageInput) { pageInput.value = String(s.page); pageInput.max = String(pages); }
    const pagesNode = $("[data-oh-pages]", root); if (pagesNode) pagesNode.textContent = String(pages);
    const prev = $('[data-oh-action="prev"]', root), next = $('[data-oh-action="next"]', root); if (prev) prev.disabled = s.page <= 1; if (next) next.disabled = s.page >= pages;
  }

  function bind(kind, root) {
    root.addEventListener("input", event => {
      const control = event.target.closest("[data-oh-filter]"); if (!control) return;
      const s = state[kind], key = control.dataset.ohFilter;
      if (key === "query") s.query = control.value; else if (key === "origin") s.origin = control.value;
      else if (key === "page-size") s.pageSize = control.value; else if (key === "page") s.page = control.value;
      else if (key === "last-days") s.lastDays = control.value; else return;
      if (key !== "page") s.page = 1; render(kind);
    });
    root.addEventListener("change", event => {
      const control = event.target.closest("[data-oh-filter]"); if (!control) return;
      const s = state[kind], key = control.dataset.ohFilter;
      if (key === "status") s.status = control.value; else if (key === "sort") s.sort = control.value;
      else if (key === "date-from") { s.dateFrom = control.value; s.lastDays = ""; const last = $('[data-oh-filter="last-days"]', root); if (last) last.value = ""; }
      else if (key === "date-to") { s.dateTo = control.value; s.lastDays = ""; const last = $('[data-oh-filter="last-days"]', root); if (last) last.value = ""; }
      else if (key === "page-size") s.pageSize = control.value; else if (key === "page") s.page = control.value; else return;
      if (key !== "page") s.page = 1; render(kind);
    });
    root.addEventListener("click", async event => {
      const mode = event.target.closest("[data-oh-mode]");
      if (mode) { state[kind].mode = mode.dataset.ohMode || "completed"; state[kind].status = ""; state[kind].page = 1; const status = $('[data-oh-filter="status"]', root); if (status) status.value = ""; render(kind); return; }
      const detail = event.target.closest("[data-oh-detail]");
      if (detail) { const row = detail.closest(".op-history-row"), panel = row && $("[data-oh-detail-panel]", row); if (!panel) return; const hidden = panel.classList.toggle("hidden"); detail.setAttribute("aria-expanded", String(!hidden)); detail.textContent = hidden ? "Detalhes" : "Ocultar"; return; }
      const action = event.target.closest("[data-oh-action]"); if (!action) return;
      const type = action.dataset.ohAction, s = state[kind];
      if (type === "prev") { s.page = Math.max(1, s.page - 1); render(kind); return; }
      if (type === "next") { s.page += 1; render(kind); return; }
      if (type === "clear-period") { s.dateFrom = ""; s.dateTo = ""; s.lastDays = ""; s.page = 1; render(kind); return; }
      if (type === "last-days") { const input = $('[data-oh-filter="last-days"]', root); const days = Math.max(1, Math.min(3650, Number.parseInt(input?.value, 10) || 0)); if (!days) return; s.lastDays = String(days); s.dateFrom = ""; s.dateTo = ""; s.page = 1; render(kind); return; }
      if (type === "download") { downloadCsv(kind); return; }
      if (type === "delete") {
        const label = kind === "update" ? "atualizações" : "adições";
        if (!window.confirm(`Apagar todo o histórico de ${label}? Esta ação não pode ser desfeita.`)) return;
        action.disabled = true;
        try { await request("/operacoes/historico/apagar", {method:"POST", body:JSON.stringify({kind})}); s.items = []; s.counts = {completed:0,errors:0}; s.page = 1; s.loaded = false; await load(kind, true); }
        catch (error) { window.alert(error?.message || String(error)); } finally { action.disabled = false; }
      }
    });
  }

  function csvCell(value) { const raw = String(value ?? ""); return `"${raw.replace(/"/g, '""')}"`; }
  function downloadCsv(kind) {
    const rows = filtered(kind), headers = ["Produto","WooCommerce ID","Estado","Origem","Versão anterior","Versão final","Início","Fim","Duração (s)","Resultado","Erro"];
    const body = rows.map(item => [item.name,item.woo_product_id||"",item.status_label||item.status,item.origin,item.version_from,item.version_to,item.started_at,item.finished_at,item.duration_seconds||0,item.result,item.error].map(csvCell).join(","));
    const blob = new Blob(["\ufeff" + [headers.map(csvCell).join(","), ...body].join("\r\n")], {type:"text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob), anchor = document.createElement("a"); anchor.href = url; anchor.download = `historico-${kind === "update" ? "atualizacoes" : "adicoes"}.csv`; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
  }

  function observe() {
    if (observer || !document.body) return;
    observer = new MutationObserver(mutations => {
      const relevant = mutations.some(mutation => {
        const target = mutation.target?.nodeType === 1 ? mutation.target : mutation.target?.parentElement;
        return !!target?.closest?.("#updates_history_accordion,#addition_history_accordion,#tab_panel_atualizacoes,#tab_panel_adicoes");
      });
      if (relevant) scheduleEnsure(18);
    });
    observer.observe(document.body, {childList:true, subtree:true});
  }

  function init() {
    ensureAll(); observe();
    [80,220,500,1000,1800,3200].forEach(delay => window.setTimeout(ensureAll, delay));
    document.addEventListener("click", event => {
      const id = event.target?.closest?.("button")?.id || "";
      if (["tab_btn_atualizacoes","tab_btn_adicoes","updates_refresh_btn","addition_history_refresh"].includes(id)) scheduleEnsure(30);
    }, true);
  }

  window.__crapScraperOperationalHistoryShared = { ensure: ensureAll, mount: ensureMounted, load, render };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once:true}); else init();
})();
