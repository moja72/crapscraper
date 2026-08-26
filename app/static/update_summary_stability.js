(() => {
  "use strict";

  if (window.__crapScraperUpdateSummaryStabilityInstalled) return;
  window.__crapScraperUpdateSummaryStabilityInstalled = true;

  const LEGACY_ID = "updates_summary";
  const CANONICAL_ID = "cs_update_summary_canonical";
  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const esc = value => String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#039;");

  const GROUPS = Object.freeze({
    prepared: Object.freeze({
      label: "Preparados",
      states: Object.freeze(["plan_ready"]),
      help: "Produtos realmente liberados para execução: plano pronto.",
    }),
    running: Object.freeze({
      label: "Em andamento",
      states: Object.freeze([
        "executing", "installing", "filesystem_validated", "updating_wordpress",
        "validating_wordpress", "validated", "dry_run_ready", "rolling_back",
      ]),
      help: "Produtos que já entraram na execução e ainda não chegaram a um estado terminal.",
    }),
    completed: Object.freeze({
      label: "Concluídos",
      states: Object.freeze(["completed"]),
      help: "Atualizações concluídas com sucesso.",
    }),
    errors: Object.freeze({
      label: "Erros",
      states: Object.freeze(["blocked", "error", "failed", "interrupted", "rollback_required"]),
      help: "Itens bloqueados, com erro, falha, interrupção ou rollback necessário.",
    }),
  });
  const ORDER = Object.freeze(["total", "prepared", "running", "completed", "errors"]);

  let activeGroup = "total";
  let runtime = null;
  let polling = null;
  let lastSignature = "";

  function installStyles() {
    if ($("#cs-update-summary-stability-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-summary-stability-style";
    style.textContent = `
      #${LEGACY_ID},
      #cs_update_operational_summary{display:none!important}
      #${CANONICAL_ID}{
        display:grid!important;
        grid-template-columns:repeat(5,minmax(0,1fr))!important;
        gap:8px!important;
        margin:2px 0 0!important;
        padding:0!important;
        border:0!important;
        background:transparent!important
      }
      #${CANONICAL_ID} .cs-update-summary-card{
        display:flex!important;
        flex-direction:column!important;
        justify-content:center!important;
        align-items:stretch!important;
        gap:5px!important;
        width:100%!important;
        min-width:0!important;
        min-height:82px!important;
        padding:12px!important;
        border:1px solid var(--line)!important;
        border-radius:10px!important;
        background:rgba(255,255,255,.025)!important;
        color:var(--text)!important;
        text-align:left!important;
        font:inherit!important;
        box-shadow:none!important;
        transform:none!important;
        cursor:pointer!important
      }
      #${CANONICAL_ID} .cs-update-summary-card:hover,
      #${CANONICAL_ID} .cs-update-summary-card.is-active{
        border-color:rgba(124,58,237,.72)!important;
        background:rgba(124,58,237,.13)!important
      }
      #${CANONICAL_ID} .cs-update-summary-card>strong{
        display:block!important;
        margin:0!important;
        font-size:20px!important;
        font-weight:800!important;
        line-height:1!important;
        font-variant-numeric:tabular-nums
      }
      #${CANONICAL_ID} .cs-update-summary-footer{
        display:flex!important;
        align-items:center!important;
        gap:6px!important;
        min-width:0;
        color:var(--text-muted)!important;
        font-size:12px!important;
        font-weight:600!important;
        line-height:1.25!important
      }
      #${CANONICAL_ID} .comparison-help{
        flex:0 0 24px!important;
        width:24px!important;
        min-width:24px!important;
        height:24px!important;
        min-height:24px!important;
        font-size:11px!important
      }
      @media(max-width:1180px){#${CANONICAL_ID}{grid-template-columns:repeat(3,minmax(0,1fr))!important}}
      @media(max-width:760px){#${CANONICAL_ID}{grid-template-columns:repeat(2,minmax(0,1fr))!important}}
      @media(max-width:480px){#${CANONICAL_ID}{grid-template-columns:1fr!important}}
    `;
    document.head.appendChild(style);
  }

  function legacySummary() {
    return document.getElementById(LEGACY_ID);
  }

  function ensureCanonicalSummary() {
    const legacy = legacySummary();
    if (!legacy) return null;
    legacy.setAttribute("aria-hidden", "true");
    legacy.dataset.csCompatibilityOnly = "1";

    let summary = document.getElementById(CANONICAL_ID);
    if (!summary) {
      summary = document.createElement("div");
      summary.id = CANONICAL_ID;
      summary.className = "cs-update-summary-canonical";
      summary.setAttribute("aria-label", "Resumo das atualizações");
      legacy.insertAdjacentElement("afterend", summary);
      summary.addEventListener("click", event => {
        const help = event.target.closest?.(".comparison-help");
        if (help) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        const card = event.target.closest?.("[data-cs-update-summary-group]");
        if (!card) return;
        activateGroup(card.dataset.csUpdateSummaryGroup || "total");
      });
    } else if (summary.previousElementSibling !== legacy) {
      legacy.insertAdjacentElement("afterend", summary);
    }
    return summary;
  }

  async function requestRuntime() {
    const response = await fetch("/atualizacoes/jobs", {
      cache: "no-store",
      credentials: "same-origin",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || `HTTP ${response.status}`);
    }
    return payload;
  }

  function activeQueueJobs(data) {
    const queueName = clean(data?.queue?.active_queue || "default");
    return (Array.isArray(data?.jobs) ? data.jobs : []).filter(
      job => clean(job?.queue_name || "default") === queueName
    );
  }

  function jobsForGroup(jobs, key) {
    const group = GROUPS[key];
    if (!group) return [];
    return jobs.filter(job => group.states.includes(clean(job?.state)));
  }

  function publicJobs(jobs) {
    const byId = new Map();
    for (const key of Object.keys(GROUPS)) {
      for (const job of jobsForGroup(jobs, key)) {
        const id = clean(job?.job_id) || `${key}:${job?.woo_product_id || ""}:${job?.name || ""}`;
        if (!byId.has(id)) byId.set(id, job);
      }
    }
    return [...byId.values()];
  }

  function currentActiveGroup() {
    if (clean($("#updates_queue_status_filter")?.value)) return "";
    const contract = window.__crapscraperUpdateOperationalStage1;
    const legacyActive = clean(contract?.activeGroup);
    if (legacyActive && (legacyActive === "total" || GROUPS[legacyActive])) {
      activeGroup = legacyActive;
    }
    return activeGroup;
  }

  function countsFor(data) {
    const jobs = activeQueueJobs(data);
    const counts = {
      prepared: jobsForGroup(jobs, "prepared").length,
      running: jobsForGroup(jobs, "running").length,
      completed: jobsForGroup(jobs, "completed").length,
      errors: jobsForGroup(jobs, "errors").length,
    };
    counts.total = publicJobs(jobs).length;
    return counts;
  }

  function render(data) {
    const summary = ensureCanonicalSummary();
    if (!summary) return;
    const counts = countsFor(data);
    const selected = currentActiveGroup();
    const signature = JSON.stringify([counts, selected]);
    if (signature === lastSignature && summary.childElementCount === ORDER.length) return;
    lastSignature = signature;

    summary.innerHTML = ORDER.map(key => {
      const group = key === "total"
        ? {label: "Total", help: "Soma exata de Preparados, Em andamento, Concluídos e Erros."}
        : GROUPS[key];
      const isActive = selected === key;
      return `<button type="button" class="cs-update-summary-card${isActive ? " is-active" : ""}" data-cs-update-summary-group="${esc(key)}" aria-pressed="${isActive ? "true" : "false"}"><strong>${counts[key] || 0}</strong><span class="cs-update-summary-footer"><span>${esc(group.label)}</span><span class="comparison-help" role="button" aria-label="Ajuda sobre ${esc(group.label)}" data-tooltip="${esc(group.help)}">?</span></span></button>`;
    }).join("");
  }

  function activateGroup(key) {
    const normalized = key === "total" || GROUPS[key] ? key : "total";
    activeGroup = normalized;
    lastSignature = "";

    // A camada da Etapa 1 continua responsável pela listagem agrupada. O resumo
    // visível é separado do legado, mas reutiliza exatamente o mesmo controlador.
    const clickLegacy = (attempt = 0) => {
      const legacyCard = legacySummary()?.querySelector?.(
        `[data-cs-stage1-group="${normalized}"]`
      );
      if (legacyCard) {
        legacyCard.click();
        return;
      }
      if (attempt < 6) window.setTimeout(() => clickLegacy(attempt + 1), 60);
    };
    clickLegacy();

    if (runtime) render(runtime);
  }

  async function refresh() {
    const panel = $("#tab_panel_atualizacoes");
    if (!panel || panel.classList.contains("hidden") || document.hidden) return;
    try {
      runtime = await requestRuntime();
      render(runtime);
    } catch (_error) {
      // O resumo nunca interfere no fluxo de atualização.
    }
  }

  function boot() {
    installStyles();
    ensureCanonicalSummary();
    refresh();

    window.clearInterval(polling);
    polling = window.setInterval(refresh, 1800);

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
    document.addEventListener("crapscraper:main-tab-changed", event => {
      if (String(event?.detail?.key || "") === "atualizacoes") {
        lastSignature = "";
        window.setTimeout(refresh, 0);
      }
    });
    $("#tab_btn_atualizacoes")?.addEventListener("click", () => {
      lastSignature = "";
      window.setTimeout(refresh, 0);
    });
  }

  window.__crapscraperUpdateSummaryStability = Object.freeze({
    groups: GROUPS,
    countsFor,
    publicJobs,
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, {once: true});
  } else {
    boot();
  }
})();