(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  const clean=v=>String(v??"").replace(/\s+/g," ").trim();
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");

  function legacyCard(){
    const action=$$('button').find(b=>/Aplicar preços em lote/i.test(clean(b.textContent)));
    return action?.closest('.card')||null;
  }
  function periodInputs(card,label){
    const fs=$$('fieldset',card).find(n=>new RegExp(label,'i').test(clean(n.querySelector('legend')?.textContent||'')));
    const inputs=fs?$$('input',fs).filter(i=>i.type!=="checkbox"):[];
    return {regular:inputs[0]||null,sale:inputs[1]||null};
  }
  function categoryCheck(card,label){
    const l=$$('label',card).find(n=>clean(n.textContent)===label);
    return l?.querySelector('input[type=checkbox]')||null;
  }
  function current(card,category,period){
    const root=$$('div',card).find(n=>/Valores atuais no WooCommerce/i.test(clean(n.textContent)));
    if(!root)return {regular:"",sale:""};
    const blocks=$$('div',root).filter(n=>clean(n.textContent).startsWith(category));
    const block=blocks.sort((a,b)=>clean(a.textContent).length-clean(b.textContent).length)[0];
    if(!block)return {regular:"",sale:""};
    const p=$$('strong,h3,h4',block).find(n=>clean(n.textContent)===period);
    const raw=clean((p?.parentElement||block).textContent);
    return {regular:raw.match(/Original:\s*R\$\s*([0-9.,]+)/i)?.[1]||"",sale:raw.match(/Promocional:\s*R\$\s*([0-9.,]+)/i)?.[1]||""};
  }
  async function postPrices(payload){
    const response=await fetch('/loja/precos',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok||data?.ok===false)throw new Error(data?.message||data?.error||`HTTP ${response.status}`);
    return data;
  }
  function install(){
    const card=legacyCard(); if(!card||$('#store_category_pricing_table'))return;
    const annual=periodInputs(card,'Versão anual'), lifetime=periodInputs(card,'Versão vitalícia');
    const plugin=categoryCheck(card,'Plugins'), theme=categoryCheck(card,'Temas');
    if(!annual.regular||!annual.sale||!lifetime.regular||!lifetime.sale||!plugin||!theme)return;

    const data={plugin:{label:'Plugins',annual:current(card,'Plugins','Anual'),lifetime:current(card,'Plugins','Vitalício')},theme:{label:'Temas',annual:current(card,'Temas','Anual'),lifetime:current(card,'Temas','Vitalício')}};
    const box=document.createElement('div'); box.id='store_category_pricing_table';
    box.innerHTML=`<div class="section-title">Preços de Plugins e Temas</div><div class="small" style="margin:6px 0 14px">Mesmo padrão da tabela de Packs, porém por categoria e variação.</div><div class="table-wrap"><table class="catalogos-table"><thead><tr><th>Categoria</th><th>Variação</th><th>Preço atual original</th><th>Preço atual promocional</th><th>Novo original</th><th>Novo promocional</th><th>Ação</th></tr></thead><tbody></tbody></table></div><div id="store_category_pricing_status" class="small" style="margin-top:10px"></div>`;
    const tbody=$('tbody',box);
    for(const kind of ['plugin','theme'])for(const period of ['annual','lifetime']){
      const item=data[kind], cur=item[period], periodLabel=period==='annual'?'Anual':'Vitalício';
      const tr=document.createElement('tr');
      tr.innerHTML=`<td><strong>${item.label}</strong></td><td>${periodLabel}</td><td>${cur.regular?`R$ ${esc(cur.regular)}`:'—'}</td><td>${cur.sale?`R$ ${esc(cur.sale)}`:'Sem promoção'}</td><td><input data-store-kind="${kind}" data-store-period="${period}" data-store-field="regular" inputmode="decimal" value="${esc(cur.regular)}"></td><td><input data-store-kind="${kind}" data-store-period="${period}" data-store-field="sale" inputmode="decimal" value="${esc(cur.sale)}"></td><td>${period==='lifetime'?`<button class="btn-success" type="button" data-store-save="${kind}">Salvar ${item.label}</button>`:''}</td>`;
      tbody.appendChild(tr);
    }
    card.prepend(box);
    [...card.children].forEach(n=>{if(n!==box)n.style.display='none'});
    box.addEventListener('click',async e=>{
      const btn=e.target.closest('[data-store-save]'); if(!btn)return;
      const kind=btn.dataset.storeSave, val=(period,field)=>$(`[data-store-kind="${kind}"][data-store-period="${period}"][data-store-field="${field}"]`,box)?.value||'';
      const payload={kinds:[kind],annual_regular:val('annual','regular'),annual_sale:val('annual','sale'),lifetime_regular:val('lifetime','regular'),lifetime_sale:val('lifetime','sale'),confirmation:'ALTERAR PRECOS'};
      btn.disabled=true; const old=btn.textContent; btn.textContent='Salvando...';
      try{const result=await postPrices(payload);$('#store_category_pricing_status').textContent=result?.message||`${data[kind].label}: preços atualizados.`;}
      catch(error){$('#store_category_pricing_status').textContent=`Falha: ${error.message}`;}
      finally{btn.disabled=false;btn.textContent=old;}
    });
  }
  const start=()=>{install();new MutationObserver(install).observe(document.body,{childList:true,subtree:true});};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
