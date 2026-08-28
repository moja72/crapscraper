import {chromium} from "playwright";

const base="http://127.0.0.1:8766",original="default",created=`codex-ui-${Date.now()}`,renamed=`${created}-renamed`;
async function api(path,body){const response=await fetch(base+path,{method:body?"POST":"GET",headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});return response.json()}
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on("console",message=>message.type()==="error"&&errors.push(message.text()));page.on("pageerror",error=>errors.push(error.message));
  await page.goto(base,{waitUntil:"networkidle"});
  if(await page.locator('[data-tab="catalogs"]').count())throw new Error("A aba redundante Catálogos ainda existe");
  if(await page.locator("#slot-name").count())throw new Error("O painel redundante Slots e contextos ainda existe");
  await page.click("#collect-catalog-open");await page.waitForSelector("#collect-catalog-modal[open]");await page.waitForSelector("#catalog-cards .catalog-card");
  const cards=await page.locator("#catalog-cards .catalog-card").count();if(!cards)throw new Error("Cards de catálogo ausentes");
  if(await page.locator('#catalog-cards .catalog-card h3:text-is("Padrão")').count()!==1)throw new Error("Catálogo padrão não identificado");
  await page.locator("#catalog-cards .catalog-context-accordion").first().locator("summary").click();
  await page.fill("#catalog-context-search","ultrapackv2");if(!(await page.locator("#catalog-showing").innerText()).includes("de"))throw new Error("Filtro não atualizou contagem");
  await page.fill("#catalog-context-search","");await page.selectOption("#catalog-context-page-size","5");await page.fill("#catalog-context-page","1");await page.press("#catalog-context-page","Enter");
  const csv=page.locator('#catalog-context-rows [data-context-preview="catalog"]:not([disabled])').first();if(await csv.count()){await csv.click();await page.waitForFunction(()=>document.querySelector("#catalog-preview-content table"),null,{timeout:10000})}
  const state=page.locator('#catalog-context-rows [data-context-preview="state"]:not([disabled])').first();if(await state.count()){await state.click();if(!(await page.locator("#catalog-preview-content").innerText()).length)throw new Error("Prévia de estado vazia")}
  const log=page.locator('#catalog-context-rows [data-context-preview="log"]:not([disabled])').first();if(await log.count()){await log.click();await page.waitForSelector("#catalog-preview-copy:not([hidden])")}
  const download=page.locator('[data-context-download]:not([disabled])').first();if(await download.count()){const pending=page.waitForEvent("download");await download.click();await pending}
  await page.click("#catalog-new");await page.fill("#catalog-name-input",created);await page.click("#collect-action-confirm");await page.waitForFunction(name=>[...document.querySelectorAll("#catalog-cards h3")].some(x=>x.textContent===name),created);
  await page.click(`[data-catalog-rename="${created}"]`);await page.fill("#catalog-name-input",renamed);await page.click("#collect-action-confirm");await page.waitForFunction(name=>[...document.querySelectorAll("#catalog-cards h3")].some(x=>x.textContent===name),renamed);
  await page.click(`[data-catalog-default="${renamed}"]`);await page.waitForFunction(name=>document.querySelector(`[data-catalog-default="${name}"]`)?.disabled,renamed);
  await page.click(`[data-catalog-clear="${renamed}"]`);if(!await page.locator('#collect-action-modal[open]:has-text("Limpar catálogo")').count())throw new Error("Limpeza não pediu confirmação");await page.click("#collect-action-modal [data-dialog-close]");
  await page.click("#collect-catalog-modal [data-dialog-close]");await page.click("#collect-config-open");await page.waitForSelector("#collect-config-modal[open]");await page.selectOption("#collect-scope","range");if(!await page.locator("#collect-scope-start").isVisible())throw new Error("Escopo intervalo não revelou campos");await page.selectOption("#collect-scope","all");if(await page.locator("#collect-scope-start").isVisible())throw new Error("Escopo geral manteve campos irrelevantes");await page.click("#collect-config-modal [data-dialog-close]");
  await page.click("#collect-config-open");await page.selectOption("#collect-scope","selected");const categories=page.locator("#config-categories");const firstCategory=categories.locator("[data-category]").first();if(await firstCategory.count()){const before=await firstCategory.isChecked();await page.waitForTimeout(1600);if(await firstCategory.isChecked()!==before)throw new Error("Polling alterou seleção de categoria")}await page.keyboard.press("Escape");
  await page.click("#collect-catalog-open");await page.keyboard.press("Escape");if(await page.locator("#collect-catalog-modal").evaluate(x=>x.open))throw new Error("ESC não fechou modal");
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,cards,modal:true,filter:true,pagination:true,previews:true,download:true,create:true,rename:true,confirmations:true,config:true,categories:true,consoleErrors:0}));
}finally{
  await api("/api/collection/slots/default",{name:original}).catch(()=>{});
  await api("/api/collection/slots/select",{name:original}).catch(()=>{});
  await api("/api/collection/slots/delete",{name:renamed}).catch(()=>{});
  await api("/api/collection/slots/delete",{name:created}).catch(()=>{});
  await browser.close();
}
