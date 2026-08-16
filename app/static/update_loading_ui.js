(() => {
  "use strict";

  const PANEL_ID = "tab_panel_atualizacoes";
  const OVERLAY_ID = "cs_update_loading_overlay";
  const STYLE_ID = "cs_update_loading_style";
  const CACHE_KEY = "crapscraper:update-loading-cache:v1";
  const MAX_CACHE_AGE = 24 * 60 * 60 * 1000;
  const MIN_VISIBLE_MS = 450;
  const MAX_VISIBLE_MS = 9000;
  let shownAt = 0;
  let hideTimer = null;
  let catalogMetadataPromise = null;
  let catalogMetadataAt = 0;

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #${PANEL_ID}{position:relative!important;}
    #${OVERLAY_ID}{
      position:absolute;inset:0;z-index:40;display:flex;flex-direction:column;gap:14px;
      padding:0;background:var(--bg,#09090b);pointer-events:none;transition:opacity .22s ease;
    }
    #${OVERLAY_ID}.is-hiding{opacity:0;}
    .cs-update-loading-head{display:flex;align-items:center;gap:10px;color:var(--text-muted,#9ca3af);font-size:13px;padding:4px 2px;}
    .cs-update-loading-spinner{width:15px;height:15px;border-radius:50%;border:2px solid rgba(255,255,255,.14);border-top-color:var(--accent,#8b5cf6);animation:csUpdateSpin .75s linear infinite;}
    .cs-update-sk-card{border:1px solid var(--line,#27272a);border-radius:16px;padding:18px;background:#111113;display:grid;gap:14px;}
    .cs-update-sk-row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;}
    .cs-update-sk-line,.cs-update-sk-pill,.cs-update-sk-button,.cs-update-sk-block{
      position:relative;overflow:hidden;background:rgba(255,255,255,.06);border-radius:8px;
    }
    .cs-update-sk-line::after,.cs-update-sk-pill::after,.cs-update-sk-button::after,.cs-update-sk-block::after{
      content:"";position:absolute;inset:0;transform:translateX(-100%);
      background:linear-gradient(90deg,transparent,rgba(255,255,255,.12),transparent);
      animation:csUpdateSweep 1.15s ease-in-out infinite;
    }
    .cs-update-sk-line{height:14px}.cs-update-sk-pill{height:34px;border-radius:999px}.cs-update-sk-button{height:44px;border-radius:10px}.cs-update-sk-block{height:72px;border-radius:12px}
    .w-12{width:12%}.w-18{width:18%}.w-24{width:24%}.w-32{width:32%}.w-45{width:45%}.w-60{width:60%}.w-75{width:75%}.w-100{width:100%}
    @keyframes csUpdateSpin{to{transform:rotate(360deg)}}
    @keyframes csUpdateSweep{100%{transform:translateX(100%)}}
    @media (prefers-reduced-motion:reduce){.cs-update-loading-spinner,.cs-update-sk-line::after,.cs-update-sk-pill::after,.cs-update-sk-button::after,.cs-update-sk-block::after{animation:none!important}}
  `;
  document.head.appendChild(style);

  function panel(){ return document.getElementById(PANEL_ID); }
  function txt(node){ return String(node?.textContent || "").replace(/\s+/g," ").trim(); }
  function normalize(value){ return String(value ?? "").replace(/\s+/g," ").trim(); }

  function formatCount(value){
    const number = Number(String(value ?? "").replace(/\D/g, ""));
    return Number.isFinite(number) ? number.toLocaleString("pt-BR") : "0";
  }

  function formatDateBR(value){
    const raw = normalize(value);
    if(!raw) return "";
    if(/^\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2}$/.test(raw)) return raw;
    const date = new Date(raw);
    if(Number.isNaN(date.getTime())) return raw;
    return date.toLocaleString("pt-BR", {
      day:"2-digit", month:"2-digit", year:"numeric",
      hour:"2-digit", minute:"2-digit", hour12:false
    }).replace(",", "");
  }

  function catalogKey(slot, site, type, account){
    return [slot,site,type,account].map(value => normalize(value).toLowerCase()).join("|");
  }

  async function loadCatalogMetadata(){
    const now = Date.now();
    if(catalogMetadataPromise && now - catalogMetadataAt < 30000) return catalogMetadataPromise;
    catalogMetadataAt = now;
    catalogMetadataPromise = Promise.all([
      fetch("/catalogos/data", {credentials:"same-origin"}).then(r => r.ok ? r.json() : {}).catch(() => ({})),
      fetch("/comparacao/fontes", {credentials:"same-origin"}).then(r => r.ok ? r.json() : {}).catch(() => ({}))
    ]).then(([catalogs, sources]) => {
      const rows = Array.isArray(catalogs?.catalogos) ? catalogs.catalogos : (Array.isArray(catalogs?.rows) ? catalogs.rows : []);
      const saved = new Map();
      rows.forEach(row => {
        saved.set(catalogKey(row.slot_name || row.catalogo_nome, row.site_key, row.item_type_key, row.account_key), row);
      });
      const imported = new Map();
      (Array.isArray(sources?.imported_catalogs) ? sources.imported_catalogs : []).forEach(item => imported.set(normalize(item.id), item));
      return {saved, imported};
    });
    return catalogMetadataPromise;
  }

  async function formatComparisonCatalogSelectors(){
    const source = document.getElementById("comparison_source_catalog");
    const target = document.getElementById("comparison_target_catalog");
    if(!source && !target) return;
    const metadata = await loadCatalogMetadata();

    if(source){
      Array.from(source.options || []).forEach(option => {
        const value = normalize(option.value);
        if(!value || !value.startsWith("saved|")) return;
        const parts = value.split("|");
        const slot = parts[1] || "";
        const site = parts[2] || "";
        const type = parts[3] || "";
        const account = parts[4] || "";
        const row = metadata.saved.get(catalogKey(slot,site,type,account));
        const displaySlot = slot.toLowerCase() === "default" ? "Padrão" : slot;
        const date = normalize(row?.updated_at);
        const count = row?.items_count ?? (option.textContent.match(/\((\d+)\s+itens\)/i)?.[1] || 0);
        const label = `${displaySlot} • ${site} • ${type} • ${account}${date ? ` | ${date}` : ""} | ${formatCount(count)} itens`;
        if(option.textContent !== label) option.textContent = label;
      });
    }

    if(target){
      Array.from(target.options || []).forEach(option => {
        const value = normalize(option.value);
        if(!value) return;
        const item = metadata.imported.get(value);
        if(item){
          const rawName = normalize(item.label).replace(/\s+atualizados em\s+.*$/i, "").replace(/\s*\([^)]*itens\)\s*$/i, "");
          const name = rawName || normalize(item.filename).replace(/^plugintema-/i, "").replace(/\.csv$/i, "");
          const date = formatDateBR(item.updated_at);
          const label = `${name}${date ? ` | ${date}` : ""} | ${formatCount(item.items_count)} itens`;
          if(option.textContent !== label) option.textContent = label;
          return;
        }
        const current = normalize(option.textContent);
        const match = current.match(/^(.*?)\s+atualizados em\s+(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})\s+\((\d+)\s+itens\)$/i);
        if(match){
          const label = `${match[1]} | ${match[2]} | ${formatCount(match[3])} itens`;
          if(option.textContent !== label) option.textContent = label;
        }
      });
    }
  }

  function formatQueueCheckpoint(){
    const checkpoint = document.getElementById("updates_queue_checkpoint");
    if(!checkpoint) return;
    const current = normalize(checkpoint.textContent);
    const iso = current.match(/Última conclusão:\s*([^·]+?)(?:\s*·|$)/i)?.[1]?.trim();
    if(!iso) return;
    const date = formatDateBR(iso);
    const select = document.getElementById("updates_queue_select");
    const selectedText = normalize(select?.selectedOptions?.[0]?.textContent);
    const total = selectedText.match(/\(\s*\d+\s*\/\s*(\d+)\s*\)/)?.[1];
    const label = `${date}${total ? ` | ${formatCount(total)} itens` : ""}`;
    if(label && checkpoint.textContent !== label) checkpoint.textContent = label;
  }

  function applyDisplayFormatting(){
    // Formatação consolidada no render principal de panel.js.
  }

  function readCache(){
    try{
      const data = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
      if(!data || !data.savedAt || Date.now() - Number(data.savedAt) > MAX_CACHE_AGE) return null;
      return data;
    }catch(_){ return null; }
  }

  function writeCache(){
    const root = panel(); if(!root) return;
    const pct = txt(root.querySelector("#updates_progress_percent"));
    const processed = txt(root.querySelector("#updates_progress_text"));
    const current = txt(root.querySelector("#updates_current_job"));
    const env = txt(root.querySelector(".standard-update-accordion-card[data-update-accordion-kind='environment'] .standard-update-accordion-meta"));
    const queue = txt(root.querySelector("#updates_queue_meta"));
    const payload = {savedAt:Date.now(), pct, processed, current, env, queue};
    if([pct, processed, current, env, queue].some(Boolean)){
      try{ localStorage.setItem(CACHE_KEY, JSON.stringify(payload)); }catch(_){}
    }
  }

  function isInitialLoading(){
    const root = panel(); if(!root) return false;
    const body = txt(root).toLowerCase();
    const zero = /0%\s+0\s+de\s+0\s+processados/.test(body);
    const checking = /verificando pré-requisitos/.test(body);
    const emptyPrep = /abra a aba para materializar os jobs aprovados/.test(body);
    return zero || checking || emptyPrep;
  }

  function buildOverlay(){
    const root = panel(); if(!root || document.getElementById(OVERLAY_ID)) return;
    const cache = readCache();
    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.setAttribute("aria-live","polite");
    overlay.innerHTML = `
      <div class="cs-update-loading-head"><span class="cs-update-loading-spinner"></span><span>${cache ? "Atualizando dados em segundo plano" : "Carregando atualizações"}</span></div>
      <div class="cs-update-sk-card">
        <div class="cs-update-sk-row"><div class="cs-update-sk-line w-18"></div><div class="cs-update-sk-line w-12"></div></div>
        <div class="cs-update-sk-line w-32"></div>
        <div class="cs-update-sk-row"><div class="cs-update-sk-line w-12"></div><div class="cs-update-sk-line w-18"></div></div>
        <div class="cs-update-sk-line w-100"></div>
        <div class="cs-update-sk-block w-100"></div>
      </div>
      <div class="cs-update-sk-card"><div class="cs-update-sk-row"><div class="cs-update-sk-line w-18"></div><div class="cs-update-sk-line w-24"></div></div></div>
      <div class="cs-update-sk-card">
        <div class="cs-update-sk-line w-18"></div>
        <div class="cs-update-sk-row"><div class="cs-update-sk-pill w-18"></div><div class="cs-update-sk-pill w-18"></div><div class="cs-update-sk-pill w-24"></div><div class="cs-update-sk-pill w-18"></div></div>
        <div class="cs-update-sk-row"><div class="cs-update-sk-button w-24"></div><div class="cs-update-sk-button w-24"></div><div class="cs-update-sk-button w-24"></div></div>
      </div>
      <div class="cs-update-sk-card"><div class="cs-update-sk-line w-24"></div><div class="cs-update-sk-block w-100"></div></div>
      <div class="cs-update-sk-card"><div class="cs-update-sk-line w-18"></div></div>
    `;
    root.prepend(overlay);
    shownAt = Date.now();
    window.clearTimeout(hideTimer);
    hideTimer = window.setTimeout(hideOverlay, MAX_VISIBLE_MS);
  }

  function hideOverlay(){
    const overlay = document.getElementById(OVERLAY_ID); if(!overlay) return;
    const elapsed = Date.now() - shownAt;
    if(elapsed < MIN_VISIBLE_MS){
      window.setTimeout(hideOverlay, MIN_VISIBLE_MS - elapsed);
      return;
    }
    overlay.classList.add("is-hiding");
    window.setTimeout(() => overlay.remove(), 230);
    writeCache();
  }

  function reconcile(){
    const root = panel();
    if(root){
      if(isInitialLoading()) buildOverlay();
      else hideOverlay();
    }
    applyDisplayFormatting();
  }

  function bindTab(){
    document.addEventListener("click", event => {
      const target = event.target.closest?.("[data-tab],button,a");
      if(!target) return;
      const label = txt(target).toLowerCase();
      if(label === "atualizar" || label === "comparar" || target.getAttribute("data-tab") === "atualizacoes"){
        window.setTimeout(reconcile, 0);
        window.setTimeout(applyDisplayFormatting, 250);
      }
    });
  }

  bindTab();
  reconcile();
  window.setTimeout(applyDisplayFormatting, 250);
  window.setTimeout(applyDisplayFormatting, 900);
  const observer = new MutationObserver(() => window.setTimeout(reconcile, 40));
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
})();
