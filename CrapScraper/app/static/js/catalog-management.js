import {get,post} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);
let rowsById=new Map();
let syncTimer;

const fallbackLabel=id=>String(id||"").split("/").at(-1)?.replace(/\.csv$/i,"")||String(id||"Catálogo");
const rowLabel=row=>String(row?.display_name||row?.label||fallbackLabel(row?.id)).trim();
const pluginTemaRows=rows=>rows.filter(row=>{
  const id=String(row?.id||"").toLowerCase();
  return id.includes("plugintema")&&!id.includes("plugintheme");
});

async function syncRows(){
  const data=await get("/api/catalogs?page_size=100");
  rowsById=new Map(pluginTemaRows(data.rows||[]).map(row=>[String(row.id),row]));
  patchAll();
  return data;
}

function catalogIdFromCard(card){
  return $("[data-catalog-preview]",card)?.dataset.catalogPreview||$("[data-catalog-download]",card)?.dataset.catalogDownload||$("[data-catalog-use]",card)?.dataset.catalogUse||"";
}

function patchCard(card){
  const id=catalogIdFromCard(card);
  if(!id)return;
  const row=rowsById.get(id);
  const title=$("h3",card);
  if(title){
    title.textContent=row?rowLabel(row):title.textContent;
    title.title=id;
  }
  const actions=$(".compact-actions",card);
  if(!actions||actions.dataset.catalogManagementReady==="1")return;
  actions.dataset.catalogManagementReady="1";
  actions.insertAdjacentHTML("beforeend",`<button type="button" data-catalog-name="${id.replaceAll('&','&amp;').replaceAll('"','&quot;')}">Renomear</button><button type="button" data-catalog-delete="${id.replaceAll('&','&amp;').replaceAll('"','&quot;')}">Excluir</button>`);
}

function patchSiteSelect(){
  const select=$("#comparison-site");
  if(!select)return;
  [...select.options].forEach(option=>{
    const row=rowsById.get(option.value);
    if(row)option.textContent=rowLabel(row);
  });
}

function patchAll(){
  document.querySelectorAll("#comparison-catalog-list .catalog-card").forEach(patchCard);
  patchSiteSelect();
}

async function refreshSiteSelect(){
  const select=$("#comparison-site");
  if(!select)return;
  const data=await get("/api/comparison/catalogs");
  const sites=(data.catalogs||[]).filter(row=>row.role==="site");
  select.innerHTML='<option value="">Selecione</option>'+sites.map(row=>{
    const managed=rowsById.get(String(row.id));
    const label=managed?rowLabel(managed):fallbackLabel(row.id);
    const value=String(row.id).replaceAll('&','&amp;').replaceAll('"','&quot;');
    return `<option value="${value}">${label.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}</option>`;
  }).join("");
  select.value=data.site_id||"";
}

function scheduleSync(){
  clearTimeout(syncTimer);
  syncTimer=setTimeout(()=>syncRows().catch(()=>{}),50);
}

const observer=new MutationObserver(mutations=>{
  if(mutations.some(mutation=>mutation.target.closest?.("#comparison-catalog-list")||mutation.target.id==="comparison-site"))scheduleSync();
});
observer.observe(document.body,{childList:true,subtree:true});

async function renameCatalog(button){
  const id=button.dataset.catalogName;
  const row=rowsById.get(id);
  const current=row?.display_name||$("h3",button.closest(".catalog-card"))?.textContent||fallbackLabel(id);
  const requested=window.prompt("Nome do catálogo:",current);
  if(requested===null)return;
  const name=requested.trim();
  if(!name){window.alert("Informe um nome para o catálogo.");return;}
  button.disabled=true;
  try{
    const response=await post("/api/catalogs/name",{catalog_id:id,name});
    if(response.catalog)rowsById.set(id,response.catalog);
    patchAll();
  }catch(error){
    window.alert(`Não foi possível renomear o catálogo. ${error.message}`);
  }finally{button.disabled=false;}
}

async function deleteCatalog(button){
  const id=button.dataset.catalogDelete;
  const row=rowsById.get(id);
  const card=button.closest(".catalog-card");
  const title=row?rowLabel(row):$("h3",card)?.textContent||fallbackLabel(id);
  if(!window.confirm(`Excluir permanentemente o catálogo “${title}”?\n\nO arquivo CSV será removido e esta ação não poderá ser desfeita.`))return;
  button.disabled=true;
  try{
    await post("/api/catalogs/delete",{catalog_id:id});
    card?.remove();
    rowsById.delete(id);
    const preview=$("#comparison-catalog-preview");
    if(preview){preview.className="preview-empty";preview.textContent="Selecione um catálogo.";}
    const list=$("#comparison-catalog-list");
    if(list&&!list.querySelector(".catalog-card"))list.innerHTML='<div class="empty">Nenhum catálogo PluginTema disponível.</div>';
    await syncRows();
    await refreshSiteSelect();
  }catch(error){
    window.alert(`Não foi possível excluir o catálogo. ${error.message}`);
    button.disabled=false;
  }
}

document.addEventListener("click",event=>{
  if(event.target.closest("#comparison-manage-catalogs"))scheduleSync();
  const rename=event.target.closest("[data-catalog-name]");
  if(rename){event.preventDefault();event.stopPropagation();renameCatalog(rename);return;}
  const remove=event.target.closest("[data-catalog-delete]");
  if(remove){event.preventDefault();event.stopPropagation();deleteCatalog(remove);}
});

syncRows().catch(()=>{});
