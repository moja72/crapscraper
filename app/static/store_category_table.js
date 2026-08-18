(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  const clean=v=>String(v??"").replace(/\s+/g," ").trim();
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  function legacyCard(){
    const action=$$('button').find(b=>/Aplicar preços em lote/i.test(clean(b.textContent)));
    return action?.closest('.card')||null;
  }
  async function loadCurrent(){
    const r=await fetch('/loja/precos?tipo=plugin&tipo=theme',{cache:'no-store',credentials:'same-origin'});
    const d=await r.json().catch(()=>({}));
    if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);
    return d;
  }
  function currentFromSummary(summary,period){
    const rows=Array.isArray(summary?.distribution?.[period])?summary.distribution[period]:[];
    const first=rows[0]||{};
    return {regular:clean(first.regular_price),sale:clean(first.sale_price),count:Number(first.count||0)};
  }
  async function waitJob(jobId,status){
    const started=Date.now();
    while(Date.now()-started<60*60*1000){
      const r=await fetch('/loja/precos/status',{cache:'no-store',credentials:'same-origin'});
      const d=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(d?.message||`HTTP ${r.status}`);
      if(jobId&&d.job_id&&d.job_id!==jobId){await sleep(500);continue;}
      status.textContent=d.message||'Atualizando preços...';
      if(d.status==='completed')return d;
      if(d.status==='error')throw new Error(d.message||d.error||'Falha ao atualizar preços.');
      await sleep(700);
    }
    throw new Error('A atualização excedeu 60 minutos.');
  }
  async function postPrices(payload,status){
    const response=await fetch('/loja/precos',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok||data?.ok===false)throw new Error(data?.message||data?.error||`HTTP ${response.status}`);
    return waitJob(data.job_id,status);
  }
  function values(box,kind){
    const val=(period,field)=>$(`[data-store-kind="${kind}"][data-store-period="${period}"][data-store-field="${field}"]`,box)?.value||'';
    return {kinds:[kind],annual_regular:val('annual','regular'),annual_sale:val('annual','sale'),lifetime_regular:val('lifetime','regular'),lifetime_sale:val('lifetime','sale'),confirmation:'ALTERAR PRECOS'};
  }
  async function saveKind(box,kind,status,button){
    const old=button.textContent;
    button.disabled=true;
    button.textContent='Salvando...';
    try{
      const result=await postPrices(values(box,kind),status);
      status.textContent=result.message||`${kind==='plugin'?'Plugins':'Temas'}: preços atualizados.`;
      return true;
    }catch(error){
      status.textContent=`Falha: ${error.message}`;
      return false;
    }finally{
      button.disabled=false;
      button.textContent=old;
    }
  }
  function render(box,payload){
    const data={
      plugin:{label:'Plugins',annual:currentFromSummary(payload?.by_kind?.plugin,'annual'),lifetime:currentFromSummary(payload?.by_kind?.plugin,'lifetime')},
      theme:{label:'Temas',annual:currentFromSummary(payload?.by_kind?.theme,'annual'),lifetime:currentFromSummary(payload?.by_kind?.theme,'lifetime')},
    };
    box.style.width='100%';
    box.style.maxWidth='100%';
    box.style.minWidth='0';
    box.style.boxSizing='border-box';
    box.innerHTML=`<div class="section-title">Preços de Plugins e Temas</div><div class="small" style="margin:6px 0 14px">Edite por categoria e variação. Os valores atuais são lidos diretamente do WooCommerce.</div><div class="table-wrap" style="width:100%;max-width:100%;overflow-x:hidden;box-sizing:border-box"><table class="catalogos-table" style="width:100%;max-width:100%;min-width:0;table-layout:fixed"><colgroup><col style="width:9%"><col style="width:8%"><col style="width:14%"><col style="width:16%"><col style="width:20%"><col style="width:20%"><col style="width:13%"></colgroup><thead><tr><th>Categoria</th><th>Variação</th><th>Preço atual original</th><th>Preço atual promocional</th><th>Novo original</th><th>Novo promocional</th><th>Ação</th></tr></thead><tbody></tbody></table></div><div style="width:100%;max-width:100%;box-sizing:border-box;margin-top:14px;padding:0 12px 4px"><button class="btn-success" type="button" id="store_category_save_all" style="display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap">Salvar preços</button></div><div id="store_category_pricing_status" class="small" style="margin-top:10px;padding:0 12px;box-sizing:border-box"></div>`;
    const tbody=$('tbody',box);
    for(const kind of ['plugin','theme'])for(const period of ['annual','lifetime']){
      const item=data[kind],cur=item[period],periodLabel=period==='annual'?'Anual':'Vitalício';
      const tr=document.createElement('tr');
      tr.innerHTML=`<td><strong>${item.label}</strong></td><td>${periodLabel}</td><td>${cur.regular?`R$ ${esc(cur.regular)}`:'—'}</td><td>${cur.sale?`R$ ${esc(cur.sale)}`:'Sem promoção'}</td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-store-kind="${kind}" data-store-period="${period}" data-store-field="regular" inputmode="decimal" value="${esc(cur.regular)}"></td><td><input style="width:100%;max-width:100%;min-width:0;box-sizing:border-box" data-store-kind="${kind}" data-store-period="${period}" data-store-field="sale" inputmode="decimal" value="${esc(cur.sale)}"></td><td><button class="btn-success btn-sm" style="width:100%;max-width:100%;min-width:0;box-sizing:border-box;white-space:nowrap;padding-left:6px;padding-right:6px" type="button" data-store-save="${kind}">Salvar preços</button></td>`;
      tbody.appendChild(tr);
    }
    const status=$('#store_category_pricing_status',box);
    box.querySelectorAll('[data-store-save]').forEach(btn=>btn.addEventListener('click',()=>saveKind(box,btn.dataset.storeSave,status,btn)));
    $('#store_category_save_all',box)?.addEventListener('click',async event=>{
      const btn=event.currentTarget;btn.disabled=true;const old=btn.textContent;
      try{
        btn.textContent='Salvando Plugins...';await postPrices(values(box,'plugin'),status);
        btn.textContent='Salvando Temas...';const result=await postPrices(values(box,'theme'),status);
        status.textContent=result.message||'Preços de Plugins e Temas atualizados.';
      }catch(error){status.textContent=`Falha: ${error.message}`;}
      finally{btn.disabled=false;btn.textContent=old;}
    });
  }
  let installing=false;
  async function install(){
    const card=legacyCard(); if(!card||installing)return;
    card.style.minWidth='0';
    card.style.maxWidth='100%';
    card.style.boxSizing='border-box';
    let box=$('#store_category_pricing_table');
    if(!box){box=document.createElement('div');box.id='store_category_pricing_table';card.prepend(box);[...card.children].forEach(n=>{if(n!==box)n.style.display='none'});}
    installing=true;box.innerHTML='<div class="small">Carregando preços atuais do WooCommerce...</div>';
    try{render(box,await loadCurrent());}
    catch(error){box.innerHTML=`<div class="notice is-danger">Não foi possível carregar os preços atuais: ${esc(error.message)}</div><button type="button" class="btn-secondary btn-sm" id="store_category_retry">Tentar novamente</button>`;$('#store_category_retry',box)?.addEventListener('click',install,{once:true});}
    finally{installing=false;}
  }
  const start=()=>{install();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
