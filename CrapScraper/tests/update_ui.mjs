import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8784",fixture=mkdtempSync(join(tmpdir(),"crapscraper-update-ui-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3.11"),["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

const job={job_id:"upd-ui",woo_product_id:700,product_name:"Produto UI",current_version:"1.0",source_version:"2.0",source_kind:"ultrapackv2",source_name:"UltraPackV2",source_url:"https://example.test/item",state:"ready",stage:"prepared",attempts:0,error:null,logs:[],created_at:"2026-09-03T16:00:00+00:00",updated_at:"2026-09-03T17:35:00+00:00",execution:{allowed:true,action:"execute",blockers:[]}};
const environment={ok:true,checks:[
  {key:"woocommerce",label:"WooCommerce",state:"ok",value:"VALIDADO",detail:"Leitura autenticada confirmada."},
  {key:"source",label:"Fonte autenticada",state:"ok",value:"VALIDADA",detail:"Fonte confirmada."},
  {key:"storage",label:"Armazenamento de destino",state:"ok",value:"VALIDADO",detail:"Destino confirmado."},
  {key:"individual",label:"Execução individual",state:"ok",value:"HABILITADA",detail:"Execução habilitada."},
  {key:"woo_write",label:"WooCommerce escrita",state:"ok",value:"HABILITADA",detail:"Escrita habilitada."},
],attention_count:0,plugintheme:{status:"VALIDADA",cookie_count:10}};
const listing={ok:true,items:[job],total:1,page:1,page_size:5,pages:1,counts:{total:1,prepared:1,running:0,success:0,error:0},batch:{running:false,total:0,processed:0,pending:0,success:0,errors:0}};

let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on("console",m=>m.type()==="error"&&errors.push(m.text()));page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:1,status:"success",logs:[]})}));
  await page.route("**/api/updates/environment/check",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/updates/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/updates/job?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,item:job,history:[]})}));
  await page.route("**/api/updates/jobs?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(listing)}));
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="update"]');await page.waitForSelector(".update-job-card");
  const structure=await page.evaluate(()=>{const root=document.querySelector('[data-page="update"]'),blocks=[...root.children].filter(x=>x.matches('.panel'));return{blocks:blocks.map(x=>x.id),environment:document.querySelectorAll('.environment-chip').length,environmentTips:document.querySelectorAll('.environment-chip .help-tip').length,cards:document.querySelectorAll('#update-cards .metric-card').length,cardTips:document.querySelectorAll('#update-cards .help-tip').length,headerActions:root.querySelectorAll('.page-head button').length,pageSize:document.querySelector('#update-page-size').value,jobs:document.querySelectorAll('.update-job-card').length,progress:getComputedStyle(document.querySelector('#update-progress-fill')).transform,historyClosed:!document.querySelector('#update-history-details').open,logClosed:!document.querySelector('#update-log-details').open}});if(errors.length||structure.blocks.join(',')!=="update-environment,update-overview,update-queue,update-history-details,update-log-details"||structure.environment!==5||structure.environmentTips!==5||structure.cards!==5||structure.cardTips!==5||structure.headerActions||structure.pageSize!=="5"||structure.jobs>5||!structure.historyClosed||!structure.logClosed)throw new Error(JSON.stringify({errors,structure}));
  await page.click('#update-environment summary');if(!await page.locator('#update-environment-chips').isVisible())throw new Error('Ambiente não abriu');await page.click('#update-environment-refresh');await page.waitForFunction(()=>document.querySelector('#update-environment-refresh')?.disabled===false);await page.click('#update-environment summary');
  await page.click('#update-select-page');if(!await page.locator('#update-selected-count').textContent().then(x=>!x.startsWith('0 ')))throw new Error('Seleção da página falhou');await page.click('#update-select-page');if(!await page.locator('#update-selected-count').textContent().then(x=>x.startsWith('0 ')))throw new Error('Desmarcação da página falhou');await page.click('#update-select-all');if(await page.locator('#update-selected-count').textContent()==='0 selecionados')throw new Error('Seleção global falhou');await page.click('#update-clear-selection');
  const first=page.locator('[data-update-select]').first();await first.click();await page.waitForSelector('#update-detail-modal[open]');await page.keyboard.press('Escape');await page.click('#update-history-details summary');if(!await page.locator('#update-history').isVisible())throw new Error('Histórico não abriu');await page.click('#update-log-details summary');if(!await page.locator('#update-log').isVisible())throw new Error('Log não abriu');
  const pages=+await page.locator('#update-pages').textContent();if(pages>1){await page.fill('#update-page-input','2');await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelector('#update-page-input').value==='2')}
  for(const [tab,selector] of Object.entries({compare:'#comparison-page-size',add:'#add-page-size',store:'#store-page-size'})){if(await page.locator(selector).inputValue()!=="5")throw new Error(`${tab} não inicia com 5 itens`)}
  await page.setViewportSize({width:375,height:800});await page.click('[data-tab="update"]');const mobile=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,columns:getComputedStyle(document.querySelector('.update-filter-grid')).gridTemplateColumns.split(' ').length}));if(mobile.overflow||mobile.columns!==1)throw new Error(JSON.stringify(mobile));if(errors.length)throw new Error(JSON.stringify(errors));console.log(JSON.stringify({ok:true,blocks:5,environment:true,overview:true,queue:true,history:true,logs:true,defaultPageSize:5,detailsModal:true,selection:true,pagination:true,consoleErrors:0}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
