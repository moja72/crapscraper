import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8782",fixture=mkdtempSync(join(tmpdir(),"crapscraper-update-progress-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3.11"),["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

const sequence=[
  ["prepared","ready","Aguardando execução",[]],
  ["validating","running","Validando WooCommerce",["Validando Produto Progress (Woo #700)."]],
  ["downloading","running","Baixando arquivo",["Validando Produto Progress (Woo #700).","Baixando versão 2.0 do UltraPackV2."]],
  ["installing","running","Instalando nova versão",["Download concluído e ZIP validado.","Substituindo o arquivo de destino."]],
  ["completed","success","Atualização concluída",["Atualizando pt_versao para 2.0.","Atualização concluída e validada."]],
  ["staging","error","Validando ZIP",["Validando ZIP atual de destino antes do download: missing.zip.","ZIP atual do produto não foi encontrado no repositório de downloads."]],
];
const successFullLogs=["linha 1","linha 2","linha 3","linha 4","linha 5","linha 6","linha 7","linha 8"];
let reads=0,stageIndex=0;
function snapshot(){
  const [stage,state,label,progressLogs]=sequence[stageIndex],running=state==="running",success=state==="success",failed=state==="error";
  const logs=success?successFullLogs:progressLogs;
  return{ok:true,items:[{job_id:"upd-progress",woo_product_id:700,product_name:"Produto Progress",current_version:"1.0",source_version:"2.0",source_kind:"ultrapackv2",source_name:"UltraPackV2",source_url:"https://example.test/item",state,stage,attempts:stage==="prepared"?0:1,error:failed?{message:"ZIP atual do produto não foi encontrado no repositório de downloads.",diagnosis:"Arquivo atual ausente."}:null,logs,created_at:"2026-09-03T16:00:00+00:00",updated_at:"2026-09-03T17:35:00+00:00",started_at:stage==="prepared"?"":"2026-09-03T17:30:00+00:00",finished_at:success||failed?"2026-09-03T17:35:00+00:00":"",execution:{allowed:state==="ready",action:state==="ready"?"execute":failed?"retry":"none",blockers:state==="ready"?[]:failed?[]:[{code:running?"job_running":"job_completed",message:running?"Job já está em execução.":"Atualização já concluída."}]},progress:{active:running,complete:success,failed,stage,label,step:{prepared:0,validating:1,downloading:3,installing:6,completed:9,staging:4}[stage],total:9,logs:progressLogs}}],total:1,page:1,page_size:5,pages:1,counts:{total:1,prepared:state==="ready"?1:0,running:running?1:0,success:success?1:0,error:failed?1:0},batch:{running:false,total:0,processed:0,pending:0}};
}
const response=()=>{reads+=1;return snapshot()};
const environment={ok:true,checks:[],attention_count:0,plugintheme:{status:"VALIDADA",cookie_count:10}};

let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const context=await browser.newContext({permissions:["clipboard-read","clipboard-write"]});const page=await context.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:1,status:"success",logs:[]})}));
  await page.route("**/api/updates/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/updates/job?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,item:snapshot().items[0],history:[]})}));
  await page.route("**/api/updates/jobs?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(response())}));
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="update"]');await page.waitForSelector('.update-job-card');

  stageIndex=1;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Validando WooCommerce'));
  if(await page.locator('.update-job-progress').evaluate(element=>element.tagName)!=="SECTION")throw new Error("Log running foi transformado em sanfona");

  stageIndex=2;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Baixando arquivo'));
  if(!String(await page.locator('.update-job-live-log').textContent()).includes('Baixando versão'))throw new Error("Log novo não apareceu no card");

  stageIndex=3;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Instalando nova versão'));

  stageIndex=4;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('details.update-job-progress-terminal[data-progress-state="complete"]')&&document.querySelector('details.update-job-progress-terminal strong')?.textContent.includes('Atualização concluída'));
  const terminal=page.locator('details.update-job-progress-terminal');
  if(await terminal.getAttribute('open')!==null)throw new Error("Sanfona concluída deveria nascer fechada");
  if(!String(await terminal.locator('summary').textContent()).includes('Etapa 9 de 9'))throw new Error("Summary terminal não mostra etapa final");
  await page.waitForFunction(()=>document.querySelector('.update-status-time')?.textContent.includes('Concluído em:'));
  const progress=await terminal.locator('progress').evaluate(element=>({value:element.value,max:element.max}));if(progress.value!==progress.max)throw new Error(`Barra não finalizou: ${JSON.stringify(progress)}`);
  const copy=terminal.locator('[data-update-copy-log]');if(await copy.getAttribute('aria-label')!=="Copiar log")throw new Error("Botão de copiar sem aria-label correto");
  await copy.click();await page.waitForFunction(()=>document.querySelector('[data-update-copy-log]')?.dataset.copied==="1");
  const copied=await page.evaluate(()=>navigator.clipboard.readText());if(copied!==successFullLogs.join("\n"))throw new Error(`Cópia não usou log completo: ${copied}`);
  if(await terminal.getAttribute('open')!==null)throw new Error("Copiar log alternou a sanfona");

  stageIndex=5;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('details.update-job-progress-terminal[data-progress-state="error"]'));
  if(await terminal.getAttribute('open')!==null)throw new Error("Sanfona de erro deveria nascer fechada");
  await page.waitForFunction(()=>document.querySelector('.update-status-time')?.textContent.includes('Erro em:'));

  if(reads>12)throw new Error(`Polling duplicado detectado: ${reads} leituras`);
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,stages:true,liveLog:true,terminalAccordion:true,timestamps:true,copyFullLog:true,errorTerminal:true,centralPolling:true,reads}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
