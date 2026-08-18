(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), clean=v=>String(v??"").replace(/\s+/g," ").trim();
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const money=v=>{const n=Number(String(v??"").replace(',','.'));return Number.isFinite(n)?n.toLocaleString('pt-BR',{style:'currency',currency:'BRL'}):'—';};

  async function getRows(){
    const r=await fetch('/loja/pacotes/precos',{cache:'no-store',credentials:'same-origin'});
    const d=await r.json().catch(()=>({}));
    if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);
    return Array.isArray(d.products)?d.products:[];
  }

  async function saveRow(row,button,status){
    const productId=Number(row.dataset.productId||0),variationId=Number(row.dataset.variationId||0);
    const regular=$('[data-pack-regular]',row)?.value||'', sale=$('[data-pack-sale]',row)?.value||'';
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
    return `<tr data-pack-custom-row data-product-id="${id}" data-variation-id="${variationId}"><td><strong>${esc(item.product_name||`Produto #${id}`)}</strong><div class="small">WooCommerce #${id}${variationId?` · variação #${variationId}`:''}</div></td><td>${esc(item.product_type||'—')}</td><td><strong>${esc(item.variation||'Produto')}</strong></td><td>${money(item.last_price)}</td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-pack-regular inputmode="decimal" value="${esc(item.regular_price||'')}"></td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-pack-sale inputmode="decimal" value="${esc(item.sale_price||'')}" placeholder="Sem promoção"></td><td><button class="btn-success btn-sm" style="width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap;padding-left:6px;padding-right:6px" type="button" data-pack-save>Salvar preços</button></td></tr>`;
  }

  function packCard(root){
    return root.closest('.card')||root.parentElement;
  }

  function renameSection(root){
    const card=packCard(root);
    const title=card?.querySelector('.section-title');
    if(title)title.textContent='Preços de pacotes';
    if(card){
      card.style.minWidth='0';
      card.style.maxWidth='100%';
      card.style.boxSizing='border-box';
      card.style.overflow='visible';
    }
  }

  function ensureGlobalFooter(root){
    const card=packCard(root);
    if(!card)return {button:null,status:null};
    let footer=document.getElementById('store_pack_global_footer');
    if(!footer){
      footer=document.createElement('div');
      footer.id='store_pack_global_footer';
      footer.style.cssText='display:block;width:100%;max-width:100%;box-sizing:border-box;padding:14px 12px 4px;clear:both;overflow:visible;';
      card.appendChild(footer);
    }else if(footer.parentElement!==card){
      card.appendChild(footer);
    }
    footer.innerHTML='<button class="btn-success" type="button" id="store_pack_save_all" style="display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap">Salvar preços</button><div id="store_pack_global_status" class="small" style="margin-top:10px"></div>';
    return {button:$('#store_pack_save_all',footer),status:$('#store_pack_global_status',footer)};
  }

  function bindActions(root){
    const footer=ensureGlobalFooter(root);
    const status=footer.status;
    root.querySelectorAll('[data-pack-save]').forEach(btn=>{
      btn.addEventListener('click',()=>saveRow(btn.closest('[data-pack-custom-row]'),btn,status));
    });
    footer.button?.addEventListener('click',async event=>{
      const button=event.currentTarget;
      const rows=[...root.querySelectorAll('[data-pack-custom-row]')];
      button.disabled=true;
      const old=button.textContent;
      let ok=0;
      try{
        for(let i=0;i<rows.length;i++){
          button.textContent=`Salvando ${i+1}/${rows.length}...`;
          const row=rows[i], rowButton=$('[data-pack-save]',row);
          if(await saveRow(row,rowButton,status))ok++;
        }
        status.textContent=`${ok} de ${rows.length} linha(s) de pacotes salvas.`;
      }finally{
        button.disabled=false;
        button.textContent=old;
      }
    });
  }

  let busy=false;
  async function refresh(){
    if(busy)return;
    const root=$('#store_pack_prices');
    if(!root)return;
    busy=true;
    root.style.width='100%';
    root.style.maxWidth='100%';
    root.style.minWidth='0';
    root.style.boxSizing='border-box';
    renameSection(root);
    try{
      const rows=await getRows();
      root.innerHTML=`<div class="table-wrap" style="width:100%;max-width:100%;overflow-x:hidden;box-sizing:border-box"><table class="catalogos-table" style="width:100%;max-width:100%;min-width:0;table-layout:fixed"><colgroup><col style="width:23%"><col style="width:7%"><col style="width:8%"><col style="width:10%"><col style="width:18%"><col style="width:19%"><col style="width:15%"></colgroup><thead><tr><th>Produto</th><th>Tipo</th><th>Variação</th><th>Último preço</th><th>Preço original</th><th>Preço promocional</th><th>Ação</th></tr></thead><tbody>${rows.map(rowHtml).join('')||'<tr><td colspan="7" class="small">Nenhum pacote encontrado.</td></tr>'}</tbody></table></div>`;
      bindActions(root);
    }catch(error){
      root.innerHTML=`<div class="notice is-danger">Não foi possível carregar os pacotes: ${esc(error.message)}</div>`;
      ensureGlobalFooter(root);
    }finally{
      busy=false;
    }
  }

  const start=()=>{
    refresh();
    setTimeout(refresh,1200);
    setTimeout(refresh,3000);
    $('#store_pack_refresh')?.addEventListener('click',()=>setTimeout(refresh,0));
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
