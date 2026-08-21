(() => {
  "use strict";
  if (window.__crapScraperActiveProcessesInstalled) return;
  window.__crapScraperActiveProcessesInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const escapeHtml = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const nativeFetch = window.fetch.bind(window);
  const clientProcesses = new Map();
  const recentProcesses = new Map();
  let backendProcesses = new Map();
  let requestSequence = 0;
  let modalOpen = false;
  let polling = false;

  const PREPARING_STATES = new Set(["validating", "downloading", "staging", "prepared", "planned"]);
  const EXECUTING_STATES = new Set([
    "executing", "installing", "filesystem_validated", "updating_wordpress",
    "validating_wordpress", "validated", "rolling_back"
  ]);
  const MANUAL_ACTIVE_STATES = new Set([
    "processing", "locating", "comparing", "preparing", "downloading",
    "executing", "installing", "validating", "updating_wordpress"
  ]);

  function installStyles() {
    if ($("#cs-active-processes-style")) return;
    const style = document.createElement("style");
    style.id = "cs-active-processes-style";
    style.textContent = `
      #cs_processes_button{display:inline-flex;align-items:center;justify-content:center;gap:8px;white-space:nowrap}
      #cs_processes_button .cs-process-count{display:none;min-width:20px;height:20px;padding:0 6px;align-items:center;justify-content:center;border-radius:999px;background:#7c3aed;color:#fff;font-size:11px;font-weight:800}
      #cs_processes_button.has-active .cs-process-count{display:inline-flex}
      #cs_processes_overlay{position:fixed;inset:0;z-index:120000;display:flex;align-items:flex-start;justify-content:center;padding:72px 18px 24px;background:rgba(0,0,0,.68);backdrop-filter:blur(4px)}
      #cs_processes_overlay.hidden{display:none!important}
      .cs-process-modal{width:min(920px,100%);max-height:calc(100vh - 96px);overflow:hidden;display:flex;flex-direction:column;border:1px solid #34343d;border-radius:18px;background:#0f0f12;box-shadow:0 24px 80px rgba(0,0,0,.55)}
      .cs-process-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:20px 22px;border-bottom:1px solid #292931}
      .cs-process-modal-title{font-size:20px;font-weight:850;color:#fff}.cs-process-modal-subtitle{margin-top:5px;color:#9ca3af;font-size:12px;line-height:1.45}
      .cs-process-close{min-width:40px;height:40px;padding:0;border:1px solid #34343d;border-radius:10px;background:#19191f;color:#fff;font-size:20px;cursor:pointer}
      .cs-process-modal-body{overflow:auto;padding:18px 22px 22px;display:grid;gap:12px}
      .cs-process-empty{padding:28px 18px;border:1px dashed #34343d;border-radius:14px;color:#9ca3af;text-align:center;background:#121216}
      .cs-process-card{display:grid;gap:10px;padding:14px 16px;border:1px solid #2c2c34;border-radius:14px;background:#151519}
      .cs-process-card.is-recent{opacity:.72}.cs-process-row{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
      .cs-process-name{font-weight:800;color:#fff;line-height:1.35}.cs-process-detail{margin-top:3px;color:#a9b0bc;font-size:12px;line-height:1.45}
      .cs-process-status{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;padding:6px 9px;border:1px solid #3a3a43;border-radius:999px;color:#d9d9e2;font-size:11px;font-weight:800}
      .cs-process-status.is-active::before{content:"";width:8px;height:8px;border-radius:50%;background:#10b981;box-shadow:0 0 0 4px rgba(16,185,129,.10);animation:csProcessPulse 1.1s ease-in-out infinite}
      .cs-process-status.is-error{border-color:rgba(239,68,68,.5);color:#fca5a5}.cs-process-status.is-done{color:#a7f3d0}
      .cs-process-progress{height:7px;overflow:hidden;border-radius:999px;background:#24242b}.cs-process-progress>span{display:block;height:100%;border-radius:inherit;background:#10b981;transition:width .25s ease}
      .cs-process-progress.is-indeterminate>span{width:32%;animation:csProcessSlide 1.1s ease-in-out infinite}
      .cs-process-meta{display:flex;flex-wrap:wrap;gap:8px 14px;color:#858b97;font-size:11px}
      .cs-process-log{padding:9px 11px;border:1px solid #292931;border-radius:10px;background:#0c0c0f;color:#b8c0cc;font:11px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
      @keyframes csProcessPulse{50%{opacity:.45;transform:scale(.84)}}@keyframes csProcessSlide{0%{transform:translateX(-115%)}100%{transform:translateX(330%)}}
      @media(max-width:720px){#cs_processes_overlay{padding:18px 10px}.cs-process-modal{max-height:calc(100vh - 36px)}.cs-process-row{flex-direction:column}.cs-process-status{align-self:flex-start}}
      @media(prefers-reduced-motion:reduce){.cs-process-status.is-active::before,.cs-process-progress.is-indeterminate>span{animation:none!important}}
    `;
    document.head.appendChild(style);
  }

  function ensureUi() {
    installStyles();
    let button = $("#cs_processes_button");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.id = "cs_processes_button";
      button.className = "btn-secondary";
      button.innerHTML = 'Processos <span class="cs-process-count">0</span>';
      const loja = $("#tab_btn_loja");
      if (loja?.parentElement) loja.insertAdjacentElement("afterend", button);
      else document.body.appendChild(button);
      button.addEventListener("click", openModal);
    }

    if (!$("#cs_processes_overlay")) {
      const overlay = document.createElement("div");
      overlay.id = "cs_processes_overlay";
      overlay.className = "hidden";
      overlay.innerHTML = `
        <section class="cs-process-modal" role="dialog" aria-modal="true" aria-labelledby="cs_processes_title">
          <header class="cs-process-modal-head">
            <div><div class="cs-process-modal-title" id="cs_processes_title">Processos ativos</div><div class="cs-process-modal-subtitle">Coletas, comparações, atualizações, adições, downloads, auditorias e operações da Loja que estão acontecendo agora.</div></div>
            <button class="cs-process-close" id="cs_processes_close" type="button" aria-label="Fechar">×</button>
          </header>
          <div class="cs-process-modal-body" id="cs_processes_body"></div>
        </section>`;
      document.body.appendChild(overlay);
      $("#cs_processes_close", overlay)?.addEventListener("click", closeModal);
      overlay.addEventListener("click", event => { if (event.target === overlay) closeModal(); });
    }
  }

  function openModal() {
    ensureUi();
    modalOpen = true;
    $("#cs_processes_overlay")?.classList.remove("hidden");
    render();
  }

  function closeModal() {
    modalOpen = false;
    $("#cs_processes_overlay")?.classList.add("hidden");
  }

  document.addEventListener("keydown", event => { if (event.key === "Escape" && modalOpen) closeModal(); });

  function pathOf(input) {
    try {
      const raw = typeof input === "string" || input instanceof URL ? String(input) : String(input?.url || "");
      return new URL(raw, location.href).pathname;
    } catch (_error) { return ""; }
  }

  function methodOf(input, init) {
    return text(init?.method || (typeof Request !== "undefined" && input instanceof Request ? input.method : "GET")).toUpperCase() || "GET";
  }

  function genericOperationTitle(path) {
    const last = text(path.split("/").filter(Boolean).at(-1) || "operação").replace(/[-_]+/g, " ");
    return last ? last.charAt(0).toUpperCase() + last.slice(1) : "Operação";
  }

  function requestDefinition(path, method) {
    const write = method !== "GET" && method !== "HEAD";
    if (path.endsWith("/comparacao/data")) return {kind:"comparison", title:"Comparação de catálogos"};
    if (write && path.endsWith("/plugintema/catalogo/gerar")) return {kind:"catalog", title:"Atualização do catálogo PluginTema"};
    if (write && path.endsWith("/plugintema/catalogo/exportar")) return {kind:"catalog", title:"Exportação do catálogo PluginTema"};
    if (write && path.endsWith("/catalogos/download")) return {kind:"catalog", title:"Coleta de catálogo"};
    if (write && path.endsWith("/atualizacoes/materializar")) return {kind:"update", title:"Sincronização da fila de atualização"};
    if (write && path.endsWith("/atualizacoes/prerequisitos")) return {kind:"update", title:"Verificação do Ambiente"};
    if (write && path.endsWith("/atualizacoes/preparar")) return {kind:"update", title:"Preparação e download de atualização"};
    if (write && path.endsWith("/atualizacoes/plano")) return {kind:"update", title:"Geração do plano de atualização"};
    if (write && /\/atualizacoes\/fila\/(?:iniciar|continuar|adicionar|pausar|parar|limpar)$/.test(path)) return {kind:"update", title:"Operação da fila de atualização"};
    if (write && path.endsWith("/loja/precos")) return {kind:"store", title:"Alteração de preços da Loja"};
    if (write && path.endsWith("/loja/pacotes/precos")) return {kind:"store", title:"Alteração de preço de produto"};
    if (write && path.endsWith("/loja/produtos/campos-ausentes")) return {kind:"store", title:"Auditoria de qualidade da Loja"};
    if (write && path.endsWith("/loja/produtos/sem-breve-descricao")) return {kind:"store", title:"Verificação de descrições da Loja"};
    if (write && path.endsWith("/loja/wordpress-manual/control")) return {kind:"store", title:"Controle do monitor WordPress"};
    if (write && path.endsWith("/adicoes/automatico")) return {kind:"addition", title:"Cadastro automático de produto"};
    if (write && path.endsWith("/adicoes/preparar-arquivo")) return {kind:"addition", title:"Download e preparação do ZIP"};
    if (write && path.endsWith("/adicoes/criar-rascunho")) return {kind:"addition", title:"Criação de rascunho WooCommerce"};
    if (write && path.endsWith("/adicoes/publicar")) return {kind:"addition", title:"Publicação de novo produto"};
    if (write && path.endsWith("/adicoes/conteudo")) return {kind:"addition", title:"Gravação de conteúdo do produto"};
    if (write && path.endsWith("/adicoes/sincronizar")) return {kind:"addition", title:"Sincronização de adições aprovadas"};
    if (write && path.endsWith("/adicoes/resetar")) return {kind:"addition", title:"Reinicialização de cadastro"};
    if (write && /\/(?:start|continue|resume|pause|stop)$/.test(path)) return {kind:"collection", title:"Coleta / processamento de catálogo"};
    if (!write) return null;

    const families = [
      ["/comparacao/", "comparison", "Operação de comparação"],
      ["/plugintema/catalogo/", "catalog", "Operação do catálogo PluginTema"],
      ["/catalogos/", "catalog", "Operação de catálogo"],
      ["/atualizacoes/", "update", "Operação de atualização"],
      ["/adicoes/", "addition", "Operação de adição"],
      ["/loja/", "store", "Operação da Loja"],
    ];
    const family = families.find(([prefix]) => path.includes(prefix));
    return family ? {kind:family[1], title:`${family[2]} · ${genericOperationTitle(path)}`} : null;
  }

  function startClientProcess(definition, path) {
    const id = `request:${Date.now()}:${++requestSequence}`;
    clientProcesses.set(id, {
      id, title: definition.title, kind: definition.kind, status: "Em andamento", detail: path,
      startedAt: Date.now(), active: true, progress: null, latestLog: ""
    });
    render();
    return id;
  }

  function finishClientProcess(id, ok, message = "") {
    const process = clientProcesses.get(id);
    if (!process) return;
    clientProcesses.delete(id);
    recentProcesses.set(id, {
      ...process, active: false, status: ok ? "Concluído" : "Erro",
      error: !ok, detail: message || process.detail, finishedAt: Date.now(), expiresAt: Date.now() + 9000
    });
    render();
  }

  window.fetch = function trackedFetch(input, init = {}) {
    const path = pathOf(input), method = methodOf(input, init), definition = requestDefinition(path, method);
    if (!definition) return nativeFetch(input, init);
    const id = startClientProcess(definition, path);
    return nativeFetch(input, init).then(response => {
      finishClientProcess(id, response.ok, response.ok ? "" : `HTTP ${response.status}`);
      return response;
    }, error => {
      finishClientProcess(id, false, text(error?.message || error));
      throw error;
    });
  };

  async function getJson(url) {
    const response = await nativeFetch(url, {credentials:"same-origin", cache:"no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  function parsedTime(value, fallback = Date.now()) {
    const parsed = Date.parse(text(value));
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function jobLogs(job) {
    const live = Array.isArray(job?.live_execution_logs) ? job.live_execution_logs : [];
    const persisted = Array.isArray(job?.execution_logs) ? job.execution_logs : [];
    return live.length ? live : persisted;
  }

  function updateBackendProcesses(runtime, target) {
    const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
    const queue = runtime?.queue || {};
    const activeName = text(queue.active_queue || "default") || "default";
    const listJobs = jobs.filter(job => (text(job?.queue_name || "default") || "default") === activeName);
    const executing = listJobs.find(job => EXECUTING_STATES.has(text(job?.state)));
    const preparing = listJobs.filter(job => PREPARING_STATES.has(text(job?.state)));
    const queued = listJobs.filter(job => text(job?.state) === "queued").length;
    const completed = listJobs.filter(job => text(job?.state) === "completed" && job?.history_ready === true).length;

    if (text(queue.status) === "running" || executing) {
      const logs = jobLogs(executing);
      target.set(`backend:update-queue:${activeName}`, {
        id:`backend:update-queue:${activeName}`, title:`Fila de atualização · ${activeName === "default" ? "Padrão" : activeName}`,
        kind:"update", status:"Executando", active:true, startedAt: parsedTime(executing?.executing_at),
        detail: executing ? `${executing.name} · ${executing.plugintema_version || "-"} → ${executing.effective_source_version || executing.approved_source_version || executing.ultrapack_version || "-"}` : `${queued} item(ns) aguardando execução`,
        latestLog: text(logs.at(-1) || executing?.live_log_tail || ""),
        progress: listJobs.length ? Math.round((completed / listJobs.length) * 100) : null,
        meta: `${completed} concluído(s) · ${queued} aguardando`
      });
    }

    preparing.slice(0, 12).forEach(job => {
      const logs = jobLogs(job);
      target.set(`backend:prepare:${job.job_id}`, {
        id:`backend:prepare:${job.job_id}`, title:"Preparação de atualização", kind:"update",
        status:text(job.state) || "Preparando", active:true, startedAt:parsedTime(job.updated_at || job.created_at),
        detail:`${job.name} · Woo #${job.woo_product_id}`,
        latestLog:text(logs.at(-1) || job.live_log_tail || job.diagnostics?.at?.(-1) || ""), progress:null,
        meta:`${job.plugintema_version || "-"} → ${job.effective_source_version || job.approved_source_version || job.ultrapack_version || "-"}`
      });
    });
  }

  function storePriceProcess(data, target) {
    if (text(data?.status) !== "running") return;
    const done = Number(data.completed || 0), total = Number(data.total || 0);
    target.set("backend:store-price", {
      id:"backend:store-price", title:"Atualização de preços da Loja", kind:"store", status:"Executando", active:true,
      startedAt:Date.now(), detail:text(data.current_product || data.message || "Atualizando preços"),
      latestLog:text(data.message || ""), progress:total > 0 ? Math.round((done / total) * 100) : null,
      meta:total > 0 ? `${done} de ${total}` : ""
    });
  }

  function storeDescriptionProcess(data, target) {
    if (text(data?.status) !== "running") return;
    target.set("backend:store-description", {
      id:"backend:store-description", title:"Verificação de descrições da Loja", kind:"store", status:"Executando", active:true,
      startedAt:Date.now(), detail:text(data.current_product || data.message || "Verificando produtos"), latestLog:text(data.message || ""),
      progress:null, meta:`${Number(data.examined || 0)} verificados · ${Number(data.found || 0)} encontrados`
    });
  }

  function storeQualityProcess(data, target) {
    if (text(data?.status) !== "running") return;
    const phase = text(data?.phase);
    const variationDone = Number(data?.variation_completed || 0);
    const variationTotal = Number(data?.variation_total || 0);
    const progress = phase === "variations" && variationTotal > 0
      ? Math.round((variationDone / variationTotal) * 100)
      : null;
    target.set("backend:store-quality", {
      id:"backend:store-quality", title:"Auditoria de qualidade da Loja", kind:"store", status:"Executando", active:true,
      startedAt:Date.now(), detail:text(data.current_product || data.message || "Verificando produtos"),
      latestLog:text(data.message || ""), progress,
      meta:phase === "variations" && variationTotal > 0
        ? `${variationDone} de ${variationTotal} variações`
        : `${Number(data.examined || 0)} verificados · ${Number(data.found || 0)} encontrados`
    });
  }

  function additionAutomaticProcesses(data, target) {
    const tasks = Array.isArray(data?.tasks) ? data.tasks : [];
    tasks.filter(task => task?.running === true).forEach(task => {
      const jobId = text(task?.job_id || task?.job?.job_id || "addition");
      const job = task?.job || {};
      const logs = Array.isArray(task?.logs) ? task.logs : [];
      target.set(`backend:addition-auto:${jobId}`, {
        id:`backend:addition-auto:${jobId}`, title:"Cadastro automático de produto", kind:"addition",
        status:text(task?.step || "Executando"), active:true, startedAt:parsedTime(task?.started_at),
        detail:text(job?.title || job?.source_name || `Cadastro ${jobId}`),
        latestLog:text(logs.at(-1) || ""), progress:Number.isFinite(Number(task?.progress)) ? Number(task.progress) : null,
        meta:job?.woo_product_id ? `Woo #${job.woo_product_id}` : ""
      });
    });
  }

  function wordpressManualProcess(data, target) {
    const status = text(data?.monitor_status).toLowerCase();
    const requestId = text(data?.request_id);
    if (!requestId || !MANUAL_ACTIVE_STATES.has(status)) return;
    const productId = Number(data?.product_id || 0);
    const versions = [text(data?.current_version), text(data?.new_version)].filter(Boolean).join(" → ");
    target.set(`backend:wordpress-manual:${requestId}`, {
      id:`backend:wordpress-manual:${requestId}`, title:"Atualização solicitada pelo WordPress", kind:"update",
      status:text(data?.state || data?.monitor_status || "Processando"), active:true,
      startedAt:parsedTime(data?.last_check), detail:text(data?.product || (productId ? `Woo #${productId}` : requestId)),
      latestLog:text((Array.isArray(data?.logs) ? data.logs.at(-1) : "") || ""), progress:null,
      meta:versions
    });
  }

  function collectionProcesses(data, target) {
    const runs = Array.isArray(data?.runs) ? data.runs : Array.isArray(data) ? data : [];
    runs.filter(run => run?.running === true || /rodando|running|iniciando|processando/i.test(text(run?.status))).slice(0, 16).forEach(run => {
      const id = text(run.run_id || run.id || "run");
      target.set(`backend:run:${id}`, {
        id:`backend:run:${id}`, title:"Coleta de catálogo", kind:"collection", status:text(run.status || "Rodando"), active:true,
        startedAt:Date.now() - Math.max(0, Number(run.timer_seconds || 0) * 1000),
        detail:text(run.summary || [run?.context?.site_key, run?.context?.item_type_key, run?.context?.slot_name].filter(Boolean).join(" · ") || id),
        latestLog:"", progress:Number.isFinite(Number(run.progress_percent)) ? Number(run.progress_percent) : null,
        meta:`${Number(run.saved_count || 0)} de ${Number(run.total_expected || 0) || "?"}`
      });
    });
  }

  function preservePrefix(target, prefix) {
    for (const [id, process] of backendProcesses) if (id.startsWith(prefix)) target.set(id, process);
  }

  async function pollBackend() {
    if (polling || document.hidden) return;
    polling = true;
    const next = new Map();
    try {
      const results = await Promise.allSettled([
        getJson("/atualizacoes/jobs"),
        getJson("/loja/precos/status"),
        getJson("/loja/produtos/sem-breve-descricao"),
        getJson("/runs"),
        getJson("/loja/produtos/campos-ausentes"),
        getJson("/adicoes/automatico/status"),
        getJson("/loja/wordpress-manual/status")
      ]);
      if (results[0].status === "fulfilled") updateBackendProcesses(results[0].value, next);
      else { preservePrefix(next, "backend:update-queue:"); preservePrefix(next, "backend:prepare:"); }
      if (results[1].status === "fulfilled") storePriceProcess(results[1].value, next); else preservePrefix(next, "backend:store-price");
      if (results[2].status === "fulfilled") storeDescriptionProcess(results[2].value, next); else preservePrefix(next, "backend:store-description");
      if (results[3].status === "fulfilled") collectionProcesses(results[3].value, next); else preservePrefix(next, "backend:run:");
      if (results[4].status === "fulfilled") storeQualityProcess(results[4].value, next); else preservePrefix(next, "backend:store-quality");
      if (results[5].status === "fulfilled") additionAutomaticProcesses(results[5].value, next); else preservePrefix(next, "backend:addition-auto:");
      if (results[6].status === "fulfilled") wordpressManualProcess(results[6].value, next); else preservePrefix(next, "backend:wordpress-manual:");

      for (const [id, previous] of backendProcesses) {
        if (next.has(id)) continue;
        recentProcesses.set(id, {...previous, active:false, status:"Finalizado", finishedAt:Date.now(), expiresAt:Date.now()+7000});
      }
      backendProcesses = next;
      render();
    } finally { polling = false; }
  }

  function cleanRecent() {
    const now = Date.now();
    for (const [id, process] of recentProcesses) if (Number(process.expiresAt || 0) <= now) recentProcesses.delete(id);
  }

  function elapsed(process) {
    const start = Number(process.startedAt || 0);
    if (!start) return "";
    const seconds = Math.max(0, Math.floor(((process.finishedAt || Date.now()) - start) / 1000));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60), rest = seconds % 60;
    return `${minutes}m ${rest}s`;
  }

  function processCard(process) {
    const progress = Number(process.progress);
    const hasProgress = Number.isFinite(progress) && progress >= 0;
    const pct = hasProgress ? Math.max(0, Math.min(100, Math.round(progress))) : 0;
    const statusClass = process.error ? "is-error" : process.active ? "is-active" : "is-done";
    return `<article class="cs-process-card ${process.active ? "" : "is-recent"}">
      <div class="cs-process-row"><div><div class="cs-process-name">${escapeHtml(process.title)}</div><div class="cs-process-detail">${escapeHtml(process.detail || "")}</div></div><span class="cs-process-status ${statusClass}">${escapeHtml(process.status || (process.active ? "Em andamento" : "Finalizado"))}</span></div>
      <div class="cs-process-progress ${hasProgress ? "" : "is-indeterminate"}"><span style="${hasProgress ? `width:${pct}%` : ""}"></span></div>
      <div class="cs-process-meta"><span>${hasProgress ? `${pct}%` : "Progresso em andamento"}</span>${process.meta ? `<span>${escapeHtml(process.meta)}</span>` : ""}<span>Tempo: ${escapeHtml(elapsed(process))}</span></div>
      ${process.latestLog ? `<div class="cs-process-log">${escapeHtml(process.latestLog)}</div>` : ""}
    </article>`;
  }

  function allProcesses() {
    cleanRecent();
    const active = [...backendProcesses.values(), ...clientProcesses.values()];
    const deduped = new Map();
    active.forEach(process => deduped.set(process.id, process));
    return {active:[...deduped.values()], recent:[...recentProcesses.values()]};
  }

  function render() {
    ensureUi();
    const {active, recent} = allProcesses();
    const button = $("#cs_processes_button"), count = $(".cs-process-count", button);
    if (count) count.textContent = String(active.length);
    button?.classList.toggle("has-active", active.length > 0);
    if (!modalOpen) return;
    const body = $("#cs_processes_body");
    if (!body) return;
    const items = [...active, ...recent];
    body.innerHTML = items.length ? items.map(processCard).join("") : '<div class="cs-process-empty">Nenhum processo ativo no momento.</div>';
  }

  function start() {
    ensureUi();
    pollBackend();
    window.setInterval(pollBackend, 2200);
    window.setInterval(() => { if (modalOpen) render(); else { cleanRecent(); render(); } }, 1000);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
