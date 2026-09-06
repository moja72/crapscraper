import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8782",fixture=mkdtempSync(join(tmpdir(),"crapscraper-compare-loading-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3.11"),["tests/e2e_server.py"],{cwd,env:{...Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith("SCRAPER_"))),SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED:"0",SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<80;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

let browser;const comparisonRequests=[];
try{
  await ready();
  browser=await chromium.launch({headless:true});
  const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});
  page.on("pageerror",error=>errors.push(error.message));

  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:10,status:"success",logs:[]})}));
  await page.route("**/api/comparison/catalogs",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,catalogs:[{id:"source-e2e.csv",role:"source",updated_at:0},{id:"site-e2e.csv",role:"site",updated_at:0}],source_id:"source-e2e.csv",site_id:"site-e2e.csv",statuses:["update_available"],decisions:["pending"]})}));
  await page.route("**/api/comparison/run",async route=>{comparisonRequests.push(route.request().postDataJSON());await sleep(550);await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,rows:[],pagination:{page:1,total_pages:1,total_rows:0,page_size:5},summary:{total_rows:0,status_counts:{},decision_summary:{}},operation:{log:["E2E concluído"]}})})});

  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});
  await page.click('[data-tab="compare"]');
  await page.waitForSelector('[data-comparison-run]');
  await page.click('[data-comparison-run]');
  await page.waitForFunction(()=>document.querySelector('#comparison-result-status')?.classList.contains('loading'));

  const loading=await page.evaluate(()=>{
    const node=document.querySelector('#comparison-result-status'),pseudo=getComputedStyle(node,'::before');
    return {text:node.textContent,animationName:pseudo.animationName,display:pseudo.display,content:pseudo.content};
  });
  if(!loading.text.includes("Comparando catálogos")||!loading.animationName.includes("cs-runtime-spin")||loading.display==="none")throw new Error(`Loading visual não aplicado: ${JSON.stringify(loading)}`);

  await page.locator('#comparison-score-min').fill('42');await page.locator('#comparison-score-min').dispatchEvent('change');
  await page.locator('#comparison-score-max').fill('90');await page.locator('#comparison-score-max').dispatchEvent('change');
  await page.waitForFunction(()=>document.querySelector('#comparison-result-status')?.classList.contains('success'));
  if(comparisonRequests.at(-1).score_min!=='42'||comparisonRequests.at(-1).score_max!=='90')throw new Error('Latest filters were dropped during the pending comparison: '+JSON.stringify(comparisonRequests));
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,comparisonLoading:true,animation:loading.animationName}));
}finally{
  if(browser)await browser.close();
  server.kill();
  await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);
  rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
