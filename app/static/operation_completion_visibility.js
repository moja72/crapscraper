(() => {
  "use strict";

  if (window.__crapScraperOperationCompletionVisibilityInstalled) return;
  window.__crapScraperOperationCompletionVisibilityInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  const state = {
    additions: [],
    updates: [],
    addByJob: new Map(),
    addByComparison: new Map(),
    addByWoo: new Map(),
    updateByJob: new Map(),
    updateByComparison: new Map(),
    updateByWoo: new Map(),
    inFlight: null,
    lastFetchedAt: 0,
    observers: new Map(),
    completionRefreshTimer: null,
  };

  function installStyles() {
    if ($("#cs-operation-completion-visibility-style")) return;
    const style = document.createElement("style");
    style.id = "cs-operation-completion-visibility-style";
    style.textContent = `
      .cs-operation-completion-statuses{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-top:5px}
      .cs-operation-completion-badge{display:inline-flex;align-items:center;width:max-content;max-width:100%;padding:3px 7px;border:1px solid rgba(16,185,129,.40);border-radius:999px;background:rgba(16,185,129,.08);color:#a7f3d0;font-size:10px;font-weight:800;line-height:1.25;white-space:nowrap}
      .cs-operation-completion-badge.is-update{border-color:rgba(96,165,250,.42);background:rgba(96,165,250,.08);color:#bfdbfe}
      #comparison_rows .cs-operation-completion-statuses{margin:5px 0 0}
      #updates_history .cs-operation-completion-statuses,
      #addition_history_rows .cs-operation-completion-statuses{margin-top:6px}
    `;
    document.head.appendChild(style);
  }

  function normalizeRecord(raw) {
    return {
      kind: text(raw?.kind),
      label: text(raw?.label),
      job_id: text(raw?.job_id),
      comparison_item_id: text(raw?.comparison_item_id),
      woo_product_id: Number(raw?.woo_product_id || 0) || 0,
      name: text(raw?.name),
      version: text(raw?.version),
      completed_at: text(raw?.completed_at),
    };
  }

  function rebuildMaps() {
    state.addByJob.clear();
    state.addByComparison.clear();
    state.addByWoo.clear();
    state.updateByJob.clear();
    state.updateByComparison.clear();
    state.updateByWoo.clear();

    state.additions.forEach(record => {
      if (record.job_id) state.addByJob.set(record.job_id, record);
      if (record.comparison_item_id) state.addByComparison.set(record.comparison_item_id, record);
      if (record.woo_product_id > 0) state.addByWoo.set(record.woo_product_id, record);
    });
    state.updates.forEach(record => {
      if (record.job_id) state.updateByJob.set(record.job_id, record);
      if (record.comparison_item_id) state.updateByComparison.set(record.comparison_item_id, record);
      if (record.woo_product_id > 0) state.updateByWoo.set(record.woo_product_id, record);
    });
  }

  function extractWooId(value) {
    const raw = text(value);
    const match = raw.match(/(?:Woo(?:Commerce)?\s*#?|Woo\s*#)\s*(\d+)/i);
    return match ? Number(match[1]) || 0 : 0;
  }

  function tooltip(record) {
    const parts = [record.label || (record.kind === "update" ? "Já atualizado" : "Já adicionado")];
    if (record.woo_product_id) parts.push(`Woo #${record.woo_product_id}`);
    if (record.version) parts.push(`versão ${record.version}`);
    if (record.completed_at) {
      const parsed = new Date(record.completed_at);
      parts.push(Number.isNaN(parsed.getTime()) ? record.completed_at : parsed.toLocaleString("pt-BR"));
    }
    return parts.join(" · ");
  }

  function renderBadges(host, records) {
    if (!host) return;
    const unique = [];
    const seen = new Set();
    records.filter(Boolean).forEach(record => {
      const key = `${record.kind}:${record.job_id || record.comparison_item_id || record.woo_product_id}`;
      if (seen.has(key)) return;
      seen.add(key);
      unique.push(record);
    });

    let wrap = $(".cs-operation-completion-statuses", host);
    if (!unique.length) {
      wrap?.remove();
      return;
    }
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "cs-operation-completion-statuses";
      host.appendChild(wrap);
    }
    wrap.innerHTML = unique.map(record => {
      const label = record.label || (record.kind === "update" ? "Já atualizado" : "Já adicionado");
      const cls = record.kind === "update" ? " is-update" : "";
      const title = tooltip(record).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
      return `<span class="cs-operation-completion-badge${cls}" title="${title}">${label}</span>`;
    }).join("");
  }

  function comparisonRecords(row) {
    const itemNode = $("[data-comparison-item-id]", row);
    const itemId = text(itemNode?.dataset?.comparisonItemId || row.dataset?.comparisonItemId);
    const wooId = extractWooId(row.textContent);
    return [
      itemId ? state.addByComparison.get(itemId) : null,
      itemId ? state.updateByComparison.get(itemId) : null,
      wooId ? state.addByWoo.get(wooId) : null,
      wooId ? state.updateByWoo.get(wooId) : null,
    ];
  }

  function decorateComparison() {
    const root = $("#comparison_rows");
    if (!root) return;
    $$(`tr`, root).forEach(row => {
      const records = comparisonRecords(row).filter(Boolean);
      if (!records.length) return;
      const host = row.querySelector("td") || row;
      renderBadges(host, records);
    });
  }

  function decorateUpdates() {
    const root = $("#tab_panel_atualizacoes");
    if (!root) return;
    $$(`[data-update-detail]`, root).forEach(detail => {
      const jobId = text(detail.dataset.updateDetail);
      const row = detail.closest(".update-queue-row, article, tr, .card") || detail.parentElement;
      const wooId = extractWooId(row?.textContent);
      const record = state.updateByJob.get(jobId) || (wooId ? state.updateByWoo.get(wooId) : null);
      if (!record || !row) return;
      const host = row.querySelector(".update-job-main, .update-queue-main") || row.children?.[1] || row;
      renderBadges(host, [record]);
    });

    const history = $("#updates_history");
    if (history) {
      Array.from(history.children).forEach(row => {
        const wooId = extractWooId(row.textContent);
        const record = wooId ? state.updateByWoo.get(wooId) : null;
        if (record) renderBadges(row, [record]);
      });
    }
  }

  function decorateAdditions() {
    const root = $("#tab_panel_adicoes");
    if (!root) return;
    $$(`[data-add-job]`, root).forEach(row => {
      const jobId = text(row.dataset.addJob);
      const wooId = extractWooId(row.textContent);
      const record = state.addByJob.get(jobId) || (wooId ? state.addByWoo.get(wooId) : null);
      if (!record) return;
      const host = row.querySelector(".addition-op-main") || row.children?.[1] || row;
      renderBadges(host, [record]);
    });

    const history = $("#addition_history_rows");
    if (history) {
      $$(".addition-history-row", history).forEach(row => {
        const wooId = extractWooId(row.textContent);
        const record = wooId ? state.addByWoo.get(wooId) : null;
        if (record) renderBadges(row.firstElementChild || row, [record]);
      });
    }
  }

  function decorateAll() {
    decorateComparison();
    decorateUpdates();
    decorateAdditions();
  }

  async function refresh(force = false) {
    const now = Date.now();
    if (!force && now - state.lastFetchedAt < 1500 && state.additions.length + state.updates.length > 0) {
      decorateAll();
      return;
    }
    if (state.inFlight) return state.inFlight;
    state.inFlight = fetch("/operacoes/conclusoes", {cache:"no-store", credentials:"same-origin"})
      .then(async response => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
        state.additions = (Array.isArray(payload.additions) ? payload.additions : []).map(normalizeRecord);
        state.updates = (Array.isArray(payload.updates) ? payload.updates : []).map(normalizeRecord);
        state.lastFetchedAt = Date.now();
        rebuildMaps();
        decorateAll();
        return payload;
      })
      .catch(() => null)
      .finally(() => { state.inFlight = null; });
    return state.inFlight;
  }

  function scheduleCompletionRefresh() {
    if (state.completionRefreshTimer || Date.now() - state.lastFetchedAt < 1200) return;
    state.completionRefreshTimer = setTimeout(() => {
      state.completionRefreshTimer = null;
      refresh(true);
    }, 180);
  }

  function bindObserver(selector) {
    const root = $(selector);
    if (!root || state.observers.has(selector)) return;
    const observer = new MutationObserver(mutations => {
      let completionHint = false;
      mutations.forEach(mutation => {
        Array.from(mutation.addedNodes || []).forEach(node => {
          if (!(node instanceof Element)) return;
          if (node.matches?.(".cs-operation-completion-statuses") || node.closest?.(".cs-operation-completion-statuses")) return;
          const content = text(node.textContent).toLowerCase();
          if (content.includes("concluído") || content.includes("concluido")) completionHint = true;
        });
      });
      decorateAll();
      if (completionHint) scheduleCompletionRefresh();
    });
    observer.observe(root, {childList:true, subtree:true});
    state.observers.set(selector, observer);
  }

  function bindObservers() {
    [
      "#comparison_rows",
      "#updates_queue_jobs",
      "#updates_history",
      "#addition_preparation_rows",
      "#addition_queue_rows",
      "#addition_history_rows",
    ].forEach(bindObserver);
  }

  function bindEvents() {
    ["tab_btn_comparacao", "tab_btn_atualizacoes", "tab_btn_adicoes"].forEach(id => {
      $(`#${id}`)?.addEventListener("click", () => setTimeout(() => {
        bindObservers();
        refresh(true);
      }, 0));
    });
    ["updates_refresh_btn", "addition_sync_approved", "addition_history_refresh"].forEach(id => {
      $(`#${id}`)?.addEventListener("click", () => setTimeout(() => refresh(true), 250));
    });
  }

  function boot() {
    installStyles();
    bindEvents();
    bindObservers();
    refresh(true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true});
  else boot();
})();
