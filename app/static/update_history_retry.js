(() => {
  "use strict";

  if (window.__crapScraperUpdateHistoryRetryInstalled) return;
  window.__crapScraperUpdateHistoryRetryInstalled = true;

  const ROOT = "#updates_history_accordion";
  const ERROR_MODE = '[data-oh-mode="errors"].is-active';
  const RETRY_ATTR = "data-update-history-retry";
  const POLL_MS = 900;
  const TIMEOUT_MS = 30 * 60 * 1000;

  const $ = (selector, root = document) => root?.querySelector?.(selector) || null;
  const $$ = (selector, root = document) => Array.from(root?.querySelectorAll?.(selector) || []);
  const clean = value => String(value ?? "").replace(/\s+/g, " ").trim();
  const sleep = ms => new Promise(resolve => window.setTimeout(resolve, ms));

  async function request(url, options = {}) {
    const response = await window.fetch(url, {
      cache: "no-store",
      credentials: "same-origin",
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
  }

  function retryButton() {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn-primary";
    button.setAttribute(RETRY_ATTR, "1");
    button.textContent = "Tentar novamente";
    button.title = "Revalidar, preparar e tentar esta atualização novamente";
    return button;
  }

  function decorate() {
    const root = $(ROOT);
    if (!root) return;

    const errorsVisible = !!$(ERROR_MODE, root);
    $$(".op-history-row", root).forEach(row => {
      const existing = $(`[${RETRY_ATTR}]`, row);
      if (!errorsVisible) {
        existing?.remove();
        return;
      }
      const jobId = clean(row.dataset.ohRow);
      const actions = $(".op-history-row-actions", row);
      if (!jobId || !actions || existing) return;
      actions.insertBefore(retryButton(), actions.firstChild);
    });
  }

  function latestResult(batch, jobId) {
    const results = Array.isArray(batch?.results) ? batch.results : [];
    for (let index = results.length - 1; index >= 0; index -= 1) {
      const row = results[index] || {};
      if (clean(row.job_id) === jobId) return row;
    }
    return null;
  }

  async function waitForResult(jobId) {
    const deadline = Date.now() + TIMEOUT_MS;
    while (Date.now() < deadline) {
      const payload = await request("/operacoes/simples/status");
      const batch = payload?.update || {};
      const result = latestResult(batch, jobId);
      if (!batch.running && batch.done) {
        if (result) return result;
        throw new Error("A tentativa terminou, mas o resultado deste produto não foi encontrado.");
      }
      await sleep(POLL_MS);
    }
    throw new Error("A tentativa continua em execução além do tempo de acompanhamento da tela. Consulte Processos antes de iniciar outra tentativa.");
  }

  async function reloadHistory(showCompleted) {
    const shared = window.__crapScraperOperationalHistoryShared;
    if (shared?.load) {
      await shared.load("update", true);
    }
    const root = $(ROOT);
    if (showCompleted && root) {
      $("[data-oh-mode='completed']", root)?.click();
    }
    decorate();
  }

  async function retry(button) {
    const row = button.closest(".op-history-row");
    const jobId = clean(row?.dataset?.ohRow);
    if (!jobId) return;

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Tentando novamente…";
    row?.classList.add("is-retrying");

    try {
      await request("/operacoes/simples/atualizar", {
        method: "POST",
        body: JSON.stringify({job_id: jobId}),
      });
      const result = await waitForResult(jobId);
      if (!result?.ok) {
        throw new Error(clean(result?.message) || "A nova tentativa terminou com erro.");
      }

      // O histórico de atualização é uma projeção do estado atual do job. Quando
      // o executor confirma COMPLETED, o mesmo job deixa naturalmente o bucket
      // Erros e reaparece em Concluídos; basta recarregar a projeção persistida.
      await reloadHistory(true);
    } catch (error) {
      await reloadHistory(false).catch(() => {});
      window.alert(clean(error?.message || error) || "Não foi possível tentar esta atualização novamente.");
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = original || "Tentar novamente";
      }
    } finally {
      row?.classList.remove("is-retrying");
    }
  }

  let observer = null;
  function attach() {
    const root = $(ROOT);
    if (!root) return false;
    if (!observer) {
      observer = new MutationObserver(() => window.queueMicrotask(decorate));
      observer.observe(root, {childList: true, subtree: true});
    }
    decorate();
    return true;
  }

  document.addEventListener("click", event => {
    const button = event.target?.closest?.(`[${RETRY_ATTR}]`);
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    retry(button);
  }, true);

  function init() {
    if (attach()) return;
    let attempts = 0;
    const timer = window.setInterval(() => {
      attempts += 1;
      if (attach() || attempts >= 40) window.clearInterval(timer);
    }, 250);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, {once: true});
  } else {
    init();
  }
})();
