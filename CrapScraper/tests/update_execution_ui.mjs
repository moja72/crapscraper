import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8778",fixture=mkdtempSync(join(tmpdir(),"crapscraper-update-gating-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn("python",["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

let validated=false,executeCalls=0,batchCalls=[],batch={running:false,paused:false,cancelled:false,total:0,processed:0,pending:0,success:0,errors:0};
const execution=()=>validated?{allowed:true,action:"execute",blockers:[]}:{allowed:false,action:"execute",blockers:[
  {code:"woocommerce_not_validated",message:"WooCommerce não validado. Execute Verificar pré-requisitos."},
  {code:"storage_not_validated",message:"Armazenamento de destino não validado. Execute Verificar pré-requisitos."},
  {code:"source_not_validated",message:"Fonte UltraPackV2 não validada. Execute Verificar pré-requisitos."},
]};
const jobs=()=>[
  {job_id:"upd-listeo",comparison_item_id:"cmp-listeo",woo_product_id:95422,product_name:"Listeo - Directory & Listings With Booking - WordPress Theme",current_version:"2.0.36",source_version:"2.0.53",source_kind:"ultrapackv2",source_name:"UltraPackV2",source_url:"https://ultrapack.example/listeo",source_product_id:"",state:"ready",stage:"prepared",attempts:0,group:"prepared",logs:[],error:null,execution:execution()},
  {job_id:"upd-listify",comparison_item_id:"cmp-listify",woo_product_id:95191,product_name:"Listify - Directory WordPress Theme",current_version:"3.2.8",source_version:"3.2.9",source_kind:"ultrapackv2",source_name:"UltraPackV2",source_url:"https://ultrapack.example/listify",source_product_id:"",state:"ready",stage:"prepared",attempts:0,group:"prepared",logs:[],error:null,execution:execution()},
];
const environment=()=>({ok:true,checks:validated?[
  {key:"woocommerce",label:"WooCommerce",state:"ok",value:"VALIDADO",detail:"Leitura autenticada confirmada."},
  {key:"source",label:"Fonte autenticada",state:"ok",value:"VALIDADA",detail:"UltraPackV2: acesso autenticado confirmado."},
  {key:"storage",label:"Armazenamento de destino",state:"ok",value:"VALIDADO",detail:"Destino confirmado."},
  {key:"individual",label:"Execução individual",state:"ok",value:"HABILITADA"},
  {key:"woo_write",label:"WooCommerce escrita",state:"ok",value:"HABILITADA"},
]:[
  {key:"woocommerce",label:"WooCommerce",state:"attention",value:"CONFIGURADO / NÃO VALIDADO",detail:"Execute Verificar pré-requisitos."},
  {key:"source",label:"Fonte autenticada",state:"attention",value:"CONFIGURADA / SESSÃO NÃO VALIDADA",detail:"Execute Verificar pré-requisitos."},
  {key:"storage",label:"Armazenamento de destino",state:"blocked",value:"CONFIGURADO / NÃO VALIDADO",detail:"Execute Verificar pré-requisitos."},
  {key:"individual",label:"Execução individual",state:"ok",value:"HABILITADA"},
  {key:"woo_write",label:"WooCommerce escrita",state:"blocked",value:"DESABILITADA"},
],attention_count:validated?0:4,plugintheme:{configured:true,account_key:"account-a",profile_exists:true,cookie_count:10,httponly_cookie_count:3,authenticated:false,status:"CONFIGURADA / SESSÃO NÃO VALIDADA",renewal_available:true,credits:50,credit_stale:true,credit_status:"expired",logs:[]}});

let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:50,status:"success",logs:[]})}));
  await page.route("**/api/updates/environment/check",async route=>{await sleep(120);validated=true;await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment())})});
  await page.route("**/api/updates/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment())}));
  await page.route("**/api/updates/jobs?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,items:jobs(),total:2,page:1,page_size:5,pages:1,counts:{total:2,prepared:2,running:0,success:0,error:0},batch})}));
  await page.route("**/api/updates/job?*",route=>{const id=new URL(route.request().url()).searchParams.get("job_id");const item=jobs().find(job=>job.job_id===id);return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,item,history:[]})})});
  await page.route("**/api/updates/execute",async route=>{executeCalls+=1;await sleep(180);await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,job_id:"upd-listeo",attempt_id:"upd-listeo-a1"})})});
  await page.route("**/api/updates/selection",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,items:jobs(),total:2})}));
  await page.route("**/api/updates/batch/start",async route=>{batchCalls=JSON.parse(route.request().postData()||"{}").job_ids||[];batch={running:true,paused:false,cancelled:false,total:2,processed:0,pending:2,success:0,errors:0};await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,batch})})});

  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="update"]');await page.waitForSelector('.update-job-card');
  const initial=await page.evaluate(()=>({disabled:[...document.querySelectorAll('[data-update-execute]')].map(button=>button.disabled),blockers:[...document.querySelectorAll('.execution-blocker')].map(item=>item.textContent),batchDisabled:document.querySelector('#update-batch-start').disabled}));
  if(initial.disabled.some(value=>!value)||initial.blockers.length!==2||!initial.blockers.every(value=>value.includes("WooCommerce não validado"))||!initial.batchDisabled)throw new Error(`Bloqueio inicial incorreto: ${JSON.stringify(initial)}`);

  if(!await page.locator('#update-environment').getAttribute('open'))await page.click('#update-environment summary');
  await page.click('#update-environment-refresh');await page.waitForFunction(()=>[...document.querySelectorAll('[data-update-execute]')].every(button=>!button.disabled));
  if(await page.locator('.execution-blocker').count())throw new Error("Bloqueador permaneceu após preflight válido");

  const executeButton=page.locator('[data-update-execute="upd-listeo"]');await executeButton.click();await page.waitForFunction(()=>document.querySelector('[data-update-execute="upd-listeo"]').disabled);if(!String(await executeButton.textContent()).includes("Executando"))throw new Error("Execução individual não exibiu loading");await page.waitForFunction(()=>!document.querySelector('[data-update-execute="upd-listeo"]').disabled);if(executeCalls!==1)throw new Error(`Execução individual chamou ${executeCalls} vezes`);

  await page.locator('[data-update-select-check="upd-listeo"]').check();await page.locator('[data-update-select-check="upd-listify"]').check();if(await page.locator('#update-batch-start').isDisabled())throw new Error("Executar fila não habilitou para dois jobs elegíveis");
  await page.click('#update-batch-start');for(let index=0;index<40&&batchCalls.length!==2;index++)await sleep(50);await page.waitForFunction(()=>document.querySelector('#update-operation-status').textContent.includes("execução"));
  if(batchCalls.join(',')!=="upd-listeo,upd-listify")throw new Error(`Seleção enviada divergiu: ${batchCalls.join(',')}`);

  await page.setViewportSize({width:375,height:812});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error("Fila de atualização causou overflow horizontal");
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,preparedBlockedWithReason:true,preflightReleases:true,individual:true,selection:true,batch:true,noDuplicate:true,responsive:true,executeCalls,batchCalls}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
