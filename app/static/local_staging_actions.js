(() => {
  "use strict";
  const $=(s,r=document)=>r.querySelector(s), clean=v=>String(v??"").replace(/\s+/g," ").trim();
  const esc=v=>String(v??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const SAFE_STATES=new Set(['approved','blocked','error','failed','interrupted','canceled','prepared']);
  const FORBIDDEN_STATES=new Set(['completed','rolled_back','rollback_required','executing','queued']);
  const TRANSIENT_STATES=new Set(['validating','downloading','preparing']);
  const RISKY_STEPS=new Set(['production_zip_installed','pt_versao_updated','wordpress_validated']);
  const localArtifact=j=>Boolean(clean(j?.local_staging_path)&&clean(j?.new_sha256));
  const filename=p=>clean(p).split(/[\\/]/).pop()||'arquivo.zip';
  const sizeLabel=n=>{const v=Number(n||0);if(v>=1024*1024)return`${(v/(1024*1024)).toFixed(1)} MB`;if(v>=1024)return`${(v/1024).toFixed(1)} KB`;return`${v} B`;};
  const normalizedVersion=v=>clean(v).toLowerCase().replace(/^v/,'');
  const versionInFilename=(name,version)=>{const v=normalizedVersion(version);if(!v)return false;const stem=clean(name).toLowerCase();const variants=[v,v.replace(/[^0-9a-z]+/g,''),v.replace(/[^0-9a-z]+/g,'-'),v.replace(/[^0-9a-z]+/g,'.')].filter(Boolean);return variants.some(token=>stem.includes(token));};
  async function request(path,body){const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json().catch(()=>({}));if(!r.ok||d?.ok===false)throw new Error(d?.message||d?.error||`HTTP ${r.status}`);return d;}
  async function load(){const r=await fetch('/atualizacoes/jobs',{cache:'no-store',credentials:'same-origin'});const d=await r.json().catch(()=>({}));if(!r.ok||d?.ok===false)throw new Error(d?.message||`HTTP ${r.status}`);return d;}
  function safeState(j){const state=clean(j?.state).toLowerCase();return SAFE_STATES.has(state)&&!FORBIDDEN_STATES.has(state)&&!RISKY_STEPS.has(clean(j?.last_completed_step));}
  function linkedEligible(j){return localArtifact(j)&&safeState(j);}
  function expectedVersion(j){return clean(j?.effective_source_version||j?.approved_source_version||j?.ultrapack_version);}
  function recoveryChoice(job,items){
    if(!job||!safeState(job)||!items.length)return {ok:false,reason:'Estado não elegível para recuperação.'};
    if(items.length===1)return {ok:true,item:items[0]};
    const version=expectedVersion(job),matching=items.filter(item=>versionInFilename(item.filename||filename(item.path),version));
    if(matching.length===1)return {ok:true,item:matching[0]};
    return {ok:false,reason:`Há ${items.length} ZIPs neste job e não foi possível escolher um único arquivo com segurança.`};
  }
  async function rebuild(job,button,status){
    button.disabled=true;const old=button.textContent;button.textContent='Recuperando...';status.textContent=`${job.name||job.woo_product_id}: validando ZIP local e reconstruindo evidências...`;
    try{
      await request('/atualizacoes/preparar',{job_id:job.job_id});
      await request('/atualizacoes/plano',{job_id:job.job_id});
      status.textContent=`${job.name||job.woo_product_id}: ZIP recuperado, SHA persistido e plano pronto. Agora adicione à fila.`;
      return true;
    }catch(error){status.textContent=`${job.name||job.woo_product_id}: ${error.message}`;return false;}
    finally{button.disabled=false;button.textContent=old;}
  }
  let busy=false;
  async function refresh(){
    if(busy||!$('#tab_panel_atualizacoes'))return;busy=true;
    try{
      const data=await load(), allJobs=Array.isArray(data.jobs)?data.jobs:[], jobMap=new Map(allJobs.map(j=>[clean(j.job_id),j]));
      const inventory=Array.isArray(data?.queue?.local_staging_inventory)?data.queue.local_staging_inventory:[];
      const rootPath=clean(data?.queue?.local_staging_root)||'data\\staging\\updates';
      const byJob=new Map();
      for(const item of inventory){const id=clean(item.job_id);if(!byJob.has(id))byJob.set(id,[]);byJob.get(id).push(item);}
      const linkedJobs=allJobs.filter(linkedEligible);
      const recoverableJobs=[];
      for(const [jobId,items] of byJob){const job=jobMap.get(jobId),choice=recoveryChoice(job,items);if(job&&choice.ok&&!linkedEligible(job))recoverableJobs.push(job);}
      let card=$('#local_staging_update_card');
      if(!card){card=document.createElement('div');card.id='local_staging_update_card';card.className='card';const queue=$('#updates_queue_jobs')?.closest('details,.card');const panel=$('#tab_panel_atualizacoes');(queue||panel).insertAdjacentElement(queue?'beforebegin':'afterbegin',card);}
      const message=inventory.length
        ? `${inventory.length} arquivo(s) ZIP encontrados em ${rootPath}. ${linkedJobs.length} já possuem SHA persistido e ${recoverableJobs.length} job(s) podem reconstruir as evidências sem novo download.`
        : `Nenhum ZIP foi encontrado fisicamente em ${rootPath}.`;
      const rows=[];
      for(const item of inventory){
        const job=jobMap.get(clean(item.job_id)),items=byJob.get(clean(item.job_id))||[],choice=recoveryChoice(job,items),linked=job&&linkedEligible(job);
        const state=clean(job?.state).toLowerCase();
        let action='';
        if(state==='plan_ready') action='<span class="small"><strong>Plano pronto.</strong> Selecione o item na lista de atualizações e use “Adicionar à fila”.</span>';
        else if(TRANSIENT_STATES.has(state)) action='<span class="small">Recuperação/preparação em andamento. Aguarde a conclusão deste item.</span>';
        else if(linked) action=`<button type="button" class="btn-success" data-local-job="${esc(job.job_id)}">Revalidar e gerar plano</button>`;
        else if(job&&choice.ok&&!FORBIDDEN_STATES.has(state)) action=`<button type="button" class="btn-success" data-local-job="${esc(job.job_id)}">Recuperar ZIP e gerar plano</button>`;
        else if(state==='completed') action='<span class="small">Já concluído. Nenhuma recuperação necessária.</span>';
        else if(state==='queued') action='<span class="small">Já está na fila de atualização.</span>';
        else if(state==='executing') action='<span class="small">Atualização em execução.</span>';
        else if(state==='rollback_required') action='<span class="small">Rollback necessário — revisão manual obrigatória.</span>';
        else if(job&&FORBIDDEN_STATES.has(state)) action='<span class="small">Não reprocessar automaticamente neste estado.</span>';
        else if(job) action=`<span class="small">${esc(choice.reason||'Não elegível para recuperação automática segura.')}</span>`;
        else action='<span class="small">Sem job correspondente no runtime atual.</span>';
        rows.push({item,job,action});
      }
      card.innerHTML=`<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><div class="section-title">ZIPs locais disponíveis</div><div class="small">${esc(message)}</div></div><div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">${recoverableJobs.length?'<button type="button" class="btn-success" id="local_staging_recover_all">Recuperar todos elegíveis</button>':''}<button type="button" class="btn-secondary" id="local_staging_refresh">Atualizar lista</button></div></div><div id="local_staging_status" class="small" style="margin:10px 0"></div><div class="table-wrap"><table class="catalogos-table"><thead><tr><th>Produto / arquivo</th><th>Estado</th><th>Versão</th><th>ZIP local</th><th>Ação</th></tr></thead><tbody>${rows.slice(0,100).map(({item,job,action})=>`<tr><td><strong>${esc(job?.name||filename(item.path))}</strong><div class="small">${job?`Woo #${job.woo_product_id||'-'} · job ${esc(job.job_id)}`:'Arquivo órfão: não corresponde a um job atual'}</div></td><td>${esc(job?.state||'Somente no disco')}</td><td>${job?`${esc(job.plugintema_version||job.site_version||'-')} → ${esc(expectedVersion(job)||'-')}`:'—'}</td><td><span class="cs-zip-local-badge">ZIP no disco</span><div class="small">${esc(item.filename||filename(item.path))} · ${sizeLabel(item.size_bytes)}</div></td><td>${action}</td></tr>`).join('')||'<tr><td colspan="5" class="small">Nenhum ZIP local encontrado no disco.</td></tr>'}</tbody></table></div>${rows.length>100?`<div class="small" style="margin-top:8px">Mostrando os primeiros 100 de ${rows.length} arquivos.</div>`:''}`;
      $('#local_staging_refresh',card)?.addEventListener('click',refresh);
      const status=$('#local_staging_status',card);
      card.querySelectorAll('[data-local-job]').forEach(btn=>btn.addEventListener('click',async()=>{const job=jobMap.get(btn.dataset.localJob);if(job){await rebuild(job,btn,status);await refresh();}}));
      $('#local_staging_recover_all',card)?.addEventListener('click',async event=>{
        const button=event.currentTarget;button.disabled=true;const old=button.textContent;let ok=0,failed=0;
        try{
          for(let i=0;i<recoverableJobs.length;i++){
            const job=recoverableJobs[i];button.textContent=`Recuperando ${i+1}/${recoverableJobs.length}...`;
            const dummy={disabled:false,textContent:'Recuperar'};
            if(await rebuild(job,dummy,status))ok++;else failed++;
          }
          status.textContent=`Recuperação concluída: ${ok} plano(s) pronto(s); ${failed} falha(s). Nenhum ZIP concluído/rollback foi reprocessado.`;
        }finally{button.disabled=false;button.textContent=old;await refresh();}
      });
    }catch(error){const status=$('#local_staging_status');if(status)status.textContent=`Falha ao verificar os ZIPs locais: ${error.message}`;}
    finally{busy=false;}
  }
  const start=()=>{refresh();setInterval(()=>{if(!$('#tab_panel_atualizacoes')?.classList.contains('hidden'))refresh();},5000);};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
