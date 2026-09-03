const $=(selector,root=document)=>root.querySelector(selector);
const $$=(selector,root=document)=>[...root.querySelectorAll(selector)];

const DEFAULT_PAGE_SIZE="5";
let comparisonPreviewCatalogId="";
let collectPreviewSlot="";
let refineTimer=0;

function ensureStyle(){
  if(document.getElementById("catalog-modal-standardization-style"))return;
  const style=document.createElement("style");
  style.id="catalog-modal-standardization-style";
  style.textContent=`
    #comparison-catalog-list .catalog-card.is-previewing,
    #catalog-cards .catalog-card.is-previewing{
      border-color:var(--accent)!important;
      box-shadow:0 0 0 2px rgba(34,197,94,.28),0 10px 28px rgba(0,0,0,.22)!important;
    }
    #comparison-catalog-list .catalog-card.is-previewing [data-catalog-preview],
    #catalog-cards .catalog-card.is-previewing [data-catalog-view]{
      background:var(--accent)!important;
      border-color:var(--accent)!important;
      color:#04120a!important;
    }
  `;
  document.head.appendChild(style);
}

function standardizeComparisonPageSize(){
  const select=$("#comparison-catalog-preview-page-size");
  if(!select)return;

  if(!select.querySelector('option[value="5"]')){
    const option=document.createElement("option");
    option.value=DEFAULT_PAGE_SIZE;
    option.textContent=DEFAULT_PAGE_SIZE;
    select.insertBefore(option,select.firstChild);
  }

  if(select.dataset.defaultFiveApplied==="1")return;
  select.dataset.defaultFiveApplied="1";
  select.value=DEFAULT_PAGE_SIZE;
  select.dispatchEvent(new Event("change",{bubbles:true}));
}

function standardizeComparisonButtons(){
  $$("#comparison-catalog-list [data-catalog-preview]").forEach(button=>{
    if(button.textContent.trim()!=="Visualizar")button.textContent="Visualizar";
    button.title="Visualizar catálogo";
    button.setAttribute("aria-label","Visualizar catálogo");
  });
}

function standardizeCollectButtons(){
  $$("#catalog-cards [data-catalog-view]").forEach(button=>{
    if(button.textContent.trim()!=="Visualizar")button.textContent="Visualizar";
    button.title="Visualizar catálogo";
    const card=button.closest(".catalog-card");
    const name=card?.querySelector("h3")?.textContent?.trim();
    button.setAttribute("aria-label",name?`Visualizar catálogo ${name}`:"Visualizar catálogo");
  });
}

function highlightComparisonCatalog(){
  $$("#comparison-catalog-list .catalog-card").forEach(card=>{
    const id=card.querySelector("[data-catalog-preview]")?.dataset.catalogPreview||"";
    card.classList.toggle("is-previewing",Boolean(comparisonPreviewCatalogId)&&id===comparisonPreviewCatalogId);
  });
}

function highlightCollectCatalog(){
  $$("#catalog-cards .catalog-card").forEach(card=>{
    const slot=card.querySelector("[data-catalog-view]")?.dataset.catalogView||"";
    card.classList.toggle("is-previewing",Boolean(collectPreviewSlot)&&slot===collectPreviewSlot);
  });
}

function refine(){
  refineTimer=0;
  ensureStyle();
  standardizeComparisonPageSize();
  standardizeComparisonButtons();
  standardizeCollectButtons();
  highlightComparisonCatalog();
  highlightCollectCatalog();
}

function scheduleRefine(){
  if(refineTimer)return;
  refineTimer=window.setTimeout(refine,20);
}

document.addEventListener("click",event=>{
  const comparisonButton=event.target.closest?.("#comparison-catalog-list [data-catalog-preview]");
  if(comparisonButton){
    comparisonPreviewCatalogId=comparisonButton.dataset.catalogPreview||"";
    scheduleRefine();
  }

  const collectButton=event.target.closest?.("#catalog-cards [data-catalog-view]");
  if(collectButton){
    collectPreviewSlot=collectButton.dataset.catalogView||"";
    scheduleRefine();
  }
},true);

new MutationObserver(scheduleRefine).observe(document.documentElement,{childList:true,subtree:true});

if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",refine,{once:true});
else refine();
