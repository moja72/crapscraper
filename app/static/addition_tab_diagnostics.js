(() => {
  "use strict";
  if (window.__crapScraperAdditionTabDiagnosticsInstalled) return;
  window.__crapScraperAdditionTabDiagnosticsInstalled = true;

  const ENDPOINT = "/adicoes/diagnostico/event";
  const now = () => Math.round(performance.now() * 10) / 10;
  const panelState = () => {
    const ids = ["principal", "comparacao", "atualizacoes", "adicoes", "loja"];
    const panels = {};
    ids.forEach(key => {
      const node = document.getElementById(`tab_panel_${key}`);
      panels[key] = node ? !node.classList.contains("hidden") : null;
    });
    const env = document.querySelector(".updates-environment-card");
    return {
      activeTab: document.body?.dataset?.activeTab || "",
      panels,
      environmentParent: env?.parentElement?.id || "",
      additionChildren: document.getElementById("tab_panel_adicoes")?.children?.length || 0,
      operationalRoot: !!document.getElementById("addition_operational_root"),
    };
  };

  function emit(stage, extra = {}) {
    const payload = JSON.stringify({stage, perf_ms: now(), ts: Date.now(), ...panelState(), ...extra});
    try {
      const blob = new Blob([payload], {type:"application/json"});
      if (navigator.sendBeacon?.(ENDPOINT, blob)) return;
    } catch (_error) {}
    try {
      fetch(ENDPOINT, {method:"POST", headers:{"Content-Type":"application/json"}, body:payload, keepalive:true, cache:"no-store"}).catch(() => {});
    } catch (_error) {}
  }

  emit("DIAGNOSTICS_BOOT");

  const button = document.getElementById("tab_btn_adicoes");
  if (button) {
    button.addEventListener("click", () => emit("ADDITION_TARGET_BUBBLE"));
  }

  document.addEventListener("click", event => {
    const target = event.target?.closest?.("#tab_btn_adicoes");
    if (!target) return;
    emit("ADDITION_CLICK_CAPTURE");
    queueMicrotask(() => emit("ADDITION_MICROTASK_AFTER_CLICK"));
    requestAnimationFrame(() => {
      emit("ADDITION_RAF_1");
      requestAnimationFrame(() => emit("ADDITION_RAF_2"));
    });
    setTimeout(() => emit("ADDITION_TIMEOUT_0"), 0);
    setTimeout(() => emit("ADDITION_TIMEOUT_100"), 100);
    setTimeout(() => emit("ADDITION_TIMEOUT_500"), 500);
    setTimeout(() => emit("ADDITION_TIMEOUT_1500"), 1500);
  }, true);

  const bodyObserver = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === "attributes" && record.target === document.body && record.attributeName === "data-active-tab") {
        emit("BODY_ACTIVE_TAB_CHANGED");
      }
    }
  });
  if (document.body) bodyObserver.observe(document.body, {attributes:true, attributeFilter:["data-active-tab"]});

  ["principal", "comparacao", "atualizacoes", "adicoes", "loja"].forEach(key => {
    const panel = document.getElementById(`tab_panel_${key}`);
    if (!panel) return;
    new MutationObserver(records => {
      const classChanged = records.some(record => record.type === "attributes" && record.attributeName === "class");
      if (classChanged) emit(`PANEL_CLASS_CHANGED:${key}`);
    }).observe(panel, {attributes:true, attributeFilter:["class"]});
  });

  const env = document.querySelector(".updates-environment-card");
  if (env) {
    const parents = ["tab_panel_atualizacoes", "tab_panel_adicoes", "tab_panel_loja"].map(id => document.getElementById(id)).filter(Boolean);
    parents.forEach(parent => {
      new MutationObserver(records => {
        if (records.some(record => [...record.addedNodes, ...record.removedNodes].includes(env))) {
          emit("ENVIRONMENT_MOVED", {observedParent: parent.id});
        }
      }).observe(parent, {childList:true});
    });
  }

  if (typeof PerformanceObserver !== "undefined") {
    try {
      const observer = new PerformanceObserver(list => {
        list.getEntries().forEach(entry => emit("LONG_TASK", {duration_ms: Math.round(entry.duration * 10) / 10, name: entry.name || ""}));
      });
      observer.observe({entryTypes:["longtask"]});
    } catch (_error) {}
  }

  const upstreamFetch = window.fetch.bind(window);
  window.fetch = function diagnosticFetch(input, init = {}) {
    let path = "";
    try { path = new URL(typeof input === "string" ? input : input?.url || "", location.href).pathname; } catch (_error) {}
    if (!path.startsWith("/adicoes/")) return upstreamFetch(input, init);
    const method = String(init?.method || "GET").toUpperCase();
    const started = now();
    emit("ADDITION_FETCH_START", {path, method});
    return upstreamFetch(input, init).then(response => {
      emit("ADDITION_FETCH_END", {path, method, status:response.status, duration_ms:Math.round((now()-started)*10)/10});
      return response;
    }, error => {
      emit("ADDITION_FETCH_ERROR", {path, method, error:String(error?.message || error), duration_ms:Math.round((now()-started)*10)/10});
      throw error;
    });
  };
})();
