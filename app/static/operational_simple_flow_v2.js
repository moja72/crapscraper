(() => {
  "use strict";

  if (window.__crapScraperOperationalSimpleFlowV2Installed) return;
  window.__crapScraperOperationalSimpleFlowV2Installed = true;
  // Impede a camada visual v1 de montar um segundo fluxo. O backend v1 continua ativo.
  window.__crapScraperOperationalSimpleFlowInstalled = true;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const $$ = (selector, root = document) => Array.from(root?.querySelectorAll?.(selector) || []);
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const running = { update: false, addition: false };
  let pollingTimer = 0;
  let decorating = false;

  function installStyles() {
    if ($("#operational-simple-flow-v2-style")) return;
    const style = document.createElement("style");
    style.id = "operational-simple-flow-v2-style";
    style.textContent = `
      /* O fluxo simples é o único fluxo operacional visível. */
      #tab_panel_atualizacoes .cs-queue-v1,
      #tab_panel_adicoes .cs-queue-v1,
      #tab_panel_atualizacoes #updates_queue_accordion,
      #tab_panel_adicoes #addition_queue_accordion,
      #tab_panel_atualizacoes #cs_simple_update_bar,
      #tab_panel_adicoes #cs_simple_addition_bar,
      #tab_panel_atualizacoes #updates_prepare_selected,
      #tab_panel_atualizacoes #updates_enqueue_selected,
      #tab_panel_atualizacoes #updates_select_filtered,
      #tab_panel_adicoes #addition_prepare_selected,
      #tab_panel_adicoes #addition_add_selected_from_prep,
      #tab_panel_atualizacoes .update-prepare,
      #tab_panel_atualizacoes .update-enqueue-one,
      #tab_panel_atualizacoes .update-execute,
      #tab_panel_adicoes [data-add-action="prepare"],
      #tab_panel_adicoes [data-add-action="add"]{
        display:none!important;
      }

      #tab_panel_atualizacoes .cs-prep-v13,
      #tab_panel_adicoes .cs-prep-v13{
        border-color:var(--line-strong)!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-header,
      #tab_panel_adicoes .cs-prep-v13-header{
        cursor:default!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-header .updates-disclosure-chevron,
      #tab_panel_adicoes .cs-prep-v13-header .updates-disclosure-chevron{
        display:none!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-actions,
      #tab_panel_adicoes .cs-prep-v13-actions{
        display:flex!important;
        align-items:center!important;
        justify-content:flex-end!important;
        gap:8px!important;
      }
      .cs-canonical-execute{
        min-height:42px!important;
        padding:0 16px!important;
        border-radius:9px!important;
        font-size:12px!important;
        font-weight:850!important;
        white-space:nowrap!important;
      }
      .cs-canonical-row-execute{
        min-height:34px!important;
        padding:7px 11px!important;
        border-radius:8px!important;
        font-size:11px!important;
        font-weight:800!important;
      }
      .cs-canonical-progress{
        display:none;
        align-items:center;
        gap:9px;
        width:100%;
        min-height:38px;
        margin:0;
        padding:9px 11px;
        border:1px solid var(--line);
        border-radius:10px;
        background:rgba(255,255,255,.018);
        color:var(--text-muted);
        font-size:11px;
        line-height:1.45;
        box-sizing:border-box;
      }
      .cs-canonical-progress.is-visible{display:flex}
      .cs-canonical-progress.is-success{border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.055);color:#a7f3d0}
      .cs-canonical-progress.is-error{border-color:rgba(239,68,68,.35);background:rgba(239,68,68,.055);color:#fecaca}
      .cs-canonical-progress strong{color:inherit}
      #tab_panel_atualizacoes .update-job.cs-canonical-selected,
      #tab_panel_adicoes .addition-op-row.cs-canonical-selected{
        outline:1px solid rgba(16,185,129,.34);
        outline-offset:-1px;
        background:rgba(16,185,129,.028)!important;
      }
      #tab_panel_atualizacoes .cs-prep-v13-description,
      #tab_panel_adicoes .cs-prep-v13-description{
        max-width:920px;
      }
      @media(max-width:760px){
        #tab_panel_atualizacoes .cs-prep-v13-actions,
        #tab_panel_adicoes .cs-prep-v13-actions{
          width:100%!important;
          justify-content:flex-start!important;
        }
        .cs-canonical-execute{width:100%!important}
      }
    `;
    document.head.appendChild(style);
  }

  function toast(message, kind = "ok") {
    $("#cs_canonical_flow_toast")?.remove();
    const node = document.createElement("div");
    node.id = "cs_canonical_flow_toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = clean(message);
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

  function panel(kind) {
    return $(kind === "update" ? "#tab_panel_atualizacoes" : "#tab_panel_adicoes");
  }

  function preparationRoot(kind) {
    return $(".cs-prep-v13", panel(kind));
  }

  function jobIdFromUpdateCard(card) {
    return clean(card?.dataset?.updateJobId);
  }

  function jobIdFromAdditionRow(row) {
    const box = $("[data-add-select=\"preparation\"]", row);
    return clean(box?.dataset?.job || row?.dataset?.job || row?.dataset?.jobId);
  }

  function selectedIds(kind) {
    const root = preparationRoot(kind);
    if (!root) return [];
    if (kind === "update") {
      return $$(".update-job .update-select:checked:not(:disabled)", root)
        .map(box => jobIdFromUpdateCard(box.closest("[data-update-job-id]")))
        .filter(Boolean);
    }
    return $$('[data-add-select="preparation"]:checked', root)
      .map(box => clean(box.dataset.job))
      .filter(Boolean);
  }

  function progressNode(kind) {
    return $(`#cs_canonical_${kind}_progress`);
  }

  function executeButton(kind) {
    return $(`#cs_canonical_${kind}_execute`);
  }

  function ensureProgress(kind, root) {
    let node = progressNode(kind);
    if (node) return node;
    node = document.createElement("div");
    node.id = `cs_canonical_${kind}_progress`;
    node.className = "cs-canonical-progress";
    node.setAttribute("aria-live", "polite");
    const bulk = $(".cs-prep-v13-bulk", root);
    if (bulk?.parentNode) bulk.parentNode.insertBefore(node, bulk.nextSibling);
    else root.appendChild(node);
    return node;
  }

  function updateSelectionAppearance(kind) {
    const root = preparationRoot(kind);
    if (!root) return;
    if (kind === "update") {
      $$(".update-job", root).forEach(card => {
        const box = $(".update-select", card);
        card.classList.toggle("cs-canonical-selected", Boolean(box?.checked));
      });
    } else {
      $$(".addition-op-row", root).forEach(row => {
        const box = $('[data-add-select="preparation"]', row);
        row.classList.toggle("cs-canonical-selected", Boolean(box?.checked));
      });
    }
    const button = executeButton(kind);
    if (button && !running[kind]) button.disabled = selectedIds(kind).length === 0;
  }

  function renderBatch(kind, batch) {
    const root = preparationRoot(kind);
    if (!root) return;
    const progress = ensureProgress(kind, root);
    const button = executeButton(kind);
    const isRunning = Boolean(batch?.running);
    running[kind] = isRunning;
    if (button) {
      button.disabled = isRunning || (!isRunning && selectedIds(kind).length === 0);
      button.textContent = isRunning ? "Executando…" : "Executar selecionados";
    }

    const total = Number(batch?.total || 0);
    const processed = Number(batch?.processed || 0);
    const success = Number(batch?.success || 0);
    const errors = Number(batch?.errors || 0);
    const message = clean(batch?.message || (isRunning ? "Processando…" : "Pronto."));

    if (!isRunning && !batch?.done && !errors) {
      progress.className = "cs-canonical-progress";
      progress.textContent = "";
      return;
    }

    progress.className = `cs-canonical-progress is-visible${errors && !isRunning ? " is-error" : (!isRunning && batch?.done ? " is-success" : "")}`;
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
      if (!anyRunning && pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = 0;
        setTimeout(refreshNativePanels, 350);
      }
    } catch (_error) {}
  }

  function ensurePolling() {
    pollStatus(true);
    if (!pollingTimer) pollingTimer = setInterval(() => pollStatus(false), 1200);
  }

  function refreshNativePanels() {
    const updateRefresh = $("#updates_refresh, #updates_refresh_btn, [data-update-refresh]");
    if (updateRefresh && !updateRefresh.disabled) updateRefresh.click();
    const addRefresh = $("#addition_refresh, #addition_preparation_refresh, [data-addition-refresh]");
    if (addRefresh && !addRefresh.disabled) addRefresh.click();
    window.dispatchEvent(new CustomEvent("crapscraper:canonical-flow-finished"));
  }

  async function startBatch(kind, ids, button) {
    const normalized = [...new Set((ids || []).map(clean).filter(Boolean))];
    if (!normalized.length) {
      toast("Selecione ao menos um produto.", "warning");
      return;
    }
    const label = kind === "update" ? "atualizar" : "adicionar";
    const noun = kind === "update" ? "atualização" : "cadastro";
    if (!window.confirm(`Executar ${noun} automática de ${normalized.length} produto(s)? O CrapScraper fará todas as etapas técnicas e validações sozinho.`)) return;

    if (button) {
      button.disabled = true;
      button.textContent = "Iniciando…";
    }
    try {
      const payload = await post(`/operacoes/simples/${label}`, {job_ids:normalized});
      renderBatch(kind, payload?.batch || {running:true,total:normalized.length,processed:0,message:"Iniciando…"});
      toast("Execução iniciada.");
      ensurePolling();
    } catch (error) {
      toast(error?.message || "Falha ao iniciar a execução.", "error");
      if (button) {
        button.disabled = selectedIds(kind).length === 0;
        button.textContent = "Executar selecionados";
      }
    }
  }

  function renamePreparation(kind, root) {
    const title = kind === "update"
      ? $(".standard-update-accordion-title", root)
      : $(".section-title", root);
    if (title) title.textContent = kind === "update" ? "Produtos para atualizar" : "Produtos para adicionar";

    const description = $(".cs-prep-v13-description", root);
    if (description) {
      description.textContent = kind === "update"
        ? "Selecione os produtos aprovados e execute. O CrapScraper valida o vínculo e as versões, prepara o ZIP e o backup, gera o plano, atualiza e valida o resultado automaticamente."
        : "Selecione os produtos aprovados e execute. O CrapScraper prepara conteúdo, imagem, categoria, preços e ZIP, cria o produto e as variações, publica e valida o resultado automaticamente.";
    }

    if (root.tagName === "DETAILS") root.open = true;
    root.classList.remove("is-collapsed");
    const header = $(".cs-prep-v13-header", root);
    if (header) {
      header.setAttribute("aria-expanded", "true");
      if (!header.dataset.canonicalNoToggle) {
        header.dataset.canonicalNoToggle = "1";
        header.addEventListener("click", event => {
          event.preventDefault();
          if (root.tagName === "DETAILS") root.open = true;
          root.classList.remove("is-collapsed");
        }, true);
      }
    }
  }

  function hideLegacyOperationalControls(kind, root) {
    const selectors = kind === "update"
      ? ["#updates_prepare_selected", "#updates_enqueue_selected", "#updates_select_filtered"]
      : ["#addition_prepare_selected", "#addition_add_selected_from_prep"];
    selectors.forEach(selector => $(selector, root)?.classList.add("cs-canonical-hidden"));

    if (kind === "update") {
      $$(".update-prepare,.update-enqueue-one,.update-execute", root).forEach(node => node.style.display = "none");
    } else {
      $$('[data-add-action="prepare"],[data-add-action="add"]', root).forEach(node => node.style.display = "none");
    }
  }

  function ensureBulkExecute(kind, root) {
    const actions = $(".cs-prep-v13-actions", root);
    if (!actions) return;
    const id = `cs_canonical_${kind}_execute`;
    let button = $(`#${id}`, actions);
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.id = id;
      button.className = "btn-success cs-canonical-execute";
      button.textContent = "Executar selecionados";
      button.addEventListener("click", () => startBatch(kind, selectedIds(kind), button));
      actions.appendChild(button);
    }
    button.disabled = running[kind] || selectedIds(kind).length === 0;
    ensureProgress(kind, root);
  }

  function bindSelection(kind, root) {
    const selector = kind === "update"
      ? ".update-job .update-select"
      : '[data-add-select="preparation"]';
    $$(selector, root).forEach(box => {
      if (box.dataset.canonicalSelectionBound) return;
      box.dataset.canonicalSelectionBound = "1";
      box.addEventListener("change", () => updateSelectionAppearance(kind));
    });
    updateSelectionAppearance(kind);
  }

  function isTerminalUpdate(card) {
    const badge = clean($(".badge", card)?.textContent).toLowerCase();
    return /conclu|rollback conclu|cancelad/.test(badge) || card.classList.contains("is-completed");
  }

  function isTerminalAddition(row) {
    const badge = clean($(".addition-state-badge", row)?.textContent).toLowerCase();
    return /conclu|cancelad/.test(badge);
  }

  function ensureRowExecute(kind, root) {
    if (kind === "update") {
      $$(".update-job", root).forEach(card => {
        const jobId = jobIdFromUpdateCard(card);
        const actions = $(".update-row-actions", card);
        if (!jobId || !actions || isTerminalUpdate(card)) return;
        if ($(".cs-canonical-row-execute", actions)) return;
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn-success cs-canonical-row-execute";
        button.textContent = "Executar";
        button.addEventListener("click", () => startBatch("update", [jobId], button));
        actions.appendChild(button);
      });
      return;
    }

    $$(".addition-op-row", root).forEach(row => {
      const jobId = jobIdFromAdditionRow(row);
      const actions = $(".addition-op-actions", row);
      if (!jobId || !actions || isTerminalAddition(row)) return;
      if ($(".cs-canonical-row-execute", actions)) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn-success cs-canonical-row-execute";
      button.textContent = "Executar";
      button.addEventListener("click", () => startBatch("addition", [jobId], button));
      actions.appendChild(button);
    });
  }

  function hideQueues() {
    ["update", "addition"].forEach(kind => {
      const root = panel(kind);
      if (!root) return;
      $$(".cs-queue-v1", root).forEach(node => node.style.display = "none");
      const direct = kind === "update" ? $("#updates_queue_accordion", root) : $("#addition_queue_accordion", root);
      if (direct) direct.style.display = "none";
    });
  }

  function decorateKind(kind) {
    const root = preparationRoot(kind);
    if (!root) return;
    renamePreparation(kind, root);
    hideLegacyOperationalControls(kind, root);
    ensureBulkExecute(kind, root);
    bindSelection(kind, root);
    ensureRowExecute(kind, root);
  }

  function decorate() {
    if (decorating) return;
    decorating = true;
    try {
      installStyles();
      hideQueues();
      decorateKind("update");
      decorateKind("addition");
      // Remove barras da v1 caso tenham sido persistidas no DOM por um hot reload.
      $("#cs_simple_update_bar")?.remove();
      $("#cs_simple_addition_bar")?.remove();
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
    }, 1200);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true});
  else boot();
})();
