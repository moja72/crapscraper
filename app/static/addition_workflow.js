(() => {
  "use strict";
  if (window.__crapScraperAdditionWorkflowInstalled) return;
  window.__crapScraperAdditionWorkflowInstalled = true;

  const $ = (s, r = document) => r.querySelector(s);
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const text = value => String(value ?? "").trim();
  const CHAT_URL_KEY = "crapscraper:additions:chatgpt-url:v1";
  let state = {jobs: [], active: [], history: [], counts: {}};
  let editorJobId = "";
  let timer = null;
  let refreshing = false;

  const busyStates = new Set(["preparing", "creating_draft", "publishing"]);
  const stateClasses = {
    approved: "is-neutral", preparing: "is-running", awaiting_content: "is-warning",
    content_ready: "is-ready", creating_draft: "is-running", draft_created: "is-ready",
    publishing: "is-running", completed: "is-success", blocked: "is-danger", error: "is-danger"
  };

  function installStyles() {
    if ($("#addition-workflow-style")) return;
    const style = document.createElement("style");
    style.id = "addition-workflow-style";
    style.textContent = `
      .addition-shell{display:grid;gap:16px}.addition-hero-row,.addition-toolbar,.addition-card-head,.addition-actions,.addition-inline-form{display:flex;align-items:center;gap:10px}.addition-hero-row,.addition-toolbar,.addition-card-head{justify-content:space-between}.addition-flow{margin-top:14px;padding:10px 12px;border:1px solid #2b2c31;border-radius:10px;background:#0d0e10;color:#9ec6e6;font-size:12px}.addition-kpis{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;margin-top:14px}.addition-kpi{padding:10px;border:1px solid #2b2c31;border-radius:10px;background:#101114}.addition-kpi strong{display:block;font-size:18px;color:#fff}.addition-kpi span{display:block;margin-top:3px;color:#8ea8bf;font-size:10px}.addition-chatgpt-card>summary,.addition-history-card>summary{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:800}.addition-chatgpt-card>summary::-webkit-details-marker,.addition-history-card>summary::-webkit-details-marker{display:none}.addition-chevron{transition:transform .16s ease}.addition-chatgpt-card[open] .addition-chevron{transform:rotate(90deg)}.addition-chatgpt-body,.addition-history-body{margin-top:14px;display:grid;gap:10px}.addition-chatgpt-body label{font-size:11px;font-weight:800}.addition-inline-form input{flex:1;min-width:0}.addition-toolbar-fields{display:flex;gap:8px;min-width:min(620px,55%)}.addition-toolbar-fields input{flex:1}.addition-toolbar-fields select{min-width:190px}.addition-job-list{display:grid;gap:10px;margin-top:14px}.addition-job{border:1px solid #2b2c31;border-radius:13px;background:#0e0f11;padding:14px}.addition-card-head{align-items:flex-start}.addition-product{font-weight:850;color:#fff;font-size:14px}.addition-meta{margin-top:3px;color:#8fb5d1;font-size:11px;line-height:1.5}.addition-state{flex:0 0 auto;padding:6px 9px;border:1px solid #33353b;border-radius:999px;font-size:10px;font-weight:850}.addition-state.is-running{color:#a7f3d0;border-color:#17765b}.addition-state.is-warning{color:#fcd34d;border-color:#7b5b10}.addition-state.is-ready{color:#c4b5fd;border-color:#6d46b8}.addition-state.is-success{color:#a7f3d0;border-color:#167054}.addition-state.is-danger{color:#fecaca;border-color:#9a3434}.addition-source-links{display:flex;flex-wrap:wrap;gap:10px;margin-top:8px;font-size:11px}.addition-source-links a{color:#a78bfa}.addition-status-note{margin-top:10px;padding:9px 10px;border-radius:9px;background:#16171b;color:#b5bcc7;font-size:11px}.addition-error{border:1px solid #9c3030;background:#341719;color:#fecaca}.addition-actions{flex-wrap:wrap;margin-top:12px}.addition-actions select{width:auto;min-width:135px}.addition-actions button{min-height:34px}.addition-logs{margin-top:10px;padding:9px 10px;border:1px solid #24262b;border-radius:9px;background:#08090a;color:#aeb8c5;font:10px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-word}.addition-spinner{display:inline-block;width:10px;height:10px;margin-right:6px;border:2px solid #2b5a4c;border-top-color:#34d399;border-radius:50%;animation:addSpin .8s linear infinite}.addition-editor{margin-top:12px;padding:13px;border:1px solid #3a2b59;border-radius:11px;background:#111015;display:grid;gap:10px}.addition-editor-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.addition-editor label{display:grid;gap:5px;font-size:11px;font-weight:800}.addition-editor textarea{min-height:100px;resize:vertical}.addition-editor .addition-description{min-height:220px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.addition-editor input,.addition-editor textarea,.addition-editor select{width:100%;box-sizing:border-box}.addition-editor-actions{display:flex;justify-content:flex-end;gap:8px}.addition-file-status{color:#8fb5d1;font-size:11px}.addition-history-body .addition-job{opacity:.9}.addition-empty{margin-top:14px;padding:18px;border:1px dashed #33353b;border-radius:11px;color:#9ca3af;text-align:center}.addition-toast{position:fixed;right:18px;bottom:18px;z-index:150000;max-width:440px;padding:12px 14px;border-radius:10px;background:#17251f;border:1px solid #23694f;color:#d1fae5;box-shadow:0 12px 35px #0008;font-size:12px}.addition-toast.is-error{background:#35191b;border-color:#a63b3b;color:#fee2e2}@keyframes addSpin{to{transform:rotate(360deg)}}
      @media(max-width:1000px){.addition-kpis{grid-template-columns:repeat(3,1fr)}.addition-toolbar{align-items:stretch;flex-direction:column}.addition-toolbar-fields{min-width:0;width:100%}.addition-editor-grid{grid-template-columns:1fr}}@media(max-width:640px){.addition-kpis{grid-template-columns:repeat(2,1fr)}.addition-inline-form,.addition-toolbar-fields{flex-direction:column;align-items:stretch}.addition-card-head{flex-direction:column}.addition-state{align-self:flex-start}}
      @media(prefers-reduced-motion:reduce){.addition-spinner{animation:none}}
    `;
    document.head.appendChild(style);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: "same-origin", cache: "no-store", ...options});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.ok === false) throw new Error(data?.message || `HTTP ${response.status}`);
    return data;
  }

  function toast(message, error = false) {
    $(".addition-toast")?.remove();
    const node = document.createElement("div");
    node.className = "addition-toast" + (error ? " is-error" : "");
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 4800);
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes) return "—";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  function chatUrl() {
    try { return localStorage.getItem(CHAT_URL_KEY) || ""; } catch (_error) { return ""; }
  }

  function saveChatUrl() {
    const value = text($("#add_chatgpt_url")?.value);
    try { localStorage.setItem(CHAT_URL_KEY, value); } catch (_error) {}
    toast(value ? "Conversa do ChatGPT salva." : "URL da conversa removida.");
  }

  function openChat() {
    const url = chatUrl();
    if (!url) return toast("Salve primeiro a URL da conversa do ChatGPT.", true);
    try {
      const parsed = new URL(url);
      if (!/^(chatgpt\.com|chat\.openai\.com)$/i.test(parsed.hostname)) throw new Error();
      window.open(parsed.href, "_blank", "noopener");
    } catch (_error) { toast("A URL salva não parece ser uma conversa válida do ChatGPT.", true); }
  }

  async function copyPrompt(job) {
    const prompt = text(job.prompt_text);
    if (!prompt) return toast("Briefing ainda não foi preparado.", true);
    try { await navigator.clipboard.writeText(prompt); toast("Prompt copiado. Cole na sua conversa do ChatGPT."); }
    catch (_error) { toast("Não foi possível copiar automaticamente.", true); }
  }

  function kpiHtml(label, value) {
    return `<div class="addition-kpi"><strong>${Number(value || 0)}</strong><span>${esc(label)}</span></div>`;
  }

  function renderKpis() {
    const c = state.counts || {};
    const node = $("#add_kpis");
    if (!node) return;
    node.innerHTML = [
      kpiHtml("Total", c.total), kpiHtml("Aguardando", c.approved),
      kpiHtml("Aguardando conteúdo", c.awaiting_content), kpiHtml("Conteúdo pronto", c.content_ready),
      kpiHtml("Rascunhos", c.draft_created), kpiHtml("Concluídos", c.completed),
      kpiHtml("Erros / bloqueados", Number(c.error || 0) + Number(c.blocked || 0)),
    ].join("");
  }

  function recentLogs(job) {
    const logs = Array.isArray(job.logs) ? job.logs.slice(-6) : [];
    if (!logs.length) return "";
    return `<div class="addition-logs">${logs.map(row => `[${esc(row.at || "")}] ${esc(row.message || "")}`).join("\n")}</div>`;
  }

  function links(job) {
    const result = [];
    if (job.source_product_url) result.push(`<a href="${esc(job.source_product_url)}" target="_blank" rel="noopener">Abrir fonte</a>`);
    if (job.source_official_url) result.push(`<a href="${esc(job.source_official_url)}" target="_blank" rel="noopener">Página oficial</a>`);
    if (job.woo_product_id) {
      const base = location.origin.replace(/:\d+$/, "");
      result.push(`<span>WooCommerce #${Number(job.woo_product_id)}</span>`);
    }
    return result.length ? `<div class="addition-source-links">${result.join("")}</div>` : "";
  }

  function actionHtml(job) {
    const id = esc(job.job_id);
    const typeSelect = `<select data-add-type><option value="plugin"${job.item_type === "plugin" ? " selected" : ""}>Plugin</option><option value="theme"${job.item_type === "theme" ? " selected" : ""}>Tema</option></select>`;
    if (job.state === "approved") return `${typeSelect}<button class="btn-success" data-add-action="prepare" data-job="${id}">Preparar arquivo</button>`;
    if (job.state === "preparing") return `<button class="btn-secondary" disabled><span class="addition-spinner"></span>Preparando…</button>`;
    if (["awaiting_content", "content_ready"].includes(job.state)) {
      return `<button class="btn-secondary" data-add-action="copy" data-job="${id}">Copiar prompt para ChatGPT</button><button class="btn-secondary" data-add-action="chat" data-job="${id}">Abrir conversa</button><button class="btn-success" data-add-action="edit" data-job="${id}">${job.has_content ? "Editar conteúdo" : "Adicionar conteúdo"}</button>${job.state === "content_ready" ? `<button class="btn-success" data-add-action="draft" data-job="${id}">Criar rascunho</button>` : ""}`;
    }
    if (job.state === "creating_draft") return `<button class="btn-secondary" disabled><span class="addition-spinner"></span>Criando rascunho…</button>`;
    if (job.state === "draft_created") return `<button class="btn-secondary" data-add-action="edit" data-job="${id}">Editar conteúdo local</button><button class="btn-success" data-add-action="publish" data-job="${id}">Publicar</button>`;
    if (job.state === "publishing") return `<button class="btn-secondary" disabled><span class="addition-spinner"></span>Publicando…</button>`;
    if (["blocked", "error"].includes(job.state)) return `<button class="btn-success" data-add-action="retry" data-job="${id}">Tentar novamente</button>`;
    return "";
  }

  function editorHtml(job) {
    if (editorJobId !== job.job_id) return "";
    return `<form class="addition-editor" data-add-editor="${esc(job.job_id)}">
      <div class="addition-editor-grid">
        <label>Tipo<select name="item_type"><option value="plugin"${job.item_type === "plugin" ? " selected" : ""}>Plugin</option><option value="theme"${job.item_type === "theme" ? " selected" : ""}>Tema</option></select></label>
        <label>Título<input name="title" value="${esc(job.title || job.source_name || "")}" required></label>
      </div>
      <label>Breve descrição<textarea name="short_description" required>${esc(job.short_description || "")}</textarea></label>
      <label>Descrição completa <span class="small">HTML simples é aceito</span><textarea class="addition-description" name="description" required>${esc(job.description || "")}</textarea></label>
      <div class="addition-editor-grid">
        <label>Meta description<textarea name="meta_description">${esc(job.meta_description || "")}</textarea></label>
        <label>Tags<input name="tags_text" value="${esc(job.tags_text || "")}" placeholder="seo, elementor, formulário"></label>
      </div>
      <label>Imagem do produto<input name="image" type="file" accept="image/jpeg,image/png,image/webp"><span class="addition-file-status">${job.has_image ? `Imagem atual: ${esc(job.image_name || "arquivo salvo")}` : "Selecione a imagem 1:1 baixada da conversa do ChatGPT."}</span></label>
      <div class="addition-editor-actions"><button class="btn-secondary" type="button" data-add-action="cancel-edit" data-job="${esc(job.job_id)}">Cancelar</button><button class="btn-success" type="submit">Salvar conteúdo</button></div>
    </form>`;
  }

  function card(job, history = false) {
    const note = job.error ? `<div class="addition-status-note addition-error">${esc(job.error)}</div>` :
      `<div class="addition-status-note">${job.has_zip ? `ZIP: ${esc(job.zip_file_name)} · ${formatBytes(job.zip_size)} · ${Number(job.zip_entries || 0)} entradas` : "ZIP ainda não preparado."}${job.has_content ? " · Conteúdo salvo" : ""}${job.has_image ? " · Imagem salva" : ""}</div>`;
    return `<article class="addition-job" data-add-job="${esc(job.job_id)}">
      <div class="addition-card-head"><div><div class="addition-product">${esc(job.title || job.source_name || "Novo produto")}</div><div class="addition-meta">${job.item_type === "theme" ? "Tema" : "Plugin"} · versão ${esc(job.source_version || "—")}${job.woo_product_id ? ` · Woo #${Number(job.woo_product_id)}` : ""}</div>${links(job)}</div><span class="addition-state ${stateClasses[job.state] || ""}">${esc(job.state_label || job.state)}</span></div>
      ${note}${recentLogs(job)}${history ? "" : `<div class="addition-actions">${actionHtml(job)}</div>${editorHtml(job)}`}
    </article>`;
  }

  function currentFilteredJobs() {
    const query = text($("#add_search")?.value).toLowerCase();
    const filter = text($("#add_state_filter")?.value);
    return (state.active || []).filter(job => {
      if (filter && job.state !== filter) return false;
      if (!query) return true;
      return [job.title, job.source_name, job.source_version, job.state_label, job.item_type, job.woo_product_id]
        .some(value => String(value ?? "").toLowerCase().includes(query));
    });
  }

  function render() {
    renderKpis();
    const active = $("#add_active_jobs");
    if (active) {
      const jobs = currentFilteredJobs();
      active.innerHTML = jobs.length ? `<div class="addition-job-list">${jobs.map(job => card(job)).join("")}</div>` : `<div class="addition-empty">Nenhum cadastro novo corresponde aos filtros. Se não houver itens, aprove um produto como <strong>Cadastro novo</strong> na aba Comparar.</div>`;
    }
    const history = $("#add_history_jobs");
    if (history) history.innerHTML = state.history?.length ? `<div class="addition-job-list">${state.history.map(job => card(job, true)).join("")}</div>` : `<div class="addition-empty">Nenhum produto novo concluído ainda.</div>`;
    const count = $("#add_history_count");
    if (count) count.textContent = `${state.history?.length || 0} item(ns)`;
    bindDynamic();
  }

  function findJob(id) { return state.jobs?.find(job => job.job_id === id); }

  async function fileAsDataUrl(file) {
    if (!file) return {data: "", name: ""};
    if (file.size > 8 * 1024 * 1024) throw new Error("A imagem deve ter no máximo 8 MB.");
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({data: String(reader.result || ""), name: file.name});
      reader.onerror = () => reject(new Error("Não foi possível ler a imagem."));
      reader.readAsDataURL(file);
    });
  }

  async function submitEditor(form) {
    const id = form.dataset.addEditor;
    const image = await fileAsDataUrl(form.elements.image?.files?.[0]);
    const payload = {
      job_id: id, item_type: form.elements.item_type.value, title: form.elements.title.value,
      short_description: form.elements.short_description.value, description: form.elements.description.value,
      meta_description: form.elements.meta_description.value, tags_text: form.elements.tags_text.value,
      image_data: image.data, image_name: image.name,
    };
    const button = form.querySelector('button[type="submit"]');
    if (button) { button.disabled = true; button.textContent = "Salvando…"; }
    try {
      await api("/adicoes/conteudo", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
      editorJobId = "";
      toast("Conteúdo salvo.");
      await refresh(true);
    } catch (error) { toast(error.message, true); if (button) { button.disabled = false; button.textContent = "Salvar conteúdo"; } }
  }

  async function action(event) {
    const button = event.target.closest("[data-add-action]");
    if (!button) return;
    const id = button.dataset.job || "";
    const job = findJob(id);
    const actionName = button.dataset.addAction;
    if (actionName === "copy" && job) return copyPrompt(job);
    if (actionName === "chat") return openChat();
    if (actionName === "edit") { editorJobId = id; render(); return; }
    if (actionName === "cancel-edit") { editorJobId = ""; render(); return; }
    if (!job) return;
    try {
      button.disabled = true;
      if (actionName === "prepare") {
        const itemType = button.closest(".addition-actions")?.querySelector("[data-add-type]")?.value || job.item_type;
        await api("/adicoes/preparar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: id, item_type: itemType})});
        toast("Preparação iniciada.");
      } else if (actionName === "draft") {
        if (!confirm("Criar o produto como RASCUNHO no WooCommerce? Ele ainda não será publicado.")) { button.disabled = false; return; }
        await api("/adicoes/rascunho", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: id, confirmation: "CRIAR RASCUNHO"})});
        toast("Criação do rascunho iniciada.");
      } else if (actionName === "publish") {
        if (!confirm("Publicar este produto no PluginTema? Confirme somente depois de revisar o rascunho.")) { button.disabled = false; return; }
        await api("/adicoes/publicar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: id, confirmation: "PUBLICAR"})});
        toast("Publicação iniciada.");
      } else if (actionName === "retry") {
        await api("/adicoes/reprocessar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({job_id: id})});
        toast("Item liberado para nova tentativa.");
      }
      await refresh(true);
    } catch (error) { toast(error.message, true); button.disabled = false; }
  }

  function bindDynamic() {
    document.querySelectorAll("[data-add-editor]").forEach(form => {
      if (form.dataset.bound) return;
      form.dataset.bound = "1";
      form.addEventListener("submit", event => { event.preventDefault(); submitEditor(form); });
    });
  }

  async function refresh(force = false) {
    if (refreshing) return;
    if (!force && !$("#tab_panel_adicoes")?.classList.contains("hidden") === false) return;
    refreshing = true;
    try {
      state = await api("/adicoes/jobs");
      render();
    } catch (error) {
      const node = $("#add_active_jobs");
      if (node) node.innerHTML = `<div class="notice is-danger">Falha ao carregar adições: ${esc(error.message)}</div>`;
    } finally { refreshing = false; schedule(); }
  }

  function schedule() {
    clearTimeout(timer);
    const busy = state.active?.some(job => busyStates.has(job.state));
    timer = setTimeout(() => refresh(true), busy ? 1500 : 5000);
  }

  function setup() {
    installStyles();
    const input = $("#add_chatgpt_url");
    if (input) input.value = chatUrl();
    $("#add_chatgpt_save")?.addEventListener("click", saveChatUrl);
    $("#add_chatgpt_open")?.addEventListener("click", openChat);
    $("#add_refresh")?.addEventListener("click", () => refresh(true));
    $("#add_search")?.addEventListener("input", render);
    $("#add_state_filter")?.addEventListener("change", render);
    $("#tab_panel_adicoes")?.addEventListener("click", action);
    $("#tab_btn_adicoes")?.addEventListener("click", () => setTimeout(() => refresh(true), 20));
    refresh(true);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup, {once: true});
  else setup();
})();
