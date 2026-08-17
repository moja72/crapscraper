(() => {
  'use strict';

  const state = { products: [], filtered: [], page: 1, pageSize: 12, loading: false, observer: null };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const esc = value => String(value ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
  const text = value => String(value ?? '').replace(/\s+/g,' ').trim();
  const kindLabel = kind => ({ plugin: 'Plugin', theme: 'Tema', pack: 'Pack' }[kind] || 'Produto');
  const money = value => {
    const raw = text(value).replace(',', '.');
    const number = Number.parseFloat(raw);
    return Number.isFinite(number) ? number.toLocaleString('pt-BR', { style:'currency', currency:'BRL' }) : '—';
  };

  function injectStyles() {
    if ($('#store_unified_pricing_styles')) return;
    const style = document.createElement('style');
    style.id = 'store_unified_pricing_styles';
    style.textContent = `
      .store-unified-heading{margin:26px 0 10px;font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--muted,#93a4b8)}
      .store-unified-card .section-title{font-size:18px}
      .store-unified-toolbar{display:grid;grid-template-columns:minmax(240px,1fr) 190px 140px auto;gap:10px;align-items:end;margin:18px 0}
      .store-unified-toolbar label{display:grid;gap:6px;font-size:12px;font-weight:700}
      .store-unified-toolbar input,.store-unified-toolbar select{width:100%}
      .store-unified-summary{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 16px}
      .store-unified-summary span{padding:7px 10px;border:1px solid var(--line,#2a2f3a);border-radius:999px;font-size:12px;background:rgba(255,255,255,.025)}
      .store-unified-list{display:grid;gap:10px}
      .store-price-row{border:1px solid var(--line,#292e38);border-radius:14px;padding:14px;background:rgba(255,255,255,.015)}
      .store-price-row-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
      .store-price-identity strong{display:block;font-size:14px}.store-price-identity .small{margin-top:4px}
      .store-price-kind{font-size:11px;font-weight:800;padding:5px 8px;border-radius:999px;border:1px solid var(--line,#303641)}
      .store-price-fields{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr)) auto;gap:10px;align-items:end}
      .store-price-fields.is-direct{grid-template-columns:minmax(140px,1fr) minmax(140px,1fr) auto}
      .store-price-fields label{display:grid;gap:5px;font-size:11px;font-weight:700;color:var(--muted,#a4afbf)}
      .store-price-fields input{width:100%;min-width:0}
      .store-price-period-title{grid-column:1/-1;font-size:11px;font-weight:800;color:var(--muted,#9aa6b6);margin-top:2px}
      .store-price-note{font-size:11px;color:#eab308;margin-top:8px}
      .store-price-status{min-height:18px;margin-top:8px;font-size:12px}.store-price-status.is-ok{color:#34d399}.store-price-status.is-error{color:#f87171}
      .store-unified-pagination{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:14px}
      .store-unified-empty{padding:24px;text-align:center;border:1px dashed var(--line,#303641);border-radius:12px;color:var(--muted,#9aa6b6)}
      .store-unified-loading{padding:28px;text-align:center;color:var(--muted,#9aa6b6)}
      @media(max-width:1050px){.store-unified-toolbar{grid-template-columns:1fr 1fr}.store-price-fields,.store-price-fields.is-direct{grid-template-columns:1fr 1fr}.store-price-fields button{grid-column:1/-1}}
    `;
    document.head.appendChild(style);
  }

  function organizeStoreTab() {
    const panel = $('#tab_panel_loja');
    const root = $('#store_pack_prices');
    if (!panel || !root) return null;

    const legacyForm = $('#store_pricing_form');
    const legacyCard = legacyForm?.closest('.card');
    if (legacyCard) legacyCard.style.display = 'none';

    const pricingCard = root.closest('.card');
    if (!pricingCard) return null;
    pricingCard.classList.add('store-unified-card');
    const title = $('.section-title', pricingCard);
    if (title) title.textContent = 'Preços dos produtos';
    const description = $('.small', pricingCard);
    if (description) description.textContent = 'Edite individualmente preços de Plugins, Temas e Packs em um único lugar. As variações anual e vitalícia são preservadas separadamente.';
    const refresh = $('#store_pack_refresh');
    if (refresh) refresh.style.display = 'none';

    const introCandidates = $$('.card', panel).filter(card => {
      const heading = text($('.section-title', card)?.textContent).toLowerCase();
      return heading === 'preços da loja';
    });
    introCandidates.forEach(card => card.style.display = 'none');

    if (!$('#store_commercial_heading')) {
      const heading = document.createElement('div');
      heading.id = 'store_commercial_heading';
      heading.className = 'store-unified-heading';
      heading.textContent = 'Gestão comercial';
      pricingCard.before(heading);
    }

    const shortDescriptionForm = $('#store_missing_description_form');
    const qualityCard = shortDescriptionForm?.closest('.card');
    if (qualityCard && !$('#store_quality_heading')) {
      const heading = document.createElement('div');
      heading.id = 'store_quality_heading';
      heading.className = 'store-unified-heading';
      heading.textContent = 'Qualidade do catálogo';
      qualityCard.before(heading);
    }

    const monitor = $('.wp-manual-monitor', panel);
    if (monitor && !$('#store_integrations_heading')) {
      const heading = document.createElement('div');
      heading.id = 'store_integrations_heading';
      heading.className = 'store-unified-heading';
      heading.textContent = 'Integrações e automações';
      monitor.before(heading);
    }

    if (!$('#store_unified_toolbar')) {
      const toolbar = document.createElement('div');
      toolbar.id = 'store_unified_toolbar';
      toolbar.innerHTML = `
        <div class="store-unified-toolbar">
          <label>Buscar produto<input id="store_unified_search" type="search" placeholder="Nome ou WooCommerce ID"></label>
          <label>Tipo<select id="store_unified_kind"><option value="">Todos</option><option value="plugin">Plugins</option><option value="theme">Temas</option><option value="pack">Packs</option></select></label>
          <label>Itens por página<input id="store_unified_page_size" type="number" min="1" max="100" value="12"></label>
          <button class="btn-secondary" id="store_unified_refresh" type="button">Atualizar lista</button>
        </div>
        <div class="store-unified-summary" id="store_unified_summary"></div>`;
      root.before(toolbar);
      $('#store_unified_search')?.addEventListener('input', () => { state.page = 1; applyFilters(); });
      $('#store_unified_kind')?.addEventListener('change', () => { state.page = 1; applyFilters(); });
      $('#store_unified_page_size')?.addEventListener('change', event => { state.pageSize = Math.max(1, Math.min(100, Number(event.target.value) || 12)); state.page = 1; render(); });
      $('#store_unified_refresh')?.addEventListener('click', () => loadProducts(true));
    }
    return root;
  }

  function summarize() {
    const summary = $('#store_unified_summary');
    if (!summary) return;
    const counts = { plugin:0, theme:0, pack:0 };
    state.products.forEach(item => { if (counts[item.kind] !== undefined) counts[item.kind] += 1; });
    summary.innerHTML = `<span><strong>${state.products.length}</strong> produtos</span><span><strong>${counts.plugin}</strong> plugins</span><span><strong>${counts.theme}</strong> temas</span><span><strong>${counts.pack}</strong> packs</span>`;
  }

  function applyFilters() {
    const query = text($('#store_unified_search')?.value).toLowerCase();
    const kind = text($('#store_unified_kind')?.value);
    state.filtered = state.products.filter(item => {
      const search = `${item.product_name || ''} ${item.product_id || ''}`.toLowerCase();
      return (!kind || item.kind === kind) && (!query || search.includes(query));
    });
    render();
  }

  function field(id, label, value, disabled = false, placeholder = '') {
    return `<label for="${id}">${esc(label)}<input id="${id}" inputmode="decimal" value="${esc(value || '')}" ${disabled ? 'disabled' : ''} placeholder="${esc(placeholder)}"></label>`;
  }

  function rowHtml(product) {
    const id = Number(product.product_id || 0);
    const direct = product.pricing_mode === 'direct';
    const annual = product.annual || {};
    const lifetime = product.lifetime || {};
    const mixed = [annual, lifetime].some(period => period?.mixed);
    const fields = direct
      ? `<div class="store-price-fields is-direct">
          ${field(`sup_regular_${id}`, 'Valor original', product.regular_price, false, 'Ex.: 79,90')}
          ${field(`sup_sale_${id}`, 'Valor promocional', product.sale_price, false, 'Sem promoção')}
          <button class="btn-success" type="button" data-store-unified-save="${id}">Salvar preços</button>
        </div>`
      : `<div class="store-price-fields">
          ${field(`sup_annual_regular_${id}`, 'Anual · original', annual.regular_price, !annual.available, annual.available ? 'Ex.: 79,90' : 'Sem variação anual')}
          ${field(`sup_annual_sale_${id}`, 'Anual · promocional', annual.sale_price, !annual.available, 'Sem promoção')}
          ${field(`sup_lifetime_regular_${id}`, 'Vitalícia · original', lifetime.regular_price, !lifetime.available, lifetime.available ? 'Ex.: 149,90' : 'Sem variação vitalícia')}
          ${field(`sup_lifetime_sale_${id}`, 'Vitalícia · promocional', lifetime.sale_price, !lifetime.available, 'Sem promoção')}
          <button class="btn-success" type="button" data-store-unified-save="${id}">Salvar preços</button>
        </div>`;
    const current = direct
      ? `Preço atual: ${money(product.last_price || product.sale_price || product.regular_price)}`
      : `${annual.available ? `Anual ${money(annual.sale_price || annual.regular_price)}` : 'Sem anual'} · ${lifetime.available ? `Vitalícia ${money(lifetime.sale_price || lifetime.regular_price)}` : 'Sem vitalícia'}`;
    return `<article class="store-price-row" data-store-unified-id="${id}">
      <div class="store-price-row-head"><div class="store-price-identity"><strong>${esc(product.product_name || `Produto #${id}`)}</strong><div class="small">WooCommerce #${id} · ${esc(current)}</div></div><span class="store-price-kind">${esc(kindLabel(product.kind))}</span></div>
      ${fields}
      ${mixed ? '<div class="store-price-note">Este produto possui preços diferentes entre variações do mesmo período. Ao salvar, os valores daquele período serão padronizados.</div>' : ''}
      <div class="store-price-status" role="status"></div>
    </article>`;
  }

  function render() {
    const root = $('#store_pack_prices');
    if (!root || state.loading) return;
    summarize();
    const total = state.filtered.length;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));
    state.page = Math.min(Math.max(1, state.page), pages);
    const start = (state.page - 1) * state.pageSize;
    const visible = state.filtered.slice(start, start + state.pageSize);
    root.innerHTML = `<div class="store-unified-list">${visible.map(rowHtml).join('') || '<div class="store-unified-empty">Nenhum produto corresponde aos filtros.</div>'}</div>
      <div class="store-unified-pagination"><span class="small">${total ? `Mostrando ${start + 1}–${Math.min(start + state.pageSize, total)} de ${total}` : '0 produtos'}</span><div class="row"><button class="btn-secondary" id="store_unified_prev" type="button" ${state.page <= 1 ? 'disabled' : ''}>← Anterior</button><span class="badge">Página ${state.page} de ${pages}</span><button class="btn-secondary" id="store_unified_next" type="button" ${state.page >= pages ? 'disabled' : ''}>Próxima →</button></div></div>`;
    $('#store_unified_prev')?.addEventListener('click', () => { state.page -= 1; render(); });
    $('#store_unified_next')?.addEventListener('click', () => { state.page += 1; render(); });
    $$('[data-store-unified-save]', root).forEach(button => button.addEventListener('click', () => saveProduct(Number(button.dataset.storeUnifiedSave))));
  }

  async function request(url, options = {}) {
    const response = await fetch(url, { cache:'no-store', headers:{ 'Content-Type':'application/json', ...(options.headers || {}) }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) throw new Error(data.message || `Falha HTTP ${response.status}`);
    return data;
  }

  async function loadProducts(force = false) {
    const root = organizeStoreTab();
    if (!root || state.loading) return;
    state.loading = true;
    root.innerHTML = '<div class="store-unified-loading"><span class="inline-loading-spinner" aria-hidden="true"></span> Carregando Plugins, Temas, Packs e suas variações de preço...</div>';
    try {
      const data = await request(`/loja/pacotes/precos${force ? `?refresh=${Date.now()}` : ''}`);
      state.products = Array.isArray(data.products) ? data.products : [];
      state.filtered = state.products.slice();
      applyFilters();
    } catch (error) {
      root.innerHTML = `<div class="updates-error" role="alert"><strong>Não foi possível carregar os preços.</strong><br>${esc(error.message)}</div>`;
    } finally {
      state.loading = false;
      if (state.products.length) applyFilters();
    }
  }

  async function saveProduct(productId) {
    const product = state.products.find(item => Number(item.product_id) === productId);
    const row = $(`[data-store-unified-id="${productId}"]`);
    const button = $(`[data-store-unified-save="${productId}"]`, row || document);
    const status = $('.store-price-status', row || document);
    if (!product || !row || !button) return;
    const payload = { product_id: productId, pricing_mode: product.pricing_mode };
    if (product.pricing_mode === 'direct') {
      payload.regular_price = $(`#sup_regular_${productId}`)?.value || '';
      payload.sale_price = $(`#sup_sale_${productId}`)?.value || '';
    } else {
      payload.annual_regular = $(`#sup_annual_regular_${productId}`)?.value || '';
      payload.annual_sale = $(`#sup_annual_sale_${productId}`)?.value || '';
      payload.lifetime_regular = $(`#sup_lifetime_regular_${productId}`)?.value || '';
      payload.lifetime_sale = $(`#sup_lifetime_sale_${productId}`)?.value || '';
    }
    button.disabled = true;
    button.textContent = 'Salvando...';
    if (status) { status.className = 'store-price-status'; status.textContent = 'Atualizando WooCommerce...'; }
    try {
      const result = await request('/loja/pacotes/precos', { method:'POST', body:JSON.stringify(payload) });
      if (status) { status.className = 'store-price-status is-ok'; status.textContent = result.message || 'Preços atualizados.'; }
      window.setTimeout(() => loadProducts(true), 700);
    } catch (error) {
      if (status) { status.className = 'store-price-status is-error'; status.textContent = error.message; }
    } finally {
      button.disabled = false;
      button.textContent = 'Salvar preços';
    }
  }

  function watchLegacyRenderer() {
    const root = $('#store_pack_prices');
    if (!root || state.observer) return;
    let timer = null;
    state.observer = new MutationObserver(() => {
      if (state.loading || !state.products.length) return;
      clearTimeout(timer);
      timer = setTimeout(() => {
        const hasUnified = !!$('.store-unified-list', root);
        if (!hasUnified) render();
      }, 50);
    });
    state.observer.observe(root, { childList:true, subtree:false });
  }

  function init() {
    injectStyles();
    organizeStoreTab();
    watchLegacyRenderer();
    const lojaButton = $('#tab_loja') || $('[data-tab="loja"]') || $('[aria-controls="tab_panel_loja"]');
    lojaButton?.addEventListener('click', () => window.setTimeout(() => loadProducts(false), 120));
    if (!$('#tab_panel_loja')?.classList.contains('hidden')) loadProducts(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once:true });
  else init();
})();
