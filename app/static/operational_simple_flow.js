(() => {
  "use strict";

  if (window.__crapScraperOperationalSimpleFlowInstalled) return;
  window.__crapScraperOperationalSimpleFlowInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const selectedUpdates = new Set();
  const selectedAdditions = new Set();
  const running = { update: false, addition: false };
  let pollTimer = null;
  let decorating = false;

  function installStyles() {
    if ($("#operational-simple-flow-style")) return;
    const style = document.createElement("style");
    style.id = "operational-simple-flow-style";
    style.textContent = `
      #tab_panel_atualizacoes .cs-simple-flowbar,
      #tab_panel_adicoes .cs-simple-flowbar{
        display:grid;grid-template-columns:minmax(0,1fr) auto;gap:14px;align-items:center;
        margin:12px 0 14px;padding:14px;border:1px solid var(--line-strong);
        border-radius:14px;background:linear-gradient(180deg,rgba(255,255,255,.028),rgba(255,255,255,.012)),var(--bg-elev-2);
        box-shadow:0 8px 24px rgba(0,0,0,.18)
      }
      .cs-simple-flow-copy{display:grid;gap:5px;min-width:0}
      .cs-simple-flow-title{display:flex;align-items:center;gap:8px;color:var(--text);font-size:14px;font-weight:850}
      .cs-simple-flow-description{color:var(--text-muted);font-size:11px;line-height:1.45}
      .cs-simple-flow-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
      .cs-simple-flow-count{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--text-soft);background:rgba(255,255,255,.025);font-size:11px;font-weight:800;white-space:nowrap}
      .cs-simple-primary{min-height:42px!important;padding:10px 15px!important;border-radius:10px!important;font-size:12px!important;font-weight:850!important}
      .cs-simple-secondary{min-height:38px!important;padding:8px 11px!important;border-radius:9px!important;font-size:11px!important}
      .cs-simple-flow-progress{grid-column:1/-1;display:none;align-items:center;gap:9px;min-height:35px;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.018);color:var(--text-muted);font-size:11px}
      .cs-simple-flow-progress.is-visible{display:flex}
      .cs-simple-flow-progress.is-error{border-color:rgba(239,68,68,.35);color:#fecaca;background:rgba(239,68,68,.055)}
      .cs-simple-flow-progress.is-success{border-color:rgba(16,185,129,.35);color:#a7f3d0;background:rgba(16,185,129,.055)}
      .cs-simple-flow-progress strong{color:inherit}
      .cs-simple-add-check{display:inline-flex;align-items:center;justify-content:center;margin-right:8px;vertical-align:middle}
      .cs-simple-add-check input{width:16px!important;height:16px!important;margin:0!important;cursor:pointer}
      #tab_panel_atualizacoes .cs-simple-hidden-primary,
      #tab_panel_adicoes .cs-simple-hidden-primary{display:none!important}
      #tab_panel_atualizacoes .cs-simple-row-run,
      #tab_panel_adicoes .cs-simple-row-run{min-height:34px!important;padding:7px 10px!important;font-size:11px!important}
      #tab_panel_atualizacoes .update-job-main{min-width:0}
      #tab_panel_adicoes .addition-item.cs-simple-selected,
      #tab_panel_atualizacoes .update-job.cs-simple-selected{outline:1px solid rgba(16,185,129,.32);outline-offset:-1px;background:rgba(16,185,129,.025)}
      .cs-simple-advanced-note{margin-top:8px;color:var(--text-faint);font-size:10px;line-height:1.4}
      @media(max-width:760px){
        #tab_panel_atualizacoes .cs-simple-flowbar,#tab_panel_adicoes .cs-simple-flowbar{grid-template-columns:1fr}
        .cs-simple-flow-actions{justify-content:flex-start}
      }
    `;
    document.head.appendChild(style);
  }

  function toast(message, kind = "ok") {
    $("#cs_simple_flow_toast")?.remove();
    const node = document.createElement("div");
    node.id = "cs_simple_flow_toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = text(message);
    const palette = kind === "error"
      ? {border:"#ef4444", bg:"#451a1a"}
      : kind === "warning"
        ? {border:"#f59e0b", bg:"#3b2a05"}
        : {border:"#10b981", bg:"#063d2b"};
    Object.assign(node.style, {
      position:"fixed",right:"18px",bottom:"18px",zIndex:"195000",maxWidth:"560px",
      padding:"12px 14px",borderRadius:"12px",border:`1px solid ${palette.border}`,
      background:palette.bg,color:"#fff",fontWeight:"750",boxShadow:"0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 5200);
  }

  async function json(url, options = {}, timeoutMs = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1000, timeoutMs));
    try {
      const response = await fetch(url, {
        cache:"no-store",
        credentials:"same-origin",
        headers:{...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {})},
        ...options,
        signal:options.signal || controller.signal,
      });
      let payload = {};
      try { payload = await response.json(); } catch (_error) {}
      if (!response.ok || payload?.ok === false) throw new Error(payload?.message || `HTTP ${response.status}`);
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") throw new Error("O servidor demorou demais para responder.");
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  const post = (url, payload) => json(url, {method:"POST", body:JSON.stringify(payload || {})}, 25000);

  function progressNode(kind) {
    return $(`#cs_simple_${kind}_progress`);
  }

  function countNode(kind) {
    return $(`#cs_simple_${kind}_count`);
  }

  function executeButton(kind) {
    return $(`#cs_simple_${kind}_execute`);
  }

  function updateCount(kind) {
    const set = kind === "update" ? selectedUpdates : selectedAdditions;
    const node = countNode(kind);
    if (node) node.textContent = `${set.size} selecionado${set.size === 1 ? "" : "s"}`;
  }

  function renderBatch(kind, batch) {
    const progress = progressNode(kind);
    const button = executeButton(kind);
    if (!progress || !button) return;
    const isRunning = Boolean(batch?.running);
    running[kind] = isRunning;
    button.disabled = isRunning;
    button.textContent = isRunning ? "Executando…" : "Executar selecionados";

    const total = Number(batch?.total || 0);
    const processed = Number(batch?.processed || 0);
    const success = Number(batch?.success || 0);
    const errors = Number(batch?.errors || 0);
    const message = text(batch?.message, isRunning ? "Processando…" : "Pronto.");

    if (!isRunning && !batch?.done && !errors) {
      progress.className = "cs-simple-flow-progress";
      progress.textContent = "";
      return;
    }

    progress.className = `cs-simple-flow-progress is-visible${errors && !isRunning ? " is-error" : (!isRunning && batch?.done ? " is-success" : "")}`;
    progress.innerHTML = isRunning
      ? `<span class="inline-loading-spinner" aria-hidden="true"></span><span><strong>${esc(processed)}/${esc(total)}</strong> · ${esc(message)} · ${esc(success)} concluído(s)${errors ? ` · ${esc(errors)} erro(s)` : ""}</span>`
      : `<span>${errors ? "⚠" : "✓"}</span><span><strong>${esc(message)}</strong>${batch?.last_error ? ` · ${esc(batch.last_error)}` : ""}</span>`;
  }

  async function pollStatus(force = false) {
    if (!force && document.hidden) return;
    try {
      const payload = await json("/operacoes/simples/status", {}, 8000);
      renderBatch("update", payload?.update || {});
      renderBatch("addition", payload?.addition || {});
      const anyRunning = Boolean(payload?.update?.running || payload?.addition?.running);
      if (!anyRunning && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
        setTimeout(() => refreshNativePanels(), 300);
      }
    } catch (_error) {}
  }

  function ensurePolling() {
    pollStatus(true);
    if (!pollTimer) pollTimer = setInterval(() => pollStatus(false), 1200);
  }

  function refreshNativePanels() {
    const updateRefresh = $("#updates_refresh, #updates_refresh_btn, [data-update-refresh]");
    if (updateRefresh && !updateRefresh.disabled) updateRefresh.click();
    const addRefresh = $("#addition_refresh, #addition_preparation_refresh, [data-addition-refresh]");
    if (addRefresh && !addRefresh.disabled) addRefresh.click();
    window.dispatchEvent(new CustomEvent("crapscraper:simple-flow-finished"));
  }

  async function startBatch(kind, ids, button) {
    const normalized = [...new Set((ids || []).map(text).filter(Boolean))];
    if (!normalized.length) {
      toast("Selecione ao menos um produto.", "warning");
      return;
    }
    const verb = kind === "update" ? "atualizar" : "adicionar";
    const label = kind === "update" ? "atualização" : "cadastro";
    if (!window.confirm(`Executar ${label} automática de ${normalized.length} produto(s)? O CrapScraper fará as etapas técnicas e validações sozinho.`)) return;

    if (button) {
      button.disabled = true;
      button.textContent = "Iniciando…";
    }
    try {
      const payload = await post(`/operacoes/simples/${verb}`, {job_ids:normalized});
      renderBatch(kind, payload?.batch || {running:true,total:normalized.length,processed:0,message:"Iniciando…"});
      toast("Fluxo automático iniciado.");
      ensurePolling();
    } catch (error) {
      toast(error?.message || "Falha ao iniciar o fluxo automático.", "error");
      if (button) {
        button.disabled = false;
        button.textContent = "Executar selecionados";
      }
    }
  }

  function flowBarHtml(kind) {
    const isUpdate = kind === "update";
    return `
      <div class="cs-simple-flow-copy">
        <div class="cs-simple-flow-title"><span aria-hidden="true">${isUpdate ? "↻" : "+"}</span><span>Fluxo simplificado</span></div>
        <div class="cs-simple-flow-description">${isUpdate
          ? "Selecione os produtos e execute. Preparação, plano, backup e validação final continuam automáticos por baixo."
          : "Selecione os produtos e execute. Conteúdo, imagem, ZIP, cadastro, publicação e validação continuam automáticos por baixo."}</div>
      </div>
      <div class="cs-simple-flow-actions">
        <span class="cs-simple-flow-count" id="cs_simple_${kind}_count">0 selecionados</span>
        <button type="button" class="btn-secondary cs-simple-secondary" id="cs_simple_${kind}_select_page">Selecionar página</button>
        <button type="button" class="btn-secondary cs-simple-secondary" id="cs_simple_${kind}_clear">Limpar</button>
        <button type="button" class="btn-success cs-simple-primary" id="cs_simple_${kind}_execute">Executar selecionados</button>
      </div>
      <div class="cs-simple-flow-progress" id="cs_simple_${kind}_progress" aria-live="polite"></div>
    `;
  }

  function ensureUpdateBar() {
    const panel = $("#tab_panel_atualizacoes");
    if (!panel || $("#cs_simple_update_bar", panel)) return;
    const anchor = $("#updates_jobs", panel) || $(".updates-queue-section", panel) || panel.firstElementChild;
    const bar = document.createElement("section");
    bar.id = "cs_simple_update_bar";
    bar.className = "cs-simple-flowbar";
    bar.innerHTML = flowBarHtml("update");
    if (anchor?.parentNode) anchor.parentNode.insertBefore(bar, anchor);
    else panel.prepend(bar);

    $("#cs_simple_update_select_page")?.addEventListener("click", () => {
      $$("#tab_panel_atualizacoes .update-job .update-select:not(:disabled)").forEach(input => {
        input.checked = true;
        const id = text(input.closest("[data-update-job-id]")?.dataset?.updateJobId);
        if (id) selectedUpdates.add(id);
        input.dispatchEvent(new Event("change", {bubbles:true}));
      });
      updateCount("update");
      decorateUpdates();
    });
    $("#cs_simple_update_clear")?.addEventListener("click", () => {
      selectedUpdates.clear();
      $$("#tab_panel_atualizacoes .update-job .update-select").forEach(input => {
        if (input.checked) {
          input.checked = false;
          input.dispatchEvent(new Event("change", {bubbles:true}));
        }
      });
      updateCount("update");
      decorateUpdates();
    });
    $("#cs_simple_update_execute")?.addEventListener("click", event => startBatch("update", [...selectedUpdates], event.currentTarget));
  }

  function isUpdateTerminal(card) {
    const badge = text($(".badge", card)?.textContent).toLowerCase();
    return /conclu|rollback conclu|cancelad/.test(badge) || card.classList.contains("is-completed");
  }

  function decorateUpdates() {
    ensureUpdateBar();
    const panel = $("#tab_panel_atualizacoes");
    if (!panel) return;

    $("#updates_prepare_selected", panel)?.classList.add("cs-simple-hidden-primary");
    $("#updates_enqueue_selected", panel)?.classList.add("cs-simple-hidden-primary");
    $("#updates_select_filtered", panel)?.classList.add("cs-simple-hidden-primary");

    $$(".update-job", panel).forEach(card => {
      const id = text(card.dataset.updateJobId);
      const checkbox = $(".update-select", card);
      if (!id || !checkbox) return;

      if (checkbox.checked) selectedUpdates.add(id);
      if (selectedUpdates.has(id) && !checkbox.disabled) checkbox.checked = true;
      card.classList.toggle("cs-simple-selected", selectedUpdates.has(id));

      if (!checkbox.dataset.simpleFlowBound) {
        checkbox.dataset.simpleFlowBound = "1";
        checkbox.addEventListener("change", () => {
          checkbox.checked ? selectedUpdates.add(id) : selectedUpdates.delete(id);
          card.classList.toggle("cs-simple-selected", checkbox.checked);
          updateCount("update");
        });
      }

      $$(".update-prepare,.update-enqueue-one,.update-execute", card).forEach(button => button.classList.add("cs-simple-hidden-primary"));
      const actions = $(".update-row-actions", card);
      if (actions && !isUpdateTerminal(card) && !$(".cs-simple-row-run", actions)) {
        const run = document.createElement("button");
        run.type = "button";
        run.className = "btn-success cs-simple-row-run";
        run.textContent = "Executar";
        run.addEventListener("click", () => startBatch("update", [id], run));
        actions.appendChild(run);
      }
    });
    updateCount("update");
  }

  function additionJobId(item) {
    return text($("[data-job]", item)?.getAttribute("data-job") || item.dataset?.job || item.dataset?.jobId);
  }

  function additionOperationalUiPresent(panel) {
    return Boolean($("#addition_add_selected_from_prep", panel) || $("#addition_preparation_rows", panel));
  }

  function standardizeOperationalAddition(panel) {
    const execute = $("#addition_add_selected_from_prep", panel);
    if (execute) {
      if (text(execute.textContent) !== "Executar selecionados") execute.textContent = "Executar selecionados";
      execute.classList.add("cs-simple-primary");
    }
    $("#addition_prepare_selected", panel)?.classList.add("cs-simple-hidden-primary");
    $$('[data-add-action="add"]', panel).forEach(button => {
      if (text(button.textContent) !== "Executar") button.textContent = "Executar";
    });
    $$('[data-add-action="prepare"]', panel).forEach(button => button.classList.add("cs-simple-hidden-primary"));
  }

  function ensureAdditionBar(panel) {
    if ($("#cs_simple_addition_bar", panel)) return;
    const list = $("#addition_jobs_list", panel);
    if (!list) return;
    const bar = document.createElement("section");
    bar.id = "cs_simple_addition_bar";
    bar.className = "cs-simple-flowbar";
    bar.innerHTML = flowBarHtml("addition");
    list.parentNode.insertBefore(bar, list);

    $("#cs_simple_addition_select_page")?.addEventListener("click", () => {
      $$("#addition_jobs_list .addition-item").forEach(item => {
        const id = additionJobId(item);
        if (!id) return;
        selectedAdditions.add(id);
        const checkbox = $(".cs-simple-add-check input", item);
        if (checkbox) checkbox.checked = true;
        item.classList.add("cs-simple-selected");
      });
      updateCount("addition");
    });
    $("#cs_simple_addition_clear")?.addEventListener("click", () => {
      selectedAdditions.clear();
      $$("#addition_jobs_list .addition-item").forEach(item => {
        const checkbox = $(".cs-simple-add-check input", item);
        if (checkbox) checkbox.checked = false;
        item.classList.remove("cs-simple-selected");
      });
      updateCount("addition");
    });
    $("#cs_simple_addition_execute")?.addEventListener("click", event => startBatch("addition", [...selectedAdditions], event.currentTarget));
  }

  function decorateLegacyAdditions(panel) {
    ensureAdditionBar(panel);
    $$("#addition_jobs_list .addition-item", panel).forEach(item => {
      const id = additionJobId(item);
      if (!id) return;
      let wrap = $(".cs-simple-add-check", item);
      if (!wrap) {
        wrap = document.createElement("label");
        wrap.className = "cs-simple-add-check";
        wrap.innerHTML = `<input type="checkbox" aria-label="Selecionar produto">`;
        const first = item.firstElementChild;
        if (first) first.prepend(wrap);
        else item.prepend(wrap);
        $("input", wrap).addEventListener("change", event => {
          event.currentTarget.checked ? selectedAdditions.add(id) : selectedAdditions.delete(id);
          item.classList.toggle("cs-simple-selected", event.currentTarget.checked);
          updateCount("addition");
        });
      }
      const checkbox = $("input", wrap);
      checkbox.checked = selectedAdditions.has(id);
      item.classList.toggle("cs-simple-selected", selectedAdditions.has(id));

      const nativeRun = $("[data-addition-one-click]", item);
      if (nativeRun) {
        const active = /adicionando|executando|processando/i.test(text(nativeRun.textContent));
        const label = active ? "Executando…" : "Executar";
        if (text(nativeRun.textContent) !== label) nativeRun.textContent = label;
        nativeRun.classList.add("cs-simple-primary");
      }
    });
    updateCount("addition");
  }

  function decorateAdditions() {
    const panel = $("#tab_panel_adicoes");
    if (!panel) return;
    if (additionOperationalUiPresent(panel)) {
      standardizeOperationalAddition(panel);
      return;
    }
    decorateLegacyAdditions(panel);
  }

  function decorate() {
    if (decorating) return;
    decorating = true;
    try {
      installStyles();
      decorateUpdates();
      decorateAdditions();
    } finally {
      decorating = false;
    }
  }

  function boot() {
    installStyles();
    decorate();
    pollStatus(true);
    const observer = new MutationObserver(() => requestAnimationFrame(decorate));
    observer.observe(document.documentElement, {childList:true, subtree:true});
    setInterval(() => {
      decorate();
      if (running.update || running.addition) ensurePolling();
    }, 1400);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true});
  else boot();
})();
