import {spawn} from "node:child_process";
import {mkdtempSync,rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {chromium} from "playwright";

const port="8783",fixture=mkdtempSync(join(tmpdir(),"crapscraper-store-e2e-")),cwd=new URL("..",import.meta.url).pathname.replace(/^\/(.:)/,"$1");
const server=spawn(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3.11"),["main.py"],{cwd,env:{...process.env,SCRAPER_PORT:port,SCRAPER_DATA_DIR:fixture,SCRAPER_UPDATE_IMPORT_LEGACY:"0",SCRAPER_ADDITION_IMPORT_LEGACY:"0"},stdio:"ignore"});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ready(){for(let index=0;index<60;index++){try{if((await fetch(`http://127.0.0.1:${port}/api/health`)).ok)return}catch{}await sleep(250)}throw new Error("Servidor não iniciou")}

let enabled=false,toggleCalls=0,qualityCalls=0,productPreviewCalls=0;
const monitor=()=>({enabled,configured:true,state:"success",stage:"completed",last_run_at:"2026-09-01T12:00:00Z",next_check_at:enabled?"2026-09-01T12:05:00Z":"",current_product:"",woo_product_id:0,source:"",current_version:"",found_version:"",request_state:"",interval_seconds:300,logs:["[09:00:00] Monitor iniciado.","[09:00:01] Nenhuma solicitação pendente."],history:[{result:"success",started_at:"2026-09-01T12:00:00Z",product:"",woo_product_id:0}]});
const quality={ok:true,total:1,page:1,page_size:10,pages:1,analysis_complete:true,items:[{product_id:101,product_name:"Elementor Demo",type:"plugin",version:"1.0",developer:"Demo",official_url:"https://example.test",short_description:"Descrição",categories:["Elementor","WooCommerce"],problems:[],problem_codes:[]}]};
const environment={ok:true,attention_count:0,checks:[{key:"woocommerce",label:"WooCommerce",state:"ok",value:"VALIDADO",detail:"Leitura confirmada."},{key:"store_write",label:"Escrita de preços",state:"ok",value:"HABILITADA",detail:"Gate ativo."},{key:"wordpress_monitor",label:"Monitor WordPress",state:"ok",value:"CONFIGURADO",detail:"HMAC ativo."}]};
const pricing={ok:true,write_enabled:true,individual:{total:1,page:1,page_size:10,pages:1,available_products:{plugin:1,theme:1},items:[{product_id:101,product_name:"Elementor Demo",product_type:"variable",kind:"plugin",pricing_mode:"variations",regular_price:"",sale_price:"",variations:[{id:1011,name:"Anual",period:"annual",regular_price:"99.00",sale_price:"79.00"},{id:1012,name:"Vitalícia",period:"lifetime",regular_price:"199.00",sale_price:"149.00"}]}]},packs:{items:[{product_id:200,product_name:"Pack Demo",product_type:"simple",price_group:"pack",regular_price:"299.00",sale_price:"249.00",variations:[]}]},plans:{items:[{product_id:300,product_name:"Plano Demo",product_type:"simple",price_group:"plan",regular_price:"399.00",sale_price:"349.00",variations:[]}]}};

let browser;
try{
  await ready();browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
  page.on("console",message=>{if(message.type()==="error")errors.push(message.text())});page.on("pageerror",error=>errors.push(error.message));
  await page.route("**/api/credits?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,credits:1,status:"success",logs:[]})}));
  await page.route("**/api/store/summary",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,counts:{products:1,plugins:1,themes:0,packs:1},monitor:monitor()})}));
  await page.route("**/api/store/environment",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/store/environment/check",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(environment)}));
  await page.route("**/api/store/pricing/catalog?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(pricing)}));
  await page.route("**/api/store/categories",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,items:[{id:1,name:"Elementor",count:1},{id:2,name:"WooCommerce",count:1}]})}));
  await page.route("**/api/store/quality/products?*",route=>{qualityCalls+=1;return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(quality)})});
  await page.route("**/api/store/product?*",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,item:{id:101,name:"Elementor Demo",type:"variable",status:"publish"},variations:[{id:1}],issues:[]})}));
  await page.route("**/api/store/monitor/enable",route=>{enabled=true;toggleCalls+=1;return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,monitor:monitor()})})});
  await page.route("**/api/store/monitor/disable",route=>{enabled=false;toggleCalls+=1;return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,monitor:monitor()})})});
  await page.route("**/api/store/monitor/run",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,processed:0,monitor:monitor()})}));
  await page.route("**/api/store/pricing/preview",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,affected:2,unchanged:0,changes:[]})}));
  await page.route("**/api/store/pricing/product/preview",async route=>{productPreviewCalls+=1;const request=route.request();const payload=request.postDataJSON();if(payload.product_id!==101||payload.variations?.length!==2)return route.fulfill({status:400,contentType:"application/json",body:JSON.stringify({ok:false,message:"Payload individual inválido"})});return route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,product_id:101,status:"change",variation_changes:payload.variations})})});

  await page.goto(`http://127.0.0.1:${port}/`,{waitUntil:"networkidle"});await page.click('[data-tab="store"]');await page.waitForSelector('#store-quality tr[data-store-select]');await page.waitForSelector('[data-product-price-card="101"]',{state:"attached"});
  const headings=await page.locator('[data-page="store"] h2').allTextContents();if(headings.slice(0,4).join('|')!=="Ambiente|Atualizações solicitadas pelo WordPress|Preços da Loja|Qualidade dos Produtos")throw new Error(`Ordem da Loja divergiu: ${headings.join('|')}`);
  if(await page.locator('.store-pricing-accordion').count()!==3)throw new Error("Loja não possui exatamente três sanfonas de preço");
  const accordions=await page.locator('.store-pricing-accordion summary').allTextContents();if(accordions.join('|')!=="Preços de Plugins e Temas|Preços de Pacotes|Preços de Planos")throw new Error(`Sanfonas divergiram: ${accordions.join('|')}`);
  await page.locator('.store-pricing-accordion').first().locator('summary').click();await sleep(1700);if(!await page.locator('.store-pricing-accordion').first().evaluate(element=>element.open))throw new Error("Polling fechou sanfona aberta");
  await page.waitForSelector('[data-product-price-card="101"]',{state:"visible"});
  if(!await page.locator('#store-product-price-query').count())throw new Error("Busca de preço individual não foi renderizada");
  if(await page.locator('[data-product-price-variation]').count()!==2)throw new Error("Variações do produto individual não foram renderizadas");
  await page.click('[data-product-price-card="101"] [data-product-price-preview]');await page.waitForFunction(()=>document.querySelector('[data-product-price-card="101"] [data-product-price-status]')?.textContent.includes('Prévia validada'));if(productPreviewCalls!==1)throw new Error(`Prévia individual chamou backend ${productPreviewCalls} vezes`);
  if(!String(await page.locator('#store-monitor-log').textContent()).includes('Nenhuma solicitação pendente'))throw new Error("Log do monitor não carregou");
  await page.click('#store-monitor-toggle');await page.waitForFunction(()=>document.querySelector('#store-monitor-toggle').getAttribute('aria-checked')==='true');if(toggleCalls!==1)throw new Error(`Toggle chamou backend ${toggleCalls} vezes`);
  await page.fill('#store-quality-query','Elementor');await sleep(350);if(qualityCalls<2)throw new Error("Busca de qualidade não consultou backend");
  await page.click('[data-store-select="101"]');await page.waitForFunction(()=>document.querySelector('#store-details')?.textContent.includes('WooCommerce'));
  await page.setViewportSize({width:375,height:812});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error("Loja causou overflow horizontal");
  if(errors.length)throw new Error(errors.join(" | "));
  console.log(JSON.stringify({ok:true,order:true,monitor:true,persistentToggle:true,pricingAccordions:true,individualPricing:true,quality:true,categories:true,stablePolling:true,responsive:true,qualityCalls,productPreviewCalls}));
}finally{if(browser)await browser.close();server.kill();await Promise.race([new Promise(resolve=>server.once("exit",resolve)),sleep(5000)]);rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200})}
