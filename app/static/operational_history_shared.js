((scope) => {
  "use strict";

  const COMPLETED_STATES = new Set(["completed", "rolled_back"]);
  const ERROR_STATES = new Set(["error", "failed", "blocked", "rollback_required", "interrupted", "canceled"]);
  const STATUS_OPTIONS = [
    ["", "Todos"],
    ["completed", "Concluído"],
    ["rolled_back", "Rollback concluído"],
    ["error", "Erro"],
    ["failed", "Falhou"],
    ["blocked", "Bloqueado"],
    ["rollback_required", "Rollback necessário"],
    ["interrupted", "Interrompido"],
    ["canceled", "Cancelado"],
    ["running", "Em andamento"],
  ];
  const SORT_OPTIONS = [
    ["recent", "Mais recente"],
    ["old", "Mais antigo"],
    ["az", "Alfabética A–Z"],
    ["za", "Alfabética Z–A"],
  ];

  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const itemTime = item => {
    const raw = text(item?.finished_at || item?.started_at);
    const parsed = raw ? new Date(raw) : null;
    return parsed && !Number.isNaN(parsed.getTime()) ? parsed.getTime() : 0;
  };
  const bucketForState = value => COMPLETED_STATES.has(text(value))
    ? "completed" : ERROR_STATES.has(text(value)) ? "errors" : "other";

  function freshState() {
    return {
      items: [], counts: {completed: 0, errors: 0}, mode: "completed",
      query: "", status: "", origin: "", dateFrom: "", dateTo: "", lastDays: "",
      sort: "recent", page: 1, pageSize: 5, loading: false, loaded: false, error: "",
    };
  }

  function normalizeItem(item = {}) {
    const state = text(item.state || item.status);
    return {
      id: text(item.id || item.job_id),
      operation_type: text(item.operation_type || item.kind),
      name: text(item.name || item.id || item.job_id),
      woo_product_id: Number(item.woo_product_id || 0),
      state,
      state_label: text(item.state_label || item.status_label || state),
      bucket: text(item.bucket) || bucketForState(state),
      origin: text(item.origin),
      previous_version: text(item.previous_version || item.version_from),
      new_version: text(item.new_version || item.version_to),
      started_at: text(item.started_at),
      finished_at: text(item.finished_at),
      duration: Math.max(0, Number(item.duration ?? item.duration_seconds) || 0),
      result: text(item.result),
      error: text(item.error),
      logs: Array.isArray(item.logs) ? item.logs.map(text).filter(Boolean) : [],
      developer: text(item.developer),
      category: text(item.category),
      official_url: text(item.official_url),
      source_url: text(item.source_url),
      current_step: text(item.current_step),
      progress: Math.max(0, Math.min(100, Number(item.progress) || 0)),
      final_state: text(item.final_state || state),
      attempt_no: Math.max(0, Number(item.attempt_no) || 0),
      product_type: text(item.product_type),
    };
  }

  function normalizePayload(payload = {}) {
    const items = Array.isArray(payload.items) ? payload.items.map(normalizeItem) : [];
    const completed = Number(payload.counts?.completed);
    const errors = Number(payload.counts?.errors);
    return {
      ok: payload.ok !== false,
      total: Number.isFinite(Number(payload.total)) ? Number(payload.total) : items.length,
      counts: {
        completed: Number.isFinite(completed) ? completed : items.filter(item => item.bucket === "completed").length,
        errors: Number.isFinite(errors) ? errors : items.filter(item => item.bucket === "errors").length,
      },
      items,
    };
  }

  function filterHistoryItems(items, filters, now = Date.now()) {
    const query = text(filters.query).toLocaleLowerCase("pt-BR");
    const origin = text(filters.origin).toLocaleLowerCase("pt-BR");
    let from = null;
    let to = null;
    if (filters.lastDays) {
      const days = Math.max(1, Number.parseInt(filters.lastDays, 10) || 0);
      if (days) from = now - days * 86400000;
    } else {
      if (filters.dateFrom) {
        const parsed = new Date(`${filters.dateFrom}T00:00:00`);
        if (!Number.isNaN(parsed.getTime())) from = parsed.getTime();
      }
      if (filters.dateTo) {
        const parsed = new Date(`${filters.dateTo}T23:59:59.999`);
        if (!Number.isNaN(parsed.getTime())) to = parsed.getTime();
      }
    }

    const result = items.filter(raw => {
      const item = normalizeItem(raw);
      if (item.bucket !== filters.mode) return false;
      if (filters.status && item.state !== filters.status) return false;
      if (query && !`${item.name} ${item.woo_product_id} ${item.id}`.toLocaleLowerCase("pt-BR").includes(query)) return false;
      if (origin && !`${item.origin} ${item.source_url}`.toLocaleLowerCase("pt-BR").includes(origin)) return false;
      const time = itemTime(item);
      if (from !== null && (!time || time < from)) return false;
      if (to !== null && (!time || time > to)) return false;
      return true;
    });

    result.sort((left, right) => {
      if (filters.sort === "old") return itemTime(left) - itemTime(right);
      if (filters.sort === "az") return left.name.localeCompare(right.name, "pt-BR", {sensitivity: "base"});
      if (filters.sort === "za") return right.name.localeCompare(left.name, "pt-BR", {sensitivity: "base"});
      return itemTime(right) - itemTime(left);
    });
    return result;
  }

  function paginateHistoryItems(items, page, pageSize) {
    const size = Math.max(1, Math.min(500, Number.parseInt(pageSize, 10) || 5));
    const pages = Math.max(1, Math.ceil(items.length / size));
    const current = Math.min(Math.max(1, Number.parseInt(page, 10) || 1), pages);
    const start = (current - 1) * size;
    return {items: items.slice(start, start + size), page: current, pageSize: size, pages, start};
  }

  function optionMarkup(rows) {
    return rows.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
  }

  function renderOperationalHistory(type) {
    const kind = type === "addition" ? "addition" : "update";
    return `<details class="cs-history card updates-card-section" data-operational-history data-history-type="${kind}">
      <summary class="cs-history-summary">
        <span class="cs-history-title"><span class="updates-disclosure-chevron" aria-hidden="true">▸</span><span class="section-title">Histórico</span></span>
        <span class="small cs-history-summary-count" data-history-summary>0 registro(s)</span>
      </summary>
      <div class="cs-history-body">
        <div class="cs-history-toolbar">
          <div class="cs-history-filters">
            <label>Buscar no histórico<input data-history-search type="search" placeholder="Nome ou WooCommerce ID"></label>
            <label>Estado<select data-history-status>${optionMarkup(STATUS_OPTIONS)}</select></label>
            <label>Origem<input data-history-origin type="search" placeholder="UltraPack, PluginTheme ou domínio"></label>
            <label>Ordenar<select data-history-sort>${optionMarkup(SORT_OPTIONS)}</select></label>
          </div>
          <div class="cs-history-actions">
            <button class="btn-secondary btn-sm" data-history-action="download" type="button">Baixar histórico</button>
            <button class="btn-secondary btn-sm" data-history-action="refresh" type="button">Atualizar</button>
            <button class="btn-danger btn-sm" data-history-action="delete" type="button">Apagar histórico</button>
          </div>
        </div>
        <div class="cs-history-period">
          <label>Data inicial<input data-history-date-from type="date"></label>
          <label>Data final<input data-history-date-to type="date"></label>
          <label>Últimos X dias<input data-history-last-days type="number" min="1" max="3650" step="1" inputmode="numeric" placeholder="30"></label>
          <button class="btn-secondary btn-sm" data-history-action="apply-period" type="button">Aplicar</button>
          <button class="btn-secondary btn-sm" data-history-action="clear-period" type="button">Limpar período</button>
        </div>
        <div class="cs-history-tabs" role="tablist" aria-label="Tipo de histórico">
          <button class="cs-history-tab is-active" data-history-tab="completed" role="tab" aria-selected="true" type="button"><span>Concluídos</span> (<span data-history-count="completed">0</span>)</button>
          <button class="cs-history-tab" data-history-tab="errors" role="tab" aria-selected="false" type="button"><span>Erros</span> (<span data-history-count="errors">0</span>)</button>
        </div>
        <div class="cs-history-meta">
          <span class="small" data-history-meta>Mostrando 0 de 0 registros</span>
          <label class="cs-history-page-size"><span class="small">Itens por página</span><input data-history-page-size type="number" min="1" max="500" step="1" value="5" inputmode="numeric"></label>
        </div>
        <div class="cs-history-pagination">
          <button class="btn-secondary" data-history-action="prev" type="button">← Anterior</button>
          <span class="badge cs-history-page">Página <input data-history-page type="number" min="1" max="1" value="1" aria-label="Ir para página"> de <span data-history-pages>1</span></span>
          <button class="btn-secondary" data-history-action="next" type="button">Próxima →</button>
        </div>
        <div class="cs-history-list" data-history-list role="tabpanel" aria-live="polite"><div class="cs-history-empty">Abra o histórico para carregar os registros.</div></div>
      </div>
    </details>`;
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return text(value);
    return new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(date).replace(",", "");
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Number.parseInt(seconds, 10) || 0);
    if (!total) return "—";
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    return [days ? `${days}d` : "", (hours || days) ? `${hours}h` : "", `${minutes}m`].filter(Boolean).join(" ");
  }

  function stateClass(value) {
    return COMPLETED_STATES.has(value) ? "is-success" : ERROR_STATES.has(value) ? "is-danger" : "is-active";
  }

  function renderHistoryRow(raw) {
    const item = normalizeItem(raw);
    const version = item.previous_version && item.new_version
      ? `${item.previous_version} → ${item.new_version}` : (item.new_version || item.previous_version || "—");
    const references = [
      item.source_url ? `<a href="${esc(item.source_url)}" target="_blank" rel="noopener">origem</a>` : "",
      item.official_url ? `<a href="${esc(item.official_url)}" target="_blank" rel="noopener">link oficial</a>` : "",
    ].filter(Boolean).join(" · ");
    const details = [
      item.product_type ? `<span><b>Tipo:</b> ${esc(item.product_type)}</span>` : "",
      item.category ? `<span><b>Categoria:</b> ${esc(item.category)}</span>` : "",
      item.developer ? `<span><b>Desenvolvedor:</b> ${esc(item.developer)}</span>` : "",
      item.previous_version ? `<span><b>Versão anterior:</b> ${esc(item.previous_version)}</span>` : "",
      item.new_version ? `<span><b>Versão nova:</b> ${esc(item.new_version)}</span>` : "",
      item.current_step ? `<span><b>Etapa:</b> ${esc(item.current_step)}</span>` : "",
      `<span><b>Progresso:</b> ${esc(item.progress)}%</span>`,
      references ? `<span><b>Referências:</b> ${references}</span>` : "",
    ].filter(Boolean).join("");

    return `<article class="cs-history-row" data-history-row="${esc(item.id)}">
      <div class="cs-history-row-main"><strong>${esc(item.name || item.id)}</strong><span>Woo #${esc(item.woo_product_id || "—")}</span><span>Origem: ${esc(item.origin || "—")}</span><span>Versão: ${esc(version)}</span></div>
      <div class="cs-history-row-status"><span class="cs-history-badge ${stateClass(item.state)}">${esc(item.state_label || item.state || "—")}</span></div>
      <div class="cs-history-row-date"><span><b>Início:</b> ${esc(formatDate(item.started_at))}</span><span><b>Fim:</b> ${esc(formatDate(item.finished_at))}</span><span><b>Duração:</b> ${esc(formatDuration(item.duration))}</span></div>
      <div class="cs-history-row-result"><span>${esc(item.result || item.final_state || "—")}</span><span>${esc(item.current_step || "Etapa não registrada")}</span><span>Progresso: ${esc(item.progress)}%</span></div>
      <div class="cs-history-row-actions"><button class="btn-secondary" data-history-detail type="button" aria-expanded="false">Detalhes</button></div>
      <div class="cs-history-details hidden" data-history-details><div class="cs-history-details-grid">${details}</div>${item.error ? `<div class="cs-history-error">${esc(item.error)}</div>` : ""}${item.logs.length ? `<pre class="cs-history-log">${item.logs.slice(-20).map(esc).join("\n")}</pre>` : ""}</div>
    </article>`;
  }

  const core = Object.freeze({bucketForState, freshState, normalizeItem, normalizePayload, filterHistoryItems, paginateHistoryItems, renderOperationalHistory, renderHistoryRow});
  if (typeof module === "object" && module.exports) module.exports = core;
  if (typeof document === "undefined") return;
  if (scope.__crapScraperOperationalHistorySharedInstalled) return;
  scope.__crapScraperOperationalHistorySharedInstalled = true;

  const states = new Map();
  const roots = new Map();
  const query = (selector, root = document) => root.querySelector(selector);
  const queryAll = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function getState(kind) {
    if (!states.has(kind)) states.set(kind, freshState());
    return states.get(kind);
  }

  function mountHost(host) {
    if (!host?.matches?.("[data-operational-history-host]")) return null;
    const kind = host.dataset.historyType === "addition" ? "addition" : "update";
    if (roots.has(kind) && document.contains(roots.get(kind))) {
      host.remove();
      return roots.get(kind);
    }
    const template = document.createElement("template");
    template.innerHTML = renderOperationalHistory(kind).trim();
    const root = template.content.firstElementChild;
    host.replaceWith(root);
    roots.set(kind, root);
    bind(kind, root);
    render(kind);
    return root;
  }

  function mountAll(container = document) {
    queryAll("[data-operational-history-host]", container).forEach(mountHost);
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
    const root = roots.get(kind);
    const state = getState(kind);
    if (!root?.open || state.loading || (state.loaded && !force)) return;
    state.loading = true;
    state.error = "";
    render(kind);
    try {
      const payload = normalizePayload(await request(`/operacoes/historico?kind=${encodeURIComponent(kind)}`));
      state.items = payload.items;
      state.counts = payload.counts;
      state.loaded = true;
      state.page = 1;
    } catch (error) {
      state.error = text(error?.message || error);
    } finally {
      state.loading = false;
      render(kind);
    }
  }

  function invalidate(kind) {
    const state = getState(kind);
    state.loaded = false;
  }

  function refresh(kind) {
    invalidate(kind);
    return load(kind, true);
  }

  function render(kind) {
    const root = roots.get(kind);
    if (!root) return;
    const state = getState(kind);
    const completed = Number(state.counts.completed || 0);
    const errors = Number(state.counts.errors || 0);
    query("[data-history-summary]", root).textContent = `${completed + errors} registro(s)`;
    query('[data-history-count="completed"]', root).textContent = String(completed);
    query('[data-history-count="errors"]', root).textContent = String(errors);
    queryAll("[data-history-tab]", root).forEach(button => {
      const active = button.dataset.historyTab === state.mode;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", String(active));
    });

    const list = query("[data-history-list]", root);
    if (state.loading) {
      list.innerHTML = '<div class="cs-history-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando histórico persistido…</span></div>';
      return;
    }
    if (state.error) {
      list.innerHTML = `<div class="cs-history-empty is-error">${esc(state.error)}</div>`;
      return;
    }

    const filtered = filterHistoryItems(state.items, state);
    const page = paginateHistoryItems(filtered, state.page, state.pageSize);
    state.page = page.page;
    state.pageSize = page.pageSize;
    list.innerHTML = page.items.length ? page.items.map(renderHistoryRow).join("") : '<div class="cs-history-empty">Nenhum registro corresponde aos filtros.</div>';

    const first = filtered.length ? page.start + 1 : 0;
    const last = Math.min(page.start + page.pageSize, filtered.length);
    query("[data-history-meta]", root).textContent = `Mostrando ${first}–${last} de ${filtered.length} registros`;
    const pageInput = query("[data-history-page]", root);
    pageInput.value = String(page.page);
    pageInput.max = String(page.pages);
    query("[data-history-pages]", root).textContent = String(page.pages);
    query('[data-history-action="prev"]', root).disabled = page.page <= 1;
    query('[data-history-action="next"]', root).disabled = page.page >= page.pages;
  }

  function bind(kind, root) {
    root.addEventListener("toggle", () => { if (root.open) load(kind); });
    root.addEventListener("input", event => {
      const state = getState(kind);
      if (event.target.matches("[data-history-search]")) state.query = event.target.value;
      else if (event.target.matches("[data-history-origin]")) state.origin = event.target.value;
      else return;
      state.page = 1;
      render(kind);
    });
    root.addEventListener("change", event => {
      const state = getState(kind);
      if (event.target.matches("[data-history-status]")) state.status = event.target.value;
      else if (event.target.matches("[data-history-sort]")) state.sort = event.target.value;
      else if (event.target.matches("[data-history-date-from]")) {
        state.dateFrom = event.target.value;
        state.lastDays = "";
        query("[data-history-last-days]", root).value = "";
      } else if (event.target.matches("[data-history-date-to]")) {
        state.dateTo = event.target.value;
        state.lastDays = "";
        query("[data-history-last-days]", root).value = "";
      } else if (event.target.matches("[data-history-page-size]")) state.pageSize = event.target.value;
      else if (event.target.matches("[data-history-page]")) state.page = event.target.value;
      else return;
      if (!event.target.matches("[data-history-page]")) state.page = 1;
      render(kind);
    });
    root.addEventListener("click", async event => {
      const state = getState(kind);
      const tab = event.target.closest("[data-history-tab]");
      if (tab) {
        state.mode = tab.dataset.historyTab;
        state.status = "";
        state.page = 1;
        query("[data-history-status]", root).value = "";
        render(kind);
        return;
      }
      const detail = event.target.closest("[data-history-detail]");
      if (detail) {
        const panel = query("[data-history-details]", detail.closest("[data-history-row]"));
        const hidden = panel.classList.toggle("hidden");
        detail.setAttribute("aria-expanded", String(!hidden));
        detail.textContent = hidden ? "Detalhes" : "Ocultar";
        return;
      }
      const action = event.target.closest("[data-history-action]");
      if (!action) return;
      const type = action.dataset.historyAction;
      if (type === "prev") state.page = Math.max(1, state.page - 1);
      else if (type === "next") state.page += 1;
      else if (type === "apply-period") {
        const lastDays = query("[data-history-last-days]", root);
        const days = Math.max(1, Math.min(3650, Number.parseInt(lastDays.value, 10) || 0));
        if (lastDays.value) {
          state.lastDays = String(days);
          state.dateFrom = "";
          state.dateTo = "";
          query("[data-history-date-from]", root).value = "";
          query("[data-history-date-to]", root).value = "";
          lastDays.value = String(days);
        }
        state.page = 1;
      } else if (type === "clear-period") {
        state.dateFrom = "";
        state.dateTo = "";
        state.lastDays = "";
        state.page = 1;
        query("[data-history-date-from]", root).value = "";
        query("[data-history-date-to]", root).value = "";
        query("[data-history-last-days]", root).value = "";
      } else if (type === "refresh") {
        await refresh(kind);
        return;
      } else if (type === "download") {
        download(kind);
        return;
      } else if (type === "delete") {
        const label = kind === "update" ? "atualizações" : "adições";
        if (!scope.confirm(`Apagar todo o histórico de ${label}? Esta ação não pode ser desfeita.`)) return;
        action.disabled = true;
        try {
          await request("/operacoes/historico/apagar", {method: "POST", body: JSON.stringify({kind})});
          state.items = [];
          state.counts = {completed: 0, errors: 0};
          state.loaded = false;
          await load(kind, true);
        } catch (error) {
          scope.alert(text(error?.message || error));
        } finally {
          action.disabled = false;
        }
        return;
      } else return;
      render(kind);
    });
  }

  function csvCell(value) {
    return `"${String(value ?? "").replace(/"/g, '""')}"`;
  }

  function download(kind) {
    const state = getState(kind);
    const items = filterHistoryItems(state.items, state);
    const rows = items.map(item => [
      item.name, item.woo_product_id || "", item.state_label, item.origin,
      item.previous_version, item.new_version, item.started_at, item.finished_at,
      item.duration, item.result, item.error,
    ].map(csvCell).join(","));
    const headers = ["Produto", "WooCommerce ID", "Estado", "Origem", "Versão anterior", "Versão final", "Início", "Fim", "Duração (s)", "Resultado", "Erro"];
    const blob = new Blob(["\ufeff" + [headers.map(csvCell).join(","), ...rows].join("\r\n")], {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `historico-${kind === "update" ? "atualizacoes" : "adicoes"}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const api = Object.freeze({...core, mountAll, invalidate, refresh});
  scope.OperationalHistory = api;
  const init = () => mountAll(document);
  document.addEventListener("operational-history:host-ready", event => mountAll(event.detail?.root || document));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, {once: true});
  else init();
})(typeof window !== "undefined" ? window : globalThis);
