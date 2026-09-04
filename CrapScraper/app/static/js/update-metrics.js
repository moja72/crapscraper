(() => {
  "use strict";

  const cache = new Map();
  let scheduled = 0;
  const nativeFetch = window.fetch.bind(window);
  const clean = value => String(value ?? "").trim();
  const dateText = value => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? clean(value) : date.toLocaleString("pt-BR", {dateStyle:"short", timeStyle:"short"});
  };

  function statusLabel(job) {
    if (job.state === "success") return "Concluído em";
    if (job.state === "error") return "Erro em";
    if (job.state === "running") return "Iniciado em";
    return "Atualizado em";
  }

  function decorate() {
    scheduled = 0;
    document.querySelectorAll(".update-job-card[data-job-id]").forEach(card => {
      const job = cache.get(clean(card.dataset.jobId));
      if (!job) return;
      const state = card.querySelector(".update-job-state");
      if (!state) return;
      let metrics = state.querySelector(".update-job-durable-metrics");
      if (!metrics) {
        metrics = document.createElement("div");
        metrics.className = "update-job-durable-metrics";
        metrics.style.cssText = "display:grid;gap:2px;margin-top:3px;font-size:11px;line-height:1.35;color:var(--muted,#94a3b8);white-space:nowrap";
        state.appendChild(metrics);
      }
      const count = Math.max(0, Number.parseInt(String(job.updates_count ?? 0), 10) || 0);
      metrics.innerHTML = `<small>${statusLabel(job)}: ${dateText(job.status_at)}</small><small>Atualizações concluídas: <strong>${count}</strong></small>`;
    });
  }

  function schedule() {
    if (scheduled) return;
    scheduled = window.setTimeout(decorate, 0);
  }

  window.fetch = async function patchedFetch(input, init) {
    const response = await nativeFetch(input, init);
    try {
      const url = typeof input === "string" ? input : clean(input?.url);
      if (url.includes("/api/updates/jobs") || url.includes("/api/updates/job?")) {
        const payload = await response.clone().json();
        const items = Array.isArray(payload?.items) ? payload.items : payload?.item ? [payload.item] : [];
        items.forEach(job => {
          if (job?.job_id) cache.set(clean(job.job_id), job);
        });
        schedule();
      }
    } catch (_error) {
      // Métrica informativa: nunca interfere no fluxo principal.
    }
    return response;
  };

  new MutationObserver(schedule).observe(document.documentElement, {childList:true, subtree:true});
  document.addEventListener("app:tab", event => { if (event.detail === "update") schedule(); });
})();
