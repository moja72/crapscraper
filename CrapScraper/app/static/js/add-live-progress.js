import {get} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);

const stages=[
  ["resolving_source","Confirmando fonte"],
  ["downloading","Baixando ZIP"],
  ["validating_zip","Validando ZIP"],
  ["generating_description","Gerando descrição no ChatGPT"],
  ["generating_image","Gerando imagem no ChatGPT"],
  ["saving_image","Salvando imagem gerada"],
  ["validating_image","Validando imagem"],
  ["preparing_payload","Preparando payload do produto"],
  ["uploading_image","Enviando mídia"],
  ["creating_woocommerce","Criando produto WooCommerce"],
  ["creating_variations","Criando variações"],
  ["validating_result","Validando resultado"],
  ["completed","Concluído"],
];
const aliases=new Map([
  ["validating","resolving_source"],
  ["reconciling_woocommerce","preparing_payload"],
  ["uploading_file","preparing_payload"],
]);
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
    #add-list .add-live-progress .update-job-live-log{max-height:104px}
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
  const raw=String(job.stage||"resolving_source");
  const normalized=aliases.get(raw)||raw;
  if(normalized==="resolving_source"&&Number(job.woo_product_id||0)>0)return "validating_result";
  return stageIndex.has(normalized)?normalized:"resolving_source";
}

function ensureProgress(row,job){
  let progressRow=row.nextElementSibling;
  if(!progressRow?.matches(`tr[data-add-progress-for="${CSS.escape(String(job.job_id))}"]`)){
    progressRow=document.createElement("tr");
    progressRow.className="add-live-progress-row";
    progressRow.dataset.addProgressFor=String(job.job_id);
    const cell=document.createElement("td");
    cell.innerHTML=`<section class="update-job-progress add-live-progress"><div class="update-job-progress-head"><strong data-add-progress-label></strong><small data-add-progress-step></small></div><progress max="13" value="1"></progress><ol class="update-job-live-log" role="log" aria-live="polite" aria-relevant="additions text"></ol></section>`;
    progressRow.appendChild(cell);
    row.after(progressRow);
  }
  const cell=progressRow.firstElementChild;
  cell.colSpan=Math.max(1,row.children.length);
  return cell.querySelector(".add-live-progress");
}

function updateProgress(row,job){
  const box=ensureProgress(row,job);
  if(!box)return;
  const stage=effectiveStage(job);
  const total=stages.length;
  const step=job.state==="success"?total:Math.max(1,stageIndex.get(stage)||1);
  const label=stageLabel.get(stage)||String(job.stage||"Em andamento");
  const state=job.state==="error"?"error":job.state==="success"?"complete":job.state==="running"?"running":"idle";
  box.dataset.progressState=state;
  box.setAttribute("aria-label",`Progresso de ${String(job.product_name||"")}`);
  const labelNode=$("[data-add-progress-label]",box);if(labelNode&&labelNode.textContent!==label)labelNode.textContent=label;
  const stepNode=$("[data-add-progress-step]",box);const stepText=`Etapa ${step} de ${total}`;if(stepNode&&stepNode.textContent!==stepText)stepNode.textContent=stepText;
  const progress=$("progress",box);if(progress){progress.max=total;if(Number(progress.value)!==step)progress.value=step;progress.setAttribute("aria-label",label)}
  const log=$(".update-job-live-log",box);
  if(log){
    const lines=(job.logs||[]).slice(-4);
    const next=JSON.stringify(lines.length?lines:[label]);
    if(log.dataset.snapshot!==next){
      log.dataset.snapshot=next;
      log.replaceChildren(...JSON.parse(next).map(line=>{const li=document.createElement("li");li.textContent=String(line);return li}));
    }
  }
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
        updateProgress(row,job);
      }catch{}
    }));
    removeOrphans();
  }finally{
    busy=false;
    if(hasRunning)timer=setTimeout(refreshProgress,900);
  }
}

function schedule(delay=80){clearTimeout(timer);timer=setTimeout(refreshProgress,delay)}

function observe(){
  const list=$("#add-list");
  if(!list||list.dataset.addLiveProgressObserved==="1")return;
  list.dataset.addLiveProgressObserved="1";
  observer?.disconnect();
  observer=new MutationObserver(mutations=>{
    const relevant=mutations.some(mutation=>[...mutation.addedNodes].some(node=>node.nodeType===1&&!node.matches?.("tr.add-live-progress-row")&&!node.matches?.("[data-add-date-column]")));
    if(relevant)schedule(80);
  });
  observer.observe(list,{childList:true,subtree:true});
}

installStyle();
queueMicrotask(()=>{observe();schedule()});
document.addEventListener("app:tab",event=>{if(event.detail==="add"){observe();schedule()}});
document.addEventListener("click",event=>{if(event.target.closest("[data-add-execute],#add-batch-start,#add-refresh,#add-materialize"))schedule(140)});
