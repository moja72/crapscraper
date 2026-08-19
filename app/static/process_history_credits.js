(() => {
  "use strict";
  if (window.__crapScraperProcessHistoryCreditsInstalled) return;
  window.__crapScraperProcessHistoryCreditsInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const escapeHtml = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const upstreamFetch = window.fetch.bind(window);
  const HISTORY_KEY = "crapscraper.process.history.v1";
  const HISTORY_LIMIT = 80;
  const PREPARING_STATES = new Set(["validating", "downloading", "staging", "prepared", "planned"]);
  const EXECUTING_STATES = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "rolling_back"
  ]);
  let history = loadHistory();
  let backendSeen = new Map();
  let creditsLoading = false;

  function installStyles() {
    if ($("#cs-process-history-credits-style")) return;
    const style = document.createElement("style");
    style.id = "cs-process-history-credits-style";
    style.textContent = `
      #cs_download_credits{display:grid;gap:1px;margin-top:5px;color:#8f99a8;font-size:10px;line-height:1.35;white-space:nowrap}
      #cs_download_credits b{color:#cbd5e1;font-weight:750}
      #cs_download_credits .is-loading b{opacity:.62}
      .cs-process-modal-body>.cs-process-card.is-recent{display:none!important}
      .cs-process-history-section{display:grid;gap:10px;margin-top:4px;padding-top:16px;border-top:1px solid #292931}
      .cs-process-history-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
      .cs-process-history-title{font-size:14px;font-weight:850;color:#fff}
      .cs-process-history-count{color:#858b97;font-size:11px}
      .cs-process-history-list{display:grid;gap:8px}
      .cs-process-history-card{display:grid;gap:8px;padding:12px 14px;border:1px solid #292931;border-radius:12px;background:#121216}
      .cs-process-history-card .cs-process-row{align-items:flex-start}
      .cs-process-history-times{display:grid;gap:3px;color:#9299a6;font-size:11px;line-height:1.35}
      .cs-process-history-times b{color:#c7ced9;font-weight:750}
      .cs-process-history-empty,.cs-process-active-empty{padding:16px;border:1px dashed #34343d;border-radius:12px;color:#858b97;font-size:12px;text-align:center;background:#111115}
      @media(max-width:720px){#cs_download_credits{white-space:normal}.cs-process-history-head{align-items:flex-start}}
    `;
    document.head.appendChild(style);
  }

  function loadHistory() {
    try {
      const parsed = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter(Boolean).slice(0, HISTORY_LIMIT) : [];
    } catch (_error) {
      return [];
    }
  }

  function persistHistory() {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, HISTORY_LIMIT))); }
    catch (_error) {}
  }

  function recordHistory(process) {
    const startedAt = Number(process?.startedAt || 0) || Date.now();
    const finishedAt = Number(process?.finishedAt || 0) || Date.now();
    const row = {
      historyId: `${text(process?.id || process?.title || "process")}:${finishedAt}`,
      processId: text(process?.id || ""),
      title: text(process?.title || "Processo"),
      detail: text(process?.detail || ""),
      status: text(process?.status || (process?.error ? "Erro" : "Concluído")),
      error: Boolean(process?.error),
      kind: text(process?.kind || ""),
      startedAt,
      finishedAt: Math.max(startedAt, finishedAt)
    };
    const duplicate = history.find(item =>
      item.processId === row.processId &&
      Math.abs(Number(item.finishedAt || 0) - row.finishedAt) < 1200
    );
    if (duplicate) return;
    history.unshift(row);
    history = history.slice(0, HISTORY_LIMIT);
    persistHistory();
    decorateModal();
  }

  function formatDate(value) {
    const number = Number(value || 0);
    if (!number) return "—";
    try { return new Date(number).toLocaleString("pt-BR"); }
    catch (_error) { return "—"; }
  }

  function historyCard(process) {
    const statusClass = process.error ? "is-error" : "is-done";
    return `<article class="cs-process-history-card">
      <div class="cs-process-row">
        <div><div class="cs-process-name">${escapeHtml(process.title)}</div>${process.detail ? `<div class="cs-process-detail">${escapeHtml(process.detail)}</div>` : ""}</div>
        <span class="cs-process-status ${statusClass}">${escapeHtml(process.status || (process.error ? "Erro" : "Concluído"))}</span>
      </div>
      <div class="cs-process-history-times">
        <span><b>Início:</b> ${escapeHtml(formatDate(process.startedAt))}</span>
        <span><b>Fim:</b> ${escapeHtml(formatDate(process.finishedAt))}</span>
      </div>
    </article>`;
  }

  function decorateModal() {
    const body = $("#cs_processes_body");
    if (!body) return;
    body.querySelector("#cs_process_history_section")?.remove();
    body.querySelector("#cs_process_active_empty")?.remove();

    const activeCards = Array.from(body.children).filter(node =>
      node.matches?.(".cs-process-card:not(.is-recent)")
    );
    const nativeEmpty = Array.from(body.children).some(node => node.matches?.(".cs-process-empty"));
    if (!activeCards.length && !nativeEmpty) {
      const empty = document.createElement("div");
      empty.id = "cs_process_active_empty";
      empty.className = "cs-process-active-empty";
      empty.textContent = "Nenhum processo ativo no momento.";
      body.appendChild(empty);
    }

    const section = document.createElement("section");
    section.id = "cs_process_history_section";
    section.className = "cs-process-history-section";
    const rows = history.slice(0, HISTORY_LIMIT);
    section.innerHTML = `
      <div class="cs-process-history-head">
        <div class="cs-process-history-title">Processos concluídos</div>
        <div class="cs-process-history-count">${rows.length} registro(s)</div>
      </div>
      <div class="cs-process-history-list">
        ${rows.length ? rows.map(historyCard).join("") : '<div class="cs-process-history-empty">Nenhum processo concluído registrado neste painel.</div>'}
      </div>`;
    body.appendChild(section);
  }

  function ensureCreditsNode() {
    const button = $("#cs_processes_button");
    const parent = button?.parentElement;
    if (!button || !parent) return null;
    let node = $("#cs_download_credits");
    if (!node) {
      node = document.createElement("div");
      node.id = "cs_download_credits";
      node.innerHTML = `
        <div id="cs_credit_ultrapack" class="is-loading">UltraPackV2: <b>—</b></div>
        <div id="cs_credit_plugintheme" class="is-loading">PluginTheme: <b>—</b></div>`;
    }
    if (node.parentElement !== parent || node.previousElementSibling !== button) {
      button.insertAdjacentElement("afterend", node);
    }
    return node;
  }

  function creditLabel(payload) {
    const remaining = Number(payload?.remaining);
    const limit = Number(payload?.limit);
    if (payload?.ok && Number.isFinite(remaining) && Number.isFinite(limit) && limit >= 0) {
      return `${Math.max(0, remaining)}/${Math.max(0, limit)}`;
    }
    return "—";
  }

  function renderCredit(id, label, payload) {
    const node = $(`#${id}`);
    if (!node) return;
    node.classList.remove("is-loading");
    node.innerHTML = `${escapeHtml(label)}: <b>${escapeHtml(creditLabel(payload))}</b>`;
    node.title = text(payload?.message || (payload?.ok ? "Créditos de download restantes / limite diário." : "Créditos indisponíveis."));
  }

  async function pollCredits() {
    ensureCreditsNode();
    if (creditsLoading || document.hidden) return;
    creditsLoading = true;
    try {
      const response = await upstreamFetch("/processos/creditos", {cache:"no-store", credentials:"same-origin"});
      const payload = await response.json();
      renderCredit("cs_credit_ultrapack", "UltraPackV2", payload?.ultrapackv2 || {});
      renderCredit("cs_credit_plugintheme", "PluginTheme", payload?.plugintheme || {});
    } catch (_error) {
      renderCredit("cs_credit_ultrapack", "UltraPackV2", {ok:false, message:"Não foi possível consultar os créditos."});
      renderCredit("cs_credit_plugintheme", "PluginTheme", {ok:false, message:"Não foi possível consultar os créditos."});
    } finally {
      creditsLoading = false;
    }
  }

  function pathOf(input) {
    try {
      const raw = typeof input === "string" || input instanceof URL ? String(input) : String(input?.url || "");
      return new URL(raw, location.href).pathname;
    } catch (_error) { return ""; }
  }

  function methodOf(input, init) {
    return text(init?.method || (typeof Request !== "undefined" && input instanceof Request ? input.method : "GET")).toUpperCase() || "GET";
  }

  function requestDefinition(path, method) {
    const write = method !== "GET" && method !== "HEAD";
    if (path.endsWith("/comparacao/data")) return {kind:"comparison", title:"Comparação de catálogos"};
    if (write && path.endsWith("/plugintema/catalogo/gerar")) return {kind:"catalog", title:"Atualização do catálogo PluginTema"};
    if (write && path.endsWith("/plugintema/catalogo/exportar")) return {kind:"catalog", title:"Exportação do catálogo PluginTema"};
    if (write && path.endsWith("/catalogos/download")) return {kind:"catalog", title:"Coleta de catálogo"};
    if (write && path.endsWith("/atualizacoes/preparar")) return {kind:"update", title:"Preparação de atualização"};
    if (write && path.endsWith("/atualizacoes/plano")) return {kind:"update", title:"Geração do plano de atualização"};
    if (write && /\/atualizacoes\/fila\/(?:iniciar|continuar|adicionar)$/.test(path)) return {kind:"update", title:"Operação da fila de atualização"};
    if (write && path.endsWith("/loja/precos")) return {kind:"store", title:"Alteração de preços da Loja"};
    if (write && path.endsWith("/loja/pacotes/precos")) return {kind:"store", title:"Alteração de preço de produto"};
    if (write && path.endsWith("/loja/produtos/sem-breve-descricao")) return {kind:"store", title:"Verificação de descrições da Loja"};
    if (write && path.endsWith("/adicoes/preparar-arquivo")) return {kind:"addition", title:"Preparação de novo produto"};
    if (write && path.endsWith("/adicoes/criar-rascunho")) return {kind:"addition", title:"Criação de rascunho WooCommerce"};
    if (write && path.endsWith("/adicoes/publicar")) return {kind:"addition", title:"Publicação de novo produto"};
    if (write && /\/(?:start|continue|resume)$/.test(path)) return {kind:"collection", title:"Coleta / processamento de catálogo"};
    return null;
  }

  window.fetch = function processHistoryFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);
    const definition = requestDefinition(path, method);
    if (!definition) return upstreamFetch(input, init);
    const startedAt = Date.now();
    const id = `request-history:${startedAt}:${Math.random().toString(36).slice(2,8)}`;
    return upstreamFetch(input, init).then(response => {
      recordHistory({
        id, title:definition.title, kind:definition.kind, detail:path,
        status:response.ok ? "Concluído" : `Erro HTTP ${response.status}`,
        error:!response.ok, startedAt, finishedAt:Date.now()
      });
      return response;
    }, error => {
      recordHistory({
        id, title:definition.title, kind:definition.kind, detail:text(error?.message || path),
        status:"Erro", error:true, startedAt, finishedAt:Date.now()
      });
      throw error;
    });
  };

  async function getJson(url) {
    const response = await upstreamFetch(url, {cache:"no-store", credentials:"same-origin"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function updateBackendMap(runtime, target) {
    const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
    const queue = runtime?.queue || {};
    const activeName = text(queue.active_queue || "default") || "default";
    const listJobs = jobs.filter(job => (text(job?.queue_name || "default") || "default") === activeName);
    const executing = listJobs.find(job => EXECUTING_STATES.has(text(job?.state)));
    if (text(queue.status) === "running" || executing) {
      target.set(`backend:update-queue:${activeName}`, {
        id:`backend:update-queue:${activeName}`,
        title:`Fila de atualização · ${activeName === "default" ? "Padrão" : activeName}`,
        kind:"update",
        detail:executing ? `${text(executing.name)} · ${text(executing.plugintema_version || "-")} → ${text(executing.effective_source_version || executing.approved_source_version || executing.ultrapack_version || "-")}` : "Fila em execução",
        startedAt:Date.parse(executing?.executing_at || "") || Date.now()
      });
    }
    listJobs.filter(job => PREPARING_STATES.has(text(job?.state))).forEach(job => {
      target.set(`backend:prepare:${job.job_id}`, {
        id:`backend:prepare:${job.job_id}`, title:"Preparação de atualização", kind:"update",
        detail:`${text(job.name)} · Woo #${text(job.woo_product_id)}`,
        startedAt:Date.parse(job.updated_at || job.created_at || "") || Date.now()
      });
    });
  }

  function storePriceMap(data, target) {
    if (text(data?.status) !== "running") return;
    target.set("backend:store-price", {
      id:"backend:store-price", title:"Atualização de preços da Loja", kind:"store",
      detail:text(data.current_product || data.message || "Atualizando preços"), startedAt:Date.now()
    });
  }

  function storeDescriptionMap(data, target) {
    if (text(data?.status) !== "running") return;
    target.set("backend:store-description", {
      id:"backend:store-description", title:"Verificação de descrições da Loja", kind:"store",
      detail:text(data.current_product || data.message || "Verificando produtos"), startedAt:Date.now()
    });
  }

  function collectionMap(data, target) {
    const runs = Array.isArray(data?.runs) ? data.runs : Array.isArray(data) ? data : [];
    runs.filter(run => run?.running === true || /rodando|running|iniciando|processando/i.test(text(run?.status))).forEach(run => {
      const runId = text(run.run_id || run.id || "run");
      target.set(`backend:run:${runId}`, {
        id:`backend:run:${runId}`, title:"Coleta de catálogo", kind:"collection",
        detail:text(run.summary || [run?.context?.site_key, run?.context?.item_type_key, run?.context?.slot_name].filter(Boolean).join(" · ") || runId),
        startedAt:Date.now() - Math.max(0, Number(run.timer_seconds || 0) * 1000)
      });
    });
  }

  function preservePrefix(target, prefix) {
    for (const [id, process] of backendSeen) if (id.startsWith(prefix)) target.set(id, process);
  }

  function syncBackend(next) {
    for (const [id, process] of next) {
      const previous = backendSeen.get(id);
      if (previous?.startedAt) process.startedAt = Math.min(Number(previous.startedAt), Number(process.startedAt || previous.startedAt));
    }
    for (const [id, previous] of backendSeen) {
      if (next.has(id)) continue;
      recordHistory({...previous, status:"Concluído", error:false, finishedAt:Date.now()});
    }
    backendSeen = next;
  }

  async function pollBackendHistory() {
    if (document.hidden) return;
    const results = await Promise.allSettled([
      getJson("/atualizacoes/jobs"),
      getJson("/loja/precos/status"),
      getJson("/loja/produtos/sem-breve-descricao"),
      getJson("/runs")
    ]);
    const next = new Map();
    if (results[0].status === "fulfilled") updateBackendMap(results[0].value, next); else { preservePrefix(next, "backend:update-queue:"); preservePrefix(next, "backend:prepare:"); }
    if (results[1].status === "fulfilled") storePriceMap(results[1].value, next); else preservePrefix(next, "backend:store-price");
    if (results[2].status === "fulfilled") storeDescriptionMap(results[2].value, next); else preservePrefix(next, "backend:store-description");
    if (results[3].status === "fulfilled") collectionMap(results[3].value, next); else preservePrefix(next, "backend:run:");
    syncBackend(next);
  }

  function observeUi() {
    const observer = new MutationObserver(() => {
      ensureCreditsNode();
      decorateModal();
    });
    observer.observe(document.documentElement, {childList:true, subtree:true});
  }

  function start() {
    installStyles();
    ensureCreditsNode();
    decorateModal();
    observeUi();
    window.setTimeout(pollCredits, 900);
    window.setInterval(pollCredits, 60000);
    window.setTimeout(pollBackendHistory, 1400);
    window.setInterval(pollBackendHistory, 2600);
    window.setInterval(() => { ensureCreditsNode(); decorateModal(); }, 1200);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
