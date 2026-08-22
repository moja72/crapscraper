(() => {
  "use strict";

  if (window.__crapScraperOperationalReliabilityV11Installed) return;
  window.__crapScraperOperationalReliabilityV11Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  const text = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function stateLabel(value) {
    const labels = {
      queued: "Aguardando execução",
      executing: "Executando",
      plan_ready: "Plano pronto",
      completed: "Concluído",
      rolled_back: "Rollback concluído",
      blocked: "Bloqueado",
      error: "Erro",
      failed: "Falhou",
      interrupted: "Interrompido",
    };
    return labels[text(value)] || text(value).replace(/_/g, " ") || "Aguardando";
  }

  function ensurePreparationListAnchor() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root || $("#updates_jobs")) return;
    const body = $("#cs_updates_preparation_body", root) || root;
    const node = document.createElement("div");
    node.id = "updates_jobs";
    node.className = "cs-preparation-list";
    node.setAttribute("aria-live", "polite");
    node.innerHTML = '<div class="notice">Carregando produtos aprovados…</div>';
    const pagination = $(".cs-preparation-pagination,.listing-pagination", body);
    if (pagination) body.insertBefore(node, pagination);
    else body.appendChild(node);
  }

  function queueSnapshotItems(payload) {
    const queue = payload?.queue || {};
    const active = text(queue.active_queue || "default");
    const source = [
      ...(Array.isArray(queue.executing) ? queue.executing : []),
      ...(Array.isArray(queue.queued) ? queue.queued : []),
    ];
    const seen = new Set();
    return source.filter(item => {
      const id = text(item?.job_id);
      const queueName = text(item?.queue_name || active || "default");
      if (!id || queueName !== active || seen.has(id)) return false;
      seen.add(id);
      return true;
    });
  }

  function fallbackRow(job) {
    const nextVersion = text(job.effective_source_version || job.approved_source_version || job.ultrapack_version || "-");
    const currentVersion = text(job.plugintema_version || "-");
    const logs = Array.isArray(job.execution_logs) ? job.execution_logs.slice(-5) : [];
    const reason = text(job.execution_error);
    const details = [reason, ...logs.map(text).filter(Boolean)];
    return `
      <article class="update-queue-row cs-update-queue-recovered" data-update-job="${esc(job.job_id)}">
        <div class="update-queue-position">${job.state === "executing" ? "Agora" : `#${esc(job.queue_position || "-")}`}</div>
        <div>
          <strong>${esc(job.name || job.source_name || `Woo #${job.woo_product_id || "-"}`)}</strong>
          <div class="small">Woo #${esc(job.woo_product_id || "-")} · ${esc(currentVersion)} → ${esc(nextVersion)}</div>
          <div class="small">Fila: ${esc(job.queue_name || "default")}</div>
          ${reason ? `<div class="updates-error">${esc(reason)}</div>` : ""}
        </div>
        <span class="badge">${esc(stateLabel(job.state))}</span>
        <details class="cs-update-queue-recovered-detail">
          <summary>Detalhes</summary>
          <div class="small" style="margin-top:8px;white-space:pre-wrap">${details.length ? details.map(esc).join("\n") : "Sem logs adicionais."}</div>
        </details>
      </article>`;
  }

  function baseLooksEmpty(wrap) {
    if (!wrap) return false;
    const content = text(wrap.textContent).toLowerCase();
    return !wrap.children.length
      || !content
      || content.includes("nenhum produto na fila ativa")
      || content.includes("nenhum produto corresponde aos filtros da fila");
  }

  async function reconcileUpdateQueue() {
    ensurePreparationListAnchor();
    const panel = $("#tab_panel_atualizacoes");
    const wrap = $("#updates_queue_jobs");
    if (!panel || !wrap) return;

    let payload;
    try {
      const response = await fetch("/atualizacoes/jobs", {cache:"no-store", credentials:"same-origin"});
      payload = await response.json();
      if (!response.ok || payload?.ok === false) return;
    } catch (_error) {
      return;
    }

    const items = queueSnapshotItems(payload);
    if (!items.length || !baseLooksEmpty(wrap)) return;

    wrap.innerHTML = items.map(fallbackRow).join("");
    $("#updates_queue_list_controls")?.classList.remove("hidden");

    const queue = payload.queue || {};
    const active = text(queue.active_queue || "default");
    const status = text(queue.status || "stopped");
    const label = status === "running" ? "Executando" : status === "paused" ? "Pausada" : "Fila parada";
    const meta = $("#updates_queue_meta");
    if (meta) meta.textContent = `${items.length} produto(s) · ${label} · ${active === "default" ? "Padrão" : active}`;
    const found = $("#updates_queue_found_count");
    if (found) found.textContent = `Mostrando ${items.length} de ${items.length} itens`;
  }

  let timers = [];
  function burst(delays = [0, 120, 400, 1000]) {
    timers.forEach(id => window.clearTimeout(id));
    timers = delays.map(delay => window.setTimeout(reconcileUpdateQueue, delay));
  }

  function start() {
    ensurePreparationListAnchor();
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(
        "#tab_btn_atualizacoes,#updates_refresh_btn,#updates_enqueue_selected," +
        "#updates_queue_start,#updates_queue_pause,#updates_queue_select"
      )) burst();
    }, true);
    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes") burst();
    });
    burst([0, 250, 900]);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
