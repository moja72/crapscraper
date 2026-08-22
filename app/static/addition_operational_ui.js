(() => {
  "use strict";

  if (window.__crapScraperAdditionOperationalUiInstalled) return;
  window.__crapScraperAdditionOperationalUiInstalled = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  const state = {
    overview: {counts:{}, queue:{status:"stopped"}, processes:[]},
    preparation: {items:[], total:0, page:1, page_size:5, pages:1, q:"", state:""},
    queue: {items:[], total:0, page:1, page_size:5, pages:1, q:"", state:""},
    selectedPreparation: new Set(), selectedQueue: new Set(), loading: new Set(),
    polling: false, started: false, technical: [], detailJobId: "",
  };

  const QUEUE_OPTIONS = [
    ["", "Todos"], ["waiting", "Aguardando"], ["preparing", "Preparando"], ["ready", "Pronto"],
    ["queued", "Na fila"], ["executing", "Adicionando"], ["completed", "Concluído"],
    ["error", "Erro"], ["interrupted", "Interrompido"], ["canceled", "Cancelado"],
  ];
  const PREPARATION_OPTIONS = QUEUE_OPTIONS.filter(([value]) => !["queued","executing","completed","canceled"].includes(value));
  const ACTIVE_STATES = new Set(["preparing","queued","executing"]);
  const ERROR_STATES = new Set(["error","interrupted"]);

  function log(message, level = "INFO") {
    const line = `[${new Date().toLocaleTimeString("pt-BR")}] [${level}] ${text(message)}`;
    state.technical.push(line);
    state.technical = state.technical.slice(-300);
    const output = $("#addition_technical_log");
    if (output) {
      output.textContent = state.technical.length ? state.technical.join("\n") : "Nenhum evento nesta sessão.";
      output.scrollTop = output.scrollHeight;
    }
  }

  function toast(message, kind = "ok") {
    $("#addition_operational_toast")?.remove();
    const node = document.createElement("div");
    node.id = "addition_operational_toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = text(message);
    const palette = kind === "error" ? {border:"#ef4444", bg:"#451a1a"}
      : kind === "warning" ? {border:"#f59e0b", bg:"#3b2a05"}
      : {border:"#10b981", bg:"#063d2b"};
    Object.assign(node.style, {
      position:"fixed", right:"18px", bottom:"18px", zIndex:"190000", maxWidth:"580px",
      padding:"12px 14px", borderRadius:"12px", border:`1px solid ${palette.border}`,
      background:palette.bg, color:"#fff", fontWeight:"700", boxShadow:"0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 6000);
  }

  async function json(url, options = {}, timeoutMs = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.max(1200, timeoutMs));
    try {
      const response = await fetch(url, {
        cache:"no-store", credentials:"same-origin",
        headers:{...(options.body ? {"Content-Type":"application/json"} : {}), ...(options.headers || {})},
        ...options, signal:options.signal || controller.signal,
      });
      let payload = {};
      try { payload = await response.json(); } catch (_error) {}
      if (!response.ok || payload?.ok === false) {
        const error = new Error(payload?.message || `HTTP ${response.status}`);
        error.status = response.status;
        throw error;
      }
      return payload;
    } catch (error) {
      if (error?.name === "AbortError") throw new Error("O servidor demorou demais para responder.");
      throw error;
    } finally { clearTimeout(timer); }
  }

  const post = (url, payload = {}) => json(url, {method:"POST", body:JSON.stringify(payload)}, 25000);

  function query(params) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value) !== "") search.set(key, String(value));
    });
    return search.toString();
  }

  function panelVisible() {
    const panel = $("#tab_panel_adicoes");
    return !!panel && !panel.classList.contains("hidden");
  }

  function installStyles() {
    if ($("#addition-operational-ui-style")) return;
    const style = document.createElement("style");
    style.id = "addition-operational-ui-style";
    style.textContent = `
      #tab_panel_adicoes .addition-operations-center{display:grid;gap:16px}
      #tab_panel_adicoes .addition-summary-card{overflow:visible}
      #tab_panel_adicoes .addition-summary-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:12px}
      #tab_panel_adicoes .addition-summary-title .section-title{margin:0}
      #tab_panel_adicoes .addition-summary-grid{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:9px}
      #tab_panel_adicoes .addition-summary-chip{display:grid;gap:4px;min-height:82px;padding:12px;border:1px solid var(--line);border-radius:12px;background:var(--bg-elev-2);cursor:default}
      #tab_panel_adicoes button.addition-summary-chip{color:inherit;text-align:left;cursor:pointer}
      #tab_panel_adicoes button.addition-summary-chip:hover{border-color:var(--line-accent);background:var(--accent-soft)}
      #tab_panel_adicoes .addition-summary-chip strong{font-size:23px;line-height:1;font-variant-numeric:tabular-nums}
      #tab_panel_adicoes .addition-summary-chip span{color:var(--text-muted);font-size:11px;font-weight:700}
      #tab_panel_adicoes .addition-guidance{margin-top:10px;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.02);color:var(--text-muted);font-size:12px;line-height:1.45}
      #tab_panel_adicoes .addition-accordion>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;cursor:pointer;list-style:none}
      #tab_panel_adicoes .addition-accordion>summary::-webkit-details-marker{display:none}
      #tab_panel_adicoes .addition-accordion-title{display:inline-flex;align-items:center;gap:8px}
      #tab_panel_adicoes .addition-accordion[open]>.addition-summary-head .updates-disclosure-chevron{transform:rotate(90deg)}
      #tab_panel_adicoes .addition-toolbar{display:grid;grid-template-columns:minmax(220px,1fr) minmax(170px,230px) auto;gap:10px;align-items:end;margin:14px 0 10px}
      #tab_panel_adicoes .addition-toolbar .field label{font-size:12px;color:var(--text-muted)}
      #tab_panel_adicoes .addition-list-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:10px 0}
      #tab_panel_adicoes .addition-list-meta-left{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
      #tab_panel_adicoes .addition-list-meta .small{margin:0}
      #tab_panel_adicoes .addition-bulk-actions{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px}
      #tab_panel_adicoes .addition-table-head,#tab_panel_adicoes .addition-op-row{display:grid;grid-template-columns:42px minmax(260px,1.35fr) minmax(165px,.8fr) minmax(175px,.9fr) auto;gap:12px;align-items:center}
      #tab_panel_adicoes .addition-table-head{padding:8px 5px;border-bottom:1px solid var(--line-strong);color:var(--text-muted);font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.04em}
      #tab_panel_adicoes .addition-op-row{padding:13px 5px;border-bottom:1px solid var(--line);min-width:0}
      #tab_panel_adicoes .addition-op-main{min-width:0;display:grid;gap:4px}
      #tab_panel_adicoes .addition-op-name{font-weight:800;color:var(--text);overflow-wrap:anywhere}
      #tab_panel_adicoes .addition-op-meta{color:var(--text-muted);font-size:11px;line-height:1.45;overflow-wrap:anywhere}
      #tab_panel_adicoes .addition-op-meta a{text-decoration:underline;text-underline-offset:2px}
      #tab_panel_adicoes .addition-op-fields{display:grid;gap:4px;color:var(--text-soft);font-size:11px;line-height:1.45;min-width:0}
      #tab_panel_adicoes .addition-op-fields span{overflow-wrap:anywhere}
      #tab_panel_adicoes .addition-state-wrap{display:grid;gap:6px;min-width:0}
      #tab_panel_adicoes .addition-state-badge{display:inline-flex;width:max-content;max-width:100%;align-items:center;gap:6px;padding:5px 8px;border:1px solid var(--line-strong);border-radius:999px;background:rgba(255,255,255,.035);color:var(--text-soft);font-size:10px;font-weight:850}
      #tab_panel_adicoes .addition-state-badge.is-success{border-color:rgba(16,185,129,.38);background:rgba(16,185,129,.09);color:#a7f3d0}
      #tab_panel_adicoes .addition-state-badge.is-warning{border-color:rgba(245,158,11,.38);background:rgba(245,158,11,.08);color:#fde68a}
      #tab_panel_adicoes .addition-state-badge.is-danger{border-color:rgba(239,68,68,.42);background:rgba(239,68,68,.08);color:#fecaca}
      #tab_panel_adicoes .addition-state-badge.is-active{border-color:rgba(96,165,250,.42);background:rgba(96,165,250,.08);color:#bfdbfe}
      #tab_panel_adicoes .addition-progress-mini{height:6px;overflow:hidden;border-radius:999px;background:#24242b}
      #tab_panel_adicoes .addition-progress-mini span{display:block;height:100%;background:var(--success);transition:width .2s ease}
      #tab_panel_adicoes .addition-op-message{color:var(--text-muted);font-size:10px;line-height:1.35;overflow-wrap:anywhere}
      #tab_panel_adicoes .addition-op-actions{display:flex;justify-content:flex-end;gap:6px;flex-wrap:wrap}
      #tab_panel_adicoes .addition-op-actions button{min-height:34px;padding:7px 9px;font-size:11px}
      #tab_panel_adicoes .addition-stage-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
      #tab_panel_adicoes .addition-stage{display:inline-flex;align-items:center;gap:4px;padding:3px 6px;border:1px solid var(--line);border-radius:999px;color:var(--text-faint);font-size:9px;font-weight:750}
      #tab_panel_adicoes .addition-stage.is-done{border-color:rgba(16,185,129,.25);color:#8ce0bf;background:rgba(16,185,129,.06)}
      #tab_panel_adicoes .addition-empty{padding:22px;border:1px dashed var(--line-strong);border-radius:12px;text-align:center;color:var(--text-muted);background:rgba(255,255,255,.015)}
      #tab_panel_adicoes .addition-loading{display:flex;align-items:center;justify-content:center;gap:9px;min-height:90px;color:var(--text-muted)}
      #tab_panel_adicoes .addition-loading .inline-loading-spinner{display:inline-block}
      #tab_panel_adicoes .addition-pagination{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:14px}
      #tab_panel_adicoes .addition-pagination .badge{display:inline-flex;align-items:center;gap:6px}
      #tab_panel_adicoes .addition-pagination input{width:62px!important;min-height:30px!important;padding:4px 7px!important;text-align:center}
      #tab_panel_adicoes .addition-queue-status{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid var(--line);border-radius:999px;color:var(--text-muted);font-size:11px;font-weight:800}
      #tab_panel_adicoes .addition-queue-status.is-running{border-color:rgba(16,185,129,.35);color:#a7f3d0}#tab_panel_adicoes .addition-queue-status.is-paused{border-color:rgba(245,158,11,.35);color:#fde68a}
      #tab_panel_adicoes .addition-history-row{display:grid;grid-template-columns:minmax(240px,1.2fr) 130px minmax(180px,.8fr) minmax(190px,.9fr);gap:12px;padding:12px 5px;border-bottom:1px solid var(--line);align-items:start}
      #tab_panel_adicoes .addition-history-times{display:grid;gap:3px;color:var(--text-muted);font-size:10px}#tab_panel_adicoes .addition-history-times b{color:var(--text-soft)}
      #tab_panel_adicoes .addition-history-error{margin-top:5px;color:#fecaca;font-size:10px;line-height:1.4;overflow-wrap:anywhere}
      #tab_panel_adicoes .addition-history-log{margin-top:6px;padding:7px 8px;border:1px solid var(--line);border-radius:8px;background:#0d0d10;color:#9da7b5;font:10px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
      #addition_operational_modal{position:fixed;inset:0;z-index:170000;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(0,0,0,.76)}
      #addition_operational_modal.is-open{display:flex}#addition_operational_modal .addition-modal-card{width:min(1050px,96vw);max-height:92vh;overflow:auto;border:1px solid var(--line-strong);border-radius:18px;background:#0c0c0e;padding:18px;box-shadow:0 24px 80px rgba(0,0,0,.55)}
      #addition_operational_modal .addition-modal-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}
      #addition_operational_modal .addition-modal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}#addition_operational_modal .wide{grid-column:1/-1}
      #addition_operational_modal textarea{min-height:125px}#addition_operational_modal #addition_detail_prompt{min-height:220px;font-family:Consolas,monospace;font-size:11px}
      #addition_operational_modal .addition-modal-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;margin-top:14px}
      #addition_operational_modal .addition-detail-facts{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}#addition_operational_modal .addition-detail-facts span{padding:6px 8px;border:1px solid var(--line);border-radius:8px;color:var(--text-muted);font-size:10px}
      @media(max-width:1050px){#tab_panel_adicoes .addition-table-head{display:none}#tab_panel_adicoes .addition-op-row{grid-template-columns:36px minmax(0,1fr) auto}#tab_panel_adicoes .addition-op-row>.addition-op-fields,#tab_panel_adicoes .addition-op-row>.addition-state-wrap{grid-column:2}#tab_panel_adicoes .addition-op-row>.addition-op-actions{grid-column:2/-1;justify-content:flex-start}}
      @media(max-width:800px){#tab_panel_adicoes .addition-summary-grid{grid-template-columns:repeat(2,1fr)}#tab_panel_adicoes .addition-toolbar{grid-template-columns:1fr}#tab_panel_adicoes .addition-history-row{grid-template-columns:1fr}#addition_operational_modal .addition-modal-grid{grid-template-columns:1fr}#addition_operational_modal .wide{grid-column:auto}}
      @media(max-width:560px){#tab_panel_adicoes .addition-summary-grid{grid-template-columns:1fr}#tab_panel_adicoes .addition-list-meta,#tab_panel_adicoes .addition-pagination{align-items:stretch;flex-direction:column}#tab_panel_adicoes .addition-pagination button{width:100%}#tab_panel_adicoes .addition-op-row{grid-template-columns:30px 1fr}#tab_panel_adicoes .addition-op-row>.addition-op-actions{grid-column:1/-1}#tab_panel_adicoes .addition-op-row>.addition-op-actions button{flex:1}}
    `;
    document.head.appendChild(style);
  }

  function sectionTitle(title, summaryId) {
    return `<summary class="addition-summary-head"><span class="addition-accordion-title"><span class="updates-disclosure-chevron" aria-hidden="true">▸</span><span class="section-title">${esc(title)}</span></span><span class="small" id="${esc(summaryId)}">Carregando…</span></summary>`;
  }

  function paginationMarkup(prefix) {
    return `<div class="addition-pagination"><button class="btn-secondary" type="button" id="${prefix}_prev">← Anterior</button><span class="badge" id="${prefix}_page">Página <input type="number" min="1" value="1" aria-label="Ir para página"> de <span>1</span></span><button class="btn-secondary" type="button" id="${prefix}_next">Próxima →</button></div>`;
  }

  function selectOptions(options) {
    return options.map(([value,label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
  }

  function installUi() {
    installStyles();
    const panel = $("#tab_panel_adicoes");
    if (!panel || $("#addition_operational_root")) return;
    const environment = $(".updates-environment-card", panel);
    [...panel.children].forEach(child => { if (child !== environment) child.remove(); });

    const root = document.createElement("div");
    root.id = "addition_operational_root";
    root.className = "addition-operations-center";
    root.innerHTML = `
      <section class="card addition-summary-card">
        <div class="addition-summary-title"><div><div class="section-title">Resumo das adições</div><div class="small">Aprovado → Preparação → Fila → Execução → Conclusão → Histórico</div></div><button class="btn-secondary btn-sm" id="addition_sync_approved" type="button">Sincronizar aprovados</button></div>
        <div class="addition-summary-grid" id="addition_summary_grid"></div><div class="addition-guidance" id="addition_guidance">Carregando estado persistido…</div>
      </section>

      <details class="card updates-card-section addition-accordion" id="addition_preparation_accordion" open>
        ${sectionTitle("Preparação", "addition_preparation_summary")}
        <div class="addition-toolbar"><div class="field"><label for="addition_preparation_search">Buscar</label><input id="addition_preparation_search" type="search" placeholder="Nome, versão, origem ou WooCommerce ID"></div><div class="field"><label for="addition_preparation_state">Estado</label><select id="addition_preparation_state">${selectOptions(PREPARATION_OPTIONS)}</select></div><button class="btn-secondary" id="addition_preparation_refresh" type="button">Atualizar</button></div>
        <div class="addition-list-meta"><div class="addition-list-meta-left"><label class="small"><input id="addition_preparation_select_all" type="checkbox"> Selecionar página</label><span class="small" id="addition_preparation_meta">0 itens</span></div><div class="listing-page-size"><label class="small">Itens por página</label><input id="addition_preparation_page_size" class="listing-page-size-input" type="number" min="1" max="100" value="5"></div></div>
        <div class="addition-bulk-actions"><button class="btn-success" id="addition_prepare_selected" type="button">Preparar selecionados</button><button class="btn-secondary" id="addition_add_selected_from_prep" type="button">Adicionar selecionados</button></div>
        <div class="addition-table-head"><span></span><span>Produto</span><span>Dados</span><span>Estado</span><span>Ações</span></div><div id="addition_preparation_rows"></div>${paginationMarkup("addition_preparation")}
      </details>

      <details class="card updates-card-section addition-accordion updates-queue-section" id="addition_queue_accordion" open>
        ${sectionTitle("Fila de adições", "addition_queue_summary")}
        <div class="updates-section-heading"><div class="row"><span class="addition-queue-status" id="addition_queue_status">Fila parada</span></div><div class="row"><button class="btn-success" id="addition_queue_start" type="button">Executar fila</button><button class="btn-secondary" id="addition_queue_pause" type="button">Pausar</button><button class="btn-secondary" id="addition_queue_recover" type="button">Recuperar interrompidos</button></div></div>
        <div class="addition-toolbar"><div class="field"><label for="addition_queue_search">Buscar na fila</label><input id="addition_queue_search" type="search" placeholder="Nome, desenvolvedor, origem ou WooCommerce ID"></div><div class="field"><label for="addition_queue_state">Estado</label><select id="addition_queue_state">${selectOptions(QUEUE_OPTIONS)}</select></div><button class="btn-secondary" id="addition_queue_refresh" type="button">Atualizar</button></div>
        <div class="addition-list-meta"><div class="addition-list-meta-left"><label class="small"><input id="addition_queue_select_all" type="checkbox"> Selecionar página</label><span class="small" id="addition_queue_meta">0 itens</span></div><div class="listing-page-size"><label class="small">Itens por página</label><input id="addition_queue_page_size" class="listing-page-size-input" type="number" min="1" max="100" value="5"></div></div>
        <div class="addition-bulk-actions"><button class="btn-success" id="addition_queue_add_selected" type="button">Adicionar selecionados</button><button class="btn-secondary" id="addition_queue_retry_selected" type="button">Tentar novamente</button><button class="btn-danger" id="addition_queue_cancel_selected" type="button">Cancelar selecionados</button><button class="btn-secondary" id="addition_queue_clear_completed" type="button">Limpar concluídos da fila</button></div>
        <div class="addition-table-head"><span></span><span>Produto</span><span>Dados</span><span>Estado</span><span>Ações</span></div><div id="addition_queue_rows"></div>${paginationMarkup("addition_queue")}
      </details>

      <div data-operational-history-host data-history-type="addition"></div>

      <details class="card updates-card-section addition-accordion updates-technical-log" id="addition_technical_accordion">
        ${sectionTitle("Log técnico da sessão", "addition_technical_summary")}<pre id="addition_technical_log" class="log-output" aria-live="polite">Nenhum evento nesta sessão.</pre><div class="log-copy-row"><button class="btn-success" id="addition_copy_log" type="button">📋 Copiar log completo</button></div>
      </details>`;
    panel.appendChild(root);
    window.OperationalHistory?.mountAll(root);
    document.dispatchEvent(new CustomEvent("operational-history:host-ready", {detail:{root}}));
    if (environment && environment.parentElement === panel) panel.insertBefore(environment, root);
    installDetailModal();
    bindEvents();
  }

  function installDetailModal() {
    if ($("#addition_operational_modal")) return;
    const modal = document.createElement("div");
    modal.id = "addition_operational_modal";
    modal.innerHTML = `<section class="addition-modal-card" role="dialog" aria-modal="true" aria-labelledby="addition_detail_title"><div class="addition-modal-head"><div><div class="section-title" id="addition_detail_title">Detalhes da adição</div><div class="small" id="addition_detail_subtitle"></div></div><button class="btn-secondary" id="addition_detail_close" type="button" aria-label="Fechar">×</button></div><div class="addition-detail-facts" id="addition_detail_facts"></div><div class="addition-modal-grid"><div class="field"><label>Tipo</label><select id="addition_detail_kind"><option value="plugin">Plugin</option><option value="theme">Tema</option></select></div><div class="field"><label>Título</label><input id="addition_detail_title_input"></div><div class="field wide"><label>Breve descrição</label><textarea id="addition_detail_short"></textarea></div><div class="field wide"><label>Descrição completa</label><textarea id="addition_detail_description"></textarea></div><div class="field"><label>Título SEO</label><input id="addition_detail_seo"></div><div class="field"><label>Meta description</label><input id="addition_detail_meta"></div><div class="field wide"><label>Tags</label><input id="addition_detail_tags"></div><div class="field"><label>Anual · original</label><input id="addition_detail_annual_regular"></div><div class="field"><label>Anual · promocional</label><input id="addition_detail_annual_sale"></div><div class="field"><label>Vitalício · original</label><input id="addition_detail_lifetime_regular"></div><div class="field"><label>Vitalício · promocional</label><input id="addition_detail_lifetime_sale"></div><div class="field"><label>Substituir imagem</label><input id="addition_detail_image" type="file" accept="image/png,image/jpeg,image/webp"></div><div class="field"><label>Imagem atual</label><input id="addition_detail_image_status" disabled></div><div class="field wide"><label>Prompt manual (compatibilidade)</label><textarea id="addition_detail_prompt" readonly></textarea></div></div><div class="addition-modal-actions"><button class="btn-secondary" id="addition_detail_copy_prompt" type="button">Copiar prompt</button><button class="btn-secondary" id="addition_detail_prepare_zip" type="button">Preparar ZIP manualmente</button><button class="btn-secondary" id="addition_detail_create_draft" type="button">Criar rascunho</button><button class="btn-success" id="addition_detail_publish" type="button">Publicar com validação</button><button class="btn-danger" id="addition_detail_reset" type="button">Resetar cadastro</button><button class="btn-success" id="addition_detail_save" type="button">Salvar conteúdo</button></div></section>`;
    document.body.appendChild(modal);
    $("#addition_detail_close")?.addEventListener("click", closeDetail);
    modal.addEventListener("click", event => { if (event.target === modal) closeDetail(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape" && modal.classList.contains("is-open")) closeDetail(); });
  }

  function fill(id, value) { const node = $(`#${id}`); if (node) node.value = value ?? ""; }
  function stateClass(value) { if (value === "completed" || value === "ready") return "is-success"; if (ERROR_STATES.has(value) || value === "canceled") return "is-danger"; if (ACTIVE_STATES.has(value)) return "is-active"; return "is-warning"; }
  function duration(seconds) { const value=Math.max(0,Number(seconds||0)); if(value<60)return `${Math.floor(value)}s`; const minutes=Math.floor(value/60),rest=Math.floor(value%60); if(minutes<60)return `${minutes}m ${rest}s`; return `${Math.floor(minutes/60)}h ${minutes%60}m`; }
  function dateTime(value) { const raw=text(value); if(!raw)return "—"; const parsed=new Date(raw); return Number.isNaN(parsed.getTime())?raw:parsed.toLocaleString("pt-BR"); }
  function loadingMarkup(label="Carregando dados persistidos…") { return `<div class="addition-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>${esc(label)}</span></div>`; }
  function stageMarkup(job) { const stages=Array.isArray(job?.preparation)?job.preparation:[]; return `<div class="addition-stage-list">${stages.map(item=>`<span class="addition-stage ${item.done?"is-done":""}">${item.done?"✓":"○"} ${esc(item.label)}</span>`).join("")}</div>`; }

  function productMain(job) {
    const source=job.source_product_url?`<a href="${esc(job.source_product_url)}" target="_blank" rel="noopener">${esc(job.origin||"Abrir origem")}</a>`:esc(job.origin||"Origem sem URL");
    return `<div class="addition-op-main"><div class="addition-op-name">${esc(job.title||job.source_name||"Produto novo")}</div><div class="addition-op-meta">${esc(job.kind_label||"Plugin")} · versão ${esc(job.source_version||"-")} · ${source}${job.woo_product_id?` · Woo #${esc(job.woo_product_id)}`:""}</div>${stageMarkup(job)}</div>`;
  }
  function fieldsMarkup(job) { const official=job.site_oficial||job.source_official_url||""; return `<div class="addition-op-fields"><span><b>Categoria:</b> ${esc(job.category_name||(job.kind_label==="Tema"?"Tema":"Plugin"))}</span><span><b>Desenvolvedor:</b> ${esc(job.desenvolvedor||"—")}</span><span><b>Link oficial:</b> ${official?`<a href="${esc(official)}" target="_blank" rel="noopener">abrir</a>`:"—"}</span></div>`; }
  function statusMarkup(job) { const pct=Math.max(0,Math.min(100,Number(job.progress||0))); return `<div class="addition-state-wrap"><span class="addition-state-badge ${stateClass(job.queue_state)}">${esc(job.queue_state_label||job.queue_state)}</span><div class="addition-progress-mini"><span style="width:${pct}%"></span></div><div class="addition-op-message"><strong>${esc(job.current_step_label||"")}</strong>${job.status_message?`<br>${esc(job.status_message)}`:""}${job.operation_error?`<br>${esc(job.operation_error)}`:""}</div></div>`; }

  function rowActions(job, scope) {
    const actions=[];
    if(scope==="preparation"&&["waiting","error","interrupted"].includes(job.queue_state))actions.push(`<button class="btn-secondary" data-add-action="prepare" data-job="${esc(job.job_id)}">Preparar</button>`);
    if(["waiting","ready","error","interrupted","canceled"].includes(job.queue_state)&&job.queue_state!=="completed")actions.push(`<button class="btn-success" data-add-action="add" data-job="${esc(job.job_id)}">Adicionar</button>`);
    if(ERROR_STATES.has(job.queue_state))actions.push(`<button class="btn-secondary" data-add-action="retry" data-job="${esc(job.job_id)}">Tentar novamente</button>`);
    if(!["preparing","executing","completed"].includes(job.queue_state)&&!job.woo_product_id)actions.push(`<button class="btn-danger" data-add-action="cancel" data-job="${esc(job.job_id)}">Cancelar</button>`);
    actions.push(`<button class="btn-secondary" data-add-action="detail" data-job="${esc(job.job_id)}">Detalhes</button>`);
    return `<div class="addition-op-actions">${actions.join("")}</div>`;
  }

  function operationalRow(job, scope, selectedSet) { return `<article class="addition-op-row" data-add-job="${esc(job.job_id)}"><div><input type="checkbox" data-add-select="${esc(scope)}" data-job="${esc(job.job_id)}" ${selectedSet.has(job.job_id)?"checked":""} aria-label="Selecionar ${esc(job.title||job.source_name||"produto")}"></div>${productMain(job)}${fieldsMarkup(job)}${statusMarkup(job)}${rowActions(job,scope)}</article>`; }

  function renderRows(scope) {
    const data=state[scope],target=$(`#addition_${scope}_rows`); if(!target)return;
    if(state.loading.has(scope)){target.innerHTML=loadingMarkup();return;}
    const selected=scope==="preparation"?state.selectedPreparation:state.selectedQueue;
    target.innerHTML=data.items.length?data.items.map(job=>operationalRow(job,scope,selected)).join(""):`<div class="addition-empty">Nenhum item corresponde aos filtros atuais.</div>`;
    target.querySelectorAll("[data-add-select]").forEach(box=>box.addEventListener("change",()=>{const set=box.dataset.addSelect==="preparation"?state.selectedPreparation:state.selectedQueue;if(box.checked)set.add(box.dataset.job);else set.delete(box.dataset.job);syncSelectAll(box.dataset.addSelect);}));
    target.querySelectorAll("[data-add-action]").forEach(button=>button.addEventListener("click",()=>handleRowAction(button.dataset.addAction,button.dataset.job)));
  }

  function renderPagination(scope) {
    const data=state[scope],prefix=`addition_${scope}`,pageWrap=$(`#${prefix}_page`);
    if(pageWrap){const input=$("input",pageWrap),total=$("span",pageWrap);if(input){input.value=String(data.page);input.max=String(data.pages);}if(total)total.textContent=String(data.pages);}
    const prev=$(`#${prefix}_prev`),next=$(`#${prefix}_next`);if(prev)prev.disabled=data.page<=1;if(next)next.disabled=data.page>=data.pages;
    const meta=$(`#${prefix}_meta`);if(meta){if(!data.total)meta.textContent=scope==="history"?"0 registros":"0 itens";else{const start=(data.page-1)*data.page_size+1,end=Math.min(data.total,data.page*data.page_size);meta.textContent=`Mostrando ${start}–${end} de ${data.total} ${scope==="history"?"registros":"itens"}`;}}
  }

  function renderSummary() {
    const counts=state.overview.counts||{},grid=$("#addition_summary_grid");if(!grid)return;
    const chips=[["Total aprovado",counts.total||0,""],["Aguardando",counts.waiting||0,"waiting"],["Preparando",counts.preparing||0,"preparing"],["Pronto",counts.ready||0,"ready"],["Na fila",counts.queued||0,"queued"],["Em execução",counts.executing||0,"executing"],["Concluído",counts.completed||0,"completed"],["Com erro",(counts.error||0)+(counts.interrupted||0),counts.error?"error":"interrupted"],["Cancelado",counts.canceled||0,"canceled"]];
    grid.innerHTML=chips.map(([label,count,filter])=>{const tag=filter?"button":"div";return `<${tag} ${filter?`type="button" data-summary-state="${esc(filter)}"`:""} class="addition-summary-chip"><strong>${esc(count)}</strong><span>${esc(label)}</span></${tag}>`;}).join("");
    grid.querySelectorAll("[data-summary-state]").forEach(button=>button.addEventListener("click",()=>{const value=button.dataset.summaryState||"";$("#addition_queue_state").value=value;state.queue.state=value;state.queue.page=1;$("#addition_queue_accordion").open=true;loadScope("queue");$("#addition_queue_accordion")?.scrollIntoView({behavior:"smooth",block:"start"});}));
    const status=text(state.overview.queue?.status||"stopped"),statusNode=$("#addition_queue_status");
    if(statusNode){statusNode.className=`addition-queue-status ${status==="running"?"is-running":status==="paused"?"is-paused":""}`;statusNode.textContent=status==="running"?"Fila executando":status==="paused"?"Fila pausada":"Fila parada";}
    const pause=$("#addition_queue_pause");if(pause){pause.disabled=status==="stopped";pause.textContent=status==="paused"?"Continuar":"Pausar";}
    const guidance=$("#addition_guidance");if(guidance){if((counts.executing||0)>0)guidance.textContent=`${counts.executing} produto(s) em cadastro. A fila exibe a etapa persistida e o último evento do backend.`;else if((counts.preparing||0)>0)guidance.textContent=`${counts.preparing} produto(s) em preparação. Descrição, imagem, categoria, preços e ZIP são reaproveitados quando já estiverem válidos.`;else if((counts.queued||0)>0)guidance.textContent=`${counts.queued} produto(s) aguardando execução sequencial na fila.`;else if((counts.error||0)+(counts.interrupted||0)>0)guidance.textContent=`${(counts.error||0)+(counts.interrupted||0)} produto(s) exigem atenção. Use Tentar novamente ou Recuperar interrompidos.`;else if((counts.ready||0)>0)guidance.textContent=`${counts.ready} produto(s) já estão preparados e podem ser adicionados sem refazer as etapas concluídas.`;else guidance.textContent="Nenhuma adição pendente no momento. Concluídos permanecem no Histórico.";}
    const prepSummary=$("#addition_preparation_summary");if(prepSummary)prepSummary.textContent=`${counts.preparing||0} preparando · ${counts.ready||0} prontos`;
    const queueSummary=$("#addition_queue_summary");if(queueSummary)queueSummary.textContent=`${counts.queued||0} na fila · ${counts.executing||0} executando · ${counts.completed||0} concluídos`;
  }

  function syncSelectAll(scope){const data=state[scope],set=scope==="preparation"?state.selectedPreparation:state.selectedQueue,box=$(`#addition_${scope}_select_all`);if(!box)return;const ids=data.items.map(item=>item.job_id);box.checked=ids.length>0&&ids.every(id=>set.has(id));box.indeterminate=ids.some(id=>set.has(id))&&!box.checked;}
  function renderScope(scope){renderRows(scope);renderPagination(scope);syncSelectAll(scope);}

  async function loadOverview(){if(state.loading.has("overview"))return;state.loading.add("overview");try{state.overview=await json("/adicoes/operacoes?scope=overview");renderSummary();}catch(error){log(`Falha ao carregar resumo: ${error.message}`,"ERRO");}finally{state.loading.delete("overview");}}
  async function loadScope(scope,{silent=false}={}){const data=state[scope];if(!data||state.loading.has(scope))return;state.loading.add(scope);if(!silent)renderRows(scope);try{const params={scope,q:data.q,state:data.state,page:data.page,page_size:data.page_size};const payload=await json(`/adicoes/operacoes?${query(params)}`);Object.assign(data,payload);renderScope(scope);}catch(error){log(`Falha em ${scope}: ${error.message}`,"ERRO");if(!silent)toast(error.message,"error");}finally{state.loading.delete(scope);}}
  async function refreshAll({silent=false}={}){await Promise.all([loadOverview(),loadScope("preparation",{silent}),loadScope("queue",{silent})]);}

  async function operation(url,payload,successMessage="Operação iniciada."){try{const result=await post(url,payload);log(result.message||successMessage);toast(result.message||successMessage);window.OperationalHistory?.invalidate("addition");await refreshAll({silent:true});return result;}catch(error){log(error.message,"ERRO");toast(error.message,"error");await refreshAll({silent:true});throw error;}}
  async function handleRowAction(action,jobId){if(!jobId)return;if(action==="detail")return openDetail(jobId);if(action==="prepare")return operation("/adicoes/operacoes/preparar",{job_ids:[jobId]},"Preparação iniciada.");if(action==="add")return operation("/adicoes/fila/adicionar",{job_ids:[jobId]},"Produto enviado ao fluxo de adição.");if(action==="retry")return operation("/adicoes/fila/retry",{job_ids:[jobId]},"Nova tentativa iniciada.");if(action==="cancel"){if(!confirm("Cancelar este item da fila? Isso só será permitido se nenhuma escrita remota já tiver começado."))return;return operation("/adicoes/fila/cancelar",{job_ids:[jobId]},"Item cancelado.");}}
  function selected(scope){return [...(scope==="preparation"?state.selectedPreparation:state.selectedQueue)];}
  function debounce(fn,ms=280){let timer=null;return(...args)=>{clearTimeout(timer);timer=setTimeout(()=>fn(...args),ms);};}

  function bindPagination(scope){const data=state[scope],prefix=`addition_${scope}`;$(`#${prefix}_prev`)?.addEventListener("click",()=>{if(data.page>1){data.page-=1;loadScope(scope);}});$(`#${prefix}_next`)?.addEventListener("click",()=>{if(data.page<data.pages){data.page+=1;loadScope(scope);}});$("input",$(`#${prefix}_page`))?.addEventListener("change",event=>{data.page=Math.max(1,Math.min(data.pages,Number(event.target.value||1)));loadScope(scope);});$(`#${prefix}_page_size`)?.addEventListener("change",event=>{data.page_size=Math.max(1,Math.min(100,Number(event.target.value||5)));event.target.value=String(data.page_size);data.page=1;loadScope(scope);});}

  function bindEvents() {
    const prepSearch=debounce(value=>{state.preparation.q=value;state.preparation.page=1;loadScope("preparation");});
    $("#addition_preparation_search")?.addEventListener("input",event=>prepSearch(event.target.value));
    $("#addition_preparation_state")?.addEventListener("change",event=>{state.preparation.state=event.target.value;state.preparation.page=1;loadScope("preparation");});
    $("#addition_preparation_refresh")?.addEventListener("click",()=>loadScope("preparation"));
    $("#addition_preparation_select_all")?.addEventListener("change",event=>{state.preparation.items.forEach(item=>event.target.checked?state.selectedPreparation.add(item.job_id):state.selectedPreparation.delete(item.job_id));renderScope("preparation");});
    $("#addition_prepare_selected")?.addEventListener("click",()=>{const ids=selected("preparation");if(!ids.length)return toast("Selecione ao menos um produto.","warning");operation("/adicoes/operacoes/preparar",{job_ids:ids});});
    $("#addition_add_selected_from_prep")?.addEventListener("click",()=>{const ids=selected("preparation");if(!ids.length)return toast("Selecione ao menos um produto.","warning");operation("/adicoes/fila/adicionar",{job_ids:ids});});

    const queueSearch=debounce(value=>{state.queue.q=value;state.queue.page=1;loadScope("queue");});
    $("#addition_queue_search")?.addEventListener("input",event=>queueSearch(event.target.value));
    $("#addition_queue_state")?.addEventListener("change",event=>{state.queue.state=event.target.value;state.queue.page=1;loadScope("queue");});
    $("#addition_queue_refresh")?.addEventListener("click",()=>loadScope("queue"));
    $("#addition_queue_select_all")?.addEventListener("change",event=>{state.queue.items.forEach(item=>event.target.checked?state.selectedQueue.add(item.job_id):state.selectedQueue.delete(item.job_id));renderScope("queue");});
    $("#addition_queue_add_selected")?.addEventListener("click",()=>{const ids=selected("queue");if(!ids.length)return toast("Selecione ao menos um produto.","warning");operation("/adicoes/fila/adicionar",{job_ids:ids});});
    $("#addition_queue_retry_selected")?.addEventListener("click",()=>{const ids=selected("queue");if(!ids.length)return toast("Selecione ao menos um produto.","warning");operation("/adicoes/fila/retry",{job_ids:ids});});
    $("#addition_queue_cancel_selected")?.addEventListener("click",()=>{const ids=selected("queue");if(!ids.length)return toast("Selecione ao menos um produto.","warning");if(confirm("Cancelar os itens selecionados quando for seguro?"))operation("/adicoes/fila/cancelar",{job_ids:ids});});
    $("#addition_queue_clear_completed")?.addEventListener("click",()=>{if(confirm("Remover os concluídos apenas da fila visual? O histórico será preservado."))operation("/adicoes/fila/limpar-concluidos",{});});
    $("#addition_queue_start")?.addEventListener("click",()=>operation("/adicoes/fila/iniciar",{}));
    $("#addition_queue_pause")?.addEventListener("click",()=>operation(state.overview.queue?.status==="paused"?"/adicoes/fila/continuar":"/adicoes/fila/pausar",{}));
    $("#addition_queue_recover")?.addEventListener("click",()=>operation("/adicoes/fila/recuperar",{}));

    bindPagination("preparation");bindPagination("queue");
    $("#addition_sync_approved")?.addEventListener("click",()=>operation("/adicoes/operacoes/sincronizar",{}));
    $("#addition_copy_log")?.addEventListener("click",async()=>{const content=state.technical.join("\n")||"Nenhum evento nesta sessão.";try{await navigator.clipboard.writeText(content);toast("Log copiado.");}catch(_error){toast("Não foi possível copiar o log.","error");}});
    $("#addition_detail_copy_prompt")?.addEventListener("click",copyDetailPrompt);$("#addition_detail_save")?.addEventListener("click",saveDetailContent);$("#addition_detail_prepare_zip")?.addEventListener("click",prepareZipManual);$("#addition_detail_create_draft")?.addEventListener("click",createDraftManual);$("#addition_detail_publish")?.addEventListener("click",publishSafeManual);$("#addition_detail_reset")?.addEventListener("click",resetManual);
    $("#tab_btn_adicoes")?.addEventListener("click",()=>setTimeout(()=>{if(panelVisible())refreshAll({silent:true});},0));
  }

  async function readFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result||""));reader.onerror=()=>reject(new Error("Não foi possível ler a imagem."));reader.readAsDataURL(file);});}
  async function openDetail(jobId){try{const payload=await json(`/adicoes/operacoes/item?${query({job_id:jobId})}`),job=payload.job||{};state.detailJobId=jobId;$("#addition_detail_title").textContent=job.title||job.source_name||"Detalhes da adição";$("#addition_detail_subtitle").textContent=`${job.queue_state_label||job.queue_state} · ${job.origin||"-"}${job.woo_product_id?` · Woo #${job.woo_product_id}`:""}`;$("#addition_detail_facts").innerHTML=[`Versão: ${job.source_version||"-"}`,`Desenvolvedor: ${job.desenvolvedor||"-"}`,`Categoria: ${job.category_name||"-"}`,`Etapa: ${job.current_step_label||"-"}`].map(value=>`<span>${esc(value)}</span>`).join("");fill("addition_detail_kind",job.kind||"plugin");fill("addition_detail_title_input",job.title||job.source_name||"");fill("addition_detail_short",job.short_description);fill("addition_detail_description",job.description);fill("addition_detail_seo",job.seo_title);fill("addition_detail_meta",job.meta_description);fill("addition_detail_tags",job.tags);fill("addition_detail_annual_regular",job.annual_regular);fill("addition_detail_annual_sale",job.annual_sale);fill("addition_detail_lifetime_regular",job.lifetime_regular);fill("addition_detail_lifetime_sale",job.lifetime_sale);fill("addition_detail_image_status",job.image_path||"Nenhuma imagem local");fill("addition_detail_prompt",job.prompt||"");$("#addition_detail_image").value="";const reset=$("#addition_detail_reset");if(reset)reset.disabled=job.queue_state==="executing";const publish=$("#addition_detail_publish");if(publish)publish.disabled=!job.woo_product_id||job.queue_state==="completed";$("#addition_operational_modal").classList.add("is-open");}catch(error){toast(error.message,"error");}}
  function closeDetail(){$("#addition_operational_modal")?.classList.remove("is-open");state.detailJobId="";}
  async function copyDetailPrompt(){const value=$("#addition_detail_prompt")?.value||"";try{await navigator.clipboard.writeText(value);toast("Prompt copiado.");}catch(_error){toast("Não foi possível copiar o prompt.","error");}}
  async function saveDetailContent(){const jobId=state.detailJobId;if(!jobId)return;const file=$("#addition_detail_image")?.files?.[0]||null;try{const image=file?await readFile(file):"";await post("/adicoes/conteudo",{job_id:jobId,kind:$("#addition_detail_kind").value,title:$("#addition_detail_title_input").value,short_description:$("#addition_detail_short").value,description:$("#addition_detail_description").value,seo_title:$("#addition_detail_seo").value,meta_description:$("#addition_detail_meta").value,tags:$("#addition_detail_tags").value,annual_regular:$("#addition_detail_annual_regular").value,annual_sale:$("#addition_detail_annual_sale").value,lifetime_regular:$("#addition_detail_lifetime_regular").value,lifetime_sale:$("#addition_detail_lifetime_sale").value,image_base64:image,image_name:file?.name||""});toast("Conteúdo salvo.");log(`Conteúdo salvo para ${jobId}.`);closeDetail();await refreshAll({silent:true});}catch(error){toast(error.message,"error");}}
  async function prepareZipManual(){const jobId=state.detailJobId;if(!jobId)return;try{await post("/adicoes/preparar-arquivo",{job_id:jobId});toast("ZIP preparado.");closeDetail();await refreshAll({silent:true});}catch(error){toast(error.message,"error");}}
  async function createDraftManual(){const jobId=state.detailJobId;if(!jobId)return;if(!confirm("Criar o rascunho WooCommerce com os dados já preparados?"))return;try{await post("/adicoes/criar-rascunho",{job_id:jobId,confirmation:"CRIAR RASCUNHO"});toast("Rascunho criado e validado.");closeDetail();await refreshAll({silent:true});}catch(error){toast(error.message,"error");}}
  async function publishSafeManual(){const jobId=state.detailJobId;if(!jobId)return;if(!confirm("Publicar este rascunho usando a validação completa e a reconciliação dos campos personalizados?"))return;try{await post("/adicoes/operacoes/publicar",{job_id:jobId});toast("Produto publicado e validado.");closeDetail();await window.OperationalHistory?.refresh("addition");await refreshAll({silent:true});}catch(error){toast(error.message,"error");}}
  async function resetManual(){const jobId=state.detailJobId;if(!jobId)return;if(!confirm("Resetar o cadastro local? Se existir produto remoto, a operação será bloqueada por segurança."))return;try{await post("/adicoes/resetar",{job_id:jobId});toast("Cadastro resetado.");closeDetail();await operation("/adicoes/operacoes/sincronizar",{});}catch(error){toast(error.message,"error");}}

  async function backgroundSyncOnce(){try{const result=await post("/adicoes/operacoes/sincronizar",{});if((result.created||0)||(result.changed||0)||(result.deactivated||0)){log(`Sincronização: ${result.created||0} novo(s), ${result.changed||0} alterado(s), ${result.deactivated||0} removido(s) da aprovação.`);await refreshAll({silent:true});}}catch(error){log(`Sincronização em segundo plano falhou: ${error.message}`,"AVISO");}}
  async function poll(){if(state.polling||document.hidden||!panelVisible())return;state.polling=true;try{await Promise.all([loadOverview(),loadScope("preparation",{silent:true}),loadScope("queue",{silent:true})]);}finally{state.polling=false;}}
  function boot(){if(state.started)return;state.started=true;installUi();if(!$("#addition_operational_root"))return;if(panelVisible())refreshAll();setTimeout(backgroundSyncOnce,350);setInterval(poll,3000);}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();
