import {get,post} from "./api.js";
import {polling} from "./polling.js";

const $=selector=>document.querySelector(selector);
const safe=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const state={active:false,quality:{query:"",field:"",status:"all",category:"",page:1,pageSize:10,pages:1},logs:[],monitorBusy:false,qualityTimer:null,pricingBusy:false,pricingPoll:null};
const formatDate=value=>value?new Date(value).toLocaleString("pt-BR"):"—";
const money=value=>value?`R$ ${safe(value)}`:"—";

function environmentView(payload){
  $("#store-environment-chips").innerHTML=(payload.checks||[]).map(item=>`<article class="environment-chip" data-state="${safe(item.state)}" title="${safe(item.detail||"")}"><div><strong>${safe(item.label)}</strong><span>${safe(item.value)}</span></div></article>`).join("");
  $("#store-environment-status").textContent=payload.attention_count?`${payload.attention_count} requisito(s) exigem atenção.`:"Ambiente da Loja validado.";
  $("#store-environment-status").className=`operation-band ${payload.attention_count?"error":"success"}`;
}

async function refreshEnvironment(check=false){
  const button=$("#store-environment-check"),label=button.textContent;
  if(check){button.disabled=true;button.textContent="Verificando…"}
  try{environmentView(check?await post("/api/store/environment/check",{}):await get("/api/store/environment"))}
  catch(error){$("#store-environment-status").textContent=`Falha ao validar ambiente: ${error.message}`;$("#store-environment-status").className="operation-band error"}
  finally{if(check){button.disabled=false;button.textContent=label}}
}

function monitorView(monitor={}){
  const enabled=Boolean(monitor.enabled),running=monitor.state==="running";
  $("#store-monitor-toggle").setAttribute("aria-checked",String(enabled));
  $("#store-monitor-toggle").textContent=`Monitoramento automático: ${enabled?"ON":"OFF"}`;
  $("#store-monitor-toggle").classList.toggle("primary",enabled);
  $("#store-monitor-toggle").disabled=state.monitorBusy||!monitor.configured;
  $("#store-monitor-run").disabled=state.monitorBusy||running||!monitor.configured;
  $("#store-monitor-state").textContent=`${enabled?"Ativo":"Desativado"} · ${monitor.state||"idle"}`;
  $("#store-last-run").textContent=formatDate(monitor.last_run_at);
  $("#store-next-run").textContent=enabled?formatDate(monitor.next_check_at):"Não agendada";
  $("#store-current-product").textContent=monitor.current_product||"Nenhum";
  $("#store-current-woo").textContent=monitor.woo_product_id?`#${monitor.woo_product_id}`:"—";
  $("#store-current-source").textContent=monitor.source||"—";
  $("#store-current-version").textContent=monitor.current_version||"—";
  $("#store-found-version").textContent=monitor.found_version||"—";
  $("#store-request-state").textContent=monitor.request_state||"—";
  const status=monitor.error?.message?`Falha: ${monitor.error.message}`:running?"Consulta em andamento.":enabled?`Próxima consulta automática em intervalos de ${monitor.interval_seconds||30}s.`:"Monitor automático desativado.";
  $("#store-monitor-operation").textContent=status;
  $("#store-monitor-operation").className=`operation-band ${monitor.error?"error":running?"loading":"info"}`;
  const logs=[...(monitor.logs||[])];
  if(JSON.stringify(logs)!==JSON.stringify(state.logs)){
    state.logs=logs;const output=$("#store-monitor-log");output.textContent=logs.join("\n")||"Sem logs.";output.scrollTop=output.scrollHeight;
  }
  $("#store-monitor-history").innerHTML=(monitor.history||[]).map(item=>`<article class="history-item"><strong>${safe(item.result)}</strong><small>${formatDate(item.started_at)} · ${safe(item.product||"Sem produto")}${item.woo_product_id?` · Woo #${item.woo_product_id}`:""}</small></article>`).join("")||"Sem execuções.";
}

async function refreshSummary(){
  if(!state.active)return;
  try{const payload=await get("/api/store/summary");monitorView(payload.monitor)}
  catch(error){$("#store-monitor-operation").textContent=`Falha ao consultar monitor: ${error.message}`;$("#store-monitor-operation").className="operation-band error"}
}

const variationPrices=items=>items.map(item=>`<li>${safe(item.product_name)} · ${safe(item.period)} · ${money(item.regular_price)} / ${money(item.sale_price)}</li>`).join("");
function priceGroup(items,group){
  if(!items.length)return`<p class="empty">Nenhum ${group==="pack"?"pacote":"plano"} configurado.</p>`;
  return items.map(item=>{const variations=item.variations||[],priceFields=variations.length?`<div class="store-variation-prices">${variations.map(row=>`<div data-price-variation="${row.id}"><strong>${safe(row.name||`Variação #${row.id}`)}</strong><label>Regular<input data-variation-regular inputmode="decimal" value="${safe(row.regular_price)}"></label><label>Promocional<input data-variation-sale inputmode="decimal" value="${safe(row.sale_price)}"></label></div>`).join("")}</div>`:`<div class="form-row"><label>Regular<input data-bundle-regular inputmode="decimal" value="${safe(item.regular_price)}"></label><label>Promocional<input data-bundle-sale inputmode="decimal" value="${safe(item.sale_price)}"></label></div>`;return`<article class="store-price-item" data-price-product="${item.product_id}" data-price-group="${group}"><header><div><strong>${safe(item.product_name)}</strong><small>Woo #${item.product_id} · ${safe(item.product_type)}</small></div><span>${variations.length?`${variations.length} variação(ões)`:money(item.regular_price)+" / "+money(item.sale_price)}</span></header>${priceFields}<div class="form-row"><label>Confirmação<input data-bundle-confirmation placeholder="ALTERAR PRECO"></label><button data-bundle-preview>Prévia</button><button data-bundle-apply class="primary">Aplicar</button></div><div data-bundle-status class="action-message" aria-live="polite"></div></article>`}).join("");
}

function ensurePricingProgress(){
  let panel=$("#store-pricing-progress");
  if(panel)return panel;
  const anchor=$("#store-pricing-preview");
  if(!anchor)return null;
  anchor.insertAdjacentHTML("afterend",`<section id="store-pricing-progress" hidden><div id="store-pricing-progress-status" class="operation-band info">Aguardando aplicação.</div><progress id="store-pricing-progress-bar" max="100" value="0" style="width:100%;height:12px;margin-top:10px"></progress><div class="head-progress-foot"><output id="store-pricing-progress-percent">0%</output><output id="store-pricing-progress-count">0 de 0</output></div><pre id="store-pricing-progress-log" class="preview-log" role="log" aria-live="polite" style="height:220px;margin-top:10px">Sem logs.</pre></section>`);
  return $("#store-pricing-progress");
}

function pricingProgressView(payload={},forceVisible=false){
  const panel=ensurePricingProgress();
  if(!panel)return;
  const terminal=["success","partial","error"].includes(payload.state),running=payload.state==="running";
  panel.hidden=!(forceVisible||running||terminal);
  const status=$("#store-pricing-progress-status"),progress=Math.max(0,Math.min(100,Number(payload.progress||0))),current=Number(payload.current||0),total=Number(payload.total||0);
  status.textContent=payload.message||"Processando preços…";
  status.className=`operation-band ${running?"loading":payload.state==="success"?"success":payload.state==="partial"||payload.state==="error"?"error":"info"}`;
  $("#store-pricing-progress-bar").value=progress;
  $("#store-pricing-progress-percent").textContent=`${progress}%`;
  $("#store-pricing-progress-count").textContent=total?`${current} de ${total}`:"Aguardando dados";
  const output=$("#store-pricing-progress-log"),logs=[...(payload.logs||[])];
  output.textContent=logs.join("\n")||"Aguardando logs da aplicação…";
  output.scrollTop=output.scrollHeight;
}

async function refreshPricingProgress(forceVisible=false){
  try{const payload=await get("/api/store/pricing/status");pricingProgressView(payload,forceVisible);return payload}
  catch(error){if(forceVisible)pricingProgressView({state:"error",message:`Falha ao consultar o status: ${error.message}`,logs:[`Falha ao consultar o status: ${error.message}`]},true);return null}
}

async function loadPricing(){
  try{
    const payload=await get("/api/store/pricing/catalog"),individual=payload.individual?.items||[];
    $("#store-pricing-gate").textContent=payload.write_enabled?"Escrita habilitada":"Somente leitura";
    $("#store-pricing-gate").dataset.status=payload.write_enabled?"success":"ready";
    const sampled=payload.individual?.sampled_products||{},available=payload.individual?.available_products||{};$("#store-individual-current").innerHTML=`<p>Amostra real: ${sampled.plugin||0} de ${available.plugin||0} plugins e ${sampled.theme||0} de ${available.theme||0} temas.</p><ul>${variationPrices(individual.slice(0,12))}</ul><small>A prévia de alteração valida o conjunto selecionado completo antes de qualquer escrita.</small>`;
    $("#store-bundles").innerHTML=priceGroup(payload.packs?.items||[],"pack");
    $("#store-plans").innerHTML=priceGroup(payload.plans?.items||[],"plan");
  }catch(error){$("#store-pricing-gate").textContent=`Falha: ${error.message}`;$("#store-bundles").textContent=$("#store-plans").textContent="Não foi possível carregar preços."}
}

async function loadCategories(){
  try{const payload=await get("/api/store/categories");$("#store-quality-category").innerHTML='<option value="">Todas as categorias</option>'+payload.items.map(item=>`<option value="${safe(item.name)}">${safe(item.name)} (${item.count||0})</option>`).join("")}
  catch(error){$("#store-quality-status-band").textContent=`Falha ao carregar categorias: ${error.message}`}
}

function qualityQuery(){return new URLSearchParams({query:state.quality.query,field:state.quality.field,status:state.quality.status,category:state.quality.category,page:state.quality.page,page_size:state.quality.pageSize})}
function qualityView(payload){
  state.quality.pages=payload.pages;
  $("#store-quality-count").textContent=`${payload.total} produto(s)`;
  $("#store-quality-status-band").textContent=payload.analysis_complete?"Auditoria completa sobre o conjunto filtrado.":"Metadados básicos carregados; validação de variações em andamento.";
  $("#store-quality-status-band").className=`operation-band ${payload.analysis_error?"error":payload.analysis_complete?"success":"loading"}`;
  $("#store-quality").innerHTML=(payload.items||[]).map(item=>`<tr data-store-select="${item.product_id}"><td><button class="store-product-link" data-store-select="${item.product_id}">${safe(item.product_name)}</button><small>Woo #${item.product_id}</small></td><td>${safe(item.type||"—")}</td><td>${safe(item.version||"Ausente")}</td><td>${safe(item.developer||"Ausente")}</td><td>${item.official_url?`<a href="${safe(item.official_url)}" target="_blank" rel="noopener">Abrir</a>`:"Ausente"}</td><td>${item.short_description?"OK":"Ausente"}</td><td>${(item.categories||[]).map(name=>`<span class="category-chip">${safe(name)}</span>`).join(" ")||"Ausente"}</td><td>${(item.problems||[]).map(problem=>`<span class="quality-problem">${safe(problem.message)}</span>`).join("")||'<span class="quality-ok">Completo</span>'}</td></tr>`).join("")||'<tr><td colspan="8">Nenhum produto neste filtro.</td></tr>';
  $("#store-quality-page").textContent=`Página ${payload.page} de ${payload.pages}`;
  $("#store-quality-prev").disabled=payload.page<=1;$("#store-quality-next").disabled=payload.page>=payload.pages;
}

async function refreshQuality(){
  if(!state.active)return;
  try{qualityView(await get(`/api/store/quality/products?${qualityQuery()}`))}
  catch(error){$("#store-quality-status-band").textContent=`Falha na auditoria: ${error.message}`;$("#store-quality-status-band").className="operation-band error"}
}

async function selectProduct(id){
  const payload=await get(`/api/store/product?product_id=${encodeURIComponent(id)}`),product=payload.item;
  $("#store-details").innerHTML=`<h3>Detalhes do produto</h3><dl class="details-grid"><div><dt>Produto</dt><dd>${safe(product.name)}</dd></div><div><dt>WooCommerce</dt><dd>#${product.id}</dd></div><div><dt>Tipo/status</dt><dd>${safe(product.type)} · ${safe(product.status)}</dd></div><div><dt>Variações</dt><dd>${payload.variations.length}</dd></div><div><dt>Problemas</dt><dd>${payload.issues.length}</dd></div></dl>`;
}

const individualPayload=()=>({kinds:[$("#store-price-plugin").checked?"plugin":"",$("#store-price-theme").checked?"theme":""].filter(Boolean),annual_regular:$("#store-annual-regular").value,annual_sale:$("#store-annual-sale").value,lifetime_regular:$("#store-lifetime-regular").value,lifetime_sale:$("#store-lifetime-sale").value,confirmation:$("#store-price-confirmation").value});
async function individualPricing(apply=false){
  const target=$("#store-pricing-preview");
  if(!apply){
    target.textContent="Gerando prévia…";
    try{const payload=await post("/api/store/pricing/preview",individualPayload());target.textContent=`${payload.affected} alteração(ões); ${payload.unchanged} inalterada(s).`}
    catch(error){target.textContent=`Falha: ${error.message}`}
    return;
  }
  if(state.pricingBusy)return;
  state.pricingBusy=true;
  const applyButton=$("#store-price-apply"),previewButton=$("#store-price-preview");
  applyButton.disabled=true;previewButton.disabled=true;target.textContent="Aplicando preços…";
  pricingProgressView({state:"running",message:"Iniciando aplicação de preços…",progress:0,current:0,total:0,logs:["Preparando aplicação e aguardando a primeira resposta do servidor…"]},true);
  state.pricingPoll=setInterval(()=>refreshPricingProgress(true),500);
  try{
    const payload=await post("/api/store/pricing/apply",individualPayload());
    await refreshPricingProgress(true);
    target.textContent=`${payload.changed} preço(s) alterado(s); ${payload.unchanged} inalterado(s).`;
    await loadPricing();
  }catch(error){
    target.textContent=`Falha: ${error.message}`;
    const latest=await refreshPricingProgress(true);
    if(!latest||latest.state==="idle")pricingProgressView({state:"error",message:`Falha ao aplicar preços: ${error.message}`,progress:0,current:0,total:0,logs:[`Falha ao aplicar preços: ${error.message}`]},true);
  }finally{
    if(state.pricingPoll){clearInterval(state.pricingPoll);state.pricingPoll=null}
    state.pricingBusy=false;applyButton.disabled=false;previewButton.disabled=false;
  }
}

async function bundlePricing(card,apply=false){
  const variations=[...card.querySelectorAll("[data-price-variation]")].map(row=>({id:Number(row.dataset.priceVariation),regular_price:row.querySelector("[data-variation-regular]").value,sale_price:row.querySelector("[data-variation-sale]").value})),target=card.querySelector("[data-bundle-status]"),payload={product_id:Number(card.dataset.priceProduct),price_group:card.dataset.priceGroup,regular_price:card.querySelector("[data-bundle-regular]")?.value||"",sale_price:card.querySelector("[data-bundle-sale]")?.value||"",variations,confirmation:card.querySelector("[data-bundle-confirmation]").value};target.textContent=apply?"Aplicando…":"Validando…";
  try{const result=await post(apply?"/api/store/bundles/apply":"/api/store/bundles/preview",payload);target.textContent=result.status==="unchanged"?"Preço já corresponde ao solicitado.":apply?"Preço atualizado.":"Alteração confirmada na prévia.";if(apply)await loadPricing()}
  catch(error){target.textContent=`Falha: ${error.message}`}
}

async function toggleMonitor(){
  if(state.monitorBusy)return;state.monitorBusy=true;const current=$("#store-monitor-toggle").getAttribute("aria-checked")==="true";
  try{const payload=await post(current?"/api/store/monitor/disable":"/api/store/monitor/enable",{});monitorView(payload.monitor)}
  catch(error){$("#store-monitor-operation").textContent=`Falha: ${error.message}`;$("#store-monitor-operation").className="operation-band error"}
  finally{state.monitorBusy=false;await refreshSummary()}
}

document.addEventListener("app:tab",event=>{state.active=event.detail==="store";if(state.active){refreshEnvironment();refreshSummary();loadPricing();ensurePricingProgress();refreshPricingProgress();loadCategories();refreshQuality()}});
document.addEventListener("input",event=>{if(event.target.id==="store-quality-query"){state.quality.query=event.target.value;state.quality.page=1;clearTimeout(state.qualityTimer);state.qualityTimer=setTimeout(refreshQuality,250)}});
document.addEventListener("change",event=>{if(event.target.id==="store-quality-field"){state.quality.field=event.target.value;state.quality.page=1;refreshQuality()}if(event.target.id==="store-quality-status"){state.quality.status=event.target.value;state.quality.page=1;refreshQuality()}if(event.target.id==="store-quality-category"){state.quality.category=event.target.value;state.quality.page=1;refreshQuality()}if(event.target.id==="store-quality-page-size"){state.quality.pageSize=Number(event.target.value);state.quality.page=1;refreshQuality()}});
document.addEventListener("click",async event=>{if(event.target.id==="store-environment-check")await refreshEnvironment(true);if(event.target.id==="store-monitor-toggle")await toggleMonitor();if(event.target.id==="store-monitor-run"){state.monitorBusy=true;event.target.disabled=true;try{const payload=await post("/api/store/monitor/run",{});monitorView(payload.monitor)}catch(error){$("#store-monitor-operation").textContent=`Falha: ${error.message}`;$("#store-monitor-operation").className="operation-band error"}finally{state.monitorBusy=false;event.target.disabled=false;await refreshSummary()}}if(event.target.id==="store-price-preview")await individualPricing(false);if(event.target.id==="store-price-apply")await individualPricing(true);const preview=event.target.closest("[data-bundle-preview]"),apply=event.target.closest("[data-bundle-apply]");if(preview||apply)await bundlePricing(event.target.closest("[data-price-product]"),Boolean(apply));const product=event.target.closest("[data-store-select]")?.dataset.storeSelect;if(product)await selectProduct(product);if(event.target.id==="store-quality-prev"&&state.quality.page>1){state.quality.page--;refreshQuality()}if(event.target.id==="store-quality-next"&&state.quality.page<state.quality.pages){state.quality.page++;refreshQuality()}});
polling.register("store-state",refreshSummary,1500);