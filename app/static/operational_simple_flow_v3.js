(() => {
  "use strict";
  if (window.__crapScraperOperationalSimpleFlowV3Installed) return;
  window.__crapScraperOperationalSimpleFlowV3Installed = true;
  window.__crapScraperOperationalSimpleFlowInstalled = true;

  const $ = (s, r = document) => r?.querySelector?.(s) || null;
  const $$ = (s, r = document) => Array.from(r?.querySelectorAll?.(s) || []);
  const clean = v => String(v ?? "").replace(/\s+/g, " ").trim();
  const esc = v => String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");
  const running = {update:false, addition:false};

  function installStyles() {
    if ($("#operational-simple-flow-v3-style")) return;
    const style = document.createElement("style");
    style.id = "operational-simple-flow-v3-style";
    style.textContent = `
      #tab_panel_atualizacoes .cs-queue-v1,#tab_panel_adicoes .cs-queue-v1,
      #tab_panel_atualizacoes #updates_queue_accordion,#tab_panel_adicoes #addition_queue_accordion,
      #tab_panel_atualizacoes #updates_prepare_selected,#tab_panel_atualizacoes #updates_enqueue_selected,
      #tab_panel_atualizacoes #updates_select_filtered,#tab_panel_adicoes #addition_prepare_selected,
      #tab_panel_adicoes #addition_add_selected_from_prep,#tab_panel_atualizacoes .update-prepare,
      #tab_panel_atualizacoes .update-enqueue-one,#tab_panel_atualizacoes .update-execute,
      #tab_panel_adicoes [data-add-action="prepare"],#tab_panel_adicoes [data-add-action="add"]{display:none!important}
      #tab_panel_atualizacoes .cs-prep-v13-header,#tab_panel_adicoes .cs-prep-v13-header{cursor:default!important}
      #tab_panel_atualizacoes .cs-prep-v13-header .updates-disclosure-chevron,
      #tab_panel_adicoes .cs-prep-v13-header .updates-disclosure-chevron{display:none!important}
      .cs-canonical-execute{min-height:42px!important;padding:0 16px!important;border-radius:9px!important;font-size:12px!important;font-weight:850!important}
      .cs-canonical-row-execute{min-height:34px!important;padding:7px 11px!important;border-radius:8px!important;font-size:11px!important;font-weight:800!important}
      .cs-canonical-progress{display:none;align-items:center;gap:9px;width:100%;min-height:38px;padding:9px 11px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.018);color:var(--text-muted);font-size:11px;box-sizing:border-box}
      .cs-canonical-progress.is-visible{display:flex}.cs-canonical-progress.is-success{border-color:rgba(16,185,129,.35);background:rgba(16,185,129,.055);color:#a7f3d0}.cs-canonical-progress.is-error{border-color:rgba(239,68,68,.35);background:rgba(239,68,68,.055);color:#fecaca}
      #tab_panel_atualizacoes .update-job.cs-canonical-selected,#tab_panel_adicoes .addition-op-row.cs-canonical-selected{outline:1px solid rgba(16,185,129,.34);outline-offset:-1px;background:rgba(16,185,129,.028)!important}
      @media(max-width:760px){.cs-canonical-execute{width:100%!important}}
    `;
    document.head.appendChild(style);
  }

  async function json(url, options = {}, timeout = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url,{cache:"no-store",credentials:"same-origin",headers:{...(options.body?{"Content-Type":"application/json"}:{}),...(options.headers||{})},...options,signal:controller.signal});
      let data={}; try{data=await response.json();}catch(_e){}
      if(!response.ok||data?.ok===false) throw new Error(data?.message||`HTTP ${response.status}`);
      return data;
    } finally { clearTimeout(timer); }
  }
  const post=(url,payload)=>json(url,{method:"POST",body:JSON.stringify(payload||{})},25000);

  function panel(kind){return $(kind==="update"?"#tab_panel_atualizacoes":"#tab_panel_adicoes");}
  function prep(kind){return $(".cs-prep-v13",panel(kind));}
  function selectedIds(kind){
    const root=prep(kind); if(!root)return[];
    if(kind==="update") return $$(".update-job .update-select:checked:not(:disabled)",root).map(b=>clean(b.closest("[data-update-job-id]")?.dataset?.updateJobId)).filter(Boolean);
    return $$('[data-add-select="preparation"]:checked',root).map(b=>clean(b.dataset.job)).filter(Boolean);
  }
  function executeButton(kind){return $(`#cs_canonical_${kind}_execute`);}
  function progressNode(kind){return $(`#cs_canonical_${kind}_progress`);}

  function ensureProgress(kind,root){
    let node=progressNode(kind); if(node)return node;
    node=document.createElement("div"); node.id=`cs_canonical_${kind}_progress`; node.className="cs-canonical-progress"; node.setAttribute("aria-live","polite");
    const bulk=$(".cs-prep-v13-bulk",root); if(bulk?.parentNode) bulk.parentNode.insertBefore(node,bulk.nextSibling); else root.appendChild(node); return node;
  }

  function refreshSelection(kind){
    const root=prep(kind); if(!root)return;
    if(kind==="update") $$(".update-job",root).forEach(c=>c.classList.toggle("cs-canonical-selected",Boolean($(".update-select",c)?.checked)));
    else $$(".addition-op-row",root).forEach(c=>c.classList.toggle("cs-canonical-selected",Boolean($('[data-add-select="preparation"]',c)?.checked)));
    const button=executeButton(kind); if(button&&!running[kind]) button.disabled=selectedIds(kind).length===0;
  }

  function toast(message,kind="ok"){
    $("#cs_canonical_toast")?.remove(); const n=document.createElement("div"); n.id="cs_canonical_toast"; n.textContent=clean(message);
    const p=kind==="error"?{b:"#ef4444",g:"#451a1a"}:kind==="warning"?{b:"#f59e0b",g:"#3b2a05"}:{b:"#10b981",g:"#063d2b"};
    Object.assign(n.style,{position:"fixed",right:"18px",bottom:"18px",zIndex:"195000",maxWidth:"560px",padding:"12px 14px",borderRadius:"12px",border:`1px solid ${p.b}`,background:p.g,color:"#fff",fontWeight:"750"}); document.body.appendChild(n); setTimeout(()=>n.remove(),5200);
  }

  async function start(kind,ids,button){
    const list=[...new Set(ids.map(clean).filter(Boolean))]; if(!list.length)return toast("Selecione ao menos um produto.","warning");
    const noun=kind==="update"?"atualização":"cadastro"; const verb=kind==="update"?"atualizar":"adicionar";
    if(!confirm(`Executar ${noun} automática de ${list.length} produto(s)? O CrapScraper fará todas as etapas e validações sozinho.`))return;
    if(button){button.disabled=true;button.textContent="Iniciando…";}
    try{const data=await post(`/operacoes/simples/${verb}`,{job_ids:list}); renderBatch(kind,data?.batch||{running:true,total:list.length,message:"Iniciando…"}); toast("Execução iniciada.");}
    catch(error){toast(error?.message||"Falha ao iniciar a execução.","error"); if(button){button.textContent="Executar selecionados";button.disabled=selectedIds(kind).length===0;}}
  }

  function renderBatch(kind,batch){
    const root=prep(kind); if(!root)return; const progress=ensureProgress(kind,root); const button=executeButton(kind); const active=Boolean(batch?.running); running[kind]=active;
    if(button){button.textContent=active?"Executando…":"Executar selecionados";button.disabled=active||selectedIds(kind).length===0;}
    const total=Number(batch?.total||0),done=Number(batch?.processed||0),ok=Number(batch?.success||0),errors=Number(batch?.errors||0),message=clean(batch?.message||(active?"Processando…":"Pronto."));
    if(!active&&!batch?.done&&!errors){progress.className="cs-canonical-progress";progress.textContent="";return;}
    progress.className=`cs-canonical-progress is-visible${errors&&!active?" is-error":(!active&&batch?.done?" is-success":"")}`;
    progress.innerHTML=active?`<span class="inline-loading-spinner" aria-hidden="true"></span><span><strong>${esc(done)}/${esc(total)}</strong> · ${esc(message)} · ${esc(ok)} concluído(s)${errors?` · ${esc(errors)} erro(s)`:""}</span>`:`<span>${errors?"⚠":"✓"}</span><span><strong>${esc(message)}</strong>${batch?.last_error?` · ${esc(batch.last_error)}`:""}</span>`;
  }

  async function pollStatus(){
    try{const data=await json("/operacoes/simples/status",{},8000);renderBatch("update",data?.update||{});renderBatch("addition",data?.addition||{});}catch(_e){}
  }

  function canonicalize(kind){
    const root=prep(kind); if(!root)return;
    const title=kind==="update"?$(".standard-update-accordion-title",root):$(".section-title",root);
    const wantedTitle=kind==="update"?"Produtos para atualizar":"Produtos para adicionar"; if(title&&clean(title.textContent)!==wantedTitle) title.textContent=wantedTitle;
    const description=$(".cs-prep-v13-description",root); const wantedDescription=kind==="update"?"Selecione os produtos aprovados e execute. O CrapScraper valida vínculo e versões, prepara ZIP e backup, gera o plano, atualiza e valida o resultado automaticamente.":"Selecione os produtos aprovados e execute. O CrapScraper prepara conteúdo, imagem, categoria, preços e ZIP, cria o produto e as variações, publica e valida o resultado automaticamente.";
    if(description&&clean(description.textContent)!==wantedDescription) description.textContent=wantedDescription;
    if(root.tagName==="DETAILS")root.open=true; root.classList.remove("is-collapsed");

    const actions=$(".cs-prep-v13-actions",root); if(actions&&!executeButton(kind)){const b=document.createElement("button");b.type="button";b.id=`cs_canonical_${kind}_execute`;b.className="btn-success cs-canonical-execute";b.textContent="Executar selecionados";b.addEventListener("click",()=>start(kind,selectedIds(kind),b));actions.appendChild(b);}
    ensureProgress(kind,root);

    const boxSelector=kind==="update"?".update-job .update-select":'[data-add-select="preparation"]';
    $$(boxSelector,root).forEach(box=>{if(box.dataset.canonicalBound)return;box.dataset.canonicalBound="1";box.addEventListener("change",()=>refreshSelection(kind));});

    if(kind==="update") $$(".update-job",root).forEach(card=>{const id=clean(card.dataset.updateJobId),actions=$(".update-row-actions",card),terminal=/conclu|rollback conclu|cancelad/.test(clean($(".badge",card)?.textContent).toLowerCase())||card.classList.contains("is-completed");if(!id||!actions||terminal||$(".cs-canonical-row-execute",actions))return;const b=document.createElement("button");b.type="button";b.className="btn-success cs-canonical-row-execute";b.textContent="Executar";b.addEventListener("click",()=>start("update",[id],b));actions.appendChild(b);});
    else $$(".addition-op-row",root).forEach(row=>{const box=$('[data-add-select="preparation"]',row),id=clean(box?.dataset.job),actions=$(".addition-op-actions",row),terminal=/conclu|cancelad/.test(clean($(".addition-state-badge",row)?.textContent).toLowerCase());if(!id||!actions||terminal||$(".cs-canonical-row-execute",actions))return;const b=document.createElement("button");b.type="button";b.className="btn-success cs-canonical-row-execute";b.textContent="Executar";b.addEventListener("click",()=>start("addition",[id],b));actions.appendChild(b);});
    refreshSelection(kind);
  }

  function canonicalizeAll(){installStyles();canonicalize("update");canonicalize("addition");}
  function boot(){canonicalizeAll();pollStatus();setInterval(canonicalizeAll,1000);setInterval(()=>{if(running.update||running.addition)pollStatus();},1200);}
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",boot,{once:true});else boot();
})();
