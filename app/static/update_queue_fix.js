(() => {
  "use strict";

  function toast(message, kind = "ok") {
    document.querySelector(".cs-update-queue-fix-toast")?.remove();
    const node = document.createElement("div");
    node.className = "cs-update-queue-fix-toast";
    node.setAttribute("role", kind === "error" ? "alert" : "status");
    node.textContent = String(message || "");
    Object.assign(node.style, {
      position: "fixed", right: "18px", bottom: "18px", zIndex: "100000",
      maxWidth: "560px", padding: "12px 14px", borderRadius: "12px",
      border: `1px solid ${kind === "error" ? "#ef4444" : "#10b981"}`,
      background: kind === "error" ? "#451a1a" : "#063d2b", color: "#fff",
      fontWeight: "700", boxShadow: "0 12px 34px rgba(0,0,0,.38)"
    });
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  async function json(url, options = {}) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: {"Content-Type": "application/json", ...(options.headers || {})},
      ...options,
    });
    let data = {};
    try { data = await response.json(); } catch (_error) {}
    if (!response.ok || data?.ok === false) {
      const error = new Error(data?.message || data?.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  const post = (url, payload = {}) => json(url, {method: "POST", body: JSON.stringify(payload)});

  async function executeQueue(button) {
    if (!button || button.dataset.csQueueBusy === "1") return;
    button.dataset.csQueueBusy = "1";
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Verificando fila...";
    try {
      const runtime = await json("/atualizacoes/jobs");
      const queue = runtime?.queue || {};
      const activeName = String(queue.active_queue || "default");
      const jobs = Array.isArray(runtime?.jobs) ? runtime.jobs : [];
      const queued = jobs.filter(job => job?.state === "queued" && String(job?.queue_name || "default") === activeName);
      const executing = jobs.filter(job => job?.state === "executing" && String(job?.queue_name || "default") === activeName);

      if (!queued.length && !executing.length) {
        toast(`A lista ${activeName === "default" ? "Padrão" : activeName} não possui itens aguardando execução.`, "error");
        return;
      }
      if (executing.length && queue.status === "running") {
        toast("A fila já está em execução.", "ok");
        return;
      }

      button.textContent = queue.status === "paused" ? "Retomando..." : "Iniciando...";
      const path = queue.status === "paused" ? "/atualizacoes/fila/continuar" : "/atualizacoes/fila/iniciar";
      const result = await post(path, {});
      const status = result?.queue?.status || "running";
      toast(result?.started === false && status === "running" ? "A fila já estava em execução." : "Fila iniciada com sucesso.", "ok");
      window.setTimeout(() => window.location.reload(), 650);
    } catch (error) {
      let message = error?.message || String(error);
      if (error?.status === 403 && /bloquead|configura/i.test(message)) {
        message += " Ative SCRAPER_UPDATE_EXECUTION_ENABLED=1 no ambiente do Windows e reinicie o CrapScraper.";
      }
      toast(message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original || "Executar fila";
      delete button.dataset.csQueueBusy;
    }
  }

  document.addEventListener("click", event => {
    const button = event.target?.closest?.("#updates_queue_start");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    executeQueue(button);
  }, true);
})();
