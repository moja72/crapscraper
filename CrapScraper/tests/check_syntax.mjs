import {readdirSync} from 'node:fs';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';

function run(command,args){
  const result=spawnSync(command,args,{stdio:'inherit'});
  if(result.error)throw result.error;
  if(result.status!==0)process.exit(result.status||1);
}
function files(root){return readdirSync(root,{withFileTypes:true}).flatMap(entry=>
  entry.isDirectory()?files(join(root,entry.name)):[join(root,entry.name)]);}
run(process.env.PYTHON||'python',['-m','compileall','-q','main.py','app','tests']);
const scripts=[...files('app/static/js'),...files('tests')].filter(path=>/\.(?:m?js)$/.test(path));
for(const script of scripts)run(process.execPath,['--check',script]);
console.log(JSON.stringify({ok:true,pythonSyntax:true,javascriptFiles:scripts.length}));
