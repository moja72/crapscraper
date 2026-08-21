(() => {
  "use strict";

  const ENDPOINT = "/loja/produtos/campos-ausentes";
  const state = {
    products: [],
    filtered: [],
    page: 1,
    pageSize: 5,
    examined: 0,
    status: "idle",
    resultFilter: "",
    pollTimer: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
  const text = (value) => String(value ?? "").replace(/\s+/g, " ").trim();

  function injectStyles() {
    if ($("#store_custom_fields_quality_styles")) return;
    const style = document.createElement("style");
    style.id = "store_custom_fields_quality_styles";
    style.textContent = `
      .store-custom-fields-options{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
      .store-custom-field-option{display:inline-flex;align-items:center;gap:8px;padding:9px 11px;border:1px solid var(--line,#2a2f3a);border-radius:12px;background:rgba(255,255,255,.02);font-size:12px;font-weight:700}
      .store-custom-field-option input{width:auto;margin:0}
      .store-custom-fields-controls{display:grid;grid-template-columns:minmax(240px,1fr) 220px auto;gap:10px;align-items:end}
      .store-custom-fields-controls label{display:grid;gap:6px;font-size:12px;font-weight:700}
      .store-custom-fields-results-toolbar{display:flex;flex-wrap:wrap;align-items:end;justify-content:space-between;gap:10px;margin:14px 0 10px}
      .store-custom-fields-results-filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end}
      .store-custom-fields-results-filters label{display:grid;gap:5px;font-size:11px;font-weight:700;color:var(--text-muted,#9aa3b2)}
      .store-custom-fields-results-filters select{min-width:150px}
      .store-custom-field-state{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border-radius:999px;border:1px solid var(--line,#2a2f3a);font-size:11px;font-weight:800}
      .store-custom-field-state.is-ok{border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.10);color:#6ee7b7}
      .store-custom-field-state.is-missing{border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.10);color:#fcd34d}
      .store-custom-field-value{display:block;margin-top:5px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:var(--text-muted,#9aa3b2)}
      .store-custom-field-value a{text-decoration:underline;text-underline-offset:2px}
      .store-custom-pending{display:flex;flex-wrap:wrap;gap:6px}
      .store-custom-fields-pagination{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;margin-top:12px}
      .store-custom-fields-progress{display:flex;align-items:center;gap:9px;padding:12px;border:1px solid var(--line,#2a2f3a);border-radius:12px;background:rgba(255,255,255,.018)}
      @media(max-width:900px){.store-custom-fields-controls{grid-template-columns:1fr}.store-custom-fields-results-toolbar{align-items:stretch}.store-custom-fields-results-filters{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function cardHtml() {
    return `
      <section class="card store-quality-card" id="store_custom_fields_quality_card" aria-labelledby="store_custom_fields_quality_title">
        <div class="store-section-head">
          <div>
            <div class="section-title" id="store_custom_fields_quality_title">Campos personalizados dos produtos</div>
            <div class="small">Localize produtos publicados sem versão, desenvolvedor ou link oficial. A verificação lê somente os metadados necessários e não altera o WooCommerce.</div>
          </div>
        </div>

        <form class="store-quality-filter" id="store_custom_fields_quality_form">
          <div class="store-custom-fields-controls">
            <label for="store_custom_fields_search">Filtrar por nome ou ID
              <input id="store_custom_fields_search" type="search" autocomplete="off" placeholder="Ex.: Elementor ou 92038">
            </label>
            <label for="store_custom_fields_match_mode">Condição
              <select id="store_custom_fields_match_mode">
                <option value="any">Qualquer campo selecionado ausente</option>
                <option value="all">Todos os campos selecionados ausentes</option>
              </select>
            </label>
            <button class="btn-secondary" id="store_custom_fields_submit" type="submit">Verificar campos</button>
          </div>

          <div class="store-custom-fields-options" role="group" aria-label="Campos personalizados a verificar">
            <label class="store-custom-field-option"><input type="checkbox" value="version" checked> Versão</label>
            <label class="store-custom-field-option"><input type="checkbox" value="developer" checked> Desenvolvedor</label>
            <label class="store-custom-field-option"><input type="checkbox" value="official" checked> Link oficial</label>
          </div>
        </form>

        <div class="store-table-wrap" id="store_custom_fields_results" aria-live="polite">
          <div class="small">Clique em “Verificar campos” para consultar os produtos publicados.</div>
        </div>
      </section>
    `;
  }

  function ensureCard() {
    if ($("#store_custom_fields_quality_card")) return true;
    const panel = $("#tab_panel_loja");
    if (!panel) return false;

    const shortForm = $("#store_missing_description_form");
    const shortCard = shortForm?.closest(".card");
    if (shortCard) {
      shortCard.insertAdjacentHTML("afterend", cardHtml());
    } else {
      panel.insertAdjacentHTML("beforeend", cardHtml());
    }

    bindEvents();
    return true;
  }

  function selectedFields() {
    return $$("#store_custom_fields_quality_form input[type='checkbox']:checked").map((node) => node.value);
  }

  function missingLabel(key) {
    return ({ version: "Versão", developer: "Desenvolvedor", official: "Link oficial" })[key] || key;
  }

  function typeLabel(value) {
    const normalized = text(value).toLowerCase();
    if (normalized === "variable") return "Variável";
    if (normalized === "simple") return "Simples";
    if (normalized === "bundle") return "Pack";
    return text(value) || "—";
  }

  function cellState(product, key) {
    const values = product.values || {};
    const value = text(values[key]);
    const missing = Array.isArray(product.missing_fields) && product.missing_fields.includes(key);
    if (missing || !value) {
      return `<span class="store-custom-field-state is-missing">⚠ Ausente</span>`;
    }

    let visible = esc(value);
    if (key === "official" && /^https?:\/\//i.test(value)) {
      visible = `<a href="${esc(value)}" target="_blank" rel="noopener noreferrer">${esc(value)}</a>`;
    }
    return `<span class="store-custom-field-state is-ok">✓ Preenchido</span><span class="store-custom-field-value" title="${esc(value)}">${visible}</span>`;
  }

  function rowHtml(product) {
    const id = Number(product.product_id || 0);
    const pending = Array.isArray(product.missing_fields) ? product.missing_fields : [];
    return `
      <tr>
        <td>
          <strong>${esc(product.product_name || `Produto #${id}`)}</strong>
          <span class="small">WooCommerce #${id}</span>
        </td>
        <td>${esc(typeLabel(product.product_type))}</td>
        <td>${cellState(product, "version")}</td>
        <td>${cellState(product, "developer")}</td>
        <td>${cellState(product, "official")}</td>
        <td><div class="store-custom-pending">${pending.map((key) => `<span class="store-custom-field-state is-missing">${esc(missingLabel(key))}</span>`).join("") || "—"}</div></td>
        <td>${product.permalink ? `<a class="btn-secondary btn-sm" href="${esc(product.permalink)}" target="_blank" rel="noopener noreferrer">Abrir produto</a>` : "—"}</td>
      </tr>
    `;
  }

  function applyResultFilter() {
    state.resultFilter = text($("#store_custom_fields_result_filter")?.value);
    state.filtered = state.products.filter((product) => {
      if (!state.resultFilter) return true;
      return Array.isArray(product.missing_fields) && product.missing_fields.includes(state.resultFilter);
    });
    state.page = 1;
    renderResults();
  }

  function renderResults() {
    const root = $("#store_custom_fields_results");
    if (!root || state.status === "running") return;

    const total = state.filtered.length;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));
    state.page = Math.max(1, Math.min(state.page, pages));
    const start = (state.page - 1) * state.pageSize;
    const visible = state.filtered.slice(start, start + state.pageSize);
    const end = total ? Math.min(start + state.pageSize, total) : 0;

    if (!state.products.length) {
      root.innerHTML = `<div class="notice is-success">Varredura concluída: nenhum produto com os campos selecionados ausentes foi encontrado entre ${Number(state.examined || 0)} produtos publicados.</div>`;
      return;
    }

    root.innerHTML = `
      <div class="store-quality-count"><strong>${state.products.length}</strong> produto(s) com pendências entre <strong>${Number(state.examined || 0)}</strong> verificados</div>
      <div class="store-custom-fields-results-toolbar">
        <div class="store-custom-fields-results-filters">
          <label>Mostrar pendência
            <select id="store_custom_fields_result_filter">
              <option value="" ${!state.resultFilter ? "selected" : ""}>Todas</option>
              <option value="version" ${state.resultFilter === "version" ? "selected" : ""}>Sem versão</option>
              <option value="developer" ${state.resultFilter === "developer" ? "selected" : ""}>Sem desenvolvedor</option>
              <option value="official" ${state.resultFilter === "official" ? "selected" : ""}>Sem link oficial</option>
            </select>
          </label>
          <label>Itens por página
            <select id="store_custom_fields_page_size">
              ${[5, 10, 25, 50, 100].map((size) => `<option value="${size}" ${state.pageSize === size ? "selected" : ""}>${size}</option>`).join("")}
            </select>
          </label>
        </div>
        <span class="small">${total ? `Mostrando ${start + 1}–${end} de ${total}` : "0 produtos"}</span>
      </div>

      ${total ? `
        <table class="store-data-table">
          <thead><tr><th>Produto</th><th>Tipo</th><th>Versão</th><th>Desenvolvedor</th><th>Link oficial</th><th>Pendências</th><th>Acesso</th></tr></thead>
          <tbody>${visible.map(rowHtml).join("")}</tbody>
        </table>
      ` : `<div class="notice">Nenhum produto corresponde ao filtro de pendência selecionado.</div>`}

      <div class="store-custom-fields-pagination">
        <span class="small">Página ${state.page} de ${pages}</span>
        <div class="row">
          <button class="btn-secondary btn-sm" id="store_custom_fields_prev" type="button" ${state.page <= 1 ? "disabled" : ""}>← Anterior</button>
          <button class="btn-secondary btn-sm" id="store_custom_fields_next" type="button" ${state.page >= pages ? "disabled" : ""}>Próxima →</button>
        </div>
      </div>
    `;

    $("#store_custom_fields_result_filter")?.addEventListener("change", applyResultFilter);
    $("#store_custom_fields_page_size")?.addEventListener("change", (event) => {
      state.pageSize = Math.max(1, Math.min(100, Number(event.target.value) || 5));
      state.page = 1;
      renderResults();
    });
    $("#store_custom_fields_prev")?.addEventListener("click", () => {
      state.page -= 1;
      renderResults();
    });
    $("#store_custom_fields_next")?.addEventListener("click", () => {
      state.page += 1;
      renderResults();
    });
  }

  function renderProgress(data) {
    const root = $("#store_custom_fields_results");
    if (!root) return;
    root.innerHTML = `
      <div class="store-custom-fields-progress">
        <span class="inline-loading-spinner" aria-hidden="true"></span>
        <div>
          <strong>Verificando campos personalizados…</strong>
          <div class="small">${esc(data.message || "Consultando produtos publicados…")}</div>
        </div>
      </div>
    `;
  }

  async function request(method, payload = null) {
    const response = await fetch(ENDPOINT, {
      method,
      cache: "no-store",
      headers: payload ? { "Content-Type": "application/json" } : {},
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.message || `Falha HTTP ${response.status}`);
    return data;
  }

  function setButtonBusy(busy) {
    const button = $("#store_custom_fields_submit");
    if (!button) return;
    button.disabled = !!busy;
    button.textContent = busy ? "Verificando…" : "Verificar campos";
  }

  function consumeSnapshot(data) {
    state.status = text(data.status || "idle");
    state.examined = Number(data.examined || 0);
    if (state.status === "running") {
      setButtonBusy(true);
      renderProgress(data);
      schedulePoll();
      return;
    }

    setButtonBusy(false);
    if (state.status === "error") {
      const root = $("#store_custom_fields_results");
      if (root) root.innerHTML = `<div class="updates-error" role="alert"><strong>Não foi possível concluir a verificação.</strong><br>${esc(data.message || data.error || "Erro desconhecido.")}</div>`;
      return;
    }

    if (state.status === "completed") {
      state.products = Array.isArray(data.products) ? data.products : [];
      state.resultFilter = "";
      state.filtered = state.products.slice();
      state.page = 1;
      renderResults();
    }
  }

  function schedulePoll() {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(pollStatus, 900);
  }

  async function pollStatus() {
    try {
      const data = await request("GET");
      consumeSnapshot(data);
    } catch (error) {
      setButtonBusy(false);
      const root = $("#store_custom_fields_results");
      if (root) root.innerHTML = `<div class="updates-error" role="alert">${esc(error.message)}</div>`;
    }
  }

  async function startScan(event) {
    event?.preventDefault?.();
    const fields = selectedFields();
    if (!fields.length) {
      window.alert("Selecione pelo menos um campo para verificar.");
      return;
    }

    state.products = [];
    state.filtered = [];
    state.page = 1;
    setButtonBusy(true);

    try {
      const data = await request("POST", {
        query: text($("#store_custom_fields_search")?.value),
        selected_fields: fields,
        match_mode: text($("#store_custom_fields_match_mode")?.value || "any"),
      });
      consumeSnapshot(data);
    } catch (error) {
      setButtonBusy(false);
      const root = $("#store_custom_fields_results");
      if (root) root.innerHTML = `<div class="updates-error" role="alert"><strong>Não foi possível iniciar a verificação.</strong><br>${esc(error.message)}</div>`;
    }
  }

  function bindEvents() {
    $("#store_custom_fields_quality_form")?.addEventListener("submit", startScan);
  }

  async function restoreLastScan() {
    try {
      const data = await request("GET");
      if (text(data.status) !== "idle") consumeSnapshot(data);
    } catch (_error) {
      // A aba Loja continua funcional mesmo que este recurso isolado falhe.
    }
  }

  function init() {
    injectStyles();
    if (ensureCard()) {
      restoreLastScan();
      return;
    }

    const observer = new MutationObserver(() => {
      if (ensureCard()) {
        observer.disconnect();
        restoreLastScan();
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
