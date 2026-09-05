import {get} from "./api.js";
import {polling} from "./polling.js";

const $=(selector,root=document)=>root.querySelector(selector);
let lastStructure="";
let busy=false;

function active(){return $("[data-page='add']")?.classList.contains("active")}
function query(){
  return new URLSearchParams({
    query:$("#add-query")?.value||"",
    group:$("#add-group")?.value||"",
    stage:$("#add-stage")?.value||"",
    page:String((()=>{const match=($("#add-page")?.textContent||"").match(/Página\s+(\d+)/i);return Number(match?.[1]||1)})()),
    page_size:$("#add-page-size")?.value||"5",
  });
}
function structure(data){
  return JSON.stringify({
    page:data.page,total:data.total,pages:data.pages,
    items:(data.items||[]).map(job=>[job.job_id,job.state,Number(job.attempts||0),Number(job.woo_product_id||0),job.error?.message||""]),
  });
}
function cards(counts={}){
  const mapping={"":"total",prepared:"prepared",running:"running",success:"success",error:"error"};
  document.querySelectorAll("#add-cards [data-add-group]").forEach(button=>{
    const key=mapping[button.dataset.addGroup??""];
    const value=button.querySelector("strong");
    if(value&&key)value.textContent=String(counts[key]??0);
  });
}
function batchView(batch={}){
  const total=Number(batch.total||0),done=Number(batch.processed||0),percent=total?Math.round(done*100/total):0;
  const percentNode=$("#add-progress-percent"),countNode=$("#add-progress-count"),fill=$("#add-progress-fill"),status=$("#add-operation-status");
  if(percentNode)percentNode.textContent=`${percent}%`;
  if(countNode)countNode.textContent=`${done} de ${total} processados`;
  if(fill){fill.style.transform=`scaleX(${percent/100})`;fill.parentElement?.setAttribute("aria-valuenow",String(percent))}
  if(status){
    status.textContent=batch.running?(batch.paused?"Lote pausado.":"Adição em execução."):batch.cancelled?"Pendentes cancelados.":total&&done>=total?(batch.errors?`Lote concluído com ${batch.errors} erro(s).`:"Lote concluído."):"Nenhuma adição em execução.";
    status.className=`operation-band ${batch.running?"loading":batch.errors?"error":"info"}`;
  }
  const actions=$("#add-running-actions");if(actions)actions.hidden=!batch.running;
  const pause=$("#add-batch-pause"),resume=$("#add-batch-resume"),cancel=$("#add-batch-cancel");
  if(pause)pause.disabled=!batch.running||batch.paused;
  if(resume)resume.disabled=!batch.running||!batch.paused;
  if(cancel)cancel.disabled=!batch.running||!batch.pending;
}
async function tick(){
  if(busy||!active())return;
  busy=true;
  try{
    const data=await get(`/api/additions/jobs?${query()}`);
    cards(data.counts||{});batchView(data.batch||{});
    const next=structure(data);
    if(!lastStructure){lastStructure=next;return}
    if(next!==lastStructure){
      lastStructure=next;
      // A renderização completa só acontece quando a estrutura/estado realmente
      // mudou. Etapas e logs em andamento são atualizados pelo add-live-progress.
      $("#add-refresh")?.click();
    }
  }catch{}
  finally{busy=false}
}

queueMicrotask(()=>{
  polling.stop("addition-state");
  polling.stop("addition-state-stable");
  polling.register("addition-state-stable",tick,1400);
});
document.addEventListener("app:tab",event=>{if(event.detail==="add"){lastStructure="";setTimeout(tick,80)}});
document.addEventListener("change",event=>{if(event.target.closest("#add-query,#add-group,#add-stage,#add-page-size"))lastStructure=""});
document.addEventListener("click",event=>{if(event.target.closest("#add-refresh,#add-filter-clear,#add-prev,#add-next,#add-batch-start,[data-add-execute]"))lastStructure=""});
