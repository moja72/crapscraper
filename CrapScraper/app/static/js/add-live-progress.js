import {get} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);
const safe=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

const stages=[
  ["validating","Validando adição"],
  ["resolving_source","Confirmando fonte"],
  ["downloading","Baixando arquivo"],
  ["validating_zip","Validando ZIP"],
  ["generating_description","Preparando conteúdo"],
  ["generating_image","Preparando imagem"],
  ["reconciling_woocommerce","Reconciliando WooCommerce"],
  ["uploading_file","Publicando ZIP"],
  ["uploading_image","Enviando imagem"],
  ["creating_woocommerce","Criando produto WooCommerce"],
  ["creating_variations","Criando variações"],
  ["validating_result","Validando resultado"],
  ["completed","Concluído"],
];
const stageIndex=new Map(stages.map(([key],index)=>[key,index+1]));
const stageLabel=new Map(stages);
let busy=false;
let timer=null;
let observer=null;

function installStyle(){
  if($("#add-live-progress-style"))return;
  const style=document.createElement("style");
  style.id="add-live-progress-style";
  style.textContent=`
    #add-list tr.add-live-progress-row td{padding-top:0!important;border-top:0!important}
    #add-list .add-live-progress{margin:0 0 10px 0}
    #add-list .add-live-progress .update-job-live-log{max-height:92px}
    #add-list .add-live-progress[data-progress-state="running"] progress{accent-color:var(--accent)}
    #add-list .add-live-progress[data-progress-state="error"] progress{accent-color:var(--danger)}
  `;
  document.head.appendChild(style);
}

function ensureStageFilters(){
  const select=$("#add-stage");
  if(!select)return;
  for(const [value,label] of stages){
    if([...select.options].some(option=>option.value===value))continue;
    const option=document.createElement("option");
    option.value=value;option.textContent=label;
    select.appendChild(option);
  }
}

function effectiveStage(job){
  const raw=String(job.stage||"validating");
  if(raw==="validating"&&Number(job.woo_product_id||0)>0)return "validating_result";
  return stageIndex.has(raw)?raw:"validating";
}

function progressMarkup(job){
  const stage=effectiveStage(job);
  const total=stages.length;
  const step=job.state==="success"?total:Math.max(1,stageIndex.get(stage)||1);
  const label=stageLabel.get(stage)||String(job.stage||"Em andamento");
  const state=job.state==="error"?"error":job.state==="success"?"complete":job.state==="running"?"running":"idle";
  const logs=(job.logs||[]).slice(-4);
  const logHtml=(logs.length?logs:[label]).map(line=>`<li>${safe(line)}</li>`).join("");
  return `<section class="update-job-progress add-live-progress" data-progress-state="${state}" aria-label="Progresso de ${safe(job.product_name)}"><div class="update-job-progress-head"><strong>${safe(label)}</strong><small>Etapa ${step} de ${total}</small></div><progress max="${total}" value="${step}" aria-label="${safe(label)}"></progress><ol class="update-job-live-log" role="log" aria-live="polite" aria-relevant="additions text">${logHtml}</ol></section>`;
}

function putProgress(row,job){
  let progressRow=row.nextElementSibling;
  if(!progressRow?.matches(`tr[data-add-progress-for="${CSS.escape(String(job.job_id))}"]`)){
    progressRow=document.createElement("tr");
    progressRow.className="add-live-progress-row";
    progressRow.dataset.addProgressFor=String(job.job_id);
    const cell=document.createElement("td");
    progressRow.appendChild(cell);
    row.after(progressRow);
  }
  const cell=progressRow.firstElementChild;
  cell.colSpan=Math.max(1,row.children.length);
  const next=progressMarkup(job);
  if(cell.innerHTML!==next)cell.innerHTML=next;
}

function removeOrphans(){
  document.querySelectorAll("#add-list tr.add-live-progress-row").forEach(row=>{
    const owner=document.querySelector(`#add-list tr[data-add-job="${CSS.escape(row.dataset.addProgressFor||"")}"]`);
    if(!owner)row.remove();
  });
}

async function refreshProgress(){
  clearTimeout(timer);
  if(busy)return;
  const page=$("[data-page='add']");
  if(!page?.classList.contains("active"))return;
  ensureStageFilters();
  const rows=[...document.querySelectorAll("#add-list tr[data-add-job]")];
  const candidates=rows.filter(row=>/Em andamento|Erro/.test(row.textContent||""));
  if(!candidates.length){removeOrphans();return;}
  busy=true;
  let hasRunning=false;
  try{
    await Promise.all(candidates.map(async row=>{
      try{
        const data=await get(`/api/additions/job?job_id=${encodeURIComponent(row.dataset.addJob)}`);
        const job=data.item||{};
        if(job.state==="running")hasRunning=true;
        putProgress(row,job);
      }catch{}
    }));
    removeOrphans();
  }finally{
    busy=false;
    if(hasRunning)timer=setTimeout(refreshProgress,850);
  }
}

function schedule(delay=80){
  clearTimeout(timer);
  timer=setTimeout(refreshProgress,delay);
}

function observe(){
  const list=$("#add-list");
  if(!list||list.dataset.addLiveProgressObserved==="1")return;
  list.dataset.addLiveProgressObserved="1";
  observer?.disconnect();
  observer=new MutationObserver(mutations=>{
    const relevant=mutations.some(mutation=>[...mutation.addedNodes].some(node=>node.nodeType===1&&!node.matches?.("tr.add-live-progress-row")&&!node.matches?.("[data-add-date-column]")));
    if(relevant)schedule(60);
  });
  observer.observe(list,{childList:true,subtree:true});
}

installStyle();
queueMicrotask(()=>{observe();schedule()});
document.addEventListener("app:tab",event=>{if(event.detail==="add"){observe();schedule()}});
document.addEventListener("click",event=>{
  if(event.target.closest("[data-add-execute],#add-batch-start,#add-refresh,#add-materialize"))schedule(120);
});
