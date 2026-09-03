const PAGE_SELECTOR='[data-page="add"]';

function ensureAddHeading(){
  const page=document.querySelector(PAGE_SELECTOR);
  if(!page||page.querySelector('[data-add-page-heading="1"]'))return;
  const environment=page.querySelector('#add-environment');
  if(!environment)return;
  const heading=document.createElement('div');
  heading.className='page-head';
  heading.dataset.addPageHeading='1';
  heading.innerHTML='<div><h1>Adicionar</h1><p>Novos produtos aprovados, preparados e publicados com segurança no WooCommerce.</p></div>';
  environment.before(heading);
}

queueMicrotask(ensureAddHeading);
setTimeout(ensureAddHeading,0);
document.addEventListener('app:tab',event=>{if(event.detail==='add')ensureAddHeading()});
