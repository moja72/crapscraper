(() => {
  "use strict";

  const ENDPOINT = "/loja/produtos/campos-ausentes";
  const state = {
    products: [], filtered: [], page: 1, pageSize: 5, examined: 0,
    status: "idle", resultFilter: "", query: "", pollTimer: null,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  function injectStyles() {
    if ($("#store_quality_unified_styles")) return;
    const style = document.createElement("style");
    style.id = "store_quality_unified_styles";
    style.textContent = `
      .store-quality-controls{display:grid;grid-template-columns:minmax(240px,1fr) 210px 220px 280px auto;gap:10px;align-items:end}
      .store-quality-controls label{display:grid;gap:6px;font-size:12px;font-weight:700}
      .store-quality-checks{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
      .store-quality-check{display:inline-flex;align-items:center;gap:8px;padding:9px 11px;border:1px solid var(--line,#2a2f3a);border-radius:12px;background:rgba(255,255,255,.02);font-size:12px;font-weight:700}
      .store-quality-check input{width:auto;margin:0}
      .store-quality-note{margin-top:8px;color:var(--text-muted,#9aa3b2);font-size:11px}
      .store-quality-results-toolbar{display:flex;flex-wrap:wrap;align-items:end;justify-content:space-between;gap:10px;margin:14px 0 10px}
      .store-quality-results-filters{display:flex;flex-wrap:wrap;gap:10px;align-items:end}
      .store-quality-results-filters label{display:grid;gap:5px;font-size:11px;font-weight:700;color:var(--text-muted,#9aa3b2)}
      .store-quality-results-filters select{min-width:150px}
      .store-quality-state{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;border-radius:999px;border:1px solid var(--line,#2a2f3a);font-size:11px;font-weight:800}
      .store-quality-state.is-ok{border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.10);color:#6ee7b7}
      .store-quality-state.is-missing{border-color:rgba(245,158,11,.35);background:rgba(245,158,11,.10);color:#fcd34d}
      .store-quality-state.is-info{border-color:rgba(59,130,246,.35);background:rgba(59,130,246,.10);color:#93c5fd}
      .store-quality-value{display:block;margin-top:5px;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:var(--text-muted,#9aa3b2)}
      .store-quality-value a{text-decoration:underline;text-underline-offset:2px}
      .store-quality-pending{display:flex;flex-wrap:wrap;gap:6px}
      .store-quality-pagination{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;margin-top:12px}
      .store-quality-progress{display:flex;align-items:center;gap:9px;padding:12px;border:1px solid var(--line,#2a2f3a);border-radius:12px;background:rgba(255,255,255,.018)}
      .store-price-inner-accordion{width:100%;box-sizing:border-box}
      .store-price-inner-accordion>summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:18px;cursor:pointer;user-select:none;padding:2px 0}
      .store-price-inner-accordion>summary::-webkit-details-marker{display:none}
      .store-price-inner-accordion>summary::marker{content:""}
      .store-price-inner-heading{display:flex;flex-direction:column;gap:4px;min-width:0}
      .store-price-inner-toggle{display:inline-flex;align-items:center;justify-content:center;font-size:16px;line-height:1;transition:transform .16s ease;transform:rotate(0deg)}
      .store-price-inner-accordion[open] .store-price-inner-toggle{transform:rotate(90deg)}
      .store-price-inner-body{margin-top:16px;min-width:0}
      @media(max-width:1200px){.store-quality-controls{grid-template-columns:1fr 1fr}.store-quality-controls button{grid-column:1/-1}}
      @media(max-width:900px){.store-quality-controls{grid-template-columns:1fr}.store-quality-results-toolbar{align-items:stretch}.store-quality-results-filters{width:100%}}
    `;
    document.head.appendChild(style);
  }

  function cardHtml() {
    return `
      <section class="card store-quality-card" id="store_custom_fields_quality_card" aria-labelledby="store_quality_unified_title">
        <div class="store-section-head">
          <div>
            <div class="section-title" id="store_quality_unified_title">Qualidade dos produtos</div>
            <div class="small">Audite versão, desenvolvedor, link oficial e breve descrição em Plugins e Temas variáveis com variações filhas. A busca por nome ou ID consulta o WooCommerce diretamente e também mostra produtos sem nenhuma pendência.</div>
          </div>
        </div>
        <form class="store-quality-filter" id="store_quality_unified_form">
          <div class="store-quality-controls">
            <label for="store_quality_search">Buscar por nome ou WooCommerce ID
              <input id="store_quality_search" type="search" autocomplete="off" placeholder="Ex.: Elementor ou 92038">
            </label>
            <label for="store_quality_match_mode">Condição dos campos
              <select id="store_quality_match_mode">
                <option value="any">Qualquer campo selecionado ausente</option>
                <option value="all">Todos os campos selecionados ausentes</option>
              </select>
            </label>
            <label for="store_quality_category_mode">Categorias
              <select id="store_quality_category_mode">
                <option value="all">Todos os Plugins e Temas</option>
                <option value="root_only">Somente categoria raiz Plugin/Tema</option>
              </select>
            </label>
            <label for="store_quality_variation_mode">Variações filhas
              <select id="store_quality_variation_mode">
                <option value="all">Todas</option>
                <option value="nonstandard">Com termo fora de 1 ano / Vitalício / Gratuito</option>
                <option value="none_standard">Sem nenhum termo 1 ano / Vitalício / Gratuito</option>
              </select>
            </label>
            <button class="btn-secondary" id="store_quality_submit" type="submit">Pesquisar / verificar</button>
          </div>
          <div class="store-quality-checks" role="group" aria-label="Campos a verificar">
            <label class="store-quality-check"><input type="checkbox" value="version" checked> Versão</label>
            <label class="store-quality-check"><input type="checkbox" value="developer" checked> Desenvolvedor</label>
            <label class="store-quality-check"><input type="checkbox" value="official" checked> Link oficial</label>
            <label class="store-quality-check"><input type="checkbox" value="description" checked> Breve descrição</label>
          </div>
          <div class="store-quality-note">Sem busca, a ferramenta lista somente produtos com as pendências selecionadas. Ao informar um nome ou ID, o produto aparece mesmo se todos os campos estiverem preenchidos.</div>
        </form>
        <div class="store-table-wrap" id="store_quality_results" aria-live="polite">
          <div class="small">Pesquise um produto específico ou clique em “Pesquisar / verificar” para auditar o catálogo.</div>
        </div>
      </section>`;
  }

  function mountUnifiedCard() {
    const panel = $("#tab_panel_loja");
    if (!panel) return false;

    const shortCard = $("#store_missing_description_form")?.closest(".card");
    const current = $("#store_custom_fields_quality_card");
    if (current && current.dataset.unifiedQuality === "1") {
      shortCard?.remove();
      return true;
    }

    const holder = document.createElement("div");
    holder.innerHTML = cardHtml().trim();
    const card = holder.firstElementChild;
    card.dataset.unifiedQuality = "1";

    if (current) current.replaceWith(card);
    else if (shortCard) shortCard.after(card);
    else panel.appendChild(card);
    shortCard?.remove();
    bindForm();
    return true;
  }

  function selectedFields() {
    return $$("#store_quality_unified_form input[type='checkbox']:checked").map(node => node.value);
  }

  function fieldLabel(key) {
    return ({version:"Versão",developer:"Desenvolvedor",official:"Link oficial",description:"Breve descrição"})[key] || key;
  }

  function kindLabel(value) {
    return ({plugin:"Plugin",theme:"Tema"})[text(value).toLowerCase()] || text(value) || "—";
  }

  function fieldCell(product, key) {
    const value = text(product?.values?.[key]);
    const missing = Array.isArray(product.missing_fields) && product.missing_fields.includes(key);
    if (missing || !value) return `<span class="store-quality-state is-missing">⚠ Ausente</span>`;

    let visible = esc(value);
    if (key === "official" && /^https?:\/\//i.test(value)) {
      visible = `<a href="${esc(value)}" target="_blank" rel="noopener noreferrer">${esc(value)}</a>`;
    }
    if (key === "description" && value.length > 110) visible = `${esc(value.slice(0,110))}…`;
    return `<span class="store-quality-state is-ok">✓ Preenchido</span><span class="store-quality-value" title="${esc(value)}">${visible}</span>`;
  }

  function structureCell(product) {
    const bits = [];
    if (product.root_category_only) bits.push('<span class="store-quality-state is-info">Só categoria raiz</span>');
    const standard = Array.isArray(product.standard_labels) ? product.standard_labels : [];
    const nonstandard = Number(product.nonstandard_variation_count || 0);
    if (standard.length) bits.push(`<span class="store-quality-value">Padrão: ${esc(standard.join(" · "))}</span>`);
    if (nonstandard) bits.push(`<span class="store-quality-state is-missing">${nonstandard} fora do padrão</span>`);
    bits.push(`<span class="store-quality-value">${Number(product.variation_count || 0)} variação(ões) filha(s)</span>`);
    return bits.join("");
  }

  function rowHtml(product) {
    const id = Number(product.product_id || 0);
    const pending = Array.isArray(product.missing_fields) ? product.missing_fields : [];
    const pendingHtml = pending.length
      ? pending.map(key => `<span class="store-quality-state is-missing">${esc(fieldLabel(key))}</span>`).join("")
      : '<span class="store-quality-state is-ok">✓ Sem pendências</span>';
    return `<tr>
      <td><strong>${esc(product.product_name || `Produto #${id}`)}</strong><span class="small">WooCommerce #${id}</span></td>
      <td>${esc(kindLabel(product.catalog_kind))}</td>
      <td>${fieldCell(product,"version")}</td>
      <td>${fieldCell(product,"developer")}</td>
      <td>${fieldCell(product,"official")}</td>
      <td>${fieldCell(product,"description")}</td>
      <td>${structureCell(product)}</td>
      <td><div class="store-quality-pending">${pendingHtml}</div></td>
      <td>${product.permalink ? `<a class="btn-secondary btn-sm" href="${esc(product.permalink)}" target="_blank" rel="noopener noreferrer">Abrir produto</a>` : "—"}</td>
    </tr>`;
  }

  function applyResultFilter() {
    state.resultFilter = text($("#store_quality_result_filter")?.value);
    state.filtered = state.products.filter(product => {
      const pending = Array.isArray(product.missing_fields) ? product.missing_fields : [];
      if (!state.resultFilter) return true;
      if (state.resultFilter === "complete") return pending.length === 0;
      return pending.includes(state.resultFilter);
    });
    state.page = 1;
    renderResults();
  }

  function renderResults() {
    const root = $("#store_quality_results");
    if (!root || state.status === "running") return;
    const total = state.filtered.length;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));
    state.page = Math.max(1, Math.min(state.page, pages));
    const start = (state.page - 1) * state.pageSize;
    const visible = state.filtered.slice(start, start + state.pageSize);
    const end = total ? Math.min(start + state.pageSize, total) : 0;

    if (!state.products.length) {
      const message = state.query
        ? `Nenhum Plugin/Tema variável com variações filhas foi encontrado para “${esc(state.query)}” com os filtros atuais.`
        : `Auditoria concluída: nenhuma pendência selecionada foi encontrada entre ${Number(state.examined || 0)} Plugins/Temas variáveis.`;
      root.innerHTML = `<div class="notice is-success">${message}</div>`;
      return;
    }

    const summary = state.query
      ? `<strong>${state.products.length}</strong> resultado(s) para <strong>${esc(state.query)}</strong>`
      : `<strong>${state.products.length}</strong> produto(s) com pendências entre <strong>${Number(state.examined || 0)}</strong> Plugins/Temas variáveis verificados`;

    root.innerHTML = `
      <div class="store-quality-count">${summary}</div>
      <div class="store-quality-results-toolbar">
        <div class="store-quality-results-filters">
          <label>Mostrar pendência
            <select id="store_quality_result_filter">
              <option value="" ${!state.resultFilter?"selected":""}>Todas</option>
              <option value="version" ${state.resultFilter==="version"?"selected":""}>Sem versão</option>
              <option value="developer" ${state.resultFilter==="developer"?"selected":""}>Sem desenvolvedor</option>
              <option value="official" ${state.resultFilter==="official"?"selected":""}>Sem link oficial</option>
              <option value="description" ${state.resultFilter==="description"?"selected":""}>Sem breve descrição</option>
              <option value="complete" ${state.resultFilter==="complete"?"selected":""}>Sem pendências</option>
            </select>
          </label>
          <label>Itens por página
            <select id="store_quality_page_size">${[5,10,25,50,100].map(size=>`<option value="${size}" ${state.pageSize===size?"selected":""}>${size}</option>`).join("")}</select>
          </label>
        </div>
        <span class="small">${total ? `Mostrando ${start+1}–${end} de ${total}` : "0 produtos"}</span>
      </div>
      ${total ? `<table class="store-data-table"><thead><tr><th>Produto</th><th>Catálogo</th><th>Versão</th><th>Desenvolvedor</th><th>Link oficial</th><th>Breve descrição</th><th>Estrutura</th><th>Pendências</th><th>Acesso</th></tr></thead><tbody>${visible.map(rowHtml).join("")}</tbody></table>` : '<div class="notice">Nenhum produto corresponde ao filtro selecionado.</div>'}
      <div class="store-quality-pagination"><span class="small">Página ${state.page} de ${pages}</span><div class="row"><button class="btn-secondary btn-sm" id="store_quality_prev" type="button" ${state.page<=1?"disabled":""}>← Anterior</button><button class="btn-secondary btn-sm" id="store_quality_next" type="button" ${state.page>=pages?"disabled":""}>Próxima →</button></div></div>`;

    $("#store_quality_result_filter")?.addEventListener("change", applyResultFilter);
    $("#store_quality_page_size")?.addEventListener("change", event => {state.pageSize=Math.max(1,Math.min(100,Number(event.target.value)||5));state.page=1;renderResults();});
    $("#store_quality_prev")?.addEventListener("click",()=>{state.page-=1;renderResults();});
    $("#store_quality_next")?.addEventListener("click",()=>{state.page+=1;renderResults();});
  }

  function renderProgress(data) {
    const root = $("#store_quality_results");
    if (!root) return;
    root.innerHTML = `<div class="store-quality-progress"><span class="inline-loading-spinner" aria-hidden="true"></span><div><strong>${text(data.phase)==="variations"?"Analisando variações filhas…":(state.query?"Buscando produto…":"Verificando qualidade…")}</strong><div class="small">${esc(data.message||"Consultando WooCommerce…")}</div></div></div>`;
  }

  async function request(method, payload = null) {
    const response = await fetch(ENDPOINT,{method,cache:"no-store",credentials:"same-origin",headers:payload?{"Content-Type":"application/json"}:{},body:payload?JSON.stringify(payload):undefined});
    const data = await response.json().catch(()=>({}));
    if (!response.ok || data.ok===false) throw new Error(data.message||`Falha HTTP ${response.status}`);
    return data;
  }

  function setBusy(busy) {
    const button = $("#store_quality_submit");
    if (!button) return;
    button.disabled = !!busy;
    button.textContent = busy ? "Consultando…" : "Pesquisar / verificar";
  }

  function consume(data) {
    state.status = text(data.status||"idle");
    state.examined = Number(data.examined||0);
    state.query = text(data.query||state.query);
    if (state.status === "running") {setBusy(true);renderProgress(data);schedulePoll();return;}
    setBusy(false);
    if (state.status === "error") {
      const root=$("#store_quality_results");
      if(root)root.innerHTML=`<div class="updates-error" role="alert"><strong>Não foi possível concluir.</strong><br>${esc(data.message||data.error||"Erro desconhecido.")}</div>`;
      return;
    }
    if (state.status === "completed") {
      state.products = Array.isArray(data.products)?data.products:[];
      state.filtered = state.products.slice();
      state.resultFilter="";state.page=1;renderResults();
    }
  }

  function schedulePoll(){window.clearTimeout(state.pollTimer);state.pollTimer=window.setTimeout(poll,700);}
  async function poll(){try{consume(await request("GET"));}catch(error){setBusy(false);const root=$("#store_quality_results");if(root)root.innerHTML=`<div class="updates-error">${esc(error.message)}</div>`;}}

  async function start(event) {
    event?.preventDefault?.();
    const fields = selectedFields();
    if (!fields.length) {window.alert("Selecione pelo menos um campo para verificar.");return;}
    state.query = text($("#store_quality_search")?.value);
    state.products=[];state.filtered=[];state.page=1;setBusy(true);
    try {
      consume(await request("POST",{
        query:state.query,selected_fields:fields,
        match_mode:text($("#store_quality_match_mode")?.value||"any"),
        category_mode:text($("#store_quality_category_mode")?.value||"all"),
        variation_mode:text($("#store_quality_variation_mode")?.value||"all"),
      }));
    } catch(error) {
      setBusy(false);const root=$("#store_quality_results");if(root)root.innerHTML=`<div class="updates-error"><strong>Não foi possível iniciar.</strong><br>${esc(error.message)}</div>`;
    }
  }

  function bindForm(){$("#store_quality_unified_form")?.addEventListener("submit",start);}

  function priceCardSpecs() {
    const category = $("#store_pricing_form");
    const packRoot = $("#store_pack_prices");
    const pack = packRoot?.closest(".store-price-subcard") || packRoot?.closest(".card");
    const plan = $("#store_plan_card");
    return [
      {card:category,key:"plugins-themes",title:"Preços de Plugins e Temas",description:"Edite valores anual e vitalício de Plugins e Temas."},
      {card:pack,key:"packs",title:"Preços de pacotes",description:"Edite os preços dos pacotes e suas variações."},
      {card:plan,key:"plans",title:"Preços dos planos",description:"Edite os preços dos planos e suas variações."},
    ].filter(item=>item.card);
  }

  function foldPriceCard(spec) {
    const card = spec.card;
    let details = $(":scope > details.store-price-inner-accordion",card);
    if (!details) {
      details = document.createElement("details");
      details.className = "store-price-inner-accordion";
      details.dataset.priceSection = spec.key;
      details.innerHTML = `<summary><div class="store-price-inner-heading"><div class="section-title">${esc(spec.title)}</div><div class="small">${esc(spec.description)}</div></div><span class="store-price-inner-toggle" aria-hidden="true">›</span></summary><div class="store-price-inner-body"></div>`;
      const body = $(".store-price-inner-body",details);
      [...card.childNodes].forEach(node=>body.appendChild(node));
      card.appendChild(details);
      details.open = false;
    } else {
      const body = $(".store-price-inner-body",details);
      [...card.childNodes].filter(node=>node!==details).forEach(node=>body.appendChild(node));
    }
  }

  function setupPriceAccordions(){priceCardSpecs().forEach(foldPriceCard);}

  function init() {
    injectStyles();
    mountUnifiedCard();
    setupPriceAccordions();
    const observer = new MutationObserver(()=>{mountUnifiedCard();setupPriceAccordions();});
    const panel = $("#tab_panel_loja") || document.body;
    observer.observe(panel,{childList:true,subtree:true});
    request("GET").then(data=>{if(text(data.status)!=="idle")consume(data);}).catch(()=>{});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded",init,{once:true});
  else init();
})();
