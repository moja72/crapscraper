import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8777",fixture=mkdtempSync(join(tmpdir(),"crapscraper-plugin-session-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn("python",["tests/e2e_server.py"],{cwd,env:{...Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith("SCRAPER_"))),SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED:"0",SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0",SCRAPER_STORE_E2E_FIXTURES:"1"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}
const checks=validated=>[
  {key:"woocommerce",label:"WooCommerce",state:"ok",value:"VALIDADO",detail:"Leitura confirmada."},
  {key:"source",label:"Fonte autenticada",state:validated?"ok":"attention",value:validated?"VALIDADA":"CONFIGURADA / NÃO VALIDADA",detail:validated?"Sessão confirmada.":"Validação pendente."},
  {key:"storage",label:"Armazenamento de destino",state:"ok",value:"VALIDADO",detail:"Destino confirmado."},
  {key:"individual",label:"Execução individual",state:"ok",value:"HABILITADA"},
  {key:"woo_write",label:"WooCommerce escrita",state:"ok",value:"HABILITADA"},
];
const payload=validated=>({ok:true,checks:checks(validated),attention_count:validated?0:1,plugintheme:{configured:true,account_key:"account-a",profile_exists:true,persistence_mode:"persistent_browser_context",cookie_count:validated?7:5,httponly_cookie_count:validated?1:0,storage_entry_count:validated?9:0,current_url:validated?"https://plugintheme.net/pt-BR/account/subscription":"",login_redirect:false,authenticated:validated,status:validated?"VALIDADA":"CONFIGURADA / SESSÃO NÃO VALIDADA",renewal_available:true,credits:validated?37:null,credit_limit:validated?50:null,credit_used:validated?13:null,credit_status:validated?"success":"unavailable",credit_stale:false,credit_source:validated?"account/subscription:api:membership/download-stats":"",last_error:validated?"":"Validação pendente.",logs:validated?["Sessão autenticada confirmada.","Saldo confirmado na área de assinatura do PluginTheme.","Saldo localizado: 37."]:[]}});

let browser,checksCalled=0,renewCalled=0;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:850}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:false,credits:null,status:"unavailable",message:"Sem cache.",logs:[]})}));
  await page.route("**/api/updates/environment/check",async route=>{checksCalled+=1;await sleep(180);await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(payload(true))})});
  await page.route("**/api/updates/plugintheme/renew",async route=>{renewCalled+=1;await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,message:"Janela de renovação aberta."})})});
  await page.route("**/api/updates/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(payload(false))}));
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="update"]');
  await page.waitForSelector("#update-plugintheme-renew",{state:"attached"});const details=page.locator("#update-environment");if(!await details.getAttribute("open"))await page.click("#update-environment summary");
  if(!(await page.locator("#update-plugintheme-credit").textContent()).includes("indisponível"))throw new Error("Saldo ausente foi convertido em zero");
  await page.click("#update-environment-refresh");
  const loading=await page.evaluate(()=>({disabled:document.querySelector("#update-environment-refresh").disabled,text:document.querySelector("#update-environment-refresh").textContent,status:document.querySelector("#update-plugintheme-status").textContent}));
  if(!loading.disabled||!loading.text.includes("Verificando")||!loading.status.includes("área protegida"))throw new Error(`Loading inválido: ${JSON.stringify(loading)}`);
  await page.waitForFunction(()=>!document.querySelector("#update-environment-refresh").disabled);
  const result=await page.evaluate(()=>({source:[...document.querySelectorAll(".environment-chip")].find(item=>item.textContent.includes("Fonte autenticada"))?.textContent,session:document.querySelector("#update-plugintheme-session").textContent,credit:document.querySelector("#update-plugintheme-credit").textContent,status:document.querySelector("#update-plugintheme-status").textContent,minHeight:parseFloat(getComputedStyle(document.querySelector("#update-plugintheme-status")).minHeight)}));
  if(!result.source.includes("VALIDADA")||!result.session.includes("VALIDADA")||!result.session.includes("7 cookie")||!result.session.includes("HttpOnly")||!result.credit.includes("37")||!result.status.includes("Sessão autenticada confirmada")||!result.status.includes("Saldo confirmado na área de assinatura")||!result.status.includes("limite diário 50")||!result.status.includes("usados hoje 13")||!result.status.includes("restantes 37")||result.minHeight<40||checksCalled!==1)throw new Error(`Estado validado incorreto: ${JSON.stringify({result,checksCalled})}`);
  await page.click("#update-plugintheme-renew");await page.waitForFunction(()=>document.querySelector("#update-plugintheme-status").textContent.includes("Janela de renovação aberta"));if(renewCalled!==1)throw new Error(`Renovação chamou ${renewCalled} vezes`);
  await page.setViewportSize({width:390,height:844});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error("Diagnóstico PluginTheme causou overflow horizontal");
  if(errors.length)throw new Error(errors.join(" | "));console.log(JSON.stringify({ok:true,functionalStatus:true,cookies:true,credits:true,loading:true,logs:true,renew:true,responsive:true,checksCalled,renewCalled}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
