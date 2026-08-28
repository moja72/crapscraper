import {get,post} from "./api.js";
const mascot=document.querySelector(".mascot-crop img"); if(mascot) mascot.src="/static/mascote.webp";
import {polling} from "./polling.js";
import "./collect.js";
import "./collection-management.js";
import "./compare.js";
import "./update.js";
import "./add.js";
import "./store.js";
import "./sync.js";
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];let active="collect";
const toast=m=>{const n=$("#toast");n.textContent=m;n.classList.add("show");setTimeout(()=>n.classList.remove("show"),3200)};
document.addEventListener("click",e=>{const tab=e.target.closest("[data-tab]")?.dataset.tab;if(!tab)return;active=tab;$$('[data-tab]').forEach(b=>b.setAttribute("aria-selected",String(b.dataset.tab===tab)));$$('.page').forEach(p=>p.classList.toggle("active",p.dataset.page===tab));document.dispatchEvent(new CustomEvent("app:tab",{detail:tab}))});
$("#processes-open")?.addEventListener("click",()=>{const collect=$("[data-tab=collect]");collect?.click();const executions=$("#executions-details");if(executions){executions.open=true;executions.scrollIntoView({behavior:"smooth",block:"start"});executions.querySelector("summary")?.focus()}});
polling.register("health",async()=>{$("#health").textContent=(await get("/api/health")).ok?"Online":"Indisponível"},10000);
const creditNodes={ultrapackv2:$("#credits-ultrapack"),plugintheme:$("#credits-plugintheme")};
function renderCredit(node,value){if(!node)return;if(value?.ok&&Number.isInteger(Number(value.remaining))){const amount=Number(value.remaining);node.textContent=`${amount} crédito${amount===1?"":"s"}`;node.title=value.limit!==undefined?`${amount} de ${value.limit} créditos disponíveis`:"Saldo informado pela plataforma";return}node.textContent=value?.status==="loading"?"consultando…":"indisponível";node.title=value?.message||"Não foi possível determinar o saldo."}
async function refreshCredits(){Object.values(creditNodes).forEach(node=>renderCredit(node,{status:"loading"}));try{const data=await get("/api/credits");renderCredit(creditNodes.ultrapackv2,data.ultrapackv2);renderCredit(creditNodes.plugintheme,data.plugintheme)}catch(error){Object.values(creditNodes).forEach(node=>renderCredit(node,{message:error.message}))}}
polling.register("download-credits",refreshCredits,60000);
document.addEventListener("app:credits-refresh",refreshCredits);
