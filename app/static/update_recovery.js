(() => {
  "use strict";

  const ERROR_STATES = new Set(["error", "failed", "blocked", "rollback_required", "canceled", "interrupted"]);
  const AUTO_RETRY_STATES = new Set(["error", "failed", "blocked", "canceled", "interrupted"]);
  const RISKY_STEPS = new Set(["production_zip_installed", "pt_versao_updated"]);

  const style = document.createElement("style");
  style.textContent = `
    .update-recovery-panel{margin:14px 0;padding:14px;border:1px solid #2f2f35;border-radius:14px;background:#101012;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px}
    .update-recovery-summary{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
    .update-recovery-chip{display:inline-flex;align-items:center;gap:6px;padding:6px 9px;border:1px solid #303039;border-radius:999px;background:#17171b;font-size:12px}
    .update-recovery-chip strong{font-size:13px}
    .update-recovery-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .update-recovery-meta{margin-top:7px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .update-recovery-category{display:inline-flex;padding:4px 8px;border:1px solid #3b3b45;border-radius:999px;background:#18181c;font-size:11px;font-weight:700}
    .update-recovery-guidance{font-size:12px;color:#a9a9b4}
    .update-retry-btn{white-space:nowrap}
    .update-retry-btn[disabled]{opacity:.55}
    .update-recovery-progress{font-size:12px;color:#b8b8c2;min-width:180px}
    @media(max-width:760px){.update-recovery-panel{align-items:stretch}.update-recovery-actions{width:100%}.update-recovery-actions button{flex:1 1 180px}}
  `;
  document.head.appendChild(style);

  const normalize = (value) => String(value ?? "").trim();
  const lower = (value) => normalize(value).toLowerCase();

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (_error) {}
    if (!response.ok || data?.ok === false) {
      throw new Error(data?.message || data?.error || `HTTP ${response.status}`);
    }
    return data;
  }

  const postJson = (url, payload) => requestJson(url, {method: "POST", body: JSON.stringify(payload || {})});

  function combinedMessage(job) {
    return [
      job?.execution_error,
      ...(Array.isArray(job?.diagnostics) ? job.diagnostics.slice(-3) : []),
      ...(Array.isArray(job?.execution_logs) ? job.execution_logs.slice(-8) : []),
    ].filter(Boolean).join(" ");
  }

  function classify(job) {
    const text = lower(combinedMessage(job));
    const state = lower(job?.state);
    if (state === "rollback_required" || /rollback/.test(text)) {
      return {key:"rollback", label:"Rollback / produção", guidance:"Exige revisão manual antes de qualquer nova tentativa."};
    }
    if (/sess[aã]o|renovar sess[aã]o|login|cookie|autentica/.test(text)) {
      return {key:"session", label:"Sessão / login", guidance:"Renove a sessão da fonte e tente novamente."};
    }
    if (/falha na fonte|download|timeout|http |http\d|conex[aã]o|expirad/.test(text)) {
      return {key:"source", label:"Fonte / download", guidance:"Revalide a fonte e refaça preparação e plano."};
    }
    if (/ssh|staging|sha-?256|zip|backup|arquivo remoto|filesystem/.test(text)) {
      return {key:"storage", label:"ZIP / armazenamento", guidance:"Revalide staging, SSH e integridade do ZIP antes de repetir."};
    }
    if (/woocommerce|wordpress|pt_versao|meta id|consumer/.test(text)) {
      return {key:"woocommerce", label:"WooCommerce", guidance:"Revalide acesso e versão do produto antes de repetir."};
    }
    if (/pré-condi|pre-condi|plano|relacionamento|autoriz|ineleg|permitid/.test(text)) {
      return {key:"precondition", label:"Pré-requisito", guidance:"Corrija o requisito indicado e gere um novo plano."};
    }
    if (state === "interrupted") {
      return {key:"interrupted", label:"Interrompido", guidance:"Pode ser revalidado e preparado novamente."};
    }
    if (state === "canceled") {
      return {key:"canceled", label:"Cancelado", guidance:"Pode retornar à preparação se ainda houver atualização pendente."};
    }
    return {key:"other", label:"Outro erro", guidance:"Abra os detalhes; a nova tentativa sempre refará validação e plano."};
  }

  function isRecoverable(job) {
    const state = lower(job?.state);
    const step = normalize(job?.last_completed_step);
    if (!AUTO_RETRY_STATES.has(state)) return false;
    if (state === "rollback_required" || RISKY_STEPS.has(step)) return false;
    return true;
  }

  async function loadJobs() {
    const result = await requestJson("/atualizacoes/jobs", {headers:{}});
    return Array.isArray(result?.jobs) ? result.jobs : [];
  }

  async function retryJob(job, onProgress = () => {}) {
    if (!job || !isRecoverable(job)) {
      throw new Error("Este item exige revisão manual e não pode ser reprocessado automaticamente.");
    }
    onProgress("Revalidando e preparando...");
    const prepared = await postJson("/atualizacoes/preparar", {job_id: job.job_id});
    const preview = prepared?.preview || {};
    if (preview.ready !== true) {
      const message = preview?.message || (preview?.validations || []).find(item => item?.ok === false)?.detail;
      throw new Error(message || "A preparação continuou bloqueada.");
    }
    onProgress("Gerando novo plano...");
    const planned = await postJson("/atualizacoes/plano", {job_id: job.job_id});
    if (planned?.plan?.ready !== true) {
      throw new Error(planned?.plan?.message || "Não foi possível gerar um plano pronto.");
    }
    return planned;
  }

  function notify(message, kind = "ok") {
    const existing = document.querySelector(".update-recovery-toast");
    existing?.remove();
    const toast = document.createElement("div");
    toast.className = "update-recovery-toast";
    toast.textContent = message;
    Object.assign(toast.style, {
      position:"fixed", right:"18px", bottom:"18px", zIndex:"99999", maxWidth:"520px",
      padding:"12px 14px", borderRadius:"12px", fontWeight:"700",
      background: kind === "error" ? "#451a1a" : "#063d2b", color:"#fff",
      border: `1px solid ${kind === "error" ? "#ef4444" : "#10b981"}`,
      boxShadow:"0 10px 30px rgba(0,0,0,.35)"
    });
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  function errorTabIsActive() {
    return document.getElementById("updates_history_errors")?.classList.contains("is-active");
  }

  function renderPanel(jobs) {
    const history = document.getElementById("updates_history");
    const controls = document.getElementById("updates_history_controls");
    if (!history || !controls) return;

    let panel = document.getElementById("updates_recovery_panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "updates_recovery_panel";
      panel.className = "update-recovery-panel";
      history.parentElement?.insertBefore(panel, history);
    }
    panel.hidden = !errorTabIsActive();
    if (panel.hidden) return;

    const errors = jobs.filter(job => ERROR_STATES.has(lower(job.state)));
    const recoverable = errors.filter(isRecoverable);
    const counts = {};
    errors.forEach(job => {
      const item = classify(job);
      counts[item.label] = (counts[item.label] || 0) + 1;
    });
    const chips = Object.entries(counts)
      .sort((a,b) => b[1] - a[1])
      .map(([label,count]) => `<span class="update-recovery-chip"><strong>${count}</strong>${label}</span>`)
      .join("");

    const signature = JSON.stringify(errors.map(job => [
      job.job_id, job.state, job.updated_at, job.execution_error, job.last_completed_step,
    ]));
    if (panel.dataset.recoverySignature === signature) return;
    panel.dataset.recoverySignature = signature;

    panel.innerHTML = `
      <div>
        <strong>Recuperação de erros</strong>
        <div class="small">${errors.length} item(ns) com atenção · ${recoverable.length} recuperável(is) automaticamente</div>
        <div class="update-recovery-summary">${chips || '<span class="small">Sem erros classificados.</span>'}</div>
      </div>
      <div class="update-recovery-actions">
        <span class="update-recovery-progress" id="updates_recovery_progress"></span>
        <button type="button" class="btn-success" id="updates_retry_recoverable" ${recoverable.length ? "" : "disabled"}>Reprocessar recuperáveis</button>
      </div>`;

    document.getElementById("updates_retry_recoverable")?.addEventListener("click", async (event) => {
      if (!recoverable.length) return;
      if (!confirm(`Reprocessar ${recoverable.length} item(ns)? Cada item será revalidado, preparado novamente e receberá um novo plano. Itens com risco de alteração em produção ou rollback não serão incluídos.`)) return;
      const button = event.currentTarget;
      const progress = document.getElementById("updates_recovery_progress");
      button.disabled = true;
      document.body.dataset.updateRecoveryBusy = "1";
      let ok = 0, failed = 0;
      for (let index = 0; index < recoverable.length; index += 1) {
        const job = recoverable[index];
        if (progress) progress.textContent = `${index + 1}/${recoverable.length} · ${job.name}`;
        try {
          await retryJob(job, (message) => { if (progress) progress.textContent = `${index + 1}/${recoverable.length} · ${message}`; });
          ok += 1;
        } catch (_error) {
          failed += 1;
        }
      }
      if (progress) progress.textContent = `${ok} recuperado(s) · ${failed} ainda bloqueado(s)`;
      notify(`${ok} item(ns) voltaram com plano pronto; ${failed} continuam exigindo atenção.`, failed ? "error" : "ok");
      delete document.body.dataset.updateRecoveryBusy;
      setTimeout(() => location.reload(), 900);
    });
  }

  function enrichRows(jobs) {
    if (!errorTabIsActive()) return;
    const map = new Map(jobs.map(job => [normalize(job.job_id), job]));
    document.querySelectorAll("#updates_history .update-queue-row").forEach(row => {
      const details = row.querySelector("[data-update-detail]");
      const job = map.get(normalize(details?.dataset.updateDetail));
      if (!job) return;
      const main = row.children?.[1] || row.querySelector("div");
      if (!main) return;
      const info = classify(job);
      let meta = main.querySelector(".update-recovery-meta");
      if (!meta) {
        meta = document.createElement("div");
        meta.className = "update-recovery-meta";
        main.appendChild(meta);
      }
      const metaHtml = `<span class="update-recovery-category">${info.label}</span><span class="update-recovery-guidance">${info.guidance}</span>`;
      if (meta.innerHTML !== metaHtml) meta.innerHTML = metaHtml;

      const existing = row.querySelector(".update-retry-btn");
      if (isRecoverable(job)) {
        if (!existing) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn-success update-retry-btn";
          button.textContent = "Tentar novamente";
          details?.parentElement?.insertBefore(button, details);
          button.addEventListener("click", async () => {
            button.disabled = true;
            document.body.dataset.updateRecoveryBusy = "1";
            const original = button.textContent;
            try {
              await retryJob(job, message => { button.textContent = message; });
              button.textContent = "Plano pronto";
              notify(`${job.name}: preparação e novo plano concluídos.`);
              setTimeout(() => location.reload(), 700);
            } catch (error) {
              button.disabled = false;
              button.textContent = original;
              notify(`${job.name}: ${error.message}`, "error");
            } finally {
              delete document.body.dataset.updateRecoveryBusy;
            }
          });
        }
      } else if (existing) {
        existing.remove();
      }
    });
  }

  let scheduled = null;
  async function refreshRecoveryUi() {
    clearTimeout(scheduled);
    scheduled = setTimeout(async () => {
      if (!document.getElementById("updates_history")) return;
      if (document.body.dataset.updateRecoveryBusy === "1") return;
      try {
        const jobs = await loadJobs();
        renderPanel(jobs);
        enrichRows(jobs);
      } catch (_error) {}
    }, 80);
  }

  document.addEventListener("click", (event) => {
    if (event.target?.closest?.("#updates_history_errors, #updates_history_completed")) {
      setTimeout(refreshRecoveryUi, 120);
    }
  });

  const observer = new MutationObserver((mutations) => {
    if (mutations.some(mutation => mutation.target?.id === "updates_history" || mutation.target?.closest?.("#updates_history"))) {
      refreshRecoveryUi();
    }
  });

  const start = () => {
    observer.observe(document.body, {childList:true, subtree:true});
    refreshRecoveryUi();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
