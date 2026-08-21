(() => {
  "use strict";

  if (window.__crapScraperFrontendRequestResilienceInstalled) return;
  window.__crapScraperFrontendRequestResilienceInstalled = true;

  const upstreamFetch = window.fetch.bind(window);
  const PACK_PATH = "/loja/pacotes/precos";
  const PACK_CACHE_MS = 4000;
  const PACK_TIMEOUT_MS = 30000;

  let packRequest = null;
  let packCache = null;

  const pathOf = input => {
    try {
      return new URL(typeof input === "string" ? input : input?.url || "", location.href).pathname;
    } catch (_error) {
      return "";
    }
  };

  const methodOf = (input, init = {}) => String(
    init?.method || (typeof input === "object" && input?.method) || "GET"
  ).toUpperCase();

  const storeVisible = () => {
    const panel = document.getElementById("tab_panel_loja");
    return !!panel && !panel.classList.contains("hidden");
  };

  const releasePackLoadingState = () => {
    ["store_pack_prices", "store_plan_prices"].forEach(id => {
      document.getElementById(id)?.setAttribute("aria-busy", "false");
    });
  };

  const responseFromSnapshot = snapshot => new Response(snapshot.body, {
    status: snapshot.status,
    statusText: snapshot.statusText,
    headers: snapshot.headers,
  });

  const deferredResponse = () => new Response(JSON.stringify({
    ok: true,
    products: [],
    total: 0,
    deferred: true,
  }), {
    status: 200,
    headers: {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
  });

  async function fetchPackSnapshot(input, init = {}) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), PACK_TIMEOUT_MS);
    const callerSignal = init?.signal || (typeof input === "object" ? input?.signal : null);
    const abortFromCaller = () => controller.abort();

    if (callerSignal) {
      if (callerSignal.aborted) controller.abort();
      else callerSignal.addEventListener("abort", abortFromCaller, {once: true});
    }

    try {
      const response = await upstreamFetch(input, {...init, signal: controller.signal});
      const body = await response.text();
      return {
        body,
        status: response.status,
        statusText: response.statusText,
        headers: Array.from(response.headers.entries()),
      };
    } finally {
      window.clearTimeout(timer);
      callerSignal?.removeEventListener?.("abort", abortFromCaller);
      releasePackLoadingState();
    }
  }

  window.fetch = function resilientFetch(input, init = {}) {
    const path = pathOf(input);
    const method = methodOf(input, init);

    if (path !== PACK_PATH) return upstreamFetch(input, init);

    if (method !== "GET") {
      packCache = null;
      return upstreamFetch(input, init).finally(releasePackLoadingState);
    }

    // A tabela avançada de packs/planos era carregada no DOMContentLoaded mesmo
    // com a aba Loja escondida. Isso executava uma varredura WooCommerce pesada
    // durante o boot da aba Principal. A leitura real fica sob demanda.
    if (!storeVisible()) {
      releasePackLoadingState();
      return Promise.resolve(deferredResponse());
    }

    const now = Date.now();
    if (packCache && now - packCache.at <= PACK_CACHE_MS) {
      return Promise.resolve(responseFromSnapshot(packCache.snapshot));
    }

    // panel.js e store_pack_variation_table.js podem pedir a mesma coleção no
    // mesmo clique. Compartilhamos uma única requisição e entregamos Responses
    // independentes para cada consumidor poder ler o body normalmente.
    if (!packRequest) {
      packRequest = fetchPackSnapshot(input, init)
        .then(snapshot => {
          packCache = {at: Date.now(), snapshot};
          return snapshot;
        })
        .finally(() => {
          packRequest = null;
          releasePackLoadingState();
        });
    }

    return packRequest.then(responseFromSnapshot);
  };

  // Defesa adicional: nenhum estado visual de carregamento desta área deve
  // sobreviver a uma troca de aba, timeout, abort ou erro de parsing/HTTP.
  document.addEventListener("crapscraper:main-tab-changed", releasePackLoadingState);
  window.addEventListener("pagehide", releasePackLoadingState);
})();
