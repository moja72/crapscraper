import {spawn} from 'node:child_process';

const selected=process.argv.slice(2);
const scripts=selected.length?selected:[
  'tests/update_execution_ui.mjs','tests/update_progress_ui.mjs','tests/chatgpt_dom_ui.mjs',
  'tests/store_ui.mjs','tests/compare_ui.mjs','tests/compare_loading_ui.mjs',
  'tests/update_ui.mjs','tests/catalogs_ui.mjs','tests/collect_ui.mjs',
  'tests/credits_ui.mjs','tests/plugintheme_update_ui.mjs','tests/e2e.mjs',
];
const results=[];
for(const script of scripts){
  console.log(`Running ${script}`);
  const child=spawn(process.execPath,[script],{stdio:'inherit'});
  const exitCode=await new Promise((resolve,reject)=>{
    child.once('error',reject);
    child.once('close',code=>resolve(code??1));
  });
  results.push({script,exitCode});
  console.log(JSON.stringify(results.at(-1)));
}
console.log(JSON.stringify({ok:results.every(result=>result.exitCode===0),results}));
process.exitCode=results.some(result=>result.exitCode!==0)?1:0;
