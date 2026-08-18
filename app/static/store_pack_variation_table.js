(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const money=v=>{const n=Number(String(v??"").replace(',','.'));return Number.isFinite(n)?n.toLocaleString('pt-BR',{style:'currency',currency:'BRL'}):'—';};
  const ACCORDION_KEY='crapscraper:store-prices-open:v1';

  function installStyles(){
    if($('#store_prices_accordion_style'))return;
    const style=document.createElement('style');
    style.id='store_prices_accordion_style';
    style.textContent=`
      #store_prices_accordion{width:100%;max-width:100%;box-sizing:border-box;overflow:visible}
      #store_prices_accordion>summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:18px;cursor:pointer;user-select:none;padding:4px 2px}
      #store_prices_accordion>summary::-webkit-details-marker{display:none}
      #store_prices_accordion>summary::marker{content:""}
      #store_prices_accordion .store-prices-accordion-heading{display:flex;flex-direction:column;gap:4px;min-width:0}
      #store_prices_accordion .store-prices-accordion-toggle{display:inline-flex;align-items:center;justify-content:center;font-size:16px;line-height:1;transition:transform .16s ease;transform:rotate(0deg)}
      #store_prices_accordion[open] .store-prices-accordion-toggle{transform:rotate(90deg)}
      #store_prices_accordion .store-prices-accordion-content{display:grid;gap:18px;margin-top:16px}
      #store_prices_accordion .store-price-subcard{width:100%;max-width:100%;min-width:0;box-sizing:border-box;margin:0}
      #store_prices_accordion .store-price-subcard>.section-title,
      #store_prices_accordion .store-price-subcard .store-section-head .section-title{font-size:17px}
      #store_plan_prices,#store_pack_prices{width:100%;max-width:100%;min-width:0;box-sizing:border-box}
      #store_prices_accordion .store-price-table-wrap{width:100%;max-width:100%;overflow-x:hidden;box-sizing:border-box}
      #store_prices_accordion .store-price-table-wrap table{width:100%;max-width:100%;min-width:0;table-layout:fixed}
      #store_prices_accordion .store-price-global-footer{display:block;width:100%;max-width:100%;box-sizing:border-box;padding:14px 12px 4px;clear:both;overflow:visible}
      #store_prices_accordion .store-price-global-footer .btn-success{display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap}
      @media(max-width:900px){#store_prices_accordion .store-price-table-wrap{overflow-x:auto}#store_prices_accordion .store-price-table-wrap table{min-width:900px}}
    `;
    document.head.appendChild(style);
  }

  async function getRows(){
    const r=await fetch('/loja/pacotes/precos',{cache:'no-store',credentials:'same-origin'});
    const d=await r.json().catch(()=>({}));
    if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);
    return Array.isArray(d.products)?d.products:[];
  }

  async function saveRow(row,button,status){
    const productId=Number(row.dataset.productId||0),variationId=Number(row.dataset.variationId||0);
    const regular=$('[data-price-regular]',row)?.value||'', sale=$('[data-price-sale]',row)?.value||'';
    button.disabled=true;
    const old=button.textContent;
    button.textContent='Salvando...';
    try{
      const r=await fetch('/loja/pacotes/precos',{
        method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({product_id:productId,variation_id:variationId,regular_price:regular,sale_price:sale})
      });
      const d=await r.json().catch(()=>({}));
      if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);
      status.textContent=d?.message||'Preço salvo.';
      return true;
    }catch(error){
      status.textContent=`Falha: ${error.message}`;
      return false;
    }finally{
      button.disabled=false;
      button.textContent=old;
    }
  }

  function rowHtml(item){
    const id=Number(item.product_id||0), variationId=Number(item.variation_id||0);
    return `<tr data-store-price-row data-product-id="${id}" data-variation-id="${variationId}"><td><strong>${esc(item.product_name||`Produto #${id}`)}</strong><div class="small">WooCommerce #${id}${variationId?` · variação #${variationId}`:''}</div></td><td>${esc(item.product_type||'—')}</td><td><strong>${esc(item.variation||'Produto')}</strong></td><td>${money(item.last_price)}</td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-price-regular inputmode="decimal" value="${esc(item.regular_price||'')}"></td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-price-sale inputmode="decimal" value="${esc(item.sale_price||'')}" placeholder="Sem promoção"></td><td><button class="btn-success btn-sm" style="width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap;padding-left:6px;padding-right:6px" type="button" data-price-save>Salvar preços</button></td></tr>`;
  }

  function tableHtml(rows,emptyMessage){
    return `<div class="store-price-table-wrap"><table class="catalogos-table"><colgroup><col style="width:23%"><col style="width:8%"><col style="width:10%"><col style="width:10%"><col style="width:17%"><col style="width:18%"><col style="width:14%"></colgroup><thead><tr><th>Produto</th><th>Tipo</th><th>Variação</th><th>Último preço</th><th>Preço original</th><th>Preço promocional</th><th>Ação</th></tr></thead><tbody>${rows.map(rowHtml).join('')||`<tr><td colspan="7" class="small">${esc(emptyMessage)}</td></tr>`}</tbody></table></div>`;
  }

  function ensurePlanCard(){
    let card=$('#store_plan_card');
    if(card)return card;
    card=document.createElement('section');
    card.id='store_plan_card';
    card.className='card store-plan-card store-price-subcard';
    card.setAttribute('aria-labelledby','store_plan_title');
    card.innerHTML=`<div class="store-section-head"><div><div class="section-title" id="store_plan_title">Preços dos planos</div><div class="small">Edite os preços dos produtos de planos e de suas variações cadastradas no WooCommerce.</div></div><button class="btn-secondary btn-sm" id="store_plan_refresh" type="button">Atualizar lista</button></div><div class="store-table-wrap" id="store_plan_prices" aria-live="polite" aria-busy="true"><span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando planos…</span></span></div>`;
    return card;
  }

  function ensureAccordion(){
    installStyles();
    const hero=$('#tab_panel_loja .store-hero');
    const categoryCard=$('#store_pricing_form');
    const packRoot=$('#store_pack_prices');
    const packCard=packRoot?.closest('.store-pack-card')||packRoot?.closest('.card');
    if(!categoryCard||!packCard)return null;

    let accordion=$('#store_prices_accordion');
    if(!accordion){
      accordion=document.createElement('details');
      accordion.id='store_prices_accordion';
      accordion.className='card store-prices-accordion';
      let open=true;
      try{const saved=localStorage.getItem(ACCORDION_KEY);if(saved!==null)open=saved==='1';}catch(_error){}
      if(open)accordion.open=true;
      accordion.innerHTML=`<summary aria-controls="store_prices_accordion_content"><div class="store-prices-accordion-heading"><div class="section-title">Preços da loja</div><div class="small">Plugins e temas, pacotes e planos em um único painel.</div></div><span class="store-prices-accordion-toggle" aria-hidden="true">›</span></summary><div class="store-prices-accordion-content" id="store_prices_accordion_content"></div>`;
      (hero||categoryCard).before(accordion);
      accordion.addEventListener('toggle',()=>{try{localStorage.setItem(ACCORDION_KEY,accordion.open?'1':'0');}catch(_error){}});
    }
    if(hero)hero.style.display='none';

    const content=$('#store_prices_accordion_content',accordion);
    categoryCard.classList.add('store-price-subcard');
    packCard.classList.add('store-price-subcard');
    const categoryTitle=$('.section-title',categoryCard);
    if(categoryTitle&&/Preços de Plugins e Temas/i.test(categoryTitle.textContent||''))categoryTitle.textContent='Preços de Plugins e Temas';
    const packTitle=$('#store_pack_title',packCard)||$('.section-title',packCard);
    if(packTitle)packTitle.textContent='Preços de pacotes';

    if(categoryCard.parentElement!==content)content.appendChild(categoryCard);
    if(packCard.parentElement!==content)content.appendChild(packCard);
    const planCard=ensurePlanCard();
    if(planCard.parentElement!==content)content.appendChild(planCard);
    return accordion;
  }

  function ensureGlobalFooter(root,key){
    const card=root?.closest('.card');
    if(!card)return {button:null,status:null};
    const footerId=`store_${key}_global_footer`, buttonId=`store_${key}_save_all`, statusId=`store_${key}_global_status`;
    let footer=document.getElementById(footerId);
    if(!footer){
      footer=document.createElement('div');
      footer.id=footerId;
      footer.className='store-price-global-footer';
      card.appendChild(footer);
    }else if(footer.parentElement!==card){card.appendChild(footer);}
    footer.innerHTML=`<button class="btn-success" type="button" id="${buttonId}">Salvar preços</button><div id="${statusId}" class="small" style="margin-top:10px"></div>`;
    return {button:$('#'+buttonId,footer),status:$('#'+statusId,footer)};
  }

  function bindActions(root,key){
    const footer=ensureGlobalFooter(root,key),status=footer.status;
    root.querySelectorAll('[data-price-save]').forEach(btn=>btn.addEventListener('click',()=>saveRow(btn.closest('[data-store-price-row]'),btn,status)));
    const rows=[...root.querySelectorAll('[data-store-price-row]')];
    if(footer.button)footer.button.disabled=rows.length===0;
    footer.button?.addEventListener('click',async event=>{
      const button=event.currentTarget, old=button.textContent;
      button.disabled=true;
      let ok=0;
      try{
        for(let i=0;i<rows.length;i++){
          button.textContent=`Salvando ${i+1}/${rows.length}...`;
          const row=rows[i], rowButton=$('[data-price-save]',row);
          if(await saveRow(row,rowButton,status))ok++;
        }
        status.textContent=`${ok} de ${rows.length} linha(s) salvas.`;
      }finally{button.disabled=false;button.textContent=old;}
    });
  }

  function renderGroup(root,rows,key,emptyMessage){
    root.style.width='100%';root.style.maxWidth='100%';root.style.minWidth='0';root.style.boxSizing='border-box';
    root.innerHTML=tableHtml(rows,emptyMessage);
    root.setAttribute('aria-busy','false');
    bindActions(root,key);
  }

  let busy=false;
  async function refresh(){
    if(busy)return;
    const accordion=ensureAccordion();
    const packRoot=$('#store_pack_prices'), planRoot=$('#store_plan_prices');
    if(!accordion||!packRoot||!planRoot)return;
    busy=true;
    packRoot.setAttribute('aria-busy','true');planRoot.setAttribute('aria-busy','true');
    packRoot.innerHTML='<span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando pacotes…</span></span>';
    planRoot.innerHTML='<span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando planos…</span></span>';
    try{
      const rows=await getRows();
      const packs=rows.filter(item=>String(item.pricing_group||'pack')!=='plan');
      const plans=rows.filter(item=>String(item.pricing_group||'')==='plan');
      renderGroup(packRoot,packs,'pack','Nenhum pacote encontrado.');
      renderGroup(planRoot,plans,'plan','Nenhum plano encontrado. O painel reconhece produtos da categoria Plano/Planos/Assinaturas e tipos de assinatura do WooCommerce.');
    }catch(error){
      packRoot.innerHTML=`<div class="notice is-danger">Não foi possível carregar os preços: ${esc(error.message)}</div>`;
      planRoot.innerHTML=`<div class="notice is-danger">Não foi possível carregar os planos: ${esc(error.message)}</div>`;
      ensureGlobalFooter(packRoot,'pack');ensureGlobalFooter(planRoot,'plan');
    }finally{busy=false;}
  }

  const start=()=>{
    ensureAccordion();
    refresh();
    setTimeout(()=>{ensureAccordion();refresh();},800);
    setTimeout(()=>{ensureAccordion();refresh();},2200);
    document.addEventListener('click',event=>{
      if(event.target.closest?.('#store_pack_refresh,#store_plan_refresh'))setTimeout(refresh,0);
    });
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
