import {get} from "./api.js";

const $=selector=>document.querySelector(selector);
let registryPromise=null;
let changeVersion=0;

const option=(value,label)=>`<option value="${value}">${label}</option>`;
const registry=()=>registryPromise||(registryPromise=get("/api/collection/context"));

function normalizeDependencies(data,{siteKey,typeKey,accountKey}){
  const site=$("#collect-site"),type=$("#collect-type"),account=$("#collect-account");
  if(!site||!type||!account)return null;

  const siteRow=(data.sites||[]).find(item=>item.key===siteKey);
  if(!siteRow)return null;

  const allowedTypes=(data.item_types||[]).filter(item=>(siteRow.item_types||[]).includes(item.key));
  const resolvedType=allowedTypes.some(item=>item.key===typeKey)?typeKey:(allowedTypes[0]?.key||"");

  site.value=siteKey;
  type.innerHTML=allowedTypes.map(item=>option(item.key,item.label)).join("");
  type.value=resolvedType;

  const allowedAccounts=(data.accounts||[]).filter(item=>(item.sites||[]).includes(siteKey)&&(item.item_types||[]).includes(resolvedType));
  const resolvedAccount=allowedAccounts.some(item=>item.key===accountKey)?accountKey:(allowedAccounts[0]?.key||"");
  account.innerHTML=allowedAccounts.map(item=>option(item.key,item.label)).join("");
  account.value=resolvedAccount;

  return {siteKey,resolvedType,resolvedAccount};
}

document.addEventListener("change",event=>{
  const target=event.target;
  if(!(target instanceof HTMLSelectElement)||!target.matches("#collect-site,#collect-type"))return;

  event.stopImmediatePropagation();
  const version=++changeVersion;
  const desired={
    siteKey:target.id==="collect-site"?target.value:$("#collect-site")?.value||"",
    typeKey:target.id==="collect-type"?target.value:$("#collect-type")?.value||"",
    accountKey:$("#collect-account")?.value||"",
  };

  registry().then(data=>{
    if(version!==changeVersion)return;
    const normalized=normalizeDependencies(data,desired);
    if(!normalized)return;
    $("#collect-account")?.dispatchEvent(new Event("change",{bubbles:true}));
  }).catch(error=>{
    console.error("Falha ao normalizar dependências do contexto de coleta:",error);
  });
},true);
