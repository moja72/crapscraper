import {get,post} from "./api.js";

const $=(selector,root=document)=>root.querySelector(selector);
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

function ensureUi(){
  const section=$(".plugintheme-session"),check=$("#update-environment-refresh");
  if(!section||!check)return null;
  const copy=section.firstElementChild;
  copy?.classList.add("plugintheme-session-copy");
  let credit=$("#update-plugintheme-credit");
  if(!credit){credit=document.createElement("p");credit.id="update-plugintheme-credit";credit.textContent="Créditos: indisponível.";copy?.append(credit)}
  let status=$("#update-plugintheme-status");
  if(!status){status=document.createElement("div");status.id="update-plugintheme-status";status.className="plugintheme-status";status.setAttribute("aria-live","polite");status.textContent="Use Verificar pré-requisitos para validar a área protegida e consultar o saldo.";copy?.append(status)}
  let actions=$(".plugintheme-actions",section);
  if(!actions){actions=document.createElement("div");actions.className="plugintheme-actions";section.append(actions);actions.append(check)}
  let renew=$("#update-plugintheme-renew");
  if(!renew){renew=document.createElement("button");renew.id="update-plugintheme-renew";renew.type="button";renew.textContent="Renovar sessão PluginTheme";actions.prepend(renew)}
  check.classList.add("primary");check.type="button";
  return{credit,status,renew,check};
}

function render(data){
  const ui=ensureUi(),plugin=data?.plugintheme||{};if(!ui)return;
  $("#update-environment-summary").textContent=data.attention_count?`${data.attention_count} requisito(s) exigem atenção`:"Todos os requisitos validados";
  $("#update-environment-chips").innerHTML=(data.checks||[]).map(item=>`<article class="environment-chip" data-state="${escapeHtml(item.state)}" title="${escapeHtml(item.detail||"")}"><div><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.value)}</span></div><button class="help-tip" type="button" data-tooltip="${escapeHtml(item.detail||"Diagnóstico de configuração.")}" aria-label="Ajuda sobre ${escapeHtml(item.label)}">?</button></article>`).join("");
  const httpOnly=plugin.httponly_cookie_count?` (${plugin.httponly_cookie_count} HttpOnly)`:"";
  $("#update-plugintheme-session").textContent=`${plugin.status||"NÃO VALIDADA"} · ${Number(plugin.cookie_count||0)} cookie(s)${httpOnly}.`;
  const known=plugin.credits!==null&&plugin.credits!==undefined&&plugin.credits!==""&&Number.isInteger(Number(plugin.credits));
  ui.credit.textContent=known?`Créditos: ${Number(plugin.credits)}${plugin.credit_stale?" · última confirmação conhecida":""}.`:"Créditos: indisponível.";
  const diagnostics=[];
  diagnostics.push(plugin.configured?"Configuração encontrada.":"Configuração não encontrada.");
  diagnostics.push(plugin.profile_exists?"Perfil carregado.":"Perfil não encontrado.");
  if(plugin.authenticated)diagnostics.push("Sessão autenticada confirmada.");
  else if(plugin.login_redirect)diagnostics.push("A área protegida redirecionou para o login.");
  if(plugin.credit_limit!==null&&plugin.credit_limit!==undefined)diagnostics.push(`Limite diário do plano: ${Number(plugin.credit_limit)}; saldo restante não exposto pelo provedor.`);
  if(plugin.current_url)diagnostics.push(`URL final: ${plugin.current_url}.`);
  if(plugin.last_error&&!plugin.authenticated)diagnostics.push(`Motivo: ${plugin.last_error}`);
  for(const line of plugin.logs||[])if(line&&!diagnostics.includes(line))diagnostics.push(line);
  ui.status.textContent=diagnostics.join(" ")||"Nenhuma validação executada.";
}

async function verify(force=false){
  const ui=ensureUi();if(!ui)return;
  if(force){ui.check.disabled=true;ui.check.textContent="Verificando…";ui.status.textContent="PluginTheme: validando configuração e perfil… Consultando a área protegida e os créditos…"}
  try{render(force?await post("/api/updates/environment/check",{}):await get("/api/updates/environment"))}
  catch(error){ui.status.textContent=`Não foi possível verificar o PluginTheme. Motivo: ${error.message}`}
  finally{if(force){ui.check.disabled=false;ui.check.textContent="Verificar pré-requisitos"}}
}

document.addEventListener("click",async event=>{
  const check=event.target.closest("#update-environment-refresh"),renew=event.target.closest("#update-plugintheme-renew");
  if(!check&&!renew)return;
  event.preventDefault();event.stopImmediatePropagation();
  if(check)return verify(true);
  const ui=ensureUi();renew.disabled=true;renew.textContent="Abrindo…";ui.status.textContent="Abrindo o perfil exclusivo do PluginTheme para renovação…";
  try{const result=await post("/api/updates/plugintheme/renew",{});ui.status.textContent=result.message||"Janela de renovação aberta."}
  catch(error){ui.status.textContent=`Não foi possível abrir a renovação. Motivo: ${error.message}`}
  finally{renew.disabled=false;renew.textContent="Renovar sessão PluginTheme"}
},true);

document.addEventListener("app:tab",event=>{if(event.detail==="update")verify(false)});
ensureUi();
