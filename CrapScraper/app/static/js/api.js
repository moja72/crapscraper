export async function request(path, options={}){
  const {timeoutMs,...fetchOptions}=options,controller=timeoutMs?new AbortController():null;
  const timer=controller?setTimeout(()=>controller.abort(),timeoutMs):null;
  try{
    const response=await fetch(path,{headers:{"Content-Type":"application/json"},...fetchOptions,...(controller?{signal:controller.signal}:{})});
    const data=await response.json();
    if(!response.ok||data.ok===false)throw new Error(data.message||data.error?.message||`HTTP ${response.status}`);
    return data;
  }catch(error){
    if(error.name==="AbortError")throw new Error("A resposta da execução demorou além do limite. Confira o estado atualizado do produto antes de tentar novamente.");
    throw error;
  }finally{if(timer)clearTimeout(timer)}
}
export const get=path=>request(path);export const post=(path,body={},options={})=>request(path,{method:"POST",body:JSON.stringify(body),...options});
