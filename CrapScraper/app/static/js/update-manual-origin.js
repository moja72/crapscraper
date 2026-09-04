import {get} from "./api.js";

const cache=new Map();
const pending=new Map();

async function job(id){
  if(cache.has(id))return cache.get(id);
  if(pending.has(id))return pending.get(id);
  const request=get(`/api/updates/job?job_id=${encodeURIComponent(id)}`)
    .then(data=>{const item=data.item||{};cache.set(id,item);return item})
    .finally(()=>pending.delete(id));
  pending.set(id,request);
  return request;
}

async function decorate(card){
  if(card.dataset.manualOriginChecked==="1")return;
  const id=card.dataset.jobId||"";
  if(!id)return;
  card.dataset.manualOriginChecked="1";
  try{
    const item=await job(id);
    if(!card.isConnected||item.execution_origin!=="manual")return;
    const state=card.querySelector(".update-job-state");
    if(!state||state.querySelector("[data-update-origin]"))return;
    const line=document.createElement("small");
    line.dataset.updateOrigin="manual";
    line.textContent="Manual";
    line.title="Atualização executada a partir do MU-plugin CrapScraper no WordPress.";
    state.appendChild(line);
  }catch(_error){
    delete card.dataset.manualOriginChecked;
  }
}

function scan(){
  document.querySelectorAll("#update-list .update-job-card").forEach(card=>void decorate(card));
}

const list=document.querySelector("#update-list");
if(list)new MutationObserver(scan).observe(list,{childList:true,subtree:true});
document.addEventListener("app:tab",event=>{if(event.detail==="update")scan()});
queueMicrotask(scan);
