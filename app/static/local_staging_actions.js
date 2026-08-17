(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), clean=v=>String(v??"").replace(/\s+/g," ").trim();
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const SAFE_STATES=new Set(['approved','blocked','error','failed','interrupted','canceled','prepared']);
  const RISKY_STEPS=new Set(['production_zip_installed','pt_versao_updated','wordpress_validated']);
  const localArtifact=j=>Boolean(clean(j?.local_staging_path)&&clean(j?.new_sha256));
  const filename=p=>clean(p).split(/[\\/]/).pop()||'arquivo.zip';
  const sizeLabel=n=>{const v=Number(n||0);if(v>=1024*1024)return`${(v/(1024*1024)).toFixed(1)} MB`;if(v>=1024)return`${(v/1024).toFixed(1)} KB`;return`${v} B`;};
  async function request(path,body){const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json().catch(()=>({}));if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);return d;}
  async function load(){const r=await fetch('/atualizacoes/jobs',{cache:'no-store',credentials:'same-origin'});const d=await r.json().catch(()=>({}));if(!r.ok||d?.ok===false)throw new Error(d?.message||`HTTP ${r.status}`);return d;}
  function eligible(j){return localArtifact(j)&&SAFE_STATES.has(clean(j.state).toLowerCase())&&!RISKY_STEPS.has(clean(j.last_completed_step));}
  async function rebuild(job,button,status){button.disabled=true;const old=button.textContent;button.textContent='Revalidando...';status.textContent=`${job.name||job.woo_product_id}: validando ZIP local...`;try{await request('/atualizacoes/preparar',{job_id:job.job_id});await request('/atualizacoes/plano',{job_id:job.job_id});status.textContent=`${job.name||job.woo_product_id}: plano pronto. Agora use “Adicionar à fila”.`;await refresh();}catch(error){status.textContent=`${job.name||job.woo_product_id}: ${error.message}`;}finally{button.disabled=false;button.textContent=old;}}
  let busy=false;
  async function refresh(){
    if(busy||!$('#tab_panel_atualizacoes'))return;busy=true;
    try{
      const data=await load(), allJobs=Array.isArray(data.jobs)?data.jobs:[], jobMap=new Map(allJobs.map(j=>[clean(j.job_id),j]));
      const inventory=Array.isArray(data?.queue?.local_staging_inventory)?data.queue.local_staging_inventory:[];
      const rootPath=clean(data?.queue?.local_staging_root)||'data\\staging\\updates';
      const linkedJobs=allJobs.filter(eligible), linkedIds=new Set(linkedJobs.map(j=>clean(j.job_id)));
      const rows=[];
      for(const item of inventory){
        const job=jobMap.get(clean(item.job_id));
        const linked=job&&linkedIds.has(clean(job.job_id));
        rows.push({item,job,linked});
      }
      let card=$('#local_staging_update_card');
      if(!card){card=document.createElement('div');card.id='local_staging_update_card';card.className='card';const queue=$('#updates_queue_jobs')?.closest('details,.card');const panel=$('#tab_panel_atualizacoes');(queue||panel).insertAdjacentElement(queue?'beforebegin':'afterbegin',card);}
      const message=inventory.length
        ? `${inventory.length} arquivo(s) ZIP encontrados fisicamente em ${rootPath}. ${linkedJobs.length} possuem vínculo + SHA persistidos e podem ser revalidados automaticamente.`
        : `Nenhum ZIP foi encontrado fisicamente em ${rootPath}.`;
      card.innerHTML=`<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><div class="section-title">ZIPs locais disponíveis</div><div class="small">${esc(message)}</div></div><button type="button" class="btn-secondary" id="local_staging_refresh">Atualizar lista</button></div><div id="local_staging_status" class="small" style="margin:10px 0"></div><div class="table-wrap"><table class="catalogos-table"><thead><tr><th>Produto / arquivo</th><th>Estado</th><th>Versão</th><th>ZIP local</th><th>Ação</th></tr></thead><tbody>${rows.slice(0,100).map(({item,job,linked})=>`<tr><td><strong>${esc(job?.name||filename(item.path))}</strong><div class="small">${job?`Woo #${job.woo_product_id||'-'} · job ${esc(job.job_id)}`:'Arquivo órfão: não corresponde a um job atual'}</div></td><td>${esc(job?.state||'Somente no disco')}</td><td>${job?`${esc(job.site_version||'-')} → ${esc(job.effective_source_version||job.approved_source_version||'-')}`:'—'}</td><td><span class="cs-zip-local-badge">ZIP no disco</span><div class="small">${esc(item.filename||filename(item.path))} · ${sizeLabel(item.size_bytes)}</div></td><td>${linked?`<button type="button" class="btn-success" data-local-job="${esc(job.job_id)}">Revalidar e gerar plano</button>`:(job?'<span class="small">Arquivo encontrado, mas faltam SHA/metadados persistidos para reaproveitamento automático seguro.</span>':'<span class="small">Sem job correspondente no runtime atual.</span>')}</td></tr>`).join('')||'<tr><td colspan="5" class="small">Nenhum ZIP local encontrado no disco.</td></tr>'}</tbody></table></div>${rows.length>100?`<div class="small" style="margin-top:8px">Mostrando os primeiros 100 de ${rows.length} arquivos.</div>`:''}`;
      $('#local_staging_refresh',card)?.addEventListener('click',refresh);const status=$('#local_staging_status',card);card.querySelectorAll('[data-local-job]').forEach(btn=>btn.addEventListener('click',()=>{const job=jobMap.get(btn.dataset.localJob);if(job)rebuild(job,btn,status);}));
    }catch(error){const status=$('#local_staging_status');if(status)status.textContent=`Falha ao verificar os ZIPs locais: ${error.message}`;}
    finally{busy=false;}
  }
  const start=()=>{refresh();setInterval(()=>{if(!$('#tab_panel_atualizacoes')?.classList.contains('hidden'))refresh();},5000);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
