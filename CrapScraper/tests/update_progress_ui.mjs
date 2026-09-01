import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8782",fixture=mkdtempSync(join(tmpdir(),"crapscraper-update-progress-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn("python",["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

const sequence=[
  ["prepared","ready","Aguardando execução",[]],
  ["validating","running","Validando WooCommerce",["Validando Produto Progress (Woo #700)."]],
  ["downloading","running","Baixando arquivo",["Validando Produto Progress (Woo #700).","Baixando versão 2.0 do UltraPackV2."]],
  ["installing","running","Instalando nova versão",["Download concluído e ZIP validado.","Substituindo o arquivo de destino."]],
  ["completed","success","Atualização concluída",["Atualizando pt_versao para 2.0.","Atualização concluída e validada."]],
];
let reads=0,stageIndex=0;
const response=()=>{reads+=1;const [stage,state,label,logs]=sequence[stageIndex],running=state==="running",success=state==="success";return{ok:true,items:[{job_id:"upd-progress",woo_product_id:700,product_name:"Produto Progress",current_version:"1.0",source_version:"2.0",source_kind:"ultrapackv2",source_name:"UltraPackV2",source_url:"https://example.test/item",state,stage,attempts:stage==="prepared"?0:1,error:null,logs,execution:{allowed:state==="ready",action:state==="ready"?"execute":"none",blockers:state==="ready"?[]:[{code:running?"job_running":"job_completed",message:running?"Job já está em execução.":"Atualização já concluída."}]},progress:{active:running,complete:success,failed:false,stage,label,step:{prepared:0,validating:1,downloading:3,installing:6,completed:9}[stage],total:9,logs}}],total:1,page:1,page_size:5,pages:1,counts:{total:1,prepared:state==="ready"?1:0,running:running?1:0,success:success?1:0,error:0},batch:{running:false,total:0,processed:0,pending:0}}};
const environment={ok:true,checks:[],attention_count:0,plugintheme:{status:"VALIDADA",cookie_count:10}};

let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:1,status:"success",logs:[]})}));
  await page.route("**/api/updates/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/updates/jobs?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(response())}));
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="update"]');await page.waitForSelector('.update-job-card');
  stageIndex=1;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Validando WooCommerce'));
  stageIndex=2;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Baixando arquivo'));
  if(!String(await page.locator('.update-job-live-log').textContent()).includes('Baixando versão'))throw new Error("Log novo não apareceu no card");
  stageIndex=3;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress strong')?.textContent.includes('Instalando nova versão'));
  stageIndex=4;await page.click('#update-refresh');await page.waitForFunction(()=>document.querySelector('.update-job-progress[data-progress-state="complete"]')&&document.querySelector('.update-job-progress strong')?.textContent.includes('Atualização concluída'));
  const progress=await page.locator('.update-job-progress progress').evaluate(element=>({value:element.value,max:element.max}));if(progress.value!==progress.max)throw new Error(`Barra não finalizou: ${JSON.stringify(progress)}`);
  if(reads>10)throw new Error(`Polling duplicado detectado: ${reads} leituras`);
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,stages:true,liveLog:true,completed:true,centralPolling:true,reads}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
