import {get,post} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);
const esc=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

let rowsById=new Map();
let syncTimer;
let previewTimer;
let openingExistingCatalog=false;
const previewState={catalogId:"",page:1,pageSize:20,query:"",pagination:{page:1,total_pages:1,total_rows:0,page_size:20}};

const isPluginTema=row=>{
  const id=String(row?.id||"").toLowerCase();
  return id.includes("plugintema")&&!id.includes("plugintheme");
};
const pluginTemaRows=rows=>(rows||[]).filter(isPluginTema);
const filename=id=>String(id||"").split("/").at(-1)||String(id||"Catálogo");

function timestampFromFilename(id){
  const name=filename(id);
  const match=name.match(/(20\d{6})[-_](\d{6})(?:[-_]\d+)?\.csv$/i);
  if(!match)return"";
  const date=match[1],time=match[2];
  return `${date.slice(6,8)}/${date.slice(4,6)}/${date.slice(0,4)} ${time.slice(0,2)}:${time.slice(2,4)}`;
}

function defaultCatalogName(row){
  const name=filename(row?.id).replace(/\.csv$/i,"");
  const lower=name.toLowerCase();
  let scope="Catálogo";
  if(lower.includes("todos_plugins")||lower.includes("todos-plugins"))scope="Plugins";
  else if(lower.includes("todos_temas")||lower.includes("todos-temas"))scope="Temas";
  else if(lower.includes("selection-tudo")||lower.includes("selection_tudo"))scope="Todos os produtos";
  else if(lower.includes("products"))scope="Produtos";
  else if(lower.includes("selection"))scope="Seleção";
  else if(lower.includes("custom"))scope="Personalizado";
  const when=timestampFromFilename(row?.id);
  return `PluginTema · ${scope}${when?` · ${when}`:""}`;
}

function rowLabel(row){
  const custom=String(row?.display_name||"").trim();
  return custom||defaultCatalogName(row);
}

function resetPreview(message="Selecione um catálogo para visualizar todos os itens."){
  previewState.catalogId="";previewState.page=1;previewState.query="";
  const input=$("#comparison-catalog-preview-search");if(input)input.value="";
  const content=$("#comparison-catalog-preview");
  if(content){content.className="preview-empty";content.textContent=message;}
  const meta=$("#comparison-catalog-preview-meta");if(meta)meta.textContent="";
  const controls=$("#comparison-catalog-preview-controls");if(controls)controls.hidden=true;
}

function ensureManagementUi(){
  const modal=$("#comparison-catalog-modal");
  if(!modal)return false;
  const list=$("#comparison-catalog-list",modal);
  if(list&&!$("#comparison-catalog-management-toolbar",modal)){
    list.insertAdjacentHTML("beforebegin",`<div id="comparison-catalog-management-toolbar" class="section-toolbar"><div><strong>Gerenciamento dos catálogos</strong><small id="comparison-catalog-count"></small></div><button type="button" id="comparison-catalog-delete-all" class="danger">Excluir todos os catálogos PluginTema</button></div>`);
  }
  const section=$(".catalog-preview",modal);
  if(section&&!$("#comparison-catalog-preview-tools",section)){
    const heading=$("h3",section);
    if(heading)heading.id="comparison-catalog-preview-title";
    (heading||section.firstChild)?.insertAdjacentHTML?.("afterend",`<div id="comparison-catalog-preview-tools" class="catalog-toolbar"><label>Buscar no catálogo<input id="comparison-catalog-preview-search" type="search" placeholder="Nome, ID, versão, categoria…" disabled></label><label>Itens por página<select id="comparison-catalog-preview-page-size" disabled><option value="10">10</option><option value="20" selected>20</option><option value="50">50</option><option value="100">100</option></select></label></div><div id="comparison-catalog-preview-meta" class="catalog-count-row"></div>`);
    section.insertAdjacentHTML("beforeend",`<div id="comparison-catalog-preview-controls" class="pager" hidden><button type="button" id="comparison-catalog-preview-prev">Anterior</button><label>Página <input id="comparison-catalog-preview-page" type="number" min="1" value="1"> de <span id="comparison-catalog-preview-pages">1</span></label><button type="button" id="comparison-catalog-preview-next">Próxima</button></div>`);
  }
  updateCount();
  return true;
}

function updateCount(){
  const count=$("#comparison-catalog-count");
  if(count)count.textContent=`${rowsById.size} catálogo(s) PluginTema`;
  const removeAll=$("#comparison-catalog-delete-all");
  if(removeAll)removeAll.disabled=!rowsById.size;
}

async function syncRows(){
  const first=await get("/api/catalogs?page=1&page_size=100");
  const rows=[...(first.rows||[])];
  const totalPages=Math.max(1,Number(first.pagination?.total_pages||1));
  for(let page=2;page<=totalPages;page++){
    const data=await get(`/api/catalogs?page=${page}&page_size=100`);
    rows.push(...(data.rows||[]));
  }
  rowsById=new Map(pluginTemaRows(rows).map(row=>[String(row.id),row]));
  ensureManagementUi();
  patchAll();
  return {...first,rows};
}

function catalogIdFromCard(card){
  return $("[data-catalog-preview]",card)?.dataset.catalogPreview||$("[data-catalog-download]",card)?.dataset.catalogDownload||$("[data-catalog-use]",card)?.dataset.catalogUse||"";
}

function patchCard(card){
  const id=catalogIdFromCard(card);
  if(!id)return;
  const row=rowsById.get(id);
  const title=$("h3",card);
  if(title){const next=row?rowLabel(row):defaultCatalogName({id});if(title.textContent!==next)title.textContent=next;if(title.title!==id)title.title=id;}
  const actions=$(".compact-actions",card);
  if(!actions||actions.dataset.catalogManagementReady==="1")return;
  actions.dataset.catalogManagementReady="1";
  actions.insertAdjacentHTML("beforeend",`<button type="button" data-catalog-update="${esc(id)}">Atualizar</button><button type="button" data-catalog-name="${esc(id)}">Renomear</button><button type="button" class="danger" data-catalog-delete="${esc(id)}">Excluir</button>`);
}

function patchSiteSelect(){
  const select=$("#comparison-site");
  if(!select)return;
  [...select.options].forEach(option=>{
    const row=rowsById.get(option.value);
    if(row){const next=rowLabel(row);if(option.textContent!==next)option.textContent=next;}
  });
}

function patchAll(){
  document.querySelectorAll("#comparison-catalog-list .catalog-card").forEach(patchCard);
  patchSiteSelect();
  updateCount();
}

async function refreshSiteSelect(){
  const select=$("#comparison-site");
  if(!select)return;
  const data=await get("/api/comparison/catalogs");
  const sites=(data.catalogs||[]).filter(row=>row.role==="site");
  select.innerHTML='<option value="">Selecione</option>'+sites.map(row=>{
    const managed=rowsById.get(String(row.id));
    const label=managed?rowLabel(managed):defaultCatalogName(row);
    return `<option value="${esc(row.id)}">${esc(label)}</option>`;
  }).join("");
  select.value=data.site_id||"";
}

function scheduleSync(){
  clearTimeout(syncTimer);
  syncTimer=setTimeout(()=>syncRows().catch(()=>{}),40);
}

async function renameCatalog(button){
  const id=button.dataset.catalogName;
  const row=rowsById.get(id)||{id};
  const current=rowLabel(row);
  const requested=window.prompt("Nome do catálogo:",current);
  if(requested===null)return;
  const name=requested.trim().replace(/\s+/g," ");
  if(!name){window.alert("Informe um nome para o catálogo.");return;}
  button.disabled=true;
  try{
    const response=await post("/api/catalogs/name",{catalog_id:id,name});
    if(response.catalog)rowsById.set(id,response.catalog);
    await syncRows();
    await refreshSiteSelect();
    patchAll();
  }catch(error){
    window.alert(`Não foi possível renomear o catálogo. ${error.message}`);
  }finally{button.disabled=false;}
}

async function deleteCatalog(button){
  const id=button.dataset.catalogDelete;
  const row=rowsById.get(id)||{id};
  const title=rowLabel(row);
  if(!window.confirm(`Excluir permanentemente o catálogo “${title}”?\n\nO arquivo CSV será removido e esta ação não poderá ser desfeita.`))return;
  button.disabled=true;
  try{
    await post("/api/catalogs/delete",{catalog_id:id});
    rowsById.delete(id);
    button.closest(".catalog-card")?.remove();
    if(previewState.catalogId===id)resetPreview("O catálogo visualizado foi excluído.");
    const list=$("#comparison-catalog-list");
    if(list&&!list.querySelector(".catalog-card"))list.innerHTML='<div class="empty">Nenhum catálogo PluginTema disponível.</div>';
    await syncRows();
    await refreshSiteSelect();
  }catch(error){
    window.alert(`Não foi possível excluir o catálogo. ${error.message}`);
    button.disabled=false;
  }
}

async function deleteAllCatalogs(button){
  await syncRows();
  const rows=[...rowsById.values()];
  if(!rows.length)return;
  if(!window.confirm(`Excluir permanentemente TODOS os ${rows.length} catálogos PluginTema?\n\nTodos os arquivos CSV listados neste modal serão removidos. Esta ação não poderá ser desfeita.`))return;
  button.disabled=true;
  const failed=[];
  let deleted=0;
  for(const row of rows){
    try{await post("/api/catalogs/delete",{catalog_id:row.id});deleted++;}
    catch(error){failed.push(`${rowLabel(row)}: ${error.message}`);}
  }
  await syncRows();
  await refreshSiteSelect();
  resetPreview(deleted?`${deleted} catálogo(s) PluginTema excluído(s).`:"Nenhum catálogo foi excluído.");
  const list=$("#comparison-catalog-list");
  if(list&&!rowsById.size)list.innerHTML='<div class="empty">Nenhum catálogo PluginTema disponível.</div>';
  button.disabled=!rowsById.size;
  if(failed.length)window.alert(`Foram excluídos ${deleted} catálogo(s), mas ${failed.length} falharam:\n\n${failed.join("\n")}`);
}

function waitUntil(test,timeout=6000){
  return new Promise((resolve,reject)=>{
    const started=Date.now();
    const tick=()=>{
      let value;
      try{value=test();}catch(_error){value=false;}
      if(value){resolve(value);return;}
      if(Date.now()-started>=timeout){reject(new Error("O modal de atualização não ficou pronto a tempo."));return;}
      setTimeout(tick,35);
    };
    tick();
  });
}

function resetGenerationIdentity(){
  const name=$("#catalog-generation-name");if(name){name.readOnly=false;name.title="";}
  const title=$("#catalog-generation-title");if(title)title.textContent="Atualizar catálogo PluginTema";
  const modal=$("#catalog-generation-modal");if(modal)delete modal.dataset.catalogUpdateId;
}

async function restoreManualIncludes(ids){
  const unique=[...new Set((ids||[]).map(Number).filter(Number.isFinite))];
  for(const id of unique){
    const search=$("#catalog-generation-product-search");
    if(!search)break;
    search.value=String(id);
    $("#catalog-generation-product-search-button")?.click();
    try{
      const add=await waitUntil(()=>document.querySelector(`[data-generation-add-product="${id}"]`),4000);
      if(add.textContent.trim()!=="Adicionado")add.click();
    }catch(_error){/* produto removido do WooCommerce: segue sem bloquear a atualização */}
  }
  const search=$("#catalog-generation-product-search");if(search)search.value="";
}

async function applyGenerationConfig(row){
  const modal=await waitUntil(()=>$("#catalog-generation-modal[open]"));
  await waitUntil(()=>{
    const select=$("#catalog-generation-categories");
    return select&&select.options.length&&![...select.options].some(option=>option.textContent.includes("Carregando"));
  });

  modal.dataset.catalogUpdateId=String(row.id||"");
  const title=$("#catalog-generation-title");if(title)title.textContent=`Atualizar catálogo PluginTema · ${rowLabel(row)}`;
  const name=$("#catalog-generation-name");if(name){name.value=rowLabel(row);name.readOnly=true;name.title="Use Renomear no gerenciamento para alterar o nome deste catálogo.";}

  document.querySelectorAll("[data-generation-remove-product]").forEach(button=>button.click());
  document.querySelectorAll('input[name="catalog-kind"]').forEach(input=>input.checked=false);
  const customRadio=$("#catalog-generation-custom-mode");
  if(customRadio)customRadio.checked=false;
  const customPanel=$("#catalog-generation-custom-panel");
  if(customPanel)customPanel.hidden=true;

  const config=row.generation_config||{};
  const mode=config.mode==="custom"?"custom":"preset";
  if(mode==="custom"){
    if(customRadio){customRadio.checked=true;customRadio.dispatchEvent(new Event("change",{bubbles:true}));}
    const custom=config.custom||{};
    if($("#catalog-generation-type"))$("#catalog-generation-type").value=custom.type||"all";
    if($("#catalog-generation-status"))$("#catalog-generation-status").value=custom.status||"publish";
    if($("#catalog-generation-query"))$("#catalog-generation-query").value=custom.query||"";
    if($("#catalog-generation-ids"))$("#catalog-generation-ids").value=custom.specific_ids||"";
    if($("#catalog-generation-version"))$("#catalog-generation-version").value=custom.version||"all";
    const wantedCategories=new Set((custom.category_ids||[]).map(String));
    const categories=$("#catalog-generation-categories");
    if(categories)[...categories.options].forEach(option=>option.selected=wantedCategories.has(String(option.value)));
    if(!config.inferred)await restoreManualIncludes(custom.include_ids||[]);
  }else{
    const wanted=new Set((config.kinds||[]).map(String));
    document.querySelectorAll('input[name="catalog-kind"]').forEach(input=>input.checked=wanted.has(input.value));
    if(!wanted.size){const plugin=document.querySelector('input[name="catalog-kind"][value="plugin"]');if(plugin)plugin.checked=true;}
  }

  const status=$("#catalog-generation-status-band");
  if(status){status.className="operation-band info";status.textContent=`Atualizando “${rowLabel(row)}”. Ao concluir, a versão anterior com este nome será substituída.`;}
}

async function updateCatalog(button){
  const id=button.dataset.catalogUpdate;
  const row=rowsById.get(id)||{id,display_name:defaultCatalogName({id})};
  button.disabled=true;
  openingExistingCatalog=true;
  try{
    const management=$("#comparison-catalog-modal");if(management?.open)management.close();
    const globalButton=$("#comparison-update-catalog");
    if(!globalButton)throw new Error("A ação global de atualização não foi encontrada.");
    globalButton.click();
    await applyGenerationConfig(row);
  }catch(error){
    window.alert(`Não foi possível preparar a atualização do catálogo. ${error.message}`);
  }finally{
    openingExistingCatalog=false;
    button.disabled=false;
  }
}

async function renderPreview(){
  if(!previewState.catalogId)return;
  ensureManagementUi();
  const content=$("#comparison-catalog-preview");
  const title=$("#comparison-catalog-preview-title");
  const meta=$("#comparison-catalog-preview-meta");
  const controls=$("#comparison-catalog-preview-controls");
  const params=new URLSearchParams({catalog_id:previewState.catalogId,query:previewState.query,page:String(previewState.page),page_size:String(previewState.pageSize)});
  if(content){content.className="preview-empty";content.textContent="Carregando itens…";}
  try{
    const data=await get(`/api/catalogs/preview?${params}`),p=data.pagination||{};
    previewState.page=Number(p.page||1);previewState.pagination=p;
    const row=rowsById.get(previewState.catalogId)||data.catalog||{id:previewState.catalogId};
    if(title)title.textContent=`Prévia · ${rowLabel(row)}`;
    if(content){
      content.className="table-wrap preview-table";
      content.innerHTML=`<table><thead><tr>${data.headers.map(header=>`<th>${esc(header)}</th>`).join("")}</tr></thead><tbody>${data.rows.map(item=>`<tr>${data.headers.map(header=>`<td>${esc(item[header])}</td>`).join("")}</tr>`).join("")||`<tr><td colspan="${Math.max(1,data.headers.length)}">Nenhum item encontrado.</td></tr>`}</tbody></table>`;
    }
    const total=Number(p.total_rows||0),pageSize=Number(p.page_size||previewState.pageSize),from=total?(previewState.page-1)*pageSize+1:0,to=Math.min(total,previewState.page*pageSize);
    if(meta)meta.textContent=`Mostrando ${from}–${to} de ${total} itens`;
    if(controls)controls.hidden=false;
    const pageInput=$("#comparison-catalog-preview-page");if(pageInput){pageInput.value=previewState.page;pageInput.max=Math.max(1,Number(p.total_pages||1));}
    const pages=$("#comparison-catalog-preview-pages");if(pages)pages.textContent=Math.max(1,Number(p.total_pages||1));
    const prev=$("#comparison-catalog-preview-prev");if(prev)prev.disabled=previewState.page<=1;
    const next=$("#comparison-catalog-preview-next");if(next)next.disabled=previewState.page>=Number(p.total_pages||1);
  }catch(error){
    if(content){content.className="error-text";content.textContent=`Falha ao carregar o catálogo: ${error.message}`;}
    if(controls)controls.hidden=true;
  }
}

async function openPreview(id){
  previewState.catalogId=id;previewState.page=1;previewState.query="";
  ensureManagementUi();
  const input=$("#comparison-catalog-preview-search");if(input){input.disabled=false;input.value="";}
  const size=$("#comparison-catalog-preview-page-size");if(size)size.disabled=false;
  await renderPreview();
}

function previewGoToPage(){
  const input=$("#comparison-catalog-preview-page");
  if(!input)return;
  const pages=Math.max(1,Number(previewState.pagination.total_pages||1));
  const page=Math.max(1,Math.min(pages,Number(input.value)||1));
  input.value=page;
  if(page!==previewState.page){previewState.page=page;renderPreview();}
}

const observer=new MutationObserver(mutations=>{
  const relevant=mutations.some(mutation=>{
    if(mutation.target.id==="comparison-site")return true;
    return [...mutation.addedNodes].some(node=>node.nodeType===1&&(node.matches?.("#comparison-catalog-modal,.catalog-card")||node.querySelector?.(".catalog-card")));
  });
  if(relevant)scheduleSync();
});
observer.observe(document.body,{childList:true,subtree:true});

// Captura antes do listener da comparação para que a prévia completa substitua a prévia simples legada.
document.addEventListener("click",event=>{
  const preview=event.target.closest("[data-catalog-preview]");
  if(preview){event.preventDefault();event.stopImmediatePropagation();openPreview(preview.dataset.catalogPreview);return;}
  const update=event.target.closest("[data-catalog-update]");
  if(update){event.preventDefault();event.stopImmediatePropagation();updateCatalog(update);return;}
  const rename=event.target.closest("[data-catalog-name]");
  if(rename){event.preventDefault();event.stopImmediatePropagation();renameCatalog(rename);return;}
  const remove=event.target.closest("[data-catalog-delete]");
  if(remove){event.preventDefault();event.stopImmediatePropagation();deleteCatalog(remove);return;}
  const removeAll=event.target.closest("#comparison-catalog-delete-all");
  if(removeAll){event.preventDefault();event.stopImmediatePropagation();deleteAllCatalogs(removeAll);return;}
  if(event.target.closest("#comparison-update-catalog")&&!openingExistingCatalog){
    setTimeout(()=>waitUntil(()=>$("#catalog-generation-modal[open]"),3000).then(resetGenerationIdentity).catch(()=>{}),0);
  }
  if(event.target.closest("#comparison-catalog-preview-prev")&&previewState.page>1){event.preventDefault();previewState.page--;renderPreview();return;}
  if(event.target.closest("#comparison-catalog-preview-next")&&previewState.page<Number(previewState.pagination.total_pages||1)){event.preventDefault();previewState.page++;renderPreview();}
},true);

document.addEventListener("input",event=>{
  if(event.target.id!=="comparison-catalog-preview-search")return;
  clearTimeout(previewTimer);
  previewTimer=setTimeout(()=>{previewState.query=event.target.value.trim();previewState.page=1;renderPreview();},250);
});

document.addEventListener("change",event=>{
  if(event.target.id==="comparison-catalog-preview-page-size"){
    previewState.pageSize=Math.max(1,Math.min(100,Number(event.target.value)||20));previewState.page=1;renderPreview();
  }
});

document.addEventListener("keydown",event=>{
  if(event.target.id==="comparison-catalog-preview-page"&&event.key==="Enter"){event.preventDefault();previewGoToPage();}
});
document.addEventListener("focusout",event=>{if(event.target.id==="comparison-catalog-preview-page")previewGoToPage();});

document.addEventListener("click",event=>{if(event.target.closest("#comparison-manage-catalogs"))scheduleSync();});

syncRows().catch(()=>{});
