import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";
const port="8770",fixture=mkdtempSync(join(tmpdir(),"crapscraper-update-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn("python",["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_UPDATE_DB_PATH:join(fixture,"updates.sqlite3"),SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_DB_PATH:join(fixture,"additions.sqlite3"),SCRAPER_ADDITION_IMPORT_LEGACY:"0",SCRAPER_ADDITION_E2E_FIXTURES:"1"},stdio:"ignore"});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function ready(){for(let i=0;i<40;i++){try{const r=await fetch(`http://127.0.0.1:${port}/api/health`);if(r.ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}
let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on("console",m=>{if(m.type()==="error")errors.push(m.text())});page.on("pageerror",e=>errors.push(e.message));page.on("response",r=>{if(r.status()===404)errors.push(`404 ${r.url()}`)});
  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});
  await page.click('[data-tab="collect"]');await page.waitForFunction(()=>document.querySelectorAll('#collect-site option').length>=2);if(await page.locator('#collect-site option[value="ultrapackv2"]').count()!==1||await page.locator('#collect-site option[value="plugintheme"]').count()!==1)throw new Error("Registries reais ausentes");
  if(await page.locator("#collect-log-details").count()!==1)throw new Error("Accordion de coleta não é único");
  await page.click('[data-tab="compare"]');await page.waitForSelector("#compare-rows tr",{timeout:240000});const rows=await page.locator("#compare-rows tr").count();if(!rows)throw new Error("Comparação sem resultados");
  await page.locator("#comparison-query").fill("plugin");await sleep(700);if(await page.locator("#comparison-query").inputValue()!=="plugin")throw new Error("Busca da comparação foi perdida");
  await page.locator("#compare-rows [data-link]").first().click();await page.waitForSelector("#relationship-modal[open]");await page.keyboard.press("Escape");if(await page.locator("#relationship-modal[open]").count())throw new Error("Escape não fechou modal");
  await page.click('[data-tab="update"]');await page.waitForSelector("#update-cards .card");
  if(await page.locator("#update-cards .card").count()!==5)throw new Error("Atualizar não possui exatamente cinco cards");
  if((await page.locator("#update-cards").innerText()).includes("Aguardando"))throw new Error("Card Aguardando reapareceu");
  const counts=await page.locator("#update-cards .card strong").allTextContents();if(Number(counts[0])!==counts.slice(1).reduce((a,v)=>a+Number(v),0))throw new Error("Total dos cards incoerente");
  await page.locator('#update-cards [data-update-group="prepared"]').click();await sleep(350);if(await page.locator("#update-list tr[data-job-id]").count()!==Number(counts[1]))throw new Error("Filtro Preparados diverge do contador");
  await page.locator('#update-cards [data-update-group="error"]').click();await sleep(350);if(await page.locator("#update-list tr[data-job-id]").count()!==Number(counts[4]))throw new Error("Filtro Erros diverge do contador");
  await page.locator("#update-query").fill("persistir busca");await page.evaluate(()=>{const d=document.querySelector("#update-log-details");d.open=true;window.__updateDetails=d});await sleep(26000);
  const stable=await page.evaluate(()=>({same:window.__updateDetails===document.querySelector("#update-log-details"),open:document.querySelector("#update-log-details").open,query:document.querySelector("#update-query").value,page:document.querySelector("#update-page").textContent}));if(!stable.same||!stable.open||stable.query!=="persistir busca"||!stable.page.includes("Página 1"))throw new Error("Polling alterou DOM/estado: "+JSON.stringify(stable));
  await page.evaluate(()=>document.querySelector("#update-log-details").open=false);await sleep(2600);if(await page.locator("#update-log-details").evaluate(d=>d.open))throw new Error("Polling reabriu log fechado");
  await page.click('[data-tab="add"]');await page.waitForSelector("#add-cards .card");if(await page.locator("#add-cards").count()!==1||await page.locator("#add-cards .card").count()!==5)throw new Error("Adicionar não possui um único conjunto de cinco cards");
  const addCounts=await page.locator("#add-cards .card strong").allTextContents();if(Number(addCounts[0])!==addCounts.slice(1).reduce((a,v)=>a+Number(v),0))throw new Error("Total de Adicionar incoerente");
  await page.locator('#add-cards [data-add-group="prepared"]').click();await sleep(350);if(await page.locator("#add-list tr[data-add-job]").count()!==Number(addCounts[1]))throw new Error("Preparados de Adicionar divergem do card");
  await page.locator('#add-cards [data-add-group="error"]').click();await sleep(350);if(await page.locator("#add-list tr[data-add-job]").count()!==Number(addCounts[4]))throw new Error("Erros de Adicionar divergem do card");
  await page.locator("#add-list [data-add-select]").first().click();await page.waitForFunction(()=>document.querySelector("#add-details").textContent.includes("PluginTheme"));
  await page.locator('#add-cards [data-add-group=""]').click();await page.locator("#add-page-size").selectOption("10");await sleep(500);await page.locator("#add-next").click();await sleep(4000);if(!(await page.locator("#add-page").innerText()).includes("Página 2")||await page.locator("#add-page-size").inputValue()!=="10")throw new Error("Polling não preservou página 2/page size em Adicionar");await page.locator("#add-query").fill("e2e-add");await sleep(350);
  await page.evaluate(()=>{const details=document.querySelector("#add-log-details");details.open=true;window.__addDetails=details});await sleep(26000);
  const addStable=await page.evaluate(()=>({same:window.__addDetails===document.querySelector("#add-log-details"),open:document.querySelector("#add-log-details").open,query:document.querySelector("#add-query").value,group:document.querySelector("#add-group").value,pageSize:document.querySelector("#add-page-size").value,page:document.querySelector("#add-page").textContent}));if(!addStable.same||!addStable.open||addStable.query!=="e2e-add"||addStable.group!==""||addStable.pageSize!=="10"||!addStable.page.includes("Página 1"))throw new Error("Polling de Adicionar alterou DOM/estado: "+JSON.stringify(addStable));
  await page.evaluate(()=>document.querySelector("#add-log-details").open=false);await sleep(2600);if(await page.locator("#add-log-details").evaluate(d=>d.open))throw new Error("Polling reabriu log de Adicionar");
  await page.setViewportSize({width:390,height:844});const overflow=await page.evaluate(()=>({page:document.documentElement.scrollWidth>innerWidth,elements:[...document.querySelectorAll("body *")].filter(x=>x.getBoundingClientRect().right>innerWidth+1&&!x.closest(".table-wrap,.tabs")).slice(0,8).map(x=>({tag:x.tagName,id:x.id,class:x.className,right:Math.round(x.getBoundingClientRect().right)}))}));if(overflow.page)throw new Error("Overflow horizontal mobile: "+JSON.stringify(overflow.elements));
  if(errors.length)throw new Error(errors.join(" | "));console.log(JSON.stringify({ok:true,collection:true,comparison:true,updates:true,additions:true,updateDetailsStable:true,addDetailsStable:true,rows,mobile:true,consoleErrors:0}));
}finally{if(browser)await browser.close();server.kill();rmSync(fixture,{recursive:true,force:true})}
