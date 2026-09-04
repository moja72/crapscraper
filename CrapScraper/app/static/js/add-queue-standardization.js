import {get} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);
const formatDate=value=>{
  if(!value)return "—";
  const date=new Date(value);
  if(Number.isNaN(date.valueOf()))return String(value);
  return date.toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"short"});
};

let jobs=new Map();
let loading=false;
let timer=null;
let decorating=false;
let listObserver=null;

function installStyle(){
  if($("#add-queue-standardization-style"))return;
  const style=document.createElement("style");
  style.id="add-queue-standardization-style";
  style.textContent=`
    .mascot-crop{width:96px!important;height:82px!important;flex:0 0 96px!important}
    .mascot-crop img{height:154px!important;max-width:none!important;transform:translate(-3px,-25px)!important}
    #add-queue table th[data-add-date-column],#add-queue table td[data-add-date-column]{white-space:nowrap;min-width:132px}
    #add-queue .add-auto-sync-note{display:inline-flex;align-items:center;gap:6px;margin-top:4px;color:var(--muted);font-size:12px}
    #add-queue .add-auto-sync-note::before{content:"↻";color:var(--accent);font-weight:700}
  `;
  document.head.appendChild(style);
}

function ensureQueueStructure(){
  const queue=$("#add-queue");
  if(!queue)return false;
  const title=$(".section-head h2",queue);
  if(title&&title.textContent!=="Fila de adição")title.textContent="Fila de adição";
  const description=$(".section-head p",queue);
  const queueDescription="Revise os itens aprovados, acompanhe datas, estado e tentativas e execute somente o que estiver pronto para criação.";
  if(description&&description.textContent!==queueDescription)description.textContent=queueDescription;
  if(!$(".add-auto-sync-note",queue)){
    const guidance=$(".add-guidance",queue);
    guidance?.insertAdjacentHTML("afterend",'<small class="add-auto-sync-note">Novas aprovações são sincronizadas automaticamente ao carregar ou atualizar esta fila.</small>');
  }
  const syncButton=$("#add-materialize");
  if(syncButton){
    if(syncButton.textContent!=="Sincronizar aprovados agora")syncButton.textContent="Sincronizar aprovados agora";
    syncButton.title="A sincronização já é automática; use este botão para forçar uma leitura imediata.";
  }
  const headerRow=$("table thead tr",queue);
  if(headerRow&&!headerRow.dataset.addDatesReady){
    const headers=[...headerRow.children];
    const wooIndex=headers.findIndex(cell=>cell.textContent.trim()==="WooCommerce");
    const targetIndex=wooIndex>=0?wooIndex:Math.max(0,headers.length-3);
    const entry=document.createElement("th");entry.textContent="Entrada na fila";entry.dataset.addDateColumn="entry";
    const updated=document.createElement("th");updated.textContent="Última atualização";updated.dataset.addDateColumn="updated";
    headerRow.insertBefore(entry,headerRow.children[targetIndex]||null);
    headerRow.insertBefore(updated,headerRow.children[targetIndex+1]||null);
    headerRow.dataset.addDatesReady="1";
  }
  const empty=$("#add-list tr .empty",queue);
  if(empty&&empty.colSpan!==9)empty.colSpan=9;
  return true;
}

function decorateRows(){
  if(decorating)return;
  decorating=true;
  try{
    if(!ensureQueueStructure())return;
    document.querySelectorAll("#add-list tr[data-add-job]").forEach(row=>{
      const job=jobs.get(row.dataset.addJob);
      if(!job)return;
      let entry=row.querySelector('td[data-add-date-column="entry"]');
      let updated=row.querySelector('td[data-add-date-column="updated"]');
      if(!entry||!updated){
        const cells=[...row.children];
        const wooIndex=Math.max(0,cells.length-3);
        entry=document.createElement("td");entry.dataset.addDateColumn="entry";
        updated=document.createElement("td");updated.dataset.addDateColumn="updated";
        row.insertBefore(entry,row.children[wooIndex]||null);
        row.insertBefore(updated,row.children[wooIndex+1]||null);
      }
      const entryText=formatDate(job.created_at);
      const updatedText=formatDate(job.finished_at||job.updated_at||job.started_at);
      if(entry.textContent!==entryText)entry.textContent=entryText;
      if(updated.textContent!==updatedText)updated.textContent=updatedText;
      entry.title=String(job.created_at||"");
      updated.title=String(job.finished_at||job.updated_at||job.started_at||"");
    });
  }finally{
    decorating=false;
  }
}

function observeList(){
  const list=$("#add-list");
  if(!list||list.dataset.addQueueObserved==="1")return;
  list.dataset.addQueueObserved="1";
  listObserver?.disconnect();
  listObserver=new MutationObserver(mutations=>{
    if(decorating)return;
    const externalChange=mutations.some(mutation=>[...mutation.addedNodes].some(node=>node.nodeType===1&&!node.matches?.('[data-add-date-column]')));
    if(externalChange)schedule();
  });
  listObserver.observe(list,{childList:true,subtree:true});
}

async function loadJobs(){
  if(loading)return;
  if(!$("[data-page='add']"))return;
  loading=true;
  try{
    const first=await get("/api/additions?page=1&page_size=100&sort_by=date&sort_order=desc");
    const all=[...(first.items||[])];
    for(let page=2;page<=Number(first.pages||1);page++){
      const data=await get(`/api/additions?page=${page}&page_size=100&sort_by=date&sort_order=desc`);
      all.push(...(data.items||[]));
    }
    jobs=new Map(all.map(job=>[String(job.job_id),job]));
  }finally{
    loading=false;
    decorateRows();
    observeList();
  }
}

function schedule(){
  clearTimeout(timer);
  timer=setTimeout(()=>{decorateRows();observeList();loadJobs().catch(()=>{})},80);
}

installStyle();
queueMicrotask(schedule);
setTimeout(schedule,0);

document.addEventListener("app:tab",event=>{if(event.detail==="add")schedule()});
document.addEventListener("click",event=>{
  if(event.target.closest("#add-refresh,#add-materialize,[data-add-execute],#add-batch-start,#add-filter-clear,#add-prev,#add-next"))setTimeout(schedule,180);
});
