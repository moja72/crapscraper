import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const cwd=fileURLToPath(new URL('..',import.meta.url));
const python=process.env.PYTHON || 'python';
function bridge(payload){
  const result=spawnSync(python,['tests/chatgpt_dom_bridge.py'],{cwd,input:JSON.stringify(payload),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  return JSON.parse(result.stdout);
}
const scripts=bridge({op:'selectors'}),product='Agricola - Agriculture and Organic Farm WordPress Theme';
const raw=readFileSync(new URL('fixtures/agricola_dom_response.txt',import.meta.url),'utf8');
const safe=text=>text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage();
  const content=marker=>page.evaluate(({source,marker})=>(0,eval)(`(${source})`)(marker),{source:scripts.content,marker});
  const image=(id,marker)=>page.locator(id).evaluate((node,{source,marker})=>(0,eval)(`(${source})`)(node,marker),{source:scripts.image,marker});
  const layouts=[
    (role,text)=>`<div data-message-author-role="${role}">${text}</div>`,
    (role,text)=>`<article data-testid="conversation-turn-${Math.random()}"><div data-message-author-role="${role}">${text}</div></article>`,
    (role,text)=>`<article aria-label="${role==='user'?'Você disse':'ChatGPT disse'}">${text}</article>`,
  ];
  for(const turn of layouts){
    const current=turn('user','CSCONTENT-current')+turn('assistant',`<pre><code>${safe(raw)}</code></pre><img id="right">`);
    await page.setContent('<main>'+turn('assistant',safe(raw))+current+
      turn('user','CSCONTENT-other')+turn('assistant','<img id="wrong">'+safe(raw))+'</main>');
    const values=await content('CSCONTENT-current');
    assert(values.length>=1);
    assert.equal(bridge({op:'parse',text:values[0].text,product}).product_name,product);
    assert.equal(await image('#right','CSCONTENT-current'),true);
    assert.equal(await image('#wrong','CSCONTENT-current'),false);
    assert.deepEqual(await content('missing-marker'),[]);
    await page.setContent('<main>'+turn('user','CSCONTENT-current')+
      '<article>Unknown turn</article>'+turn('assistant',safe(raw))+'</main>');
    assert.deepEqual(await content('CSCONTENT-current'),[]);
  }
  console.log(JSON.stringify({ok:true,chatgptDomLayouts:layouts.length,agricola:true,imageTurnIsolation:true,unknownTurnRejected:true}));
}finally{await browser.close()}
