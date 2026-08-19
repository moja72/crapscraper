(() => {
  "use strict";
  if (window.__crapScraperAdditionOneClickInstalled) return;
  window.__crapScraperAdditionOneClickInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const tasks = new Map();
  let polling = false;
  let decorating = false;

  function installStyles() {
    if ($("#addition-one-click-style")) return;
    const style = document.createElement("style");
    style.id = "addition-one-click-style";
    style.textContent = `
      #addition_chatgpt_toolbar{display:none!important}
      #tab_panel_adicoes .addition-actions{display:none!important}
      #tab_panel_adicoes .addition-progress{display:none!important}
      #tab_panel_adicoes .addition-auto-panel{display:grid;gap:8px;margin-top:10px;padding:10px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.012)}
      #tab_panel_adicoes .addition-auto-head{display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--text-muted);font-size:11px}
      #tab_panel_adicoes .addition-auto-status{font-weight:800;color:#cbd5e1}
      #tab_panel_adicoes .addition-auto-status.is-running{color:#9ff4d1}
      #tab_panel_adicoes .addition-auto-status.is-error{color:#ffc1c1}
      #tab_panel_adicoes .addition-auto-track{height:6px;overflow:hidden;border-radius:999px;background:#24242b}
      #tab_panel_adicoes .addition-auto-track span{display:block;width:0;height:100%;border-radius:inherit;background:#10b981;transition:width .25s ease}
      #tab_panel_adicoes .addition-auto-track.is-loading span{width:34%;animation:additionAutoSlide 1.15s ease-in-out infinite}
      #tab_panel_adicoes .addition-auto-log{max-height:118px;overflow:auto;padding:8px 9px;border:1px solid #292931;border-radius:8px;background:#0c0c0f;color:#aeb7c4;font:10px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
      #tab_panel_adicoes .addition-auto-action{display:flex;margin-top:2px}
      #tab_panel_adicoes .addition-auto-action button{width:100%;min-height:38px}
      @keyframes additionAutoSlide{0%{transform:translateX(-115%)}100%{transform:translateX(330%)}}
      @media(prefers-reduced-motion:reduce){#tab_panel_adicoes .addition-auto-track.is-loading span{animation:none;width:100%;opacity:.55}}
    `;
    document.head.appendChild(style);
  }

  async function request(url, options = {}) {
    const response = await fetch(url, {cache:"no-store", ...options});
    let payload = {};
    try { payload = await response.json(); } catch (_error) {}
    if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
    return payload;
  }

  async function start(jobId, button) {
    if (!jobId || button.disabled) return;
    button.disabled = true;
    button.textContent = "Adicionando…";
    try {
      const payload = await request("/adicoes/automatico", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({job_id:jobId})
      });
      if (payload?.task) tasks.set(jobId, payload.task);
      decorate();
      poll(true);
    } catch (error) {
      tasks.set(jobId, {job_id:jobId, running:false, done:false, error:String(error?.message || error), progress:0, logs:[String(error?.message || error)]});
      decorate();
    }
  }

  function findJobId(item) {
    const source = item.querySelector("[data-job]");
    return String(source?.getAttribute("data-job") || "").trim();
  }

  function taskView(jobId) {
    return tasks.get(jobId) || null;
  }

  function logText(task) {
    const logs = Array.isArray(task?.logs) ? task.logs : [];
    if (!logs.length) return "Pronto para adicionar. O CrapScraper cuidará de conteúdo, imagem, ZIP, WooCommerce e publicação.";
    return logs.slice(-8).join("\n");
  }

  function statusText(task) {
    if (!task) return "Pronto";
    if (task.running) return "Processando";
    if (task.error) return "Falhou";
    if (task.done) return "Concluído";
    return "Pronto";
  }

  function panelHtml(jobId, task) {
    const progress = Math.max(0, Math.min(100, Number(task?.progress || 0)));
    const running = Boolean(task?.running);
    const error = Boolean(task?.error);
    const statusClass = error ? "is-error" : running ? "is-running" : "";
    const trackClass = running && progress <= 2 ? "is-loading" : "";
    return `
      <div class="addition-auto-head">
        <span class="addition-auto-status ${statusClass}">${esc(statusText(task))}</span>
        <span>${running || task?.done ? `${Math.round(progress)}%` : ""}</span>
      </div>
      <div class="addition-auto-track ${trackClass}"><span style="${trackClass ? "" : `width:${progress}%`}"></span></div>
      <div class="addition-auto-log">${esc(logText(task))}</div>
      <div class="addition-auto-action">
        <button type="button" class="btn-success" data-addition-one-click="${esc(jobId)}" ${running ? "disabled" : ""}>${running ? "Adicionando…" : "Adicionar"}</button>
      </div>`;
  }

  function decorateItem(item) {
    const jobId = findJobId(item);
    if (!jobId) return;
    let panel = item.querySelector(".addition-auto-panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "addition-auto-panel";
      item.appendChild(panel);
    }
    const task = taskView(jobId);
    const signature = JSON.stringify({
      running:Boolean(task?.running), done:Boolean(task?.done), error:String(task?.error || ""),
      progress:Number(task?.progress || 0), logs:Array.isArray(task?.logs) ? task.logs.slice(-8) : []
    });
    if (panel.dataset.signature === signature) return;
    panel.dataset.signature = signature;
    panel.innerHTML = panelHtml(jobId, task);
    panel.querySelector("[data-addition-one-click]")?.addEventListener("click", event => start(jobId, event.currentTarget));
    const log = panel.querySelector(".addition-auto-log");
    if (log) log.scrollTop = log.scrollHeight;
  }

  function decorate() {
    if (decorating) return;
    decorating = true;
    try {
      installStyles();
      $$("#addition_jobs_list .addition-item").forEach(decorateItem);
    } finally {
      decorating = false;
    }
  }

  async function poll(force = false) {
    if (polling || (document.hidden && !force)) return;
    polling = true;
    try {
      const payload = await request("/adicoes/automatico/status");
      const rows = Array.isArray(payload?.tasks) ? payload.tasks : [];
      rows.forEach(task => {
        const id = String(task?.job_id || "");
        if (id) tasks.set(id, task);
      });
      decorate();

      // Ao terminar, pede à UI original que releia o job. Produtos concluídos
      // desaparecem naturalmente do filtro Ativos.
      if (rows.some(task => task?.done && !task?.running)) {
        const refresh = $("#addition_refresh");
        if (refresh && !refresh.dataset.autoRefreshPending) {
          refresh.dataset.autoRefreshPending = "1";
          setTimeout(() => {
            refresh.click();
            delete refresh.dataset.autoRefreshPending;
          }, 450);
        }
      }
    } catch (_error) {
      // O painel principal continua funcional mesmo se o endpoint de progresso
      // estiver temporariamente indisponível.
    } finally {
      polling = false;
    }
  }

  function boot() {
    installStyles();
    decorate();
    poll(true);
    const observer = new MutationObserver(() => requestAnimationFrame(decorate));
    observer.observe(document.documentElement, {childList:true, subtree:true});
    setInterval(() => { decorate(); poll(false); }, 1200);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true});
  else boot();
})();
