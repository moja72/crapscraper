(() => {
  "use strict";

  if (window.__crapScraperUpdateRetryRecoveryV2Installed) return;
  window.__crapScraperUpdateRetryRecoveryV2Installed = true;

  const RETRY_ATTR = "data-update-history-retry";
  const POLL_MS = 850;
  const TIMEOUT_MS = 35 * 60 * 1000;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

  function installStyle() {
    if (document.getElementById("cs-update-retry-recovery-v2-style")) return;
    const style = document.createElement("style");
    style.id = "cs-update-retry-recovery-v2-style";
    style.textContent = `
      #updates_history_accordion .op-history-row.is-retrying{opacity:.82}
      #updates_history_accordion .cs-retry-feedback{grid-column:1/-1;margin-top:7px;padding:8px 10px;border-radius:7px;font-size:12px;line-height:1.4;background:rgba(124,58,237,.10);border:1px solid rgba(124,58,237,.30)}
      #updates_history_accordion .cs-retry-feedback.is-success{background:rgba(16,185,129,.10);border-color:rgba(16,185,129,.36)}
      #updates_history_accordion .cs-retry-feedback.is-error{background:rgba(239,68,68,.10);border-color:rgba(239,68,68,.38)}
    `;
    document.head.appendChild(style);
  }

  async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || 15000);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
        headers: options.body
          ? {"Content-Type": "application/json", ...(options.headers || {})}
          : (options.headers || {}),
        ...options,
      });
      let payload = {};
      try { payload = await response.json(); } catch (_error) {}
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload?.message || `HTTP ${response.status}`);
      }
      return payload;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function feedback(row, message, type = "") {
    if (!row) return;
    let node = $(".cs-retry-feedback", row);
    if (!node) {
      node = document.createElement("div");
      node.className = "cs-retry-feedback";
      row.appendChild(node);
    }
    node.classList.toggle("is-success", type === "success");
    node.classList.toggle("is-error", type === "error");
    node.textContent = clean(message);
  }

  function latestResult(batch, jobId) {
    const results = Array.isArray(batch?.results) ? batch.results : [];
    for (let index = results.length - 1; index >= 0; index -= 1) {
      const result = results[index] || {};
      if (clean(result.job_id) === jobId) return result;
    }
    return null;
  }

  async function waitForRetry(jobId, row) {
    const deadline = Date.now() + TIMEOUT_MS;
    while (Date.now() < deadline) {
      const status = await request("/operacoes/simples/status", {timeoutMs: 10000});
      const batch = status?.update || {};
      const result = latestResult(batch, jobId);
      const processed = Number(batch.processed || 0);
      const total = Number(batch.total || 1);
      if (batch.running) feedback(row, `Revalidando e atualizando… ${processed} de ${total} processado(s).`);
      if (!batch.running && batch.global_block) {
        throw new Error(clean(batch.last_error || batch.message) || "A fonte exige nova autenticação antes de continuar.");
      }
      if (!batch.running && batch.done) {
        if (result) return result;
        throw new Error("A tentativa terminou, mas o resultado deste produto não foi localizado.");
      }
      await sleep(POLL_MS);
    }
    throw new Error("A atualização continua em execução além do tempo de acompanhamento da tela. Consulte o log técnico.");
  }

  async function reloadHistory(showCompleted) {
    const shared = window.__crapScraperOperationalHistoryShared;
    if (shared?.load) await shared.load("update", true);
    const root = $("#updates_history_accordion");
    if (showCompleted && root) $("[data-oh-mode='completed']", root)?.click();
    shared?.ensure?.();
  }

  async function retryFromHistory(button) {
    const row = button.closest(".op-history-row");
    const jobId = clean(row?.dataset?.ohRow);
    if (!jobId || button.disabled) return;

    button.disabled = true;
    button.textContent = "Tentando novamente…";
    row?.classList.add("is-retrying");
    feedback(row, "Nova tentativa iniciada: erro anterior permanece no histórico e o estado operacional será revalidado do zero.");

    try {
      await request("/operacoes/simples/retry-update", {
        method: "POST",
        body: JSON.stringify({job_id: jobId}),
        timeoutMs: 20000,
      });
      const result = await waitForRetry(jobId, row);
      if (!result?.ok) throw new Error(clean(result?.message) || "A nova tentativa terminou sem concluir o produto.");
      feedback(row, clean(result?.message) || "Atualização concluída.", "success");
      await reloadHistory(true);
    } catch (error) {
      const reason = clean(error?.message || String(error)) || "Falha não identificada.";
      feedback(row, `Não atualizado: ${reason}`, "error");
      button.disabled = false;
      button.textContent = "Tentar novamente";
      row?.classList.remove("is-retrying");
      try { await reloadHistory(false); } catch (_reloadError) {}
    }
  }

  function boot() {
    installStyle();
    // Único listener desta policy: retry. O accordion técnico pertence
    // exclusivamente a update_technical_log_fix.js e usa o toggle nativo.
    document.addEventListener("click", event => {
      const retry = event.target?.closest?.(`[${RETRY_ATTR}]`);
      if (!retry) return;
      event.preventDefault();
      retryFromHistory(retry);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, {once:true});
  else boot();
})();
