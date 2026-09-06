import {spawn} from 'node:child_process';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function isolatedUI(port){
  const fixture=mkdtempSync(join(tmpdir(),'crapscraper-ui-'));
  const source=join(fixture,'slots/default/ultrapackv2/plugin/coproducaolancamentos');
  mkdirSync(source,{recursive:true});mkdirSync(join(fixture,'imports'));
  writeFileSync(join(source,'catalog.csv'),'nome_produto,versao_produto,pagina_oficial,categoria_nome,link_produto\n'+
    Array.from({length:16},(_,i)=>`E2E Plugin ${i+1},2.0,https://vendor.test/${i+1},Plugins,https://ultrapackv2.example/product/${i+1}`).join('\n'));
  writeFileSync(join(fixture,'imports/plugintema-products.csv'),'ID,Nome,Tipo,Metadado: pt_versao,Metadado: site_oficial,URL,Categorias\n'+
    Array.from({length:15},(_,i)=>`${101+i},E2E Plugin ${i+1},variable,1.0,https://vendor.test/${i+1},https://shop.test/${i+1},Plugins`).join('\n'));
  const base=`http://127.0.0.1:${port}`;
  const server=spawn(process.env.PYTHON||'python',['tests/e2e_server.py'],{
    cwd:fileURLToPath(new URL('..',import.meta.url)),
    env:{...Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith('SCRAPER_'))),
      SCRAPER_PORT:String(port),SCRAPER_DATA_DIR:fixture,
      SCRAPER_COMPARISON_DECISIONS_DB_PATH:join(fixture,'comparison.sqlite3'),
      SCRAPER_UPDATE_IMPORT_LEGACY:'0',SCRAPER_ADDITION_IMPORT_LEGACY:'0',
      SCRAPER_STORE_E2E_FIXTURES:'1',SCRAPER_WORDPRESS_MANUAL_POLLING_ENABLED:'0'},
    stdio:['ignore','ignore','pipe']});
  let errors='';server.stderr.on('data',data=>{errors=(errors+data).slice(-6000)});
  const exited=new Promise(resolve=>server.once('exit',resolve));
  async function close(){
    if(server.exitCode===null){server.kill();await exited}
    rmSync(fixture,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
  try{
    for(let i=0;i<80;i++){
      if(server.exitCode!==null)throw new Error('E2E server exited: '+errors);
      try{if((await fetch(base+'/api/health')).ok)return{base,close}}catch{}
      await sleep(250);
    }
    throw new Error('E2E server did not start: '+errors);
  }catch(error){await close();throw error}
}
