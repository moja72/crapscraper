const sourceLabels={plugintheme:"PluginTheme",ultrapackv2:"UltraPackV2"};
const nativeFetch=window.fetch.bind(window);

function selectedSources(scope){
  const boxes=[...document.querySelectorAll(`[data-queue-source="${scope}"]`)];
  if(!boxes.length)return null;
  const selected=boxes.filter(box=>box.checked).map(box=>box.value);
  return selected.length?selected.join(","):"__none__";
}

function withSourceQuery(url,scope){
  const selected=selectedSources(scope);if(selected===null)return url;
  const parsed=new URL(url,location.href);parsed.searchParams.set("sources",selected);
  return parsed.pathname+parsed.search+parsed.hash;
}

window.fetch=async function(input,init={}){
  if(typeof input!=="string")return nativeFetch(input,init);
  let path=input,options=init||{};
  const parsed=new URL(path,location.href),method=String(options.method||"GET").toUpperCase();
  if(method==="GET"&&parsed.pathname==="/api/updates/jobs")path=withSourceQuery(path,"update");
  if(method==="GET"&&parsed.pathname==="/api/additions/jobs")path=withSourceQuery(path,"add");
  if(method==="POST"&&parsed.pathname==="/api/updates/selection"){
    const selected=selectedSources("update");
    if(selected!==null){
      let body={};try{body=JSON.parse(String(options.body||"{}"))}catch{}
      options={...options,body:JSON.stringify({...body,sources:selected})};
    }
  }
  return nativeFetch(path,options);
};

function styles(){
  if(document.querySelector("#runtime-fixes-style"))return;
  document.head.insertAdjacentHTML("beforeend",`<style id="runtime-fixes-style">
  @keyframes cs-runtime-spin{to{transform:rotate(360deg)}}
  .operation-band.loading{position:relative;padding-left:38px}
  .operation-band.loading::before{content:"";position:absolute;left:13px;top:50%;width:14px;height:14px;margin-top:-8px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:cs-runtime-spin .72s linear infinite}
  .runtime-source-filter{min-width:210px;margin:0;padding:0;border:0;display:grid;gap:6px;align-content:end}
  .runtime-source-filter legend{padding:0;margin:0 0 1px;font-size:12px;font-weight:700}
  .runtime-source-options{min-height:36px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:7px 10px;border:1px solid var(--border,#344054);border-radius:7px;background:var(--panel,#101827)}
  .runtime-source-options label{display:inline-flex!important;grid-template-columns:none!important;gap:6px!important;align-items:center;font-size:12px;white-space:nowrap;cursor:pointer}
  .runtime-source-options input{width:auto!important;margin:0}
  .runtime-immediate-feedback{margin-top:8px;padding:8px 10px;border:1px solid var(--border,#344054);border-radius:7px;font-size:12px;display:flex;align-items:center;gap:8px}
  .runtime-immediate-feedback::before{content:"";width:12px;height:12px;flex:0 0 12px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:cs-runtime-spin .72s linear infinite}
  @media(max-width:700px){.runtime-source-filter{min-width:0}.runtime-source-options{align-items:flex-start;flex-direction:column}}
  </style>`);
}

function sourceField(scope){
  const field=document.createElement("fieldset");field.className="runtime-source-filter";field.dataset.sourceFilterScope=scope;
  field.innerHTML=`<legend>Fonte</legend><div class="runtime-source-options">${Object.entries(sourceLabels).map(([value,label])=>`<label><input type="checkbox" data-queue-source="${scope}" value="${value}" checked> ${label}</label>`).join("")}</div>`;
  return field;
}

function installSourceFilter(scope){
  if(document.querySelector(`[data-source-filter-scope="${scope}"]`))return;
  const grid=document.querySelector(scope==="update"?"#update-queue .update-filter-grid":"#add-queue .update-filter-grid");
  if(!grid)return;
  const actions=grid.querySelector(".filter-actions");
  const field=sourceField(scope);actions?grid.insertBefore(field,actions):grid.append(field);
}

function installFilters(){installSourceFilter("update");installSourceFilter("add")}

function resetSources(scope){
  document.querySelectorAll(`[data-queue-source="${scope}"]`).forEach(box=>box.checked=true);
}

function immediateExecutionFeedback(button){
  const card=button.closest(".update-job-card");if(!card)return;
  const main=card.querySelector(".update-job-main"),name=main?.querySelector(":scope > strong")?.textContent?.trim()||"produto";
  card.querySelectorAll("[data-runtime-execution-feedback]").forEach(node=>node.remove());
  const feedback=document.createElement("div");feedback.className="runtime-immediate-feedback";feedback.dataset.runtimeExecutionFeedback="1";
  feedback.setAttribute("role","status");feedback.setAttribute("aria-live","polite");feedback.textContent="Solicitação recebida. Validando pré-requisitos e autenticando a fonte…";
  main?.append(feedback);
  const status=document.querySelector("#update-operation-status");
  if(status){status.textContent=`Iniciando atualização de ${name}…`;status.className="operation-band loading"}
}

styles();installFilters();

// A aba Adicionar constrói o próprio HTML em JavaScript. O observer cobre tanto
// a primeira montagem quanto qualquer futura reconstrução da fila.
new MutationObserver(installFilters).observe(document.documentElement,{childList:true,subtree:true});

document.addEventListener("change",event=>{
  const box=event.target.closest?.("[data-queue-source]");if(!box)return;
  const scope=box.dataset.queueSource;
  const clear=document.querySelector(scope==="update"?"#update-clear-selection":"#add-clear-selection");clear?.click();
  const refresh=document.querySelector(scope==="update"?"#update-refresh":"#add-refresh");refresh?.click();
});

document.addEventListener("click",event=>{
  if(event.target.closest?.("#update-filter-clear"))resetSources("update");
  if(event.target.closest?.("#add-filter-clear"))resetSources("add");
  const execute=event.target.closest?.("[data-update-execute]");if(execute&&!execute.disabled)immediateExecutionFeedback(execute);
},true);
