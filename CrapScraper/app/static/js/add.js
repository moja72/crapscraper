import {get,post} from "./api.js";
import {polling} from "./polling.js";

const $=(selector,root=document)=>root.querySelector(selector);
const safe=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const labels={ready:"Preparado",running:"Em andamento",success:"Concluído",error:"Erro"};
const envTips={woocommerce:"Loja de destino usada para criar o novo produto e suas variações.",source:"Indica se alguma autenticação de fonte foi configurada; a validade final é confirmada durante a execução.",storage:"Destino usado para publicar o ZIP validado do novo produto.",individual:"Indica se operações individuais autorizadas podem ser executadas.",woo_write:"Indica se a aplicação está autorizada a alterar o WooCommerce."};
const actionable=job=>["ready","error"].includes(String(job?.state||""));
const state={active:false,query:"",group:"",stage:"",sortBy:"date",sortOrder:"desc",page:1,pageSize:5,pages:1,total:0,items:[],selected:new Map(),allFiltered:false,selectedJob:"",logs:[],batch:{},timer:null,lastDetails:null};
let detailOpener=null;

function help(text,label){return `<button type="button" class="help-tip" data-tooltip="${safe(text)}" aria-label="Ajuda sobre ${safe(label)}">?</button>`}

function setupLayout(){
  const page=$("[data-page='add']");
  if(!page||page.dataset.addLegacyReady==="1")return;
  page.dataset.addLegacyReady="1";
  page.innerHTML=`
    <details class="panel update-environment" id="add-environment">
      <summary><span><strong>Ambiente</strong><small id="add-environment-summary">Verificando requisitos…</small></span></summary>
      <div id="add-environment-chips" class="environment-grid"></div>
      <section class="plugintheme-session"><div><h3>Sessão PluginTheme</h3><p id="add-plugintheme-session">Não validada.</p></div><button id="add-environment-refresh">Verificar pré-requisitos</button></section>
    </details>
    <section class="panel update-overview" id="add-overview">
      <header class="section-head"><div><h2>Adicionar produtos</h2><p>Gerencie os produtos aprovados, prepare os dados e publique novos itens com segurança no WooCommerce.</p><small id="add-last-run">Última leitura: —</small></div><div class="actions"><button id="add-materialize">Sincronizar aprovados</button></div></header>
      <div class="update-progress-meta"><strong id="add-progress-percent">0%</strong><span id="add-progress-count">0 de 0 processados</span></div>
      <div class="head-progress-track" role="progressbar" aria-label="Progresso do lote de adições" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div id="add-progress-fill"></div></div>
      <div id="add-operation-status" class="operation-band info" aria-live="polite">Nenhuma adição em execução.</div>
      <div class="cards update-summary-cards" id="add-cards"></div>
    </section>
    <section class="panel update-queue" id="add-queue">
      <header class="section-head"><div><h2>Produtos para adicionar</h2><p>Revise os itens aprovados, confira os dados essenciais e execute apenas o que estiver pronto para criação.</p></div><small id="add-result-count">0 itens encontrados</small></header>
      <p class="add-guidance">O CrapScraper preserva a fonte aprovada, valida versão e ZIP, prepara conteúdo e imagem, cria o produto variável e suas duas variações, e valida o resultado antes de concluir.</p>
      <div class="update-filter-grid">
        <label>Buscar<input id="add-query" placeholder="Nome, fonte ou WooCommerce ID"></label>
        <label>Estado<select id="add-group"><option value="">Todos</option><option value="prepared">Preparados</option><option value="running">Em andamento</option><option value="success">Concluídos</option><option value="error">Erros</option></select></label>
        <label>Etapa<select id="add-stage"><option value="">Todas</option><option value="prepared">Preparado</option><option value="validating">Validando</option><option value="resolving_source">Confirmando fonte</option><option value="downloading">Baixando</option><option value="validating_zip">Validando ZIP</option><option value="generating_description">Gerando conteúdo</option><option value="generating_image">Gerando imagem</option><option value="uploading_file">Publicando ZIP</option><option value="uploading_image">Enviando imagem</option><option value="creating_woocommerce">Criando WooCommerce</option><option value="completed">Concluído</option></select></label>
        <label>Ordenar por<select id="add-sort-by"><option value="date">Data de entrada na fila</option><option value="name">Nome do produto</option></select></label>
        <label>Ordem<select id="add-sort-order"><option value="desc">Mais recentes primeiro</option><option value="asc">Mais antigos primeiro</option></select></label>
        <div class="filter-actions"><button id="add-refresh">Atualizar</button><button id="add-filter-clear">Limpar filtros</button></div>
      </div>
      <div class="update-listing-meta"><output id="add-showing">Mostrando 0–0 de 0 itens</output><label>Itens por página<select id="add-page-size"><option selected>5</option><option>10</option><option>20</option><option>30</option><option>50</option><option>100</option></select></label></div>
      <div class="update-selection-toolbar"><div class="actions"><button id="add-select-page">Selecionar página</button><button id="add-select-all">Selecionar todo resultado</button><button id="add-clear-selection">Limpar seleção</button></div><div class="actions"><output id="add-selected-count">0 selecionado(s)</output><button id="add-batch-start" class="primary" disabled>Executar selecionados</button></div></div>
      <div class="update-batch-actions" id="add-running-actions" hidden><div class="quick-action"><button id="add-batch-pause">Pausar</button>${help("Pausa o lote sem perder o progresso já concluído.","pausar lote")}</div><div class="quick-action"><button id="add-batch-resume">Continuar</button>${help("Retoma um lote pausado.","continuar lote")}</div><div class="quick-action"><button id="add-batch-cancel" class="danger">Cancelar pendentes</button>${help("Cancela somente itens que ainda não começaram.","cancelar pendentes")}</div></div>
      <div class="table-wrap"><table><thead><tr><th></th><th>Produto</th><th>Fonte/versão</th><th>Estado/etapa</th><th>WooCommerce</th><th>Tentativas</th><th>Ações</th></tr></thead><tbody id="add-list"><tr><td colspan="7" class="empty">Carregando…</td></tr></tbody></table></div>
      <div class="pager update-pager"><button id="add-prev">Anterior</button><output id="add-page">Página 1 de 1</output><button id="add-next">Próxima</button></div>
    </section>
    <details class="panel update-history-panel" id="add-history-details"><summary><span><strong>Histórico</strong><small id="add-history-count">0 registro(s)</small></span></summary><div id="add-history" class="empty">Selecione um produto para visualizar as tentativas.</div></details>
    <details class="panel update-log-panel" id="add-log-details"><summary>Log técnico das adições</summary><div class="log-actions"><button id="add-copy-log">Copiar log completo</button></div><pre id="add-log">Sem logs.</pre></details>`;
  document.body.insertAdjacentHTML("beforeend",`<dialog id="add-detail-modal" class="form-dialog" aria-labelledby="add-detail-title"><section class="modal"><header><h2 id="add-detail-title">Detalhes do produto</h2><button class="icon-button" data-add-dialog-close aria-label="Fechar">×</button></header><section id="add-details"><p>Selecione um produto.</p></section></section></dialog>`);
  const modal=$("#add-detail-modal");
  modal.addEventListener("click",event=>{if(event.target===modal)modal.close()});
  modal.addEventListener("close",()=>detailOpener?.isConnected&&detailOpener.focus());
}

const qs=(page=state.page,pageSize=state.pageSize)=>new URLSearchParams({query:state.query,group:state.group,stage:state.stage,sort_by:state.sortBy,sort_order:state.sortOrder,page,page_size:pageSize});

function cards(counts){
  $("#add-cards").innerHTML=[["total","Total"],["prepared","Preparados"],["running","Em andamento"],["success","Concluídos"],["error","Erros"]].map(([key,label])=>`<div class="card metric-card"><button class="metric-filter" data-add-group="${key==="total"?"":key}" aria-pressed="${String((key==="total"?"":key)===state.group)}"><small>${label}</small><strong>${counts[key]??0}</strong></button></div>`).join("");
}

function selection(){
  const count=state.allFiltered?state.total:state.selected.size;
  $("#add-selected-count").textContent=`${count} selecionado(s)${state.allFiltered?" no resultado filtrado":""}`;
  $("#add-batch-start").disabled=Boolean(state.batch?.running)||count===0;
}

function rows(items){
  state.items=items;
  for(const job of items)if(state.selected.has(job.job_id))state.selected.set(job.job_id,job);
  $("#add-list").innerHTML=items.length?items.map(job=>{
    const canSelect=actionable(job);
    const checked=state.allFiltered||(state.selected.has(job.job_id)&&canSelect);
    return `<tr data-add-job="${safe(job.job_id)}"><td><input type="checkbox" data-add-select-check="${safe(job.job_id)}" aria-label="Selecionar ${safe(job.product_name)}"${checked?" checked":""}${canSelect?"":" disabled"}></td><td><strong>${safe(job.product_name)}</strong><small>${safe(job.kind)}</small></td><td>${safe(job.source_name)}<small>${safe(job.source_version)}</small></td><td><strong>${safe(labels[job.state]||job.state)}</strong><small>${safe(job.stage)}</small>${job.error?`<small class="error-text">${safe(job.error.message||"")}</small>`:""}</td><td>${job.woo_product_id?`#${job.woo_product_id}`:"—"}</td><td>${Number(job.attempts||0)}</td><td><div class="compact-actions"><button data-add-select="${safe(job.job_id)}">Detalhes</button><button class="primary" data-add-execute="${safe(job.job_id)}"${job.state==="running"||job.state==="success"?" disabled":""}>${job.state==="error"?"Tentar novamente":"Preparar/Executar"}</button></div></td></tr>`;
  }).join(""):`<tr><td colspan="7" class="empty">Nenhum item corresponde aos filtros atuais.</td></tr>`;
  selection();
}

function history(items=[]){
  $("#add-history-count").textContent=`${items.length} registro(s)`;
  $("#add-history").innerHTML=items.length?items.map(attempt=>`<article class="history-item"><strong>Tentativa ${attempt.attempt_number}: ${safe(attempt.result)}</strong><small>${safe(attempt.started_at)} · ${safe(attempt.source)}</small>${attempt.error?`<p class="error-text">${safe(attempt.error.message||"")}</p>`:""}</article>`).join(""):"Nenhuma tentativa registrada para este produto.";
}

function detail(job,attempts=[]){
  state.selectedJob=job.job_id;state.lastDetails={job,attempts};
  $("#add-details").innerHTML=`<dl class="details-grid"><div><dt>Nome</dt><dd>${safe(job.product_name)}</dd></div><div><dt>Tipo</dt><dd>${safe(job.kind)}</dd></div><div><dt>Fonte</dt><dd>${safe(job.source_name)}</dd></div><div><dt>URL da origem</dt><dd>${safe(job.source_url)}</dd></div><div><dt>Versão</dt><dd>${safe(job.source_version)}</dd></div><div><dt>Desenvolvedor</dt><dd>${safe(job.developer||"—")}</dd></div><div><dt>Página oficial</dt><dd>${safe(job.official_url||"—")}</dd></div><div><dt>Breve descrição</dt><dd>${safe(job.short_description||"—")}</dd></div><div><dt>Categorias preparadas</dt><dd>${safe((job.categories||[]).join(", ")||"—")}</dd></div><div><dt>Tags</dt><dd>${safe((job.tags||[]).join(", ")||"—")}</dd></div><div><dt>Imagem</dt><dd>${safe(job.image_state)} · ${safe(job.image_path||"—")}</dd></div><div><dt>ZIP</dt><dd>${safe(job.artifact_sha256||"—")}</dd></div><div><dt>WooCommerce ID</dt><dd>${job.woo_product_id||"—"}</dd></div><div><dt>Publicação</dt><dd>${safe(job.publication_state||"draft")}</dd></div></dl>${job.error?`<p class="error-text">${safe(job.error.message||"")}</p>`:""}`;
  history(attempts);
  const next=JSON.stringify(job.logs||[]);
  if(next!==JSON.stringify(state.logs)){state.logs=[...(job.logs||[])];$("#add-log").textContent=state.logs.length?state.logs.join("\n"):"Sem logs."}
}

async function select(id,{open=true,opener=null}={}){
  const data=await get(`/api/additions/job?job_id=${encodeURIComponent(id)}`);
  detail(data.item,data.history);
  if(open){detailOpener=opener;$("#add-detail-modal").showModal();$("#add-detail-modal [data-add-dialog-close]").focus()}
}

function batchView(batch={}){
  state.batch=batch;
  const total=Number(batch.total||0),done=Number(batch.processed||0),percent=total?Math.round(done*100/total):0;
  $("#add-progress-percent").textContent=`${percent}%`;
  $("#add-progress-count").textContent=`${done} de ${total} processados`;
  $("#add-progress-fill").style.transform=`scaleX(${percent/100})`;
  $("#add-progress-fill").parentElement.setAttribute("aria-valuenow",String(percent));
  const status=$("#add-operation-status");
  status.textContent=batch.running?(batch.paused?"Lote pausado.":"Adição em execução."):batch.cancelled?"Pendentes cancelados.":total&&done>=total?(batch.errors?`Lote concluído com ${batch.errors} erro(s).`:"Lote concluído."):"Nenhuma adição em execução.";
  status.className=`operation-band ${batch.running?"loading":batch.errors?"error":"info"}`;
  $("#add-running-actions").hidden=!batch.running;
  $("#add-batch-pause").disabled=!batch.running||batch.paused;
  $("#add-batch-resume").disabled=!batch.running||!batch.paused;
  $("#add-batch-cancel").disabled=!batch.running||!batch.pending;
  selection();
}

async function environment(check=false){
  const button=$("#add-environment-refresh");
  if(check){button.disabled=true;button.textContent="Verificando…"}
  try{
    const data=check?await post("/api/updates/environment/check",{}):await get("/api/updates/environment");
    $("#add-environment-summary").textContent=data.attention_count?`${data.attention_count} requisito(s) exigem atenção`:"Todos os requisitos validados";
    $("#add-environment-chips").innerHTML=(data.checks||[]).map(item=>`<article class="environment-chip" data-state="${safe(item.state)}" title="${safe(item.detail||"")}"><div><strong>${safe(item.label)}</strong><span>${safe(item.value)}</span></div>${help(item.detail||envTips[item.key]||"Diagnóstico de configuração.",item.label)}</article>`).join("");
    $("#add-plugintheme-session").textContent=`${data.plugintheme?.status||"Não validada"} · ${Number(data.plugintheme?.cookie_count||0)} cookie(s) configurado(s).`;
  }catch(error){$("#add-environment-summary").textContent=`Falha: ${error.message}`}
  finally{if(check){button.disabled=false;button.textContent="Verificar pré-requisitos"}}
}

async function refresh(){
  if(!state.active)return;
  try{
    const data=await get(`/api/additions/jobs?${qs()}`);
    state.pages=data.pages;state.total=data.total;state.page=data.page;
    cards(data.counts);rows(data.items);batchView(data.batch||{});
    const from=data.total?(data.page-1)*data.page_size+1:0,to=Math.min(data.total,data.page*data.page_size);
    $("#add-showing").textContent=`Mostrando ${from}–${to} de ${data.total} itens`;
    $("#add-result-count").textContent=`${data.total} item(ns) encontrado(s)`;
    $("#add-page").textContent=`Página ${data.page} de ${data.pages}`;
    $("#add-prev").disabled=data.page<=1;$("#add-next").disabled=data.page>=data.pages;
    $("#add-last-run").textContent="Última leitura: "+new Date().toLocaleString("pt-BR");
    if(state.selectedJob&&!$("#add-detail-modal").open)try{await select(state.selectedJob,{open:false})}catch{state.selectedJob=""}
  }catch(error){$("#add-operation-status").textContent=`Falha ao atualizar dados: ${error.message}`;$("#add-operation-status").className="operation-band error"}
}

async function materialize(){
  const button=$("#add-materialize");button.disabled=true;$("#add-operation-status").textContent="Sincronizando aprovações…";
  try{const result=await post("/api/additions/materialize",{});$("#add-operation-status").textContent=result.created?`${result.created} aprovação(ões) sincronizada(s).`:"Nenhuma nova aprovação.";await refresh()}
  catch(error){$("#add-operation-status").textContent=`Erro: ${error.message}`;$("#add-operation-status").className="operation-band error"}
  finally{button.disabled=false}
}

function clearSelection(){state.selected.clear();state.allFiltered=false;document.querySelectorAll("[data-add-select-check]").forEach(input=>input.checked=false);selection()}
function selectPage(){for(const job of state.items)if(actionable(job))state.selected.set(job.job_id,job);state.allFiltered=false;rows(state.items)}
function selectAll(){state.selected.clear();state.allFiltered=true;rows(state.items)}

async function filteredActionableIds(){
  const first=await get(`/api/additions/jobs?${qs(1,100)}`),ids=[];
  const addItems=items=>{for(const job of items||[])if(actionable(job))ids.push(job.job_id)};
  addItems(first.items);
  for(let page=2;page<=Number(first.pages||1);page++){const data=await get(`/api/additions/jobs?${qs(page,100)}`);addItems(data.items)}
  return [...new Set(ids)];
}

async function startBatch(){
  const button=$("#add-batch-start"),label=button.textContent;button.disabled=true;button.textContent="Validando…";
  try{
    const ids=state.allFiltered?await filteredActionableIds():[...state.selected.values()].filter(actionable).map(job=>job.job_id);
    if(!ids.length)throw new Error("Selecione ao menos um produto preparado ou com erro recuperável.");
    const result=await post("/api/additions/batch/start",{job_ids:ids});state.batch=result.batch||{};clearSelection();await refresh();
  }catch(error){$("#add-operation-status").textContent=`Lote bloqueado: ${error.message}`;$("#add-operation-status").className="operation-band error"}
  finally{button.textContent=label;selection()}
}

async function executeOne(id,button){
  button.disabled=true;
  try{
    const job=state.items.find(item=>item.job_id===id)||state.selected.get(id)||state.lastDetails?.job;
    const endpoint=job?.state==="error"?"/api/additions/retry":"/api/additions/execute";
    const result=await post(endpoint,{job_id:id});
    if(!result.ok&&result.error?.message){$("#add-operation-status").textContent=`Falha: ${result.error.message}`;$("#add-operation-status").className="operation-band error"}
    await select(id,{open:false});await refresh();
  }finally{button.disabled=false}
}

async function copyLog(){
  const text=$("#add-log").textContent||"";
  if(!text.trim())return;
  await navigator.clipboard.writeText(text);
  const button=$("#add-copy-log"),old=button.textContent;button.textContent="Log copiado";setTimeout(()=>button.textContent=old,1500);
}

function syncSortLabels(){
  const options=$("#add-sort-order").options;
  options[0].textContent=state.sortBy==="name"?"Z — A":"Mais recentes primeiro";
  options[1].textContent=state.sortBy==="name"?"A — Z":"Mais antigos primeiro";
}
setupLayout();

document.addEventListener("app:tab",event=>{state.active=event.detail==="add";if(state.active){environment();refresh()}});
document.addEventListener("input",event=>{if(event.target.id==="add-query"){state.query=event.target.value;state.page=1;clearTimeout(state.timer);state.timer=setTimeout(refresh,250)}});
document.addEventListener("change",event=>{
  if(event.target.id==="add-sort-by"||event.target.id==="add-sort-order"){
    state.sortBy=$("#add-sort-by").value;state.sortOrder=$("#add-sort-order").value;
    state.page=1;state.allFiltered=false;syncSortLabels();return refresh();
  }
  if(event.target.id==="add-group"){state.group=event.target.value;state.page=1;state.allFiltered=false;refresh()}
  if(event.target.id==="add-stage"){state.stage=event.target.value;state.page=1;state.allFiltered=false;refresh()}
  if(event.target.id==="add-page-size"){state.pageSize=Number(event.target.value)||5;state.page=1;refresh()}
  if(event.target.matches("[data-add-select-check]")){const id=event.target.dataset.addSelectCheck,job=state.items.find(item=>item.job_id===id);state.allFiltered=false;if(event.target.checked&&job&&actionable(job))state.selected.set(id,job);else state.selected.delete(id);selection()}
});

document.addEventListener("click",async event=>{
  if(event.target.closest("[data-add-dialog-close]")){$("#add-detail-modal").close();return}
  const group=event.target.closest("[data-add-group]")?.dataset.addGroup;if(group!==undefined){state.group=group;state.page=1;state.allFiltered=false;$("#add-group").value=group;return refresh()}
  const selectId=event.target.closest("[data-add-select]")?.dataset.addSelect;if(selectId){return select(selectId,{open:true,opener:event.target.closest("button")})}
  const executeId=event.target.closest("[data-add-execute]")?.dataset.addExecute;if(executeId){return executeOne(executeId,event.target.closest("button"))}
  if(event.target.id==="add-prev"&&state.page>1){state.page--;return refresh()}
  if(event.target.id==="add-next"&&state.page<state.pages){state.page++;return refresh()}
  if(event.target.id==="add-materialize")return materialize();
  if(event.target.id==="add-refresh")return refresh();
  if(event.target.id==="add-filter-clear"){state.sortBy="date";state.sortOrder="desc";$("#add-sort-by").value="date";$("#add-sort-order").value="desc";syncSortLabels();state.query=state.group=state.stage="";state.page=1;state.allFiltered=false;$("#add-query").value="";$("#add-group").value="";$("#add-stage").value="";return refresh()}
  if(event.target.id==="add-select-page"){selectPage();return}
  if(event.target.id==="add-select-all"){selectAll();return}
  if(event.target.id==="add-clear-selection"){clearSelection();return}
  if(event.target.id==="add-batch-start")return startBatch();
  if(event.target.id==="add-batch-pause"){await post("/api/additions/batch/pause",{});return refresh()}
  if(event.target.id==="add-batch-resume"){await post("/api/additions/batch/resume",{});return refresh()}
  if(event.target.id==="add-batch-cancel"){await post("/api/additions/batch/cancel",{});return refresh()}
  if(event.target.id==="add-environment-refresh")return environment(true);
  if(event.target.id==="add-copy-log")return copyLog();
});

polling.register("addition-state",refresh,1200);
