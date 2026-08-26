import {get,post} from "./api.js";
import {polling} from "./polling.js";
import "./collect.js";
import "./compare.js";
import "./update.js";
import "./add.js";
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];let active="collect",storeMonitor=false;
const toast=m=>{const n=$("#toast");n.textContent=m;n.classList.add("show");setTimeout(()=>n.classList.remove("show"),3200)};
const cards=(id,items)=>{$(id).innerHTML=items.map(([l,v])=>`<article class="card"><small>${l}</small><strong>${v??0}</strong></article>`).join("")};
async function loadStore(){const d=await get("/api/store");storeMonitor=!!d.monitor.enabled;cards("#store-cards",[["Catálogos",d.catalogs],["Produtos amostrados",d.products_sampled],["Monitor",storeMonitor?"Ativo":"Pausado"]]);$("#store-content").innerHTML=`<p>Fonte de dados: <code>SCRAPER_DATA_DIR</code></p><p>Monitor WordPress: <strong>${storeMonitor?"ativo":"pausado"}</strong></p>`;$('[data-page="store"] .last-run')?.replaceChildren(document.createTextNode("Última leitura: "+new Date().toLocaleString("pt-BR")))}
document.addEventListener("click",async e=>{const tab=e.target.closest("[data-tab]")?.dataset.tab;if(tab){active=tab;$$('[data-tab]').forEach(b=>b.setAttribute("aria-selected",String(b.dataset.tab===tab)));$$('.page').forEach(p=>p.classList.toggle("active",p.dataset.page===tab));document.dispatchEvent(new CustomEvent("app:tab",{detail:tab}));if(tab==="store")await loadStore();return}const action=e.target.closest("[data-action]")?.dataset.action;try{if(action==="store-monitor"){await post("/api/store/monitor",{enabled:!storeMonitor});await loadStore()}}catch(error){toast(error.message)}});
polling.register("health",async()=>{$("#health").textContent=(await get("/api/health")).ok?"Online":"Indisponível"},10000);
