(function () {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function parseJsonScript(id) {
    const node = byId(id);
    if (!node) return {};
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (_error) {
      return {};
    }
  }

  const BOOT = parseJsonScript("monitor-boot-data");

  const ENDPOINTS = Object.assign(
    {
      boot: "/boot",
      state: "/state",
      logsFull: "/logs_full",
      context: "/context",
      health: "/health",
      config: "/config",
      start: "/start",
      continue: "/continue",
      pause: "/pause",
      resume: "/resume",
      stop: "/stop",
      slotCreate: "/slot/create",
      slotSwitch: "/slot/switch",
      slotDefault: "/slot/default",
      slotDelete: "/slot/delete",
      slotClear: "/slot/clear",
      slotRename: "/slot/rename",

      slotRemoveContext: "/slot/remove-context",
      slotRemoveZeroContexts: "/slot/remove-zero-contexts",
      runPrefix: "/run/",
      panelCss: "/panel.css",
      panelJs: "/panel.js",
      runs: "/runs",
      runCreate: "/run/create",
      runDelete: "/run/delete",
      queueGet: "/fila",
      queueSave: "/fila",
      runPanelPrefix: "/run/",
      currentRunPanel: "/",
      catalogosData: "/catalogos/data",
      catalogosDownloadCsv: "/catalogos/download/csv",
      catalogosDownloadStatus: "/catalogos/download/status",
      catalogosDownloadLog: "/catalogos/download/log",
      plugintemaCatalogExport: "/plugintema/catalogo/exportar",
      comparisonData: "/comparacao/data",
      comparisonSources: "/comparacao/fontes",
      plugintemaCatalogGenerate: "/plugintema/catalogo/gerar",
      plugintemaCatalogOptions: "/plugintema/catalogo/opcoes",
      plugintemaProductSearch: "/plugintema/catalogo/pesquisar",
      plugintemaCatalogManage: "/plugintema/catalogo/gerenciar",
      plugintemaCatalogDownload: "/plugintema/catalogo/baixar",
      storePricing: "/loja/precos",
      comparisonProducts: "/comparacao/produtos",
      comparisonRelationshipSave: "/comparacao/vinculo/salvar",
    },
    BOOT.endpoints || {}
  );

  const POLL_INTERVAL_MS = Math.max(500, Number(BOOT.poll_interval_ms || 1200));

  const LISTING_PAGE_SIZE_OPTIONS = [5, 10];
  const LISTING_DEFAULT_PAGE_SIZE = 5;

  function normalizeListingPageSize(value, fallback = LISTING_DEFAULT_PAGE_SIZE) {
    const parsed = toInt(value, fallback);
    return LISTING_PAGE_SIZE_OPTIONS.includes(parsed) ? parsed : fallback;
  }

  function listingRangeText(total, page, pageSize, noun = "itens") {
    const safeTotal = Math.max(0, toInt(total, 0));
    const safeSize = Math.max(1, toInt(pageSize, LISTING_DEFAULT_PAGE_SIZE));
    const safePage = Math.max(1, toInt(page, 1));
    if (!safeTotal) return `Mostrando 0 de 0 ${noun}`;
    const start = ((safePage - 1) * safeSize) + 1;
    const end = Math.min(safePage * safeSize, safeTotal);
    return `Mostrando ${start}–${end} de ${safeTotal} ${noun}`;
  }

    const UI = {
    boot: BOOT,
    endpoints: ENDPOINTS,
    pollIntervalMs: POLL_INTERVAL_MS,
    pollTimer: null,
    pollInFlight: false,
    actionInFlight: false,
    internalWriteDepth: 0,
    formDirty: false,
    lastStatePayload: null,
    lastLogsText: "",
    consecutivePollErrors: 0,
    slotSelectionDirty: false,
    pendingSlotValue: "",
    runs: Array.isArray(BOOT?.runs) ? BOOT.runs : [],
    currentRunId: String(BOOT?.run_id || ""),
    primaryRunId: String(BOOT?.primary_run_id || ""),
    managerMode: !!BOOT?.manager_mode,
    runsRefreshInFlight: false,
    filaRules: [],
    filaCatalogOptions: [],
    catalogRows: [],
    plugintemaSelectedProducts: new Map(),
    plugintemaManageRows: [],
    plugintemaManagePage: 1,
    plugintemaManagePageSize: 5,
    comparison: {
      loaded: false,
      loading: false,
      sourcesLoaded: false,
      page: 1,
      pageSize: 5,
      totalPages: 1,
      status: "all",
      query: "",
      lastPayload: null,
      rowsById: {},
      selectedItemIds: new Set(),
      selectedRowsById: {},
      allResultsSelected: false,
      resultSignature: "",
      cacheRestored: false,
      logs: [],
      linkModal: {
        itemId: "",
        opener: null,
        saving: false,
        searchTimer: null,
        searchSequence: 0,
      },
      diagnosticModal: {
        itemId: "",
        opener: null,
      },
    },
    catalogPreview: {
      kind: "none",
      rawText: "",
      downloadUrl: "",
      title: "Prévia",
      page: 1,
      pageSize: 5,
      pageSizeOptions: LISTING_PAGE_SIZE_OPTIONS,
    },
  };

  const COMPARISON_CACHE_KEY = "crapscraper:last-comparison:v1";

  function appendComparisonLog(message, level = "INFO") {
    const text = normalizeText(message);
    if (!text) return;
    const timestamp = new Date().toLocaleString("pt-BR");
    UI.comparison.logs.push(`[${timestamp}] [${level}] ${text}`);
    UI.comparison.logs = UI.comparison.logs.slice(-300);
    const target = byId("comparison_log");
    if (target) {
      target.textContent = UI.comparison.logs.join("\n") || "Nenhum evento nesta sessão.";
      target.scrollTop = target.scrollHeight;
    }
  }

  function saveComparisonCache(payload) {
    try {
      const cached = {
        saved_at: new Date().toISOString(),
        source_id: normalizeText(byId("comparison_source_catalog")?.value),
        target_id: normalizeText(byId("comparison_target_catalog")?.value),
        filters: comparisonFilterSnapshot(),
        payload,
      };
      window.localStorage.setItem(COMPARISON_CACHE_KEY, JSON.stringify(cached));
    } catch (error) {
      appendComparisonLog(`O resultado foi exibido, mas não coube no cache local: ${normalizeText(error?.message, "limite excedido")}.`, "AVISO");
    }
  }

  function restoreComparisonCache() {
    if (UI.comparison.cacheRestored) return false;
    UI.comparison.cacheRestored = true;
    try {
      const cached = JSON.parse(window.localStorage.getItem(COMPARISON_CACHE_KEY) || "null");
      if (!cached?.payload || !Array.isArray(cached.payload.rows)) return false;
      const source = byId("comparison_source_catalog");
      const target = byId("comparison_target_catalog");
      if (source && qsa("option", source).some((option) => option.value === cached.source_id)) source.value = cached.source_id;
      if (target && qsa("option", target).some((option) => option.value === cached.target_id)) target.value = cached.target_id;
      const filters = cached.filters || {};
      const values = {
        comparison_status_filter: filters.status,
        comparison_decision_filter: filters.decision,
        comparison_query: filters.q,
        comparison_candidate_filter: filters.candidate_filter,
        comparison_candidate_count_min: filters.candidate_count_min,
        comparison_candidate_count_max: filters.candidate_count_max,
        comparison_score_min: filters.score_min,
        comparison_score_max: filters.score_max,
      };
      Object.entries(values).forEach(([id, value]) => { if (byId(id) && value != null) byId(id).value = String(value); });
      renderComparison(cached.payload);
      const savedAt = cached.saved_at ? new Date(cached.saved_at).toLocaleString("pt-BR") : "data não registrada";
      appendComparisonLog(`Último resultado restaurado do cache (${savedAt}).`);
      return true;
    } catch (error) {
      appendComparisonLog(`Não foi possível restaurar o cache: ${normalizeText(error?.message)}.`, "AVISO");
      return false;
    }
  }

 function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

  function normalizeText(value, fallback = "") {
    const text = String(value ?? "").replace(/\s+/g, " ").trim();
    return text || fallback;
  }

  function catalogDisplayName(value, fallback = "") {
    const name = normalizeText(value, fallback);
    return name.toLowerCase() === "default" ? "Padrão" : name;
  }

  const PT_BR_INTEGER_FORMATTER = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const PT_BR_DATE_TIME_FORMATTER = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "America/Sao_Paulo",
  });

  function formatPtBrInteger(value) {
    const parsed = Number.parseInt(String(value ?? "0").replace(/\D/g, ""), 10);
    return PT_BR_INTEGER_FORMATTER.format(Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
  }

  function formatPtBrDateTime(value, fallback = "Data não registrada") {
    const raw = normalizeText(value);
    if (!raw) return fallback;
    if (/^\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2}$/.test(raw)) return raw;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime())
      ? fallback
      : PT_BR_DATE_TIME_FORMATTER.format(parsed).replace(",", "");
  }

  function toInt(value, fallback = 0) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function ensureTrailingSlash(value) {
    const text = normalizeText(value);
    if (!text) return "";
    return text.endsWith("/") ? text : `${text}/`;
  }

  function uniqueStrings(values) {
    const out = [];
    const seen = new Set();

        for (const raw of Array.isArray(values) ? values : []) {
      const value = ensureTrailingSlash(raw);
      if (!value || seen.has(value)) continue;
      seen.add(value);
      out.push(value);
    }

    return out;
  }

  function isManagerMode() {
    return !!UI.managerMode || Boolean(UI.endpoints.runs && UI.endpoints.runCreate);
  }

  function isSameRunId(left, right) {
    return normalizeText(left) && normalizeText(left) === normalizeText(right);
  }

  function getRunPanelPath(runId) {
    const normalizedRunId = normalizeText(runId);
    if (!normalizedRunId) {
      return normalizeText(UI.endpoints.currentRunPanel, "/");
    }

    const prefix = normalizeText(UI.endpoints.runPanelPrefix, "/run/");
    const normalizedPrefix = prefix.endsWith("/") ? prefix : `${prefix}/`;
    return `${normalizedPrefix}${encodeURIComponent(normalizedRunId)}/`;
  }

  function syncCurrentRunIdWithRuns(data = null) {
    const runs = Array.isArray(UI.runs) ? UI.runs : [];
    if (!runs.length) {
      UI.currentRunId = "";
      return "";
    }

    const preferred = normalizeText(
      UI.currentRunId || data?.run_id || BOOT?.run_id || ""
    );

    if (preferred && runs.some((run) => isSameRunId(run?.run_id, preferred))) {
      UI.currentRunId = preferred;
      return preferred;
    }

    const primary = normalizeText(UI.primaryRunId);
    const fallback =
      (primary && runs.some((run) => isSameRunId(run?.run_id, primary)) && primary) ||
      normalizeText(runs[0]?.run_id);

    UI.currentRunId = fallback;
    return fallback;
  }

  function getRunSummaryContext(run) {
    return run && typeof run === "object" && run.context && typeof run.context === "object"
      ? run.context
      : {};
  }

  function getRunStatusText(run) {
    return normalizeText(run?.status, "Parado");
  }

  function getRunStatusMeta(value) {
    const statusText =
      typeof value === "string"
        ? normalizeText(value, "Parado")
        : getRunStatusText(value);

    const normalized = statusText.toLowerCase();

    if (normalized.includes("erro") || normalized.includes("error")) {
      return {
        label: statusText || "Erro",
        icon: "❌",
        badgeClass: "is-danger",
      };
    }

    if (normalized.includes("conclu") || normalized.includes("completed")) {
      return {
        label: statusText || "Concluído",
        icon: "✅",
        badgeClass: "is-completed",
      };
    }

    if (
      normalized.includes("rodando") ||
      normalized.includes("running") ||
      normalized.includes("iniciando") ||
      normalized.includes("processando") ||
      normalized.includes("em andamento")
    ) {
      return {
        label: statusText || "Rodando",
        icon: "🟢",
        badgeClass: "is-success",
      };
    }

    if (
      normalized.includes("paus") ||
      normalized.includes("parando") ||
      normalized.includes("aguard")
    ) {
      return {
        label: statusText || "Pausado",
        icon: "⏸",
        badgeClass: "is-warning",
      };
    }

    return {
      label: statusText || "Parado",
      icon: "⚪",
      badgeClass: "is-idle",
    };
  }

  function getRunTitle(run) {
    const context = getRunSummaryContext(run);
    const account = normalizeText(context.account_key);
    const itemType = normalizeText(context.item_type_key);
    const slot = catalogDisplayName(context.slot_name);

    return [account || "sem-conta", itemType || "sem-tipo", slot || "sem-slot"].join(" • ");
  }

  function getRunExpectedTotal(run) {
  const explicitTotal = Math.max(
    0,
    toInt(run?.total_expected ?? run?.totalExpected ?? 0, 0)
  );
  if (explicitTotal > 0) {
    return explicitTotal;
  }

  const availableCategories = Array.isArray(run?.available_categories)
    ? run.available_categories
    : [];

  const scopeMode = normalizeText(run?.scope_mode, "all").toLowerCase();
  const selectedCategories = new Set(
    uniqueStrings(Array.isArray(run?.selected_categories) ? run.selected_categories : [])
  );

  let total = 0;

  for (const category of availableCategories) {
    const categoryUrl = ensureTrailingSlash(
      category?.url || category?.categoria_url || ""
    );

    if (scopeMode === "selected" && selectedCategories.size > 0) {
      if (!selectedCategories.has(categoryUrl)) {
        continue;
      }
    }

    total += Math.max(
      0,
      toInt(
        category?.total ?? category?.total_esperado ?? category?.expected_total ?? 0,
        0
      )
    );
  }

  return total;
}

function formatEtaDuration(totalSeconds) {
  const seconds = Math.max(0, toInt(totalSeconds, 0));
  const totalMinutes = Math.max(1, Math.ceil(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours <= 0) {
    return `${totalMinutes} minuto${totalMinutes === 1 ? "" : "s"}`;
  }

  if (minutes <= 0) {
    return `${hours} hora${hours === 1 ? "" : "s"}`;
  }

  return `${hours} hora${hours === 1 ? "" : "s"} e ${minutes} minuto${minutes === 1 ? "" : "s"}`;
}

function getRunProgressData(run) {
  const saved = Math.max(0, toInt(run?.saved_count ?? 0, 0));
  let total = getRunExpectedTotal(run);
  const statusText = getRunStatusText(run);
  const statusLower = statusText.toLowerCase();
  const running = !!run?.running;
  const elapsedSeconds = Math.max(0, toInt(run?.timer_seconds ?? 0, 0));

  if (
    total <= 0 &&
    saved > 0 &&
    (statusLower.includes("conclu") || statusLower.includes("completed"))
  ) {
    total = saved;
  }

  let percent = 0;
  if (total > 0) {
    percent = Math.round((saved / total) * 100);
    percent = Math.max(0, Math.min(100, percent));
  } else if (statusLower.includes("conclu") || statusLower.includes("completed")) {
    percent = 100;
  }

  let etaText = "Estimativa de conclusão: aguardando início";
  let remainingSeconds = 0;

  if (percent >= 100 && (saved > 0 || total > 0)) {
    etaText = "Estimativa de conclusão: concluído";
  } else if (!running && (saved > 0 || total > 0) && percent < 100) {
    etaText = "Estimativa de conclusão: aguardando retomada";
  } else if (running && saved > 0 && total > saved && elapsedSeconds > 0) {
    const itemsPerSecond = saved / elapsedSeconds;
    if (itemsPerSecond > 0) {
      remainingSeconds = Math.ceil((total - saved) / itemsPerSecond);
      etaText = `Estimativa de conclusão: ${formatEtaDuration(remainingSeconds)}`;
    } else {
      etaText = "Estimativa de conclusão: calculando...";
    }
  } else if (running) {
    etaText = "Estimativa de conclusão: calculando...";
  }

  return {
    saved,
    total,
    percent,
    percentText: `${percent}%`,
    etaText,
    remainingSeconds,
  };
}

function ensureHeadProgressElements() {
  const badgesWrap = qs(".page-head-badges");
  if (!badgesWrap) return {};

  let wrap = byId("head_progress_wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.id = "head_progress_wrap";
    wrap.className = "head-progress-wrap";

    wrap.innerHTML = `
      <div class="head-progress-bar" aria-hidden="true">
        <div class="head-progress-fill" id="head_progress_fill"></div>
      </div>
      <div class="head-progress-meta">
        <span class="head-progress-percent" id="head_progress_percent">0%</span>
        <span class="head-progress-eta" id="head_progress_eta">Estimativa de conclusão: aguardando início</span>
      </div>
    `;

    const runsWrap = byId("head_runs_switcher_wrap");
    if (runsWrap && runsWrap.parentNode === badgesWrap) {
      badgesWrap.insertBefore(wrap, runsWrap);
    } else {
      badgesWrap.appendChild(wrap);
    }
  }

  return {
    wrap,
    fill: byId("head_progress_fill"),
    percent: byId("head_progress_percent"),
    eta: byId("head_progress_eta"),
  };
}

function renderHeadProgress(data) {
  const progressEls = ensureHeadProgressElements();
  if (!progressEls.wrap) return;

  const progress = getRunProgressData(data);

  if (progressEls.fill) {
    progressEls.fill.style.width = `${progress.percent}%`;
  }

  if (progressEls.percent) {
    progressEls.percent.textContent = progress.percentText;
  }

  if (progressEls.eta) {
    progressEls.eta.textContent = progress.etaText;
  }
}

function getRunSubtitle(run) {
  const status = getRunStatusText(run);
  const summary = normalizeText(run?.summary);
  return summary ? `${status} • ${summary}` : status;
}

function renderHeadStatusBadge(data) {
  const badge = byId("head_status_badge");
  if (!badge) return;

  const meta = getRunStatusMeta(data?.status);
  const progress = getRunProgressData(data);

  badge.classList.remove(
    "is-success",
    "is-warning",
    "is-danger",
    "is-completed",
    "is-idle"
  );
  badge.classList.add("head-status-badge", meta.badgeClass);

  badge.innerHTML = `
    <span class="head-status-label">${escapeHtml(meta.label)}</span>
    <span class="head-status-progress">${escapeHtml(progress.percentText)}</span>
    <span class="head-status-icon" aria-hidden="true">${escapeHtml(meta.icon)}</span>
  `;

  badge.title = `Status atual: ${meta.label} • ${progress.percentText}`;
  renderHeadProgress(data);
}

function renderStickyRunsSwitcher(data) {
  const wrap = byId("head_runs_switcher_wrap");
  const label = byId("head_runs_switcher_label");
  const list = byId("head_runs_switcher_list");

  if (!wrap || !label || !list) return;

  if (!isManagerMode()) {
    wrap.classList.add("hidden");
    list.innerHTML = "";
    return;
  }

  const runs = Array.isArray(UI.runs) ? UI.runs : [];
  const currentRunId = syncCurrentRunIdWithRuns(data);
  const otherRuns = runs.filter((run) => !isSameRunId(run?.run_id, currentRunId));

  if (!otherRuns.length) {
    wrap.classList.add("hidden");
    list.innerHTML = "";
    return;
  }

  wrap.classList.remove("hidden");
  label.textContent =
    otherRuns.length === 1
      ? "Outra execução disponível"
      : `${otherRuns.length} outras execuções disponíveis`;

  list.innerHTML = otherRuns
    .map((run) => {
      const runId = normalizeText(run?.run_id);
      const meta = getRunStatusMeta(run);
      const title = getRunTitle(run);
      const subtitle = getRunSubtitle(run);
      const progress = getRunProgressData(run);

      return `
        <button
          type="button"
          class="badge head-run-switch ${meta.badgeClass}"
          data-run-id="${escapeHtml(runId)}"
          title="${escapeHtml(`${subtitle} • ${progress.percentText}`)}"
        >
          <span class="head-run-switch-text">${escapeHtml(title)}</span>
          <span class="head-run-switch-progress">${escapeHtml(progress.percentText)}</span>
          <span class="head-run-switch-icon" aria-hidden="true">${escapeHtml(meta.icon)}</span>
        </button>
      `;
    })
    .join("");

  qsa(".head-run-switch", list).forEach((button) => {
    button.addEventListener("click", () => {
      const runId = normalizeText(button.getAttribute("data-run-id"));
      if (!runId) return;
      window.location.href = getRunPanelPath(runId);
    });
  });
}

  function withInternalWrite(fn) {
    UI.internalWriteDepth += 1;
    try {
      return fn();
    } finally {
      UI.internalWriteDepth = Math.max(0, UI.internalWriteDepth - 1);
    }
  }

  function isInternalWrite() {
    return UI.internalWriteDepth > 0;
  }

  function markFormDirty() {
    if (isInternalWrite()) return;
    UI.formDirty = true;
    refreshSelectedCategoriesCounter();
  }

  function clearFormDirty() {
    UI.formDirty = false;
  }

  function setText(id, value, fallback = "-") {
    const node = byId(id);
    if (!node) return;
    const text = normalizeText(value, "");
    node.textContent = text || fallback;
  }

  function setValue(id, value, fallback = "") {
    const node = byId(id);
    if (!node) return;
    node.value = value == null ? fallback : String(value);
  }

  function setChecked(id, checked) {
    const node = byId(id);
    if (!node) return;
    node.checked = !!checked;
  }

  function setDisabled(id, disabled) {
    const node = byId(id);
    if (!node) return;
    node.disabled = !!disabled;
      }

function showElement(id, visible) {
  const node = byId(id);
  if (!node) return;

  node.classList.toggle("hidden", !visible);

  if (visible) {
    node.style.removeProperty("display");
  } else {
    node.style.display = "none";
  }
}

  function getButtonLabelForPrimary(data) {
    return normalizeText(data?.primary_button_label, "▶️ Iniciar");
  }

  function getStatusTone(status) {
    const value = normalizeText(status).toLowerCase();

    if (
      value.includes("erro") ||
      value.includes("error") ||
      value.includes("interromp") ||
      value.includes("stop")
    ) {
      return "danger";
    }

    if (
      value.includes("paus") ||
      value.includes("parando") ||
      value.includes("aguard")
    ) {
      return "warning";
    }

    if (
      value.includes("rodando") ||
      value.includes("running") ||
      value.includes("conclu") ||
      value.includes("pronto") ||
      value.includes("ready")
    ) {
      return "success";
    }

    return "accent";
  }

  function clearToneClasses(node) {
    if (!node) return;
    node.classList.remove("is-success", "is-warning", "is-danger", "is-accent");
  }

  function applyTone(node, tone) {
    if (!node) return;
    clearToneClasses(node);

    if (tone === "success") node.classList.add("is-success");
    else if (tone === "warning") node.classList.add("is-warning");
    else if (tone === "danger") node.classList.add("is-danger");
    else node.classList.add("is-accent");
  }

  function applyStatusVisuals(data) {
    const tone = getStatusTone(data?.status);

    const statusText = byId("status_text");
    const summaryText = byId("summary_text");
    const phaseText = byId("current_phase_text");

    applyTone(statusText?.closest(".kpi"), tone);
    applyTone(summaryText, tone);
    applyTone(phaseText, tone);
  }

  async function getJson(url) {
    const response = await fetch(url, {
      method: "GET",
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      let message = `Falha HTTP ${response.status}`;
      try {
        const payload = await response.json();
        if (payload?.message) message = String(payload.message);
      } catch (_error) {}
      throw new Error(message);
    }

    return await response.json();
  }

  async function getJsonWithTimeout(url, timeoutMs = 30000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method: "GET",
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) {
        let message = `Falha HTTP ${response.status}`;
        try {
          const payload = await response.json();
          if (payload?.message) message = String(payload.message);
        } catch (_error) {}
        throw new Error(message);
      }
      return await response.json();
    } catch (error) {
      if (error?.name === "AbortError") {
        const seconds = Math.max(1, Math.round(timeoutMs / 1000));
        throw new Error(`A consulta excedeu ${seconds} segundos. Verifique o WooCommerce e clique em Tentar novamente.`);
      }
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(payload || {}),
    });

    let data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }

    if (!response.ok || data?.ok === false) {
      const message =
        normalizeText(data?.message) ||
        normalizeText(data?.error) ||
        `Falha HTTP ${response.status}`;
      const error = new Error(message);
      error.responseData = data;
      throw error;
    }

    return data;
  }

  function notify(message) {
    window.alert(String(message || "OK"));
  }

  function readSelectedCategoryUrls() {
    return uniqueStrings(
      qsa(".scope-category-checkbox:checked").map((node) => node.value)
    );
  }

  function getCurrentSelectedCategorySet() {
    return new Set(readSelectedCategoryUrls());
  }

  function readRunOptionsFromForm() {
    return {
      verify_mode: normalizeText(byId("verify_mode")?.value, "complete").toLowerCase(),
      scope_mode: normalizeText(byId("scope_mode")?.value, "all").toLowerCase(),
      scope_start: Math.max(1, toInt(byId("scope_start")?.value, 1)),
      scope_end: Math.max(0, toInt(byId("scope_end")?.value, 0)),
      scope_match_text: String(byId("scope_match_text")?.value || ""),
      save_every_items: Math.max(1, toInt(byId("save_every_items")?.value, 10)),
      save_every_minutes: Math.max(1, toInt(byId("save_every_minutes")?.value, 10)),
      selected_categories: readSelectedCategoryUrls(),
    };
  }

  function writeRunOptionsToForm(runOptions) {
    const data = runOptions || {};

    withInternalWrite(() => {
      setValue("verify_mode", normalizeText(data.verify_mode, "complete"));
      setValue("scope_mode", normalizeText(data.scope_mode, "all"));
      setValue("scope_start", Math.max(1, toInt(data.scope_start, 1)));
      setValue("scope_end", Math.max(0, toInt(data.scope_end, 0)));
      setValue("scope_match_text", data.scope_match_text ?? "");
      setValue("save_every_items", Math.max(1, toInt(data.save_every_items, 10)));
      setValue("save_every_minutes", Math.max(1, toInt(data.save_every_minutes, 10)));
      toggleScopeFields();
    });
  }

  function readContextFromFormIfPresent() {
    const siteNode = byId("site_key");
    const itemTypeNode = byId("item_type_key");
    const accountNode = byId("account_key");
    const slotNode = byId("slot_name");

    if (!siteNode && !itemTypeNode && !accountNode && !slotNode) {
      return {};
    }

    return {
      site_key: normalizeText(siteNode?.value),
      item_type_key: normalizeText(itemTypeNode?.value),
      account_key: normalizeText(accountNode?.value),
      slot_name: normalizeText(slotNode?.value),
    };
  }

  function buildRunRequestPayload(extraPayload = {}) {
    const runOptions = readRunOptionsFromForm();
    const contextPayload = readContextFromFormIfPresent();

    return Object.assign(
      {
        run_options: runOptions,
        clear_logs: true,
      },
      contextPayload,
      extraPayload || {}
    );
  }

  function renderContextData(data) {
    const site = data?.site_key || data?.context?.site_key || "-";
    const itemType = data?.item_type_key || data?.context?.item_type_key || "-";
    const account = data?.account_key || data?.context?.account_key || "-";
    const slot = data?.current_slot || data?.slot_name || data?.context?.slot_name || "-";
    const slotLabel = catalogDisplayName(slot, "-");

    setText("ctx_site", site);
    setText("ctx_item_type", itemType);
    setText("ctx_account", account);
    setText("ctx_slot", slotLabel);

    setText("head_slot_badge", `Catálogo: ${slotLabel}`, "Catálogo: -");
    setText("head_site_badge", `Site: ${site}`, "Site: -");
    setText("head_item_type_badge", `Tipo: ${itemType}`, "Tipo: -");
    setText("head_account_badge", `Conta: ${account}`, "Conta: -");

    renderHeadStatusBadge(data);
    renderStickyRunsSwitcher(data);
  }

  function refreshSelectedCategoriesCounter() {
    const selectedCount = readSelectedCategoryUrls().length;
    setText("selected_categories_count", `${selectedCount} selecionadas`, "0 selecionadas");
  }

  function renderCategories(data) {
    const categories = Array.isArray(data?.available_categories)
      ? data.available_categories
      : [];

    setText("available_categories_count", String(categories.length), "0");

    const wrap = byId("selected_categories_list");
    if (!wrap) {
      refreshSelectedCategoriesCounter();
      return;
    }

    const selectedSet = UI.formDirty
      ? getCurrentSelectedCategorySet()
      : new Set(
          uniqueStrings(
            Array.isArray(data?.selected_categories) ? data.selected_categories : []
          )
        );

    if (!categories.length) {
      wrap.innerHTML = '<div class="badge">Nenhuma categoria disponível ainda.</div>';
      refreshSelectedCategoriesCounter();
      return;
    }

    const running = !!data?.running;

    wrap.innerHTML = categories
      .map((category, index) => {
        const url = ensureTrailingSlash(category?.url || category?.categoria_url || "");
        const name = normalizeText(
          category?.nome || category?.categoria_nome || url || `Categoria ${index + 1}`
        );
        const total = Math.max(
          0,
          toInt(category?.total ?? category?.total_esperado ?? 0, 0)
        );
        const checked = selectedSet.has(url) ? "checked" : "";
        const disabled = running ? "disabled" : "";

        return `
          <label class="checkbox-item">
            <input
              type="checkbox"
              class="scope-category-checkbox"
              value="${escapeHtml(url)}"
              ${checked}
              ${disabled}
            >
            <span class="checkbox-text">
              <span>${escapeHtml(`${index + 1}. ${name}`)}</span>
              <span class="checkbox-meta">${escapeHtml(`${total} itens • ${url}`)}</span>
            </span>
          </label>
        `;
      })
      .join("");

    refreshSelectedCategoriesCounter();
  }

  function renderSlots(data) {
  const select = byId("slot_select");
  const slots = Array.isArray(data?.slots) ? data.slots : [];
  const currentSlot = normalizeText(data?.current_slot || data?.slot_name);
  const defaultSlot = normalizeText(data?.default_slot);
  const running = !!data?.running;

  if (select) {
    const previousValue = normalizeText(select.value);
    const pendingValue = normalizeText(UI.pendingSlotValue);

    select.innerHTML = slots
      .map((slot) => {
        const name = normalizeText(slot?.name);
        const displayName = catalogDisplayName(name);
        const label = slot?.is_default ? `${displayName} ⭐` : displayName;
        return `<option value="${escapeHtml(name)}">${escapeHtml(label)}</option>`;
      })
      .join("");
          const hasSlot = (value) =>
      !!value && slots.some((slot) => normalizeText(slot?.name) === value);

    if (UI.slotSelectionDirty && pendingValue && hasSlot(pendingValue)) {
      withInternalWrite(() => {
        select.value = pendingValue;
      });
    } else if (currentSlot && hasSlot(currentSlot)) {
      withInternalWrite(() => {
        select.value = currentSlot;
      });
      UI.pendingSlotValue = currentSlot;
      UI.slotSelectionDirty = false;
    } else if (previousValue && hasSlot(previousValue)) {
      withInternalWrite(() => {
        select.value = previousValue;
      });
      UI.pendingSlotValue = previousValue;
    } else if (slots.length) {
      const firstValue = normalizeText(slots[0]?.name);
      withInternalWrite(() => {
        select.value = firstValue;
      });
      UI.pendingSlotValue = firstValue;
      UI.slotSelectionDirty = false;
    } else {
      UI.pendingSlotValue = "";
      UI.slotSelectionDirty = false;
    }

    if (UI.slotSelectionDirty && !hasSlot(UI.pendingSlotValue)) {
      UI.slotSelectionDirty = false;
      UI.pendingSlotValue = normalizeText(select.value);
    }

    select.disabled = running;
  }

  const selectedSlot = normalizeText(
    UI.slotSelectionDirty ? UI.pendingSlotValue : (select?.value || currentSlot)
  );
  const selectedIsDefault = !!selectedSlot && selectedSlot === defaultSlot;

  setDisabled("new_slot_name", running);
  setDisabled("slot_clear_btn", running);
  setDisabled("slot_delete_btn", running || selectedIsDefault);

  withInternalWrite(() => {
    const defaultButton = byId("slot_default_btn");
    if (defaultButton) {
      defaultButton.disabled = running || selectedIsDefault;
      defaultButton.textContent = selectedIsDefault ? "⭐ Default atual" : "⭐ Default";
    }
  });

  setText("slot_current_label", catalogDisplayName(currentSlot, "-"), "-");
  setText("slot_default_label", catalogDisplayName(defaultSlot, "-"), "-");
}

  function renderKpis(data) {
    setText("status_text", data?.status || "Pronto", "Pronto");
    setText("summary_text", data?.summary || "-", "-");
    setText("current_phase_text", data?.current_phase || "-", "-");
    setText("current_category_text", data?.current_category || "-", "-");
    setText("current_item_text", data?.current_item || "-", "-");
    setText("timer_text", data?.timer_text || "0:00:00", "0:00:00");

    setText("saved_count_text", data?.saved_count ?? 0, "0");
    setText("pending_count_text", data?.pending_count ?? 0, "0");
    setText("queue_detected_count_text", data?.queue_detected_count ?? 0, "0");
    setText("new_items_added_text", data?.new_items_added ?? 0, "0");
    setText("items_updated_text", data?.items_updated ?? 0, "0");
    setText("items_unchanged_text", data?.items_unchanged ?? 0, "0");
    setText("new_links_detected_text", data?.new_links_detected ?? 0, "0");
    setText("existing_links_detected_text", data?.existing_links_detected ?? 0, "0");
    setText("reused_categories_text", data?.reused_categories ?? 0, "0");

    const reusedCategories = Math.max(0, toInt(data?.reused_categories, 0));
    const refetchedCategories = Math.max(0, toInt(data?.refetched_categories, 0));
    const totalAvailableCategories = Array.isArray(data?.available_categories)
      ? data.available_categories.length
      : 0;
    const doneCategories = reusedCategories + refetchedCategories;

    setText(
      "refetched_categories_text",
      `${doneCategories}/${totalAvailableCategories}`,
      "0/0"
    );

    const resumeIndex = Math.max(0, toInt(data?.resume_queue_index, 0));
    const resumeTotal = Math.max(0, toInt(data?.resume_queue_total, 0));
    setText("resume_queue_text", `${resumeIndex}/${resumeTotal}`, "0/0");

    setText("updated_at_text", data?.updated_at || "-", "-");
    setText("run_started_at_text", data?.run_started_at || "-", "-");
    setText("run_finished_at_text", data?.run_finished_at || "-", "-");

   const running = !!data?.running;
const paused = !!data?.paused;
const canContinue = !!data?.can_continue;
const scopeModeCurrent = normalizeText(
  byId("scope_mode")?.value || data?.scope_mode,
    "all"
).toLowerCase();
const canEditSelected = scopeModeCurrent === "selected" && !running && !UI.actionInFlight;

setDisabled("run_primary_btn", running || UI.actionInFlight);
setDisabled("run_categories_btn", running || UI.actionInFlight);
setDisabled("run_links_btn", running || UI.actionInFlight);
setDisabled("run_review_btn", running || UI.actionInFlight);
setDisabled("stop_btn", !running || UI.actionInFlight);
setDisabled("save_config_btn", UI.actionInFlight);

const pauseResumeBtn = byId("pause_resume_btn");
if (pauseResumeBtn) {
  pauseResumeBtn.style.display = "";
  pauseResumeBtn.disabled = !running || UI.actionInFlight;
  pauseResumeBtn.textContent = paused ? "▶️ Retomar" : "⏸ Pausar";
  pauseResumeBtn.className = paused ? "btn-success" : "btn-secondary";
  pauseResumeBtn.onclick = () => togglePauseResume();

  const pauseHelp = document.querySelector(".pause-help");
  if (pauseHelp) {
    pauseHelp.dataset.tooltip = paused
      ? pauseHelp.dataset.resumeTooltip
      : pauseHelp.dataset.pauseTooltip;
  }
}

const continueBtn = byId("continue_btn");
if (continueBtn) {
  continueBtn.style.display = canContinue && !running ? "" : "none";
  continueBtn.disabled = running || !canContinue || UI.actionInFlight;

  const resumeLabel = normalizeText(data?.resume_run_mode_label);
  continueBtn.title = canContinue && resumeLabel
    ? `Continuar fila salva do fluxo: ${resumeLabel}`
    : "Continuar fila salva";
}

setDisabled("site_key", running || UI.actionInFlight);
setDisabled("item_type_key", running || UI.actionInFlight);
setDisabled("account_key", running || UI.actionInFlight);
setDisabled("apply_context_btn", running || UI.actionInFlight);
setDisabled("refresh_context_btn", UI.actionInFlight);

setDisabled("select_all_categories_btn", !canEditSelected);
setDisabled("invert_selected_categories_btn", !canEditSelected);
setDisabled("clear_selected_categories_btn", !canEditSelected);

const runPrimaryBtn = byId("run_primary_btn");
if (runPrimaryBtn) {
  runPrimaryBtn.textContent = getButtonLabelForPrimary(data);
}

renderContextData(data);
applyStatusVisuals(data);
  }

  function renderLogs(logs) {
    const node = byId("logs");
    if (!node) return;

    const text = Array.isArray(logs) ? logs.join("\n") : String(logs || "");
    if (text === UI.lastLogsText) return;

    const shouldStickToBottom =
      node.scrollTop + node.clientHeight >= node.scrollHeight - 60;

    node.textContent = text;
    UI.lastLogsText = text;

    if (shouldStickToBottom) {
      node.scrollTop = node.scrollHeight;
    }
  }

  function ensureRunsManagerUi() {
  if (!isManagerMode()) return null;

  let card = byId("runs_manager_card");
  if (card) return card;

  const wrap = qs(".wrap");
  if (!wrap) return null;

  const pageHead = qs(".page-head", wrap);

  const storeExpanded = (expanded) => {
    try {
      window.localStorage.setItem("runs_manager_expanded", expanded ? "1" : "0");
    } catch (_error) {}
  };

  const applyExpandedState = (expanded) => {
    const toggleBtn = byId("runs_manager_toggle_btn");
    const content = byId("runs_manager_content");
    const chevron = byId("runs_manager_toggle_chevron");

    if (!toggleBtn || !content || !chevron) return;

    toggleBtn.setAttribute("aria-expanded", expanded ? "true" : "false");
    chevron.style.transform = expanded ? "rotate(180deg)" : "rotate(0deg)";
    content.style.maxHeight = expanded ? "4000px" : "0px";
    content.style.opacity = expanded ? "1" : "0";
    content.style.transform = expanded ? "translateY(0)" : "translateY(-8px)";
    content.style.marginTop = expanded ? "14px" : "0px";

    storeExpanded(expanded);
  };

  card = document.createElement("div");
  card.id = "runs_manager_card";
  card.className = "card runs-manager-card collect-runs-accordion";
  card.innerHTML = `
      <button
        id="runs_manager_toggle_btn"
        type="button"
        class="btn-secondary runs-manager-header"
        aria-expanded="false"
        style="
          width:100%;
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:14px;
          text-align:left;
          padding:16px 18px;
        "
      >
        <span style="display:flex; flex-direction:column; gap:4px;">
          <span style="font-size:22px; font-weight:700; line-height:1;">Execuções Simultâneas</span>
          <span class="small" style="margin:0;">Encadeamento simultâneo entre catálogos e contextos</span>
        </span>

        <span
          id="runs_manager_toggle_chevron"
          style="
            font-size:20px;
            line-height:1;
            transition:transform .25s ease;
            display:inline-flex;
            align-items:center;
            justify-content:center;
          "
        >⌄</span>
      </button>

      <div
        id="runs_manager_content"
        style="
          overflow:hidden;
          max-height:0;
          opacity:0;
          transform:translateY(-8px);
          margin-top:0;
          transition:max-height .35s ease, opacity .25s ease, transform .25s ease, margin-top .25s ease;
        "
      >
        <div class="small" style="margin-bottom:12px;">
          Cada execução é isolada. Você pode rodar mais de uma ao mesmo tempo, desde que não use a mesma conta.
        </div>

        <div class="row" style="align-items:center; justify-content:space-between; margin-bottom:12px; gap:12px;">
          <div class="row runs-tabs-wrap" id="runs_tabs_wrap" role="tablist" aria-label="Execuções simultâneas" style="flex:1 1 auto;"></div>
          <div class="row" style="flex:0 0 auto;">
            <span class="badge" id="runs_total_badge">0 execuções</span>
            <button class="btn-secondary" id="refresh_runs_btn" type="button">🔄 Atualizar execuções</button>
          </div>
        </div>

        <div class="form-grid">
          <div class="field">
            <label for="run_create_site_key">Nova execução · Site</label>
            <select id="run_create_site_key"></select>
          </div>
          <div class="field">
            <label for="run_create_item_type_key">Nova execução · Tipo</label>
            <select id="run_create_item_type_key"></select>
          </div>
          <div class="field">
            <label for="run_create_account_key">Nova execução · Conta</label>
            <select id="run_create_account_key"></select>
          </div>
          <div class="field">
            <label for="run_create_slot_name">Nova execução · Catálogo</label>
            <select id="run_create_slot_name"></select>
          </div>
        </div>

        <div class="row runs-manager-create-actions" style="justify-content:flex-end; margin-top:14px;">
          <button class="btn-secondary" id="create_run_btn" type="button">➕ Criar execução e abrir</button>
          <button class="btn-success" id="create_and_start_run_btn" type="button">▶️ Iniciar execução simultânea</button>
        </div>
      </div>
    `;

  const runsSectionWrap = byId("runs_section_wrap");

  if (runsSectionWrap) {
    runsSectionWrap.innerHTML = "";
    runsSectionWrap.appendChild(card);
  } else if (pageHead && pageHead.parentNode === wrap) {
    wrap.insertBefore(card, pageHead.nextSibling);
  } else {
    wrap.insertBefore(card, wrap.firstChild);
  }

  const toggleBtn = byId("runs_manager_toggle_btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const expanded = toggleBtn.getAttribute("aria-expanded") === "true";
      applyExpandedState(!expanded);
    });
  }

  const refreshRunsBtn = byId("refresh_runs_btn");
  if (refreshRunsBtn) {
    refreshRunsBtn.addEventListener("click", () => {
      refreshRunsList({ force: true });
    });
  }

  const createRunBtn = byId("create_run_btn");
  if (createRunBtn) {
    createRunBtn.addEventListener("click", () => {
      createRunAndOpen();
    });
  }
  const createAndStartRunBtn = byId("create_and_start_run_btn");
  if (createAndStartRunBtn) {
    createAndStartRunBtn.addEventListener("click", createAndStartRun);
  }

  const createFieldIds = [
    "run_create_site_key",
    "run_create_item_type_key",
    "run_create_account_key",
    "run_create_slot_name",
  ];

  createFieldIds.forEach((id) => {
    const node = byId(id);
    if (!node) return;

    node.addEventListener("change", () => {
      if (id === "run_create_site_key" || id === "run_create_item_type_key") {
        updateRunCreateSelectors({
          site_key: byId("run_create_site_key")?.value || "",
          item_type_key: byId("run_create_item_type_key")?.value || "",
          account_key: byId("run_create_account_key")?.value || "",
        });
      }
    });
  });

  requestAnimationFrame(() => {
    let expanded = false;
    try {
      expanded = window.localStorage.getItem("runs_manager_expanded") === "1";
    } catch (_error) {}
    applyExpandedState(expanded);
  });

  return card;
}

  function populateRunCreateSlots(selectedValue) {
    const select = byId("run_create_slot_name");
    if (!select) return;

    const stateData = UI.lastStatePayload?.data || {};
    const slots = Array.isArray(stateData?.slots) ? stateData.slots : [];
    const selectedSlot = normalizeText(
      selectedValue || select.value || stateData?.current_slot || stateData?.slot_name || BOOT?.context?.slot_name || ""
    );

    populateSelect("run_create_slot_name", slots, {
      valueKey: "name",
      labelBuilder: (slot) => {
        const name = catalogDisplayName(slot?.name);
        return slot?.is_default ? `${name} ⭐` : name;
      },
      selectedValue: selectedSlot,
    });
  }

  function updateRunCreateSelectors(seed = {}) {
    if (!isManagerMode()) return;

    ensureRunsManagerUi();

    const registry = buildContextRegistry();
    const siteSelect = byId("run_create_site_key");
    const itemTypeSelect = byId("run_create_item_type_key");
    const accountSelect = byId("run_create_account_key");
        if (!siteSelect || !itemTypeSelect || !accountSelect) return;

    const stateData = UI.lastStatePayload?.data || {};
    const mergedSeed = Object.assign({}, BOOT?.context || {}, stateData || {}, seed || {});

    const currentSiteKey = normalizeText(
      siteSelect.value || mergedSeed.site_key || registry.sites?.[0]?.key || ""
    );

    populateSelect("run_create_site_key", registry.sites, {
      valueKey: "key",
      labelBuilder: (site) => site?.label || site?.key || "",
      selectedValue: currentSiteKey,
    });

    const selectedSiteKey = normalizeText(siteSelect.value || currentSiteKey);
    const selectedSite = registry.sites.find((site) => normalizeText(site?.key) === selectedSiteKey);

    const supportedItemTypes = new Set(
      Array.isArray(selectedSite?.supported_item_types) ? selectedSite.supported_item_types : []
    );

    const itemTypes = registry.itemTypes.filter((itemType) => {
      if (!supportedItemTypes.size) return true;
      return supportedItemTypes.has(itemType?.key);
    });

    const currentItemTypeKey = normalizeText(
      itemTypeSelect.value || mergedSeed.item_type_key || itemTypes?.[0]?.key || ""
    );

    populateSelect("run_create_item_type_key", itemTypes, {
      valueKey: "key",
      labelBuilder: (itemType) => itemType?.label_plural || itemType?.key || "",
      selectedValue: currentItemTypeKey,
    });

    const selectedItemTypeKey = normalizeText(itemTypeSelect.value || currentItemTypeKey);

    const accounts = registry.accounts.filter((account) => {
      const supportsSite = Array.isArray(account?.supported_sites)
        ? account.supported_sites.includes(selectedSiteKey)
        : true;
      const supportsItemType = Array.isArray(account?.supported_item_types)
        ? account.supported_item_types.includes(selectedItemTypeKey)
        : true;
      return supportsSite && supportsItemType;
    });

    const currentAccountKey = normalizeText(
      accountSelect.value || mergedSeed.account_key || accounts?.[0]?.key || ""
    );

    populateSelect("run_create_account_key", accounts, {
      valueKey: "key",
      labelBuilder: (account) => account?.label || account?.key || "",
      selectedValue: currentAccountKey,
    });

    populateRunCreateSlots();
  }

  function renderRunsTabs() {
    if (!isManagerMode()) return;

    const wrap = byId("runs_tabs_wrap");
    const badge = byId("runs_total_badge");
    const refreshBtn = byId("refresh_runs_btn");
    const createBtn = byId("create_run_btn");
    const createAndStartBtn = byId("create_and_start_run_btn");

    if (!wrap) return;

    const runs = Array.isArray(UI.runs) ? UI.runs : [];
    const currentRunId = normalizeText(
      UI.currentRunId || BOOT?.run_id || UI.lastStatePayload?.data?.run_id || ""
    );

    if (badge) {
      const total = runs.length;
      badge.textContent = `${total} execução${total === 1 ? "" : "ões"}`;
    }

    if (refreshBtn) {
      refreshBtn.disabled = !!UI.runsRefreshInFlight || !!UI.actionInFlight;
    }

    if (createBtn) {
      createBtn.disabled = !!UI.actionInFlight;
    }
    if (createAndStartBtn) {
      createAndStartBtn.disabled = !!UI.actionInFlight;
    }

    if (!runs.length) {
      wrap.innerHTML = '<span class="badge">Nenhuma execução carregada.</span>';
      return;
    }

    wrap.innerHTML = runs
      .map((run) => {
        const runId = normalizeText(run?.run_id);
        const active = isSameRunId(runId, currentRunId);
        const running = !!run?.running;
        const paused = !!run?.paused;
        const title = getRunTitle(run);
        const subtitle = getRunSubtitle(run);
        const isPrimary = isSameRunId(runId, UI.primaryRunId);
        const canRemove = !isPrimary;

        const borderTone = active
          ? ""
          : running
            ? "box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.35);"
            : "";

        const stateEmoji = paused ? "⏸" : running ? "🟢" : "⚪";

        return `
          <div
            class="run-card-wrap"
            style="position:relative; flex:1 1 420px; min-width:320px;"
          >
            ${canRemove ? `
              <button
                type="button"
                class="btn-secondary run-remove-btn"
                data-run-id="${escapeHtml(runId)}"
                title="Remover execução"
                style="
                  position:absolute;
                  top:10px;
                  right:10px;
                  z-index:3;
                  width:32px;
                  height:32px;
                  min-width:32px;
                  padding:0;
                  border-radius:999px;
                  display:inline-flex;
                  align-items:center;
                  justify-content:center;
                  font-size:16px;
                  line-height:1;
                "
              >✕</button>
            ` : ""}

            <button
              type="button"
              class="${active ? "btn-primary" : "btn-secondary"} run-tab-btn"
              role="tab"
              aria-selected="${active}"
              data-run-id="${escapeHtml(runId)}"
              title="${escapeHtml(subtitle)}"
              style="
                justify-content:flex-start;
                align-items:flex-start;
                flex-direction:column;
                min-height:58px;
                width:100%;
                ${borderTone}
                ${canRemove ? "padding-right:52px;" : ""}
              "
            >
              <span>${escapeHtml(`${stateEmoji} ${title}${isPrimary ? " ★" : ""}`)}</span>
              <span style="font-size:12px; opacity:.82; font-weight:600;">${escapeHtml(subtitle)}</span>
            </button>
          </div>
        `;
      })
      .join("");

    qsa(".run-tab-btn", wrap).forEach((button) => {
      button.addEventListener("click", () => {
        const runId = normalizeText(button.getAttribute("data-run-id"));
        if (!runId || isSameRunId(runId, currentRunId)) return;
        window.location.href = getRunPanelPath(runId);
      });
    });

    qsa(".run-remove-btn", wrap).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();

        const runId = normalizeText(button.getAttribute("data-run-id"));
        if (!runId) return;

        removeRun(runId);
      });
    });

    renderStickyRunsSwitcher(UI.lastStatePayload?.data || {});
  }

  async function refreshRunsList(options = {}) {
    if (!isManagerMode()) return UI.runs;
    if (UI.runsRefreshInFlight && !options.force) return UI.runs;

    UI.runsRefreshInFlight = true;

    try {
      const payload = await getJson(UI.endpoints.runs);
      UI.runs = Array.isArray(payload?.runs) ? payload.runs : [];
      UI.primaryRunId = normalizeText(payload?.primary_run_id, UI.primaryRunId);
      syncCurrentRunIdWithRuns(UI.lastStatePayload?.data || {});
      renderRunsTabs();
      renderStickyRunsSwitcher(UI.lastStatePayload?.data || {});
      return UI.runs;
    } catch (error) {
      console.warn("[panel.js] Falha ao atualizar execuções:", error);
      return UI.runs;
    } finally {
      UI.runsRefreshInFlight = false;
      renderRunsTabs();
      renderStickyRunsSwitcher(UI.lastStatePayload?.data || {});
    }
  }

  function readRunCreatePayload() {
    const siteKey = normalizeText(byId("run_create_site_key")?.value);
    const itemTypeKey = normalizeText(byId("run_create_item_type_key")?.value);
    const accountKey = normalizeText(byId("run_create_account_key")?.value);
    const slotName = normalizeText(byId("run_create_slot_name")?.value);

    return {
      site_key: siteKey,
      item_type_key: itemTypeKey,
      account_key: accountKey,
      slot_name: slotName,
      load_summary: true,
    };
  }

  async function createRunAndOpen() {
    if (!isManagerMode()) return null;

    return runAction(async () => {
      const payload = readRunCreatePayload();
      if (!payload.site_key || !payload.item_type_key || !payload.account_key) {
        notify("Preencha site, tipo e conta para criar a nova execução.");
        return null;
      }

      const result = await postJson(UI.endpoints.runCreate, payload);
      UI.runs = Array.isArray(result?.runs) ? result.runs : UI.runs;
      renderRunsTabs();

      const targetUrl = normalizeText(result?.url || getRunPanelPath(result?.run_id));
      if (!targetUrl) {
        notify(result?.message || "Execução criada.");
        await refreshRunsList({ force: true });
        return result;
      }

      window.location.href = targetUrl;
      return result;
    });
  }

  async function createAndStartRun() {
    if (!isManagerMode()) return null;
    return runAction(async () => {
      const payload = readRunCreatePayload();
      if (!payload.site_key || !payload.item_type_key || !payload.account_key || !payload.slot_name) {
        notify("Preencha site, tipo, conta e catálogo para iniciar a execução simultânea.");
        return null;
      }
      const created = await postJson(UI.endpoints.runCreate, payload);
      const runId = normalizeText(created?.run_id);
      if (!runId) throw new Error("A nova execução não retornou um identificador válido.");
      const startEndpoint = `${normalizeText(UI.endpoints.runPanelPrefix, "/run/")}${encodeURIComponent(runId)}/start`;
      await postJson(startEndpoint, {
        run_mode: "primary",
        run_options: readRunOptionsFromForm(),
        clear_logs: true,
      });
      await refreshRunsList({ force: true });
      notify("Execução simultânea criada e iniciada.");
      return created;
    });
  }

  async function removeRun(runId) {
    if (!isManagerMode()) return null;

    return runAction(async () => {
      const normalizedRunId = normalizeText(runId);
      if (!normalizedRunId) {
        notify("Execução inválida.");
        return null;
      }

      if (isSameRunId(normalizedRunId, UI.primaryRunId)) {
        notify("A execução principal não pode ser removida.");
        return null;
      }

      const confirmed = window.confirm(
        `Deseja remover a execução "${normalizedRunId}"?`
      );
      if (!confirmed) return null;

      const removingCurrentRun = isSameRunId(normalizedRunId, UI.currentRunId);

      const result = await postJson(UI.endpoints.runDelete, {
        run_id: normalizedRunId,
      });

      UI.runs = Array.isArray(result?.runs) ? result.runs : UI.runs;
      UI.primaryRunId = normalizeText(result?.primary_run_id, UI.primaryRunId);
      syncCurrentRunIdWithRuns(UI.lastStatePayload?.data || {});

      notify(result?.message || "Execução removida.");

      if (removingCurrentRun) {
        const targetUrl = getRunPanelPath(result?.primary_run_id || UI.primaryRunId);
        window.location.href = targetUrl || "/";
        return result;
      }

      renderRunsTabs();
      renderStickyRunsSwitcher(UI.lastStatePayload?.data || {});
      await refreshRunsList({ force: true });
      return result;
    });
  }

  function renderStatePayload(payload, options = {}) {
    const forceConfigWrite = !!options.forceConfigWrite;
    const statePayload = payload && typeof payload === "object" ? payload : {};
    const data = statePayload.data && typeof statePayload.data === "object"
      ? statePayload.data
      : {};
    const logs = Array.isArray(statePayload.logs) ? statePayload.logs : [];

    UI.lastStatePayload = statePayload;
    UI.currentRunId = normalizeText(data?.run_id || UI.currentRunId || BOOT?.run_id || "");
    UI.primaryRunId = normalizeText(BOOT?.primary_run_id || UI.primaryRunId || "");

    if (isManagerMode()) {
      ensureRunsManagerUi();
      updateRunCreateSelectors(data);
      renderRunsTabs();
    }

    renderKpis(data);
    renderSlots(data);
    renderCategories(data);
    renderLogs(logs);

    if (!UI.formDirty || forceConfigWrite) {
      writeRunOptionsToForm(data);
      updateContextSelectorsFromState(data);
      clearFormDirty();
      refreshSelectedCategoriesCounter();
    } else {
      toggleScopeFields();
      refreshSelectedCategoriesCounter();
    }

    updateDocumentTitle(data);
  }

  function toggleScopeFields() {
    const mode = normalizeText(byId("scope_mode")?.value, "all").toLowerCase();
    const running = !!(UI.lastStatePayload?.data?.running);
    const canEditSelected = mode === "selected" && !running && !UI.actionInFlight;

    showElement("field_range_start", mode === "range");
    showElement("field_range_end", mode === "range");
    showElement("field_match", mode === "match");
    showElement("field_selected_categories", mode === "selected");

    setDisabled("select_all_categories_btn", !canEditSelected);
    setDisabled("invert_selected_categories_btn", !canEditSelected);
    setDisabled("clear_selected_categories_btn", !canEditSelected);

    refreshSelectedCategoriesCounter();
  }

  function extractBootSettings() {
    return BOOT?.settings && typeof BOOT.settings === "object" ? BOOT.settings : {};
  }

  function populateSelect(selectId, items, options = {}) {
    const select = byId(selectId);
    if (!select) return;

    const {
      valueKey = "key",
      labelBuilder = (item) => item?.label || item?.key || "",
      selectedValue = "",
    } = options;

    const normalizedItems = Array.isArray(items) ? items : [];
    const currentValue = selectedValue || normalizeText(select.value);

    withInternalWrite(() => {
      select.innerHTML = normalizedItems
        .map((item) => {
          const value = normalizeText(item?.[valueKey]);
          const label = normalizeText(labelBuilder(item));
          return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
        })
        .join("");

      if (currentValue) {
        select.value = currentValue;
      }
    });
  }

  function buildContextRegistry() {
    const settings = extractBootSettings();

    return {
      sites: Array.isArray(settings.sites) ? settings.sites : [],
      itemTypes: Array.isArray(settings.item_types) ? settings.item_types : [],
      accounts: Array.isArray(settings.accounts) ? settings.accounts : [],
    };
  }

  function updateContextSelectorsFromState(data) {
    const siteSelect = byId("site_key");
    const itemTypeSelect = byId("item_type_key");
    const accountSelect = byId("account_key");
        if (!siteSelect && !itemTypeSelect && !accountSelect) return;

    const registry = buildContextRegistry();

    const currentSiteKey = normalizeText(
      UI.formDirty ? siteSelect?.value : data?.site_key,
      BOOT?.context?.site_key || ""
    );
    const currentItemTypeKey = normalizeText(
      UI.formDirty ? itemTypeSelect?.value : data?.item_type_key,
      BOOT?.context?.item_type_key || ""
    );
    const currentAccountKey = normalizeText(
      UI.formDirty ? accountSelect?.value : data?.account_key,
      BOOT?.context?.account_key || ""
    );

    if (siteSelect) {
      populateSelect("site_key", registry.sites, {
        valueKey: "key",
        labelBuilder: (site) => site?.label || site?.key || "",
        selectedValue: currentSiteKey,
      });
    }

    if (itemTypeSelect) {
      const site = registry.sites.find((item) => item?.key === currentSiteKey);
      const supported = new Set(Array.isArray(site?.supported_item_types) ? site.supported_item_types : []);
      const itemTypes = registry.itemTypes.filter((item) => {
        if (!supported.size) return true;
        return supported.has(item?.key);
      });
      const effectiveItemTypeKey = itemTypes.some((item) => item?.key === currentItemTypeKey)
        ? currentItemTypeKey
        : normalizeText(itemTypes[0]?.key);

      populateSelect("item_type_key", itemTypes, {
        valueKey: "key",
        labelBuilder: (itemType) => itemType?.label_plural || itemType?.key || "",
        selectedValue: effectiveItemTypeKey,
      });
    }

    if (accountSelect) {
      const effectiveItemTypeKey = normalizeText(itemTypeSelect?.value || currentItemTypeKey);
      const accounts = registry.accounts.filter((account) => {
        const supportsSite = Array.isArray(account?.supported_sites)
          ? account.supported_sites.includes(currentSiteKey)
          : true;
        const supportsItemType = Array.isArray(account?.supported_item_types)
          ? account.supported_item_types.includes(effectiveItemTypeKey)
          : true;
        return supportsSite && supportsItemType;
      });

      populateSelect("account_key", accounts, {
        valueKey: "key",
        labelBuilder: (account) => account?.label || account?.key || "",
        selectedValue: currentAccountKey,
      });
    }

    if (byId("slot_name")) {
      withInternalWrite(() => {
        setValue("slot_name", data?.current_slot || data?.slot_name || "");
      });
    }
  }

  function updateDocumentTitle(data) {
    const currentTitle = normalizeText(BOOT?.title, document.title || "PT Script");
    const site = normalizeText(data?.site_key);
    const itemType = normalizeText(data?.item_type_key);
    const slot = catalogDisplayName(data?.current_slot || data?.slot_name);

    const suffixParts = [site, itemType, slot].filter(Boolean);
    document.title = suffixParts.length
      ? `${currentTitle} • ${suffixParts.join(" • ")}`
      : currentTitle;
  }

  async function loadState(options = {}) {
    if (UI.pollInFlight) return UI.lastStatePayload;
    UI.pollInFlight = true;

    try {
      const payload = await getJson(UI.endpoints.state);
      UI.consecutivePollErrors = 0;
      renderStatePayload(payload, { forceConfigWrite: !!options.forceConfigWrite });

      if (isManagerMode()) {
        refreshRunsList({ force: !!options.forceRunsRefresh });
      }

      return payload;
    } catch (error) {
      UI.consecutivePollErrors += 1;
      if (UI.consecutivePollErrors <= 2) {
        console.warn("[panel.js] Falha ao carregar estado:", error);
      }
      return UI.lastStatePayload;
    } finally {
      UI.pollInFlight = false;
    }
      }

  async function runAction(action) {
    if (UI.actionInFlight) return null;
    UI.actionInFlight = true;

    try {
      const result = await action();
      return result;
    } finally {
      UI.actionInFlight = false;
      const latest = UI.lastStatePayload?.data || {};
      renderKpis(latest);
      renderSlots(latest);
    }
  }

  async function saveConfig() {
    return runAction(async () => {
      const payload = readRunOptionsFromForm();
      const result = await postJson(UI.endpoints.config, payload);
      clearFormDirty();
      notify(result?.message || "Configuração salva.");
      await loadState({ forceConfigWrite: true });
      closeConfigModal();
      return result;
    });
  }

  async function startWithMode(runMode, extraPayload = {}) {
    return runAction(async () => {
      const payload = buildRunRequestPayload(
        Object.assign({}, extraPayload, runMode ? { run_mode: runMode } : {})
      );
      const result = await postJson(UI.endpoints.start, payload);

      if (result?.state && typeof result.state === "object") {
        renderStatePayload(result.state, { forceConfigWrite: false });
      }

      notify(result?.message || "Processo iniciado.");
      await loadState();
      return result;
    });
  }

  async function runPrimary() {
    return startWithMode("primary");
  }



  async function runMode(mode) {
    const normalizedMode = normalizeText(mode).toLowerCase();
    if (!normalizedMode) return null;

    return runAction(async () => {
      const payload = buildRunRequestPayload();
      const result = await postJson(`${UI.endpoints.runPrefix}${normalizedMode}`, payload);

      if (result?.state && typeof result.state === "object") {
        renderStatePayload(result.state, { forceConfigWrite: false });
      }

      notify(result?.message || "Processo iniciado.");
      await loadState();
      return result;
    });
  }

  async function continueRun() {
    return runAction(async () => {
      const payload = buildRunRequestPayload({ resume: true });
      const result = await postJson(UI.endpoints.continue, payload);

      if (result?.state && typeof result.state === "object") {
        renderStatePayload(result.state, { forceConfigWrite: false });
      }

      notify(result?.message || "Continuação iniciada.");
      await loadState();
      return result;
    });
  }

  async function togglePauseResume() {
    const paused = !!(UI.lastStatePayload?.data?.paused);
    return postAction(paused ? "resume" : "pause");
  }

  async function postAction(kind) {
    const normalizedKind = String(kind || "").toLowerCase();

    const map = {
      pause: UI.endpoints.pause,
      resume: UI.endpoints.resume,
      stop: UI.endpoints.stop,
    };

    const url = map[normalizedKind];
    if (!url) return null;

    if (normalizedKind === "stop") {
            const confirmed = window.confirm(
        "Deseja realmente parar o processo atual?"
      );
      if (!confirmed) return null;
    }

    return runAction(async () => {
      const result = await postJson(url, {});
      if (result?.state && typeof result.state === "object") {
        renderStatePayload(result.state, { forceConfigWrite: false });
      }
      notify(result?.message || "Ação executada.");
      await loadState();
      return result;
    });
  }

  async function createSlot() {
    return runAction(async () => {
      const slotName = normalizeText(byId("new_slot_name")?.value);
      if (!slotName) {
        notify("Digite um nome para o slot.");
        return null;
      }

      const result = await postJson(UI.endpoints.slotCreate, { slot_name: slotName });
      if (byId("new_slot_name")) byId("new_slot_name").value = "";
      clearFormDirty();
      notify(result?.message || "Slot criado.");
      await loadState({ forceConfigWrite: true });
      return result;
    });
  }

async function switchSlot() {
  return runAction(async () => {
    const activeRunOptions = readRunOptionsFromForm();
    const slotName = normalizeText(byId("slot_select")?.value);
    if (!slotName) {
      notify("Selecione um slot.");
      return null;
    }

    const result = await postJson(UI.endpoints.slotSwitch, { slot_name: slotName });
    await postJson(UI.endpoints.config, activeRunOptions);

    UI.pendingSlotValue = slotName;
    UI.slotSelectionDirty = false;

    clearFormDirty();
    notify(result?.message || "Slot carregado.");
    await loadState({ forceConfigWrite: true });
    return result;
  });
}

async function setDefaultSlotToggle() {

    return runAction(async () => {
      const slotName = normalizeText(byId("slot_select")?.value);
      if (!slotName) {
        notify("Selecione um slot.");
        await loadState({ forceConfigWrite: false });
        return null;
      }

      const result = await postJson(UI.endpoints.slotDefault, { slot_name: slotName });
      notify(result?.message || "Slot default alterado.");
      await loadState({ forceConfigWrite: false });
      return result;
    });
  }

  async function clearCurrentSlot() {
    return runAction(async () => {
      const slotName = normalizeText(byId("slot_select")?.value);
      if (!slotName) {
        notify("Selecione um slot.");
        return null;
      }

      const confirmed = window.confirm(
        `Deseja limpar todo o conteúdo do slot "${slotName}"?\n\nIsso vai apagar catálogo, progresso, caches, config e logs desse slot.`
      );
      if (!confirmed) return null;

      const result = await postJson(UI.endpoints.slotClear, { slot_name: slotName });

      UI.pendingSlotValue = slotName;
      UI.slotSelectionDirty = true;

      clearFormDirty();
      notify(result?.message || "Slot limpo.");
      await loadState({ forceConfigWrite: true });
      return result;
    });
  }



  async function removeCatalogoContext(slotName, siteKey, itemTypeKey, accountKey) {
    return runAction(async () => {
      const normalizedSlotName = normalizeText(slotName);
      const normalizedSiteKey = normalizeText(siteKey);
      const normalizedItemTypeKey = normalizeText(itemTypeKey);
      const normalizedAccountKey = normalizeText(accountKey);

      if (!normalizedSlotName || !normalizedSiteKey || !normalizedItemTypeKey || !normalizedAccountKey) {
        notify("Contexto inválido para remoção.");
        return null;
      }

      const confirmed = window.confirm(
        `Deseja remover do catálogo "${normalizedSlotName}" apenas este contexto?\n\nsite=${normalizedSiteKey}\ntipo=${normalizedItemTypeKey}\nconta=${normalizedAccountKey}\n\nIsso apaga catálogo, progresso, caches, config e logs somente desse contexto.`
      );
      if (!confirmed) return null;

      const result = await postJson(UI.endpoints.slotRemoveContext, {
        slot_name: normalizedSlotName,
        site_key: normalizedSiteKey,
        item_type_key: normalizedItemTypeKey,
        account_key: normalizedAccountKey,
      });

      UI.pendingSlotValue = normalizedSlotName;
      UI.slotSelectionDirty = true;

      clearFormDirty();
      notify(result?.message || "Contexto removido.");
      await loadState({ forceConfigWrite: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function deleteCatalogo(slotName) {
    return runAction(async () => {
      const normalizedSlotName = normalizeText(slotName);
      if (!normalizedSlotName) throw new Error("Catálogo inválido.");
      const confirmed = window.confirm(
        `Excluir o catÃ¡logo inteiro "${normalizedSlotName}" e todos os seus contextos?\n\nEsta aÃ§Ã£o nÃ£o pode ser desfeita.`
      );
      if (!confirmed) return null;
      const result = await postJson(UI.endpoints.slotDelete, { slot_name: normalizedSlotName });
      notify(result?.message || "Catálogo excluído.");
      await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function clearCatalogo(slotName) {
    return runAction(async () => {
      const normalizedSlotName = normalizeText(slotName);
      if (!normalizedSlotName) throw new Error("Catálogo inválido.");
      const confirmed = window.confirm(
        `Limpar todo o conteúdo do catálogo "${normalizedSlotName}"?\n\nO catálogo será mantido, mas seus dados, progresso, caches, configuração e logs serão apagados.`
      );
      if (!confirmed) return null;
      const result = await postJson(UI.endpoints.slotClear, { slot_name: normalizedSlotName });
      notify(result?.message || "Catálogo limpo.");
      await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function loadCatalogo(slotName) {
    return runAction(async () => {
      const activeRunOptions = readRunOptionsFromForm();
      const normalizedSlotName = normalizeText(slotName);
      if (!normalizedSlotName) throw new Error("Catálogo inválido.");
      const result = await postJson(UI.endpoints.slotSwitch, { slot_name: normalizedSlotName });
      await postJson(UI.endpoints.config, activeRunOptions);
      UI.pendingSlotValue = normalizedSlotName;
      UI.slotSelectionDirty = false;
      clearFormDirty();
      notify(result?.message || "Catálogo carregado.");
      await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function defineDefaultCatalogo(slotName) {
    return runAction(async () => {
      const normalizedSlotName = normalizeText(slotName);
      if (!normalizedSlotName) throw new Error("Catálogo inválido.");
      const confirmed = window.confirm(`Definir "${normalizedSlotName}" como catálogo default?`);
      if (!confirmed) return null;
      const result = await postJson(UI.endpoints.slotDefault, { slot_name: normalizedSlotName });
      notify(result?.message || "Catálogo default alterado.");
      await loadState({ forceConfigWrite: false, forceRunsRefresh: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function removeZeroCatalogoContexts() {
    const filterSlot = normalizeText(byId("catalogos_filter_slot")?.value);
    const zeroRows = UI.catalogRows.filter((row) => {
      const sameSlot = !filterSlot || normalizeText(row?.slot_name || row?.catalogo_nome) === filterSlot;
      return sameSlot && normalizeText(row?.site_key) && toInt(row?.items_count, 0) === 0;
    });
    if (!zeroRows.length) {
      notify("NÃ£o hÃ¡ contextos zerados para remover.");
      return null;
    }
    if (!window.confirm(`Remover ${zeroRows.length} contexto(s) com zero itens?\n\nContextos com um ou mais itens serÃ£o preservados.`)) return null;
    return runAction(async () => {
      const result = await postJson(UI.endpoints.slotRemoveZeroContexts, { slot_name: filterSlot });
      notify(result?.message || "Contextos zerados removidos.");
      await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
      await refreshCatalogos();
      return result;
    });
  }

  async function deleteCurrentSlot() {
    return runAction(async () => {
      const slotName = normalizeText(byId("slot_select")?.value);
      if (!slotName) {
        notify("Selecione um slot.");
        return null;
      }

      const confirmed = window.confirm(
        `Deseja apagar COMPLETAMENTE o slot "${slotName}"?\n\nIsso remove a pasta do slot e os logs vinculados a ele.`
      );
      if (!confirmed) return null;

      const result = await postJson(UI.endpoints.slotDelete, { slot_name: slotName });

      UI.pendingSlotValue = "";
      UI.slotSelectionDirty = false;

      clearFormDirty();
      notify(result?.message || "Slot apagado.");
      await loadState({ forceConfigWrite: true });
      return result;
    });
  }

  async function applyContext() {
    return runAction(async () => {
      const activeRunOptions = readRunOptionsFromForm();
      const payload = readContextFromFormIfPresent();
      const selectedSlot = normalizeText(byId("slot_select")?.value || UI.pendingSlotValue);
      if (selectedSlot) payload.slot_name = selectedSlot;
      if (!Object.keys(payload).length) {
        notify("Não há campos de contexto neste painel.");
        return null;
      }

      const result = await postJson(UI.endpoints.context, payload);
      await postJson(UI.endpoints.config, activeRunOptions);
      clearFormDirty();
      updateContextSelectorsFromState(payload);
      notify(result?.message || "Contexto alterado.");
      await loadState({ forceConfigWrite: true });
      return result;
    });
  }

  async function copyFullLog() {
    try {
      const payload = await getJson(UI.endpoints.logsFull);
      const text = String(payload?.text || "");

      if (!text.trim()) {
        notify("O log está vazio.");
        return;
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }

      notify("Log completo copiado.");
    } catch (_error) {
      notify("Não foi possível copiar o log.");
    }
  }

  function selectAllCategories() {
    withInternalWrite(() => {
      qsa(".scope-category-checkbox").forEach((checkbox) => {
        checkbox.checked = true;
      });
    });
    markFormDirty();
    refreshSelectedCategoriesCounter();
  }

  function clearSelectedCategories() {
    withInternalWrite(() => {
      qsa(".scope-category-checkbox").forEach((checkbox) => {
        checkbox.checked = false;
      });
    });
    markFormDirty();
    refreshSelectedCategoriesCounter();
  }

  function invertSelectedCategories() {
    withInternalWrite(() => {
      qsa(".scope-category-checkbox").forEach((checkbox) => {
        checkbox.checked = !checkbox.checked;
      });
    });
    markFormDirty();
    refreshSelectedCategoriesCounter();
  }

  function bindFormDirtyTracking() {
      const ids = [
    "verify_mode",
    "scope_mode",
    "scope_start",
    "scope_end",
    "scope_match_text",
    "save_every_items",
    "save_every_minutes",
    "site_key",
    "item_type_key",
    "account_key",
    "slot_name",
    "new_slot_name",
  ];

  ids.forEach((id) => {
    const node = byId(id);
    if (!node) return;

    node.addEventListener("input", () => {
      markFormDirty();
      if (id === "scope_mode") toggleScopeFields();
    });

    node.addEventListener("change", () => {
      markFormDirty();
      if (id === "scope_mode") toggleScopeFields();
    });
  });

  const slotSelect = byId("slot_select");
  if (slotSelect) {
    const markSlotSelection = () => {
      if (isInternalWrite()) return;
      UI.pendingSlotValue = normalizeText(slotSelect.value);
      UI.slotSelectionDirty = true;
    };

    slotSelect.addEventListener("input", markSlotSelection);
    slotSelect.addEventListener("change", markSlotSelection);
  }

  const listWrap = byId("selected_categories_list");
  if (listWrap) {
    listWrap.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      if (!target.classList.contains("scope-category-checkbox")) return;
      markFormDirty();
      refreshSelectedCategoriesCounter();
    });
  }
}

  function bindContextChaining() {
    const siteSelect = byId("site_key");
    const itemTypeSelect = byId("item_type_key");

    if (siteSelect) {
      siteSelect.addEventListener("change", () => {
        const stateData = UI.lastStatePayload?.data || {};
        updateContextSelectorsFromState({
          ...stateData,
          site_key: siteSelect.value,
          item_type_key: "",
          account_key: "",
        });
        markFormDirty();
      });
    }

    if (itemTypeSelect) {
      itemTypeSelect.addEventListener("change", () => {
        const stateData = UI.lastStatePayload?.data || {};
        updateContextSelectorsFromState({
          ...stateData,
          site_key: byId("site_key")?.value || stateData.site_key,
          item_type_key: itemTypeSelect.value,
          account_key: "",
        });
        markFormDirty();
      });
    }
  }

  function startPolling() {
    stopPolling();
    UI.pollTimer = window.setInterval(() => {
      if (document.hidden) return;
      loadState();
    }, UI.pollIntervalMs);
  }

  function stopPolling() {
    if (UI.pollTimer) {
      window.clearInterval(UI.pollTimer);
      UI.pollTimer = null;
    }
  }
    function bindVisibilityRefresh() {
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
        loadState();
      }
    });
  }

function exposeGlobals() {
  window.toggleScopeFields = toggleScopeFields;
  window.loadState = loadState;
  window.saveConfig = saveConfig;
  window.runPrimary = runPrimary;

  window.runMode = runMode;
  window.continueRun = continueRun;
  window.togglePauseResume = togglePauseResume;
  window.postAction = postAction;
  window.createSlot = createSlot;
  window.switchSlot = switchSlot;
  window.setDefaultSlotToggle = setDefaultSlotToggle;
  window.clearCurrentSlot = clearCurrentSlot;
  window.removeCatalogoContext = removeCatalogoContext;
  window.deleteCatalogo = deleteCatalogo;
  window.clearCatalogo = clearCatalogo;
  window.loadCatalogo = loadCatalogo;
  window.defineDefaultCatalogo = defineDefaultCatalogo;
  window.removeZeroCatalogoContexts = removeZeroCatalogoContexts;
  window.deleteCurrentSlot = deleteCurrentSlot;
  window.copyFullLog = copyFullLog;
  window.applyContext = applyContext;
  window.selectAllCategories = selectAllCategories;
  window.clearSelectedCategories = clearSelectedCategories;
  window.invertSelectedCategories = invertSelectedCategories;
  window.createRunAndOpen = createRunAndOpen;
  window.removeRun = removeRun;
  window.refreshRunsList = refreshRunsList;
  window.refreshCatalogos = refreshCatalogos;
  window.openCatalogRenameModal = openCatalogRenameModal;
  window.showCatalogoContexts = showCatalogoContexts;
  window.refreshFila = refreshFila;
  window.addFilaRule = addFilaRule;
  window.saveFila = saveFila;
  window.refreshComparison = refreshComparison;
  window.selectCatalogo = selectCatalogo;
  window.showCatalogoCsvPreview = showCatalogoCsvPreview;
  window.showCatalogoStatusPreview = showCatalogoStatusPreview;
  window.showCatalogoLogPreview = showCatalogoLogPreview;
  window.downloadCatalogoArquivo = downloadCatalogoArquivo;
  window.setCatalogPreviewPage = setCatalogPreviewPage;
  window.setCatalogPreviewPageSize = setCatalogPreviewPageSize;
}

  function hydrateFromBoot() {
    const initialState =
      (BOOT?.initial_state && typeof BOOT.initial_state === "object" && BOOT.initial_state) ||
      (BOOT?.state && typeof BOOT.state === "object" && BOOT.state) ||
      { data: {}, logs: [] };

    if (BOOT?.run_options && typeof BOOT.run_options === "object") {
      writeRunOptionsToForm(BOOT.run_options);
    }

    if (isManagerMode()) {
      ensureRunsManagerUi();
      updateRunCreateSelectors(initialState?.data || {});
      renderRunsTabs();
    }

    renderStatePayload(initialState, { forceConfigWrite: true });
    updateContextSelectorsFromState(initialState?.data || {});
    toggleScopeFields();
    refreshSelectedCategoriesCounter();
  }

function activateMainTab(tabKey) {
  const keys = ["principal", "comparacao", "atualizacoes", "adicoes", "loja"];
  const normalized = keys.includes(tabKey) ? tabKey : "principal";

  keys.forEach((key) => {
    const button = byId(`tab_btn_${key}`);
    const panel = byId(`tab_panel_${key}`);
    if (button) {
      const active = key === normalized;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    }
    if (panel) panel.classList.toggle("hidden", key !== normalized);
  });
  document.body.dataset.activeTab = normalized;
  qs(".page-head-sticky")?.classList.toggle("hidden", normalized !== "principal");
}

function setCatalogPreviewPage(page) {
  const nextPage = Math.max(1, toInt(page, 1));
  UI.catalogPreview.page = nextPage;
  renderCatalogPreview();
}

function setCatalogPreviewPageSize(pageSize) {
  const allowed = Array.isArray(UI.catalogPreview?.pageSizeOptions)
    ? UI.catalogPreview.pageSizeOptions
    : LISTING_PAGE_SIZE_OPTIONS;

  const nextSize = normalizeListingPageSize(pageSize, LISTING_DEFAULT_PAGE_SIZE);
  UI.catalogPreview.pageSize = allowed.includes(nextSize) ? nextSize : LISTING_DEFAULT_PAGE_SIZE;
  UI.catalogPreview.page = 1;
  renderCatalogPreview();
}

function parseCsvPreviewRows(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  const source = String(text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");

  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    const next = source[i + 1] || "";

    if (char === '"') {
      if (inQuotes && next === '"') {
        cell += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }

    if (char === "\n" && !inQuotes) {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      continue;
    }

    cell += char;
  }

  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }

  return rows.filter((currentRow) =>
    currentRow.some((value) => String(value ?? "").trim() !== "")
  );
}

function setCatalogPreviewHeader(title, downloadUrl) {
  const titleNode = byId("catalogos_preview_title");
  const downloadButton = byId("catalogos_preview_download_btn");

  if (titleNode) {
    titleNode.textContent = title || "Prévia";
  }

  if (downloadButton) {
    downloadButton.disabled = !downloadUrl;
    downloadButton.onclick = downloadUrl
      ? () => downloadCatalogoArquivo(downloadUrl)
      : null;
  }
}

function resetCatalogPreview(message = "Selecione uma prévia na tabela.") {
  UI.catalogPreview = {
    kind: "none",
    rawText: "",
    downloadUrl: "",
    title: "Prévia",
    page: 1,
    pageSize: 5,
    pageSizeOptions: LISTING_PAGE_SIZE_OPTIONS,
  };

  const searchNode = byId("catalogos_preview_search");
  if (searchNode) {
    searchNode.value = "";
  }

  setCatalogPreviewHeader("Prévia", "");

  const previewNode = byId("catalogos_status_preview");
  if (previewNode) {
    previewNode.innerHTML = `<div class="notice">${escapeHtml(message)}</div>`;
  }
}

function getCatalogPreviewColumnClass(header) {
  const normalized = String(header ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "_");

  if (normalized === "observacao") return "is-col-observacao";
  if (normalized === "nome_produto") return "is-col-nome-produto";
  if (normalized === "link_produto") return "is-col-link-produto";
  if (normalized === "categoria_url") return "is-col-categoria-url";

  return "";
}

function isCatalogPreviewLinkColumn(header) {
  const normalized = String(header ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "_");

  return (
    normalized === "categoria_url" ||
    normalized === "link_produto" ||
    normalized === "pagina_oficial"
  );
}

function buildCatalogPreviewCellHtml(header, value) {
  let text = String(value ?? "").trim();

  if (!text) {
    return "";
  }

  const normalizedHeader = String(header ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "_");

  if (normalizedHeader === "versao_produto") {
    const formulaMatch = text.match(/^="(.+)"$/);
    if (formulaMatch) {
      text = formulaMatch[1].replace(/""/g, '"').trim();
    } else if (text.startsWith("'")) {
      text = text.slice(1).trim();
    }
  }

  if (isCatalogPreviewLinkColumn(header)) {
    const safeUrl = escapeHtml(text);
    return `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer">${safeUrl}</a>`;
  }

  return escapeHtml(text);
}

function getCatalogPreviewOrderedHeaders(sourceHeaders) {
  const normalizedHeaders = Array.isArray(sourceHeaders) ? sourceHeaders : [];

  const preferredOrder = [
    "tipo",
    "nome_produto",
    "categoria_nome",
    "categoria_url",
    "link_produto",
    "pagina_oficial",
    "versao_produto",
    "observacao",
  ];

  const ordered = [];
  const used = new Set();

  preferredOrder.forEach((preferred) => {
    const found = normalizedHeaders.find((header) => {
      const normalized = String(header ?? "")
        .trim()
        .toLowerCase()
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/\s+/g, "_");

      return normalized === preferred;
    });

    if (found && !used.has(found)) {
      used.add(found);
      ordered.push(found);
    }
  });

  normalizedHeaders.forEach((header) => {
    if (!used.has(header)) {
      used.add(header);
      ordered.push(header);
    }
  });

  return ordered;
}

function buildCsvPreviewHtml(text, searchTerm = "") {
  const rows = parseCsvPreviewRows(text);

  if (!rows.length) {
    return '<div class="notice">Catálogo vazio.</div>';
  }

  const sourceHeaders = rows[0];
  const headers = getCatalogPreviewOrderedHeaders(sourceHeaders);
  const allRows = rows.slice(1);
  const normalizedSearch = normalizeText(searchTerm).toLowerCase();

  const filteredRows = normalizedSearch
    ? allRows.filter((row) =>
        row.some((cell) =>
          String(cell ?? "").toLowerCase().includes(normalizedSearch)
        )
      )
    : allRows;

  const pageSizeOptions = Array.isArray(UI.catalogPreview?.pageSizeOptions)
    ? UI.catalogPreview.pageSizeOptions
    : LISTING_PAGE_SIZE_OPTIONS;

  const pageSize = pageSizeOptions.includes(toInt(UI.catalogPreview?.pageSize, LISTING_DEFAULT_PAGE_SIZE))
    ? toInt(UI.catalogPreview?.pageSize, LISTING_DEFAULT_PAGE_SIZE)
    : 50;

  const totalRows = filteredRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / pageSize));
  const currentPage = Math.min(
    Math.max(1, toInt(UI.catalogPreview?.page, 1)),
    totalPages
  );

  UI.catalogPreview.page = currentPage;
  UI.catalogPreview.pageSize = pageSize;

  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const bodyRows = filteredRows.slice(startIndex, endIndex);

  return `
    <div class="listing-meta-row">
      <div class="small">
        Mostrando ${bodyRows.length} linha(s), da ${totalRows ? startIndex + 1 : 0} até ${Math.min(endIndex, totalRows)} de ${totalRows}.
      </div>

      <div class="listing-page-size">
        <label for="catalog_preview_page_size" class="small">Linhas por página</label>
        <select id="catalog_preview_page_size" onchange="setCatalogPreviewPageSize(this.value)">
          ${pageSizeOptions.map((size) => `
            <option value="${size}" ${size === pageSize ? "selected" : ""}>${size}</option>
          `).join("")}
        </select>
      </div>
    </div>

    <div class="listing-pagination">
      <button class="btn-secondary" type="button" onclick="setCatalogPreviewPage(${currentPage - 1})" ${currentPage <= 1 ? "disabled" : ""}>← Anterior</button>
      <span class="badge">Página ${currentPage} de ${totalPages}</span>
      <button class="btn-secondary" type="button" onclick="setCatalogPreviewPage(${currentPage + 1})" ${currentPage >= totalPages ? "disabled" : ""}>Próxima →</button>
    </div>

    <div class="table-wrap">
      <table class="catalogos-table">
        <thead>
          <tr>
            ${headers.map((header) => {
              const colClass = getCatalogPreviewColumnClass(header);
              return `<th class="${colClass}">${escapeHtml(header || "-")}</th>`;
            }).join("")}
          </tr>
        </thead>
        <tbody>
          ${
            bodyRows.length
              ? bodyRows.map((row) => `
                  <tr>
                    ${headers.map((header) => {
                      const colClass = getCatalogPreviewColumnClass(header);
                      const sourceIndex = sourceHeaders.indexOf(header);
                      return `<td class="${colClass}">${buildCatalogPreviewCellHtml(header, sourceIndex >= 0 ? row[sourceIndex] ?? "" : "")}</td>`;
                    }).join("")}
                  </tr>
                `).join("")
              : `<tr><td colspan="${headers.length || 1}">Nenhum resultado encontrado.</td></tr>`
          }
        </tbody>
      </table>
    </div>
  `;
}

function buildTextPreviewHtml(text, searchTerm = "", kind = "text") {
  const allLines = String(text ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .split("\n");

  const normalizedSearch = normalizeText(searchTerm).toLowerCase();

  const filteredLines = normalizedSearch
    ? allLines.filter((line) =>
        String(line ?? "").toLowerCase().includes(normalizedSearch)
      )
    : allLines;

  const visibleText = filteredLines.join("\n").trim() || "Sem conteúdo disponível.";

  if (kind === "status") {
    return `
      <div class="small" style="margin-bottom:10px;">
        Mostrando ${filteredLines.length} de ${allLines.length} linhas.
      </div>
      <div
        style="
          white-space:pre-wrap;
          word-break:break-word;
          background:#000;
          color:#f8fafc;
          padding:14px;
          border-radius:12px;
          border:1px solid #202020;
          font-family:Consolas,Monaco,monospace;
          font-size:14px;
          line-height:1.65;
        "
      >${escapeHtml(visibleText)}</div>
    `;
  }

  return `
    <div class="small" style="margin-bottom:10px;">
      Mostrando ${filteredLines.length} de ${allLines.length} linhas.
    </div>
    <pre style="height:320px;">${escapeHtml(visibleText)}</pre>
  `;
}

function renderCatalogPreview() {
  const previewNode = byId("catalogos_status_preview");
  if (!previewNode) return;

  const searchTerm = byId("catalogos_preview_search")?.value || "";
  const preview = UI.catalogPreview || {};
  byId("catalogos_preview_copy_log_btn")?.classList.toggle("hidden", preview.kind !== "log");

  setCatalogPreviewHeader(preview.title || "Prévia", preview.downloadUrl || "");

  if (preview.kind === "catalog") {
    previewNode.innerHTML = buildCsvPreviewHtml(preview.rawText || "", searchTerm);
    return;
  }

  if (preview.kind === "status") {
    previewNode.innerHTML = buildTextPreviewHtml(preview.rawText || "", searchTerm, "status");
    return;
  }

  if (preview.kind === "log") {
    previewNode.innerHTML = buildTextPreviewHtml(preview.rawText || "", searchTerm, "log");
    return;
  }

  previewNode.innerHTML = '<div class="notice">Selecione uma prévia na tabela.</div>';
}

function bindCatalogPreviewSearch() {
  const searchNode = byId("catalogos_preview_search");
  if (!searchNode) return;

  searchNode.addEventListener("input", () => {
    UI.catalogPreview.page = 1;
    renderCatalogPreview();
  });
}

async function fetchCatalogoPreviewText(url, acceptHeader) {
  const response = await fetch(url, {
    method: "GET",
    cache: "no-store",
    headers: {
      Accept: acceptHeader,
    },
  });

  if (!response.ok) {
    throw new Error(`Falha HTTP ${response.status}`);
  }

  return await response.text();
}

async function showCatalogoCsvPreview(url) {
  const previewNode = byId("catalogos_status_preview");
  if (!previewNode) return;

  const targetUrl = normalizeText(url);
  if (!targetUrl) {
    previewNode.innerHTML = '<div class="notice">Catálogo não disponível.</div>';
    return;
  }

  const searchNode = byId("catalogos_preview_search");
  if (searchNode) {
    searchNode.value = "";
  }

  UI.catalogPreview = {
    kind: "catalog",
    rawText: "",
    downloadUrl: targetUrl,
    title: "catálogo",
    page: 1,
    pageSize: 5,
    pageSizeOptions: LISTING_PAGE_SIZE_OPTIONS,
  };

  setCatalogPreviewHeader("Prévia de Catálogo", targetUrl);
  previewNode.innerHTML = '<div class="notice">Carregando catálogo...</div>';

  try {
    const text = await fetchCatalogoPreviewText(targetUrl, "text/csv,text/plain,*/*");
    UI.catalogPreview.rawText = String(text ?? "");
    renderCatalogPreview();
  } catch (error) {
    previewNode.innerHTML = '<div class="notice">Erro ao carregar catálogo.</div>';
    notify(error?.message || "Erro ao carregar catálogo.");
  }
}

async function showCatalogoStatusPreview(url) {
  const previewNode = byId("catalogos_status_preview");
  if (!previewNode) return;

  const targetUrl = normalizeText(url);
  if (!targetUrl) {
    previewNode.innerHTML = '<div class="notice">Estado não disponível.</div>';
    return;
  }

  const searchNode = byId("catalogos_preview_search");
  if (searchNode) {
    searchNode.value = "";
  }

  UI.catalogPreview = {
    kind: "status",
    rawText: "",
    downloadUrl: targetUrl,
    title: "Estado",
  };

  setCatalogPreviewHeader("Estado", targetUrl);
  previewNode.innerHTML = '<div class="notice">Carregando estado...</div>';

  try {
    const text = await fetchCatalogoPreviewText(targetUrl, "text/plain,*/*");
    UI.catalogPreview.rawText = String(text ?? "");
    renderCatalogPreview();
  } catch (error) {
    previewNode.innerHTML = '<div class="notice">Erro ao carregar estado.</div>';
    notify(error?.message || "Erro ao carregar estado.");
  }
}

async function showCatalogoLogPreview(url) {
  const previewNode = byId("catalogos_status_preview");
  if (!previewNode) return;

  const targetUrl = normalizeText(url);
  if (!targetUrl) {
    previewNode.innerHTML = '<div class="notice">Log não disponível.</div>';
    return;
  }

  const searchNode = byId("catalogos_preview_search");
  if (searchNode) {
    searchNode.value = "";
  }

  UI.catalogPreview = {
    kind: "log",
    rawText: "",
    downloadUrl: targetUrl,
    title: "Log",
  };

  setCatalogPreviewHeader("Log", targetUrl);
  previewNode.innerHTML = '<div class="notice">Carregando log...</div>';

  try {
    const text = await fetchCatalogoPreviewText(targetUrl, "text/plain,*/*");
    UI.catalogPreview.rawText = String(text ?? "");
    renderCatalogPreview();
  } catch (error) {
    previewNode.innerHTML = '<div class="notice">Erro ao carregar log.</div>';
    notify(error?.message || "Erro ao carregar log.");
  }
}

function downloadCatalogoArquivo(url) {
  const targetUrl = normalizeText(url);
  if (!targetUrl) {
    notify("Arquivo não disponível.");
    return;
  }

  window.location.href = targetUrl;
}

function buildCatalogosCardsHtml(rows, currentSlot, defaultSlot, selectedFilter = "") {
  const grouped = new Map();

  rows.forEach((row) => {
    const slotName = normalizeText(row?.slot_name || row?.catalogo_nome);
    if (!slotName) return;

    if (!grouped.has(slotName)) {
      grouped.set(slotName, {
        slot_name: slotName,
        items_count: 0,
        contexts_count: 0,
        has_csv: false,
        has_status: false,
        has_log: false,
        contexts: [],
        updated_at: "",
        updated_at_timestamp: 0,
      });
    }

    const entry = grouped.get(slotName);
    entry.items_count += Math.max(0, toInt(row?.items_count, 0));
    entry.contexts_count += 1;
    entry.has_csv = entry.has_csv || !!row?.csv_exists;
    entry.has_status = entry.has_status || !!row?.status_exists;
    entry.has_log = entry.has_log || !!row?.log_exists;
    const contextLabel = [row?.site_key, row?.item_type_key, row?.account_key]
      .map((value) => normalizeText(value)).filter(Boolean).join(" • ");
    if (contextLabel && !entry.contexts.some((item) => item.label === contextLabel)) {
      entry.contexts.push({label: contextLabel, items_count: Math.max(0, toInt(row?.items_count, 0)), updated_at: normalizeText(row?.updated_at)});
    }
    const updatedAtTimestamp = Number(row?.updated_at_timestamp || 0);
    if (updatedAtTimestamp >= entry.updated_at_timestamp) {
      entry.updated_at_timestamp = updatedAtTimestamp;
      entry.updated_at = normalizeText(row?.updated_at);
    }
  });

  return Array.from(grouped.values()).map((entry) => {
    const slotName = normalizeText(entry.slot_name);
    const slotDisplayName = catalogDisplayName(slotName, "-");
    const isCurrent = slotName === currentSlot;
    const isDefault = slotName === defaultSlot;
    const isPrincipal = slotName.toLowerCase() === "default";
    const isContextFilterActive = slotName === selectedFilter;
    const contextLines = entry.contexts.map((context) => `
      <span class="catalogo-context-line">
        <span>${escapeHtml(context.label)} (${escapeHtml(String(context.items_count))} itens)</span>
        <time>${escapeHtml(context.updated_at || "Data não registrada")}</time>
      </span>
    `).join("");
    const availability = [
      ["📄", "Catálogo", entry.has_csv],
      ["📝", "Estado", entry.has_status],
      ["📋", "Log", entry.has_log],
    ].map(([icon, label, available]) => `<span class="catalogo-availability-icon${available ? "" : " is-unavailable"}" tabindex="0" role="img" aria-label="${label}" aria-disabled="${available ? "false" : "true"}" title="${label}">${icon}</span>`).join("");

    return `
      <div class="card catalogo-summary-card" style="min-width:280px; flex:1 1 280px;">
        <div class="catalogo-card-actions">
          <button class="catalogo-icon-button catalogo-view-button ${isContextFilterActive ? "is-active" : ""}" type="button" aria-pressed="${isContextFilterActive}" title="${isContextFilterActive ? "Mostrar todos os catálogos" : `Ver somente os contextos de ${escapeHtml(slotName)}`}" aria-label="${isContextFilterActive ? "Mostrar todos os catálogos" : `Ver contextos do catálogo ${escapeHtml(slotName)}`}" onclick='showCatalogoContexts(${JSON.stringify(slotName)})'>👁️</button>
          ${isPrincipal ? "" : `<button class="catalogo-icon-button catalogo-rename-button" type="button" title="Renomear catálogo ${escapeHtml(slotDisplayName)}" aria-label="Renomear catálogo ${escapeHtml(slotDisplayName)}" onclick='openCatalogRenameModal(${JSON.stringify(slotName)})'><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l11-11a2.8 2.8 0 0 0-4-4L4 16v4Z"></path><path d="m13.5 6.5 4 4"></path></svg></button>`}
          <button class="catalogo-icon-button catalogo-load-button" type="button" title="Carregar catálogo ${escapeHtml(slotName)}" aria-label="Carregar catálogo ${escapeHtml(slotName)}" onclick='loadCatalogo(${JSON.stringify(slotName)})' ${isCurrent ? "disabled" : ""}>📂</button>
          <button class="catalogo-icon-button catalogo-default-button" type="button" title="Definir ${escapeHtml(slotName)} como catálogo default" aria-label="Definir ${escapeHtml(slotName)} como catálogo default" onclick='defineDefaultCatalogo(${JSON.stringify(slotName)})' ${isDefault ? "disabled" : ""}>⭐</button>
          <button class="catalogo-icon-button catalogo-clear-button" type="button" title="Limpar catálogo ${escapeHtml(slotName)}" aria-label="Limpar catálogo ${escapeHtml(slotName)}" onclick='clearCatalogo(${JSON.stringify(slotName)})'>🧹</button>
          <button class="catalogo-icon-button catalogo-delete-button" type="button" title="Excluir catálogo ${escapeHtml(slotName)}" aria-label="Excluir catálogo ${escapeHtml(slotName)}" onclick='deleteCatalogo(${JSON.stringify(slotName)})' ${isDefault ? "disabled" : ""}>🗑️</button>
        </div>
        <div class="section-title">${escapeHtml(slotDisplayName)}</div>
        <div class="catalogo-summary-meta">
          <span><strong>${escapeHtml(String(entry.items_count))}</strong> itens</span>
          <span>Última atualização: <time>${escapeHtml(entry.updated_at || "Data não registrada")}</time></span>
        </div>
        <div class="small">
          <span class="catalogo-status-row" aria-label="Status do catálogo"${!isCurrent && !isDefault ? ' aria-hidden="true"' : ""}>${isCurrent ? '<span class="catalogo-status-item">🟢 Atual</span>' : ""}${isDefault ? '<span class="catalogo-status-item">⭐ Catálogo padrão</span>' : ""}</span>
          <details class="catalogo-context-accordion">
            <summary>${entry.contexts.length} ${entry.contexts.length === 1 ? "Contexto" : "Contextos"}</summary>
            <span class="catalogo-context-list">${contextLines || "Nenhum contexto"}</span>
          </details>
          <span class="catalogo-availability" aria-label="Arquivos disponíveis">${availability}</span>
        </div>
      </div>
    `;
  }).join("");
}

function setCatalogosLoading(loading) {
  const modal = byId("tab_panel_catalogos");
  byId("catalogos_loading")?.classList.toggle("hidden", !loading);
  byId("catalogos_content")?.classList.toggle("hidden", loading);
  modal?.setAttribute("aria-busy", loading ? "true" : "false");
}

async function refreshCatalogos({ showLoading = false } = {}) {
  const cardsWrap = byId("catalogos_cards_wrap");
  const tableBody = byId("catalogos_table_body");
  const filterNode = byId("catalogos_filter_slot");

  if (!cardsWrap || !tableBody) return;
  if (showLoading) setCatalogosLoading(true);

  cardsWrap.innerHTML = '<div class="badge">Carregando catálogos...</div>';
  tableBody.innerHTML = '<tr><td colspan="10">Carregando...</td></tr>';
  resetCatalogPreview();

  try {
    const [catalogosPayload, statePayload] = await Promise.all([
      getJson(UI.endpoints.catalogosData || "/catalogos/data"),
      getJson(UI.endpoints.state),
    ]);

    const rows = Array.isArray(catalogosPayload?.catalogos) ? catalogosPayload.catalogos : [];
    UI.catalogRows = rows;
    const namesFromPayload = Array.isArray(catalogosPayload?.catalogo_nomes)
      ? catalogosPayload.catalogo_nomes
      : [];

    const stateData = statePayload?.data || {};
    const currentSlot = normalizeText(stateData?.current_slot || stateData?.slot_name || "");
    const defaultSlot = normalizeText(stateData?.default_slot || "");

    const allNames = namesFromPayload.length
      ? namesFromPayload.map((name) => normalizeText(name)).filter(Boolean)
      : Array.from(
          new Set(
            rows.map((row) => normalizeText(row?.slot_name || row?.catalogo_nome)).filter(Boolean)
          )
        );

    if (filterNode) {
      const currentFilter = normalizeText(filterNode.value);

      filterNode.innerHTML =
        '<option value="">Todos</option>' +
        allNames.map((name) => {
          const displayName = catalogDisplayName(name);
          const label = name === defaultSlot ? `${displayName} ⭐` : displayName;
          return `<option value="${escapeHtml(name)}">${escapeHtml(label)}</option>`;
        }).join("");

      if (currentFilter && allNames.includes(currentFilter)) {
        filterNode.value = currentFilter;
      }
    }

    const selectedFilter = normalizeText(filterNode?.value || "");
    const search = normalizeText(byId("catalogos_search")?.value).toLowerCase();
    const filteredRows = (selectedFilter
      ? rows.filter((row) => normalizeText(row?.slot_name || row?.catalogo_nome) === selectedFilter)
      : rows).filter((row) => !search || [row?.slot_name, row?.site_key, row?.item_type_key, row?.account_key]
        .map((value) => normalizeText(value)).join(" ").toLowerCase().includes(search));

    const contextRows = filteredRows.filter((row) => normalizeText(row?.site_key));
    const zeroCount = contextRows.filter((row) => toInt(row?.items_count, 0) === 0).length;
    const countNode = byId("catalogos_context_count");
    const removeZeroButton = byId("catalogos_remove_zero_btn");
    if (countNode) countNode.textContent = `${contextRows.length} contexto(s)`;
    if (removeZeroButton) {
      removeZeroButton.disabled = zeroCount === 0;
      removeZeroButton.textContent = zeroCount ? `Remover contextos zerados (${zeroCount})` : "Remover contextos zerados";
    }

    if (!filteredRows.length) {
      cardsWrap.innerHTML = '<div class="badge">Nenhum catálogo encontrado.</div>';
      tableBody.innerHTML = '<tr><td colspan="7">Nenhum catálogo encontrado.</td></tr>';
      resetCatalogPreview("Nenhum catálogo encontrado.");
      return;
    }

    cardsWrap.innerHTML = buildCatalogosCardsHtml(filteredRows, currentSlot, defaultSlot, selectedFilter);

    const pageSize = normalizeListingPageSize(byId("catalogos_page_size")?.value, LISTING_DEFAULT_PAGE_SIZE);
    UI.catalogPageSize = pageSize;
    const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
    UI.catalogPage = Math.min(Math.max(1, toInt(UI.catalogPage, 1)), totalPages);
    const visibleRows = filteredRows.slice((UI.catalogPage - 1) * pageSize, UI.catalogPage * pageSize);
    setText("catalogos_result_meta", listingRangeText(filteredRows.length, UI.catalogPage, pageSize));
    setText("catalogos_page_label", `Página ${UI.catalogPage} de ${totalPages}`);
    setDisabled("catalogos_prev_page", UI.catalogPage <= 1);
    setDisabled("catalogos_next_page", UI.catalogPage >= totalPages);

    tableBody.innerHTML = visibleRows.map((row) => {
      const slotName = normalizeText(row?.slot_name || row?.catalogo_nome || "-");
      const slotDisplayName = catalogDisplayName(slotName, "-");
      const rawSiteKey = normalizeText(row?.site_key);
      const rawItemTypeKey = normalizeText(row?.item_type_key);
      const rawAccountKey = normalizeText(row?.account_key);
      const hasContext = Boolean(rawSiteKey && rawItemTypeKey && rawAccountKey);
      const siteKey = rawSiteKey || "-";
      const itemTypeKey = rawItemTypeKey || "-";
      const accountKey = rawAccountKey || "-";
      const itemsCount = Math.max(0, toInt(row?.items_count, 0));
      const statusLabel = row?.status_exists ? "Disponível" : "Sem status";

      return `
        <tr>
          <td>${escapeHtml(slotDisplayName)}</td>
          <td>${escapeHtml(siteKey || "-")}</td>
          <td>${escapeHtml(itemTypeKey || "-")}</td>
          <td>${escapeHtml(accountKey || "-")}</td>
          <td>${escapeHtml(String(itemsCount))}</td>
          <td>${escapeHtml(statusLabel)}</td>
          <td>
            <div class="table-actions">
              ${row?.csv_exists && row?.download_csv_url
                ? `<button class="btn-secondary btn-sm" type="button" onclick='showCatalogoCsvPreview(${JSON.stringify(row.download_csv_url)})'>Catálogo</button>`
                : `<button class="btn-secondary btn-sm" type="button" disabled>Catálogo</button>`}
              ${row?.status_exists && row?.download_status_url
                ? `<button class="btn-secondary btn-sm" type="button" onclick='showCatalogoStatusPreview(${JSON.stringify(row.download_status_url)})'>Estado</button>`
                : `<button class="btn-secondary btn-sm" type="button" disabled>Estado</button>`}
              ${row?.log_exists && row?.download_log_url
                ? `<button class="btn-secondary btn-sm" type="button" onclick='showCatalogoLogPreview(${JSON.stringify(row.download_log_url)})'>Log</button>`
                : `<button class="btn-secondary btn-sm" type="button" disabled>Log</button>`}
              ${hasContext ? `<button
                class="btn-danger btn-sm"
                type="button"
                onclick='removeCatalogoContext(${JSON.stringify(slotName)}, ${JSON.stringify(siteKey)}, ${JSON.stringify(itemTypeKey)}, ${JSON.stringify(accountKey)})'
              >
                Remover contexto
              </button>` : ""}
            </div>
          </td>
        </tr>
      `;
    }).join("");

    resetCatalogPreview();
  } catch (error) {
    cardsWrap.innerHTML = '<div class="badge">Erro ao carregar catálogos.</div>';
    tableBody.innerHTML = '<tr><td colspan="7">Erro ao carregar catálogos.</td></tr>';
    resetCatalogPreview("Erro ao carregar catálogos.");
    notify(error?.message || "Erro ao carregar catálogos.");
  } finally {
    if (showLoading) setCatalogosLoading(false);
  }
}

function closeCatalogRenameModal() {
  const modal = byId("catalog_rename_modal");
  if (!modal) return;
  modal.classList.add("hidden");
  modal.removeAttribute("data-slot-name");
}

function openCatalogRenameModal(slotName) {
  const normalized = normalizeText(slotName);
  if (!normalized || normalized.toLowerCase() === "default") return;
  const modal = byId("catalog_rename_modal");
  const input = byId("catalog_rename_name");
  if (!modal || !input) return;
  modal.dataset.slotName = normalized;
  setText("catalog_rename_help", `Renomeando "${catalogDisplayName(normalized)}". Os contextos e arquivos serão preservados.`);
  input.value = normalized;
  modal.classList.remove("hidden");
  window.setTimeout(() => { input.focus(); input.select(); }, 0);
}

async function confirmCatalogRename() {
  const modal = byId("catalog_rename_modal");
  const oldName = normalizeText(modal?.dataset.slotName);
  const newName = normalizeText(byId("catalog_rename_name")?.value);
  if (!oldName || oldName.toLowerCase() === "default") return;
  if (!newName) {
    notify("Informe o novo nome do catálogo.");
    byId("catalog_rename_name")?.focus();
    return;
  }
  const button = byId("catalog_rename_confirm");
  if (button) { button.disabled = true; button.textContent = "Renomeando..."; }
  try {
    const result = await postJson(UI.endpoints.slotRename || "/slot/rename", {
      old_slot_name: oldName,
      new_slot_name: newName,
    });
    closeCatalogRenameModal();
    notify(result?.message || "Catálogo renomeado.");
    await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
    await refreshCatalogos({ showLoading: true });
  } catch (error) {
    notify(normalizeText(error?.message, "Falha ao renomear catálogo."));
  } finally {
    if (button) { button.disabled = false; button.textContent = "Salvar novo nome"; }
  }
}

async function selectCatalogo(slotName) {
  if (!slotName) return;

  const result = await postJson(UI.endpoints.slotSwitch, { slot_name: slotName });
  await loadState({ forceConfigWrite: true, forceRunsRefresh: true });
  openCatalogosModal();
  await refreshCatalogos();
  notify(result?.message || "Catálogo carregado.");
}

function buildFilaContextValue(context) {
  const parts = [
    normalizeText(context?.site_key),
    normalizeText(context?.item_type_key),
    normalizeText(context?.account_key),
    normalizeText(context?.slot_name),
  ].map((value) => encodeURIComponent(value));

  return parts.join("|");
}

function parseFilaContextValue(value) {
  const parts = String(value || "").split("|");

  return {
    site_key: decodeURIComponent(parts[0] || ""),
    item_type_key: decodeURIComponent(parts[1] || ""),
    account_key: decodeURIComponent(parts[2] || ""),
    slot_name: decodeURIComponent(parts[3] || ""),
  };
}

function buildFilaContextLabel(context) {
  const slotName = normalizeText(context?.slot_name, "-");
  const siteKey = normalizeText(context?.site_key, "-");
  const itemTypeKey = normalizeText(context?.item_type_key, "-");
  const accountKey = normalizeText(context?.account_key, "-");

  return `${slotName} • ${siteKey} • ${itemTypeKey} • ${accountKey}`;
}

function normalizeFilaRules(rules) {
  const normalized = [];
  const seen = new Set();

  (Array.isArray(rules) ? rules : []).forEach((rawRule, index) => {
    const source = parseFilaContextValue(buildFilaContextValue(rawRule?.source || {}));
    const target = parseFilaContextValue(buildFilaContextValue(rawRule?.target || {}));

    if (!source.site_key || !source.item_type_key || !source.account_key || !source.slot_name) {
      return;
    }

    if (!target.site_key || !target.item_type_key || !target.account_key || !target.slot_name) {
      return;
    }

    if (buildFilaContextValue(source) === buildFilaContextValue(target)) {
      return;
    }

    const pairKey = `${buildFilaContextValue(source)}>${buildFilaContextValue(target)}`;
    if (seen.has(pairKey)) {
      return;
    }
    seen.add(pairKey);

    normalized.push({
      id: normalizeText(rawRule?.id, `fila-${index + 1}`),
      enabled: !!rawRule?.enabled,
      source,
      target,
    });
  });

  return normalized;
}

function buildFilaCatalogOptions(rows) {
  const options = [];
  const seen = new Set();

  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const context = {
      site_key: normalizeText(row?.site_key),
      item_type_key: normalizeText(row?.item_type_key),
      account_key: normalizeText(row?.account_key),
      slot_name: normalizeText(row?.slot_name || row?.catalogo_nome),
    };

    if (!context.site_key || !context.item_type_key || !context.account_key || !context.slot_name) {
      return;
    }

    const value = buildFilaContextValue(context);
    if (!value || seen.has(value)) {
      return;
    }

    seen.add(value);
    options.push({
      value,
      label: buildFilaContextLabel(context),
      context,
    });
  });

  options.sort((left, right) => left.label.localeCompare(right.label, "pt-BR"));
  return options;
}

function buildFilaSelectOptionsHtml(selectedContext) {
  const selectedValue = buildFilaContextValue(selectedContext || {});
  const options = Array.isArray(UI.filaCatalogOptions) ? UI.filaCatalogOptions : [];

  if (!options.length) {
    return '<option value="">Nenhum catálogo/contexto disponível</option>';
  }

  return options.map((option) => `
    <option value="${escapeHtml(option.value)}" ${option.value === selectedValue ? "selected" : ""}>
      ${escapeHtml(option.label)}
    </option>
  `).join("");
}

function renderFilaRules() {
  const wrap = byId("fila_rules_wrap");
  const countBadge = byId("fila_rules_count_badge");

  if (!wrap) return;

  UI.filaRules = normalizeFilaRules(UI.filaRules);

  if (countBadge) {
    const total = UI.filaRules.length;
    countBadge.textContent = `${total} regra${total === 1 ? "" : "s"}`;
  }

  if (!UI.filaCatalogOptions.length) {
    wrap.innerHTML = '<div class="notice">Nenhum catálogo/contexto disponível para montar a fila ainda.</div>';
    return;
  }

  if (!UI.filaRules.length) {
    wrap.innerHTML = '<div class="notice">Nenhuma regra criada. Clique em "Adicionar regra".</div>';
    return;
  }

  wrap.innerHTML = UI.filaRules.map((rule, index) => `
    <div class="card fila-rule-card" data-fila-id="${escapeHtml(rule.id)}" style="margin-bottom:12px; padding:14px;">
      <div class="row" style="justify-content:space-between; align-items:center; margin-bottom:12px;">
        <div class="row" style="align-items:center;">
          <span class="badge">Regra ${index + 1}</span>
          <label class="checkbox-item" style="padding:8px 10px;">
            <input type="checkbox" data-fila-role="enabled" ${rule.enabled ? "checked" : ""}>
            <span class="checkbox-text">
              <span>Ativa</span>
            </span>
          </label>
        </div>

        <button class="btn-danger btn-sm" type="button" data-fila-action="remove">Apagar</button>
      </div>

      <div class="form-grid">
        <div class="field">
          <label>Quando este catálogo/contexto terminar</label>
          <select data-fila-role="source">
            ${buildFilaSelectOptionsHtml(rule.source)}
          </select>
        </div>

        <div class="field">
          <label>Rodar este catálogo/contexto depois</label>
          <select data-fila-role="target">
            ${buildFilaSelectOptionsHtml(rule.target)}
          </select>
        </div>
      </div>
    </div>
  `).join("");

  qsa("[data-fila-action='remove']", wrap).forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest(".fila-rule-card");
      const ruleId = normalizeText(card?.getAttribute("data-fila-id"));
      UI.filaRules = UI.filaRules.filter((rule) => normalizeText(rule.id) !== ruleId);
      renderFilaRules();
    });
  });
}

function collectFilaRulesFromDom() {
  const cards = qsa(".fila-rule-card");

  return cards.map((card, index) => {
    const enabled = !!qs("[data-fila-role='enabled']", card)?.checked;
    const source = parseFilaContextValue(qs("[data-fila-role='source']", card)?.value || "");
    const target = parseFilaContextValue(qs("[data-fila-role='target']", card)?.value || "");

    return {
      id: normalizeText(card.getAttribute("data-fila-id"), `fila-${index + 1}`),
      enabled,
      source,
      target,
    };
  });
}


async function loadComparisonSources(options = {}) {
  const sourceSelect = byId("comparison_source_catalog");
  const targetSelect = byId("comparison_target_catalog");
  const reloadButton = byId("comparison_reload_sources_btn");
  const notice = byId("comparison_file_notice");
  if (!sourceSelect || !targetSelect) return;

  const previousSource = normalizeText(sourceSelect.value);
  const previousTarget = normalizeText(options.preferredTarget || targetSelect.value);
  sourceSelect.disabled = true;
  targetSelect.disabled = true;
  if (reloadButton) { reloadButton.disabled = true; reloadButton.textContent = "Carregando..."; }
  if (notice) notice.textContent = "Carregando catálogos disponíveis...";
  appendComparisonLog("Carregando catálogos disponíveis para comparação.");

  try {
    const payload = await getJson(UI.endpoints.comparisonSources || "/comparacao/fontes");
    const savedCatalogs = Array.isArray(payload?.saved_catalogs) ? payload.saved_catalogs : [];
    const importedCatalogs = Array.isArray(payload?.imported_catalogs) ? payload.imported_catalogs : [];
    const pluginTemaCatalogs = importedCatalogs.filter((item) => normalizeText(item?.filename).startsWith("plugintema-"));

    sourceSelect.innerHTML = '<option value="">Selecione um catálogo salvo</option>' +
      savedCatalogs.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
    targetSelect.innerHTML = '<option value="">Selecione um catálogo PluginTema</option>' +
      pluginTemaCatalogs.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");

    if (savedCatalogs.some((item) => normalizeText(item.id) === previousSource)) sourceSelect.value = previousSource;
    else if (savedCatalogs.length) sourceSelect.value = savedCatalogs[0].id;

    if (pluginTemaCatalogs.some((item) => normalizeText(item.id) === previousTarget)) targetSelect.value = previousTarget;
    else if (pluginTemaCatalogs.length) {
      targetSelect.value = pluginTemaCatalogs[0].id;
    }

    UI.comparison.sourcesLoaded = true;
    if (notice) notice.textContent = `${savedCatalogs.length} catálogo(s) salvo(s) e ${pluginTemaCatalogs.length} catálogo(s) PluginTema disponíveis.`;
    appendComparisonLog(`${savedCatalogs.length} catálogo(s) de origem e ${pluginTemaCatalogs.length} catálogo(s) PluginTema carregados.`);
    restoreComparisonCache();
  } catch (error) {
    if (notice) notice.textContent = `Falha ao carregar catálogos: ${normalizeText(error?.message, "erro desconhecido")}`;
    console.error("[panel.js] Falha ao carregar fontes:", error);
    appendComparisonLog(`Falha ao carregar catálogos: ${normalizeText(error?.message, "erro desconhecido")}.`, "ERRO");
  } finally {
    sourceSelect.disabled = false;
    targetSelect.disabled = false;
    if (reloadButton) { reloadButton.disabled = false; reloadButton.textContent = "Atualizar lista"; }
  }
}

function comparisonStatusClass(status) {
  const value = normalizeText(status).toLowerCase();
  if (value === "updated") return "is-success";
  if (value === "update_available" || value === "site_ahead") return "is-warning";
  if (value === "new_source") return "is-accent";
  if (["site_only", "version_review"].includes(value)) return "is-danger";
  return "";
}

function comparisonDecisionClass(decision) {
  const value = normalizeText(decision).toLowerCase();
  if (["approve_update", "approve_new_product", "same_product"].includes(value)) return "is-success";
  if (value === "review_later") return "is-warning";
  if (["ignore", "different_products"].includes(value)) return "is-danger";
  return "";
}


function comparisonMethodLabel(method) {
  const value = normalizeText(method).toLowerCase();
  if (value === "official_url") return "URL oficial";
  if (value === "normalized_name") return "Nome normalizado";
  return "Sem correspondência";
}

async function saveComparisonRelationship(payload) {
  const result = await postJson(
    UI.endpoints.comparisonRelationshipSave
      || "/comparacao/vinculo/salvar",

 Object.assign(
  {
    operator: "local",
    relationship_state: "manual_confirmed",
    note: "Relacionamento salvo manualmente pelo painel.",
    source_id: normalizeText(byId("comparison_source_catalog")?.value),
    target_id: normalizeText(byId("comparison_target_catalog")?.value),
  },
  payload || {}
)

  );

  if (result?.ok === false) {
    throw new Error(
      normalizeText(
        result?.message,
        "Falha ao salvar o relacionamento."
      )
    );
  }

  notify(
   result?.message
|| "Relacionamento salvo com sucesso."
  );

  await refreshComparison({
    force: true,
    page: UI.comparison.page,
  });

  return result;
}


async function confirmSuggestedComparisonCandidate(
  itemId,
  sourceProductKey
) {
  const row = UI.comparison.rowsById?.[itemId];

  if (!row) {
    throw new Error(
      "Linha da comparação não encontrada."
    );
  }

  const candidate = (
    Array.isArray(row.match_candidates)
      ? row.match_candidates
      : []
  ).find(function (item) {
    return (
      normalizeText(item.source_product_key)
      === normalizeText(sourceProductKey)
    );
  });

  if (!candidate) {
    throw new Error(
      "Candidato não encontrado."
    );
  }

  const confirmed = window.confirm(
    'Confirmar "' +
    normalizeText(row.site_name, "produto PluginTema") +
    '" e "' +
    normalizeText(candidate.source_name, "produto Ultrapack") +
    '" como o mesmo produto?'
  );

  if (!confirmed) return;

    return saveComparisonRelationship({

    relationship_state: "manual_confirmed",

    site_product_key: row.site_product_key,
    source_product_key:
      candidate.source_product_key,

    site_id: row.site_id || "",
    site_name: row.site_name || "",
    site_official_url:
      row.site_official_url || "",

    source_name:
      candidate.source_name || "",
    source_product_url:
      candidate.source_product_url || "",
    source_official_url:
      candidate.source_official_url || "",
  });
}

async function rejectSuggestedComparisonCandidate(
  itemId,
  sourceProductKey
) {
  const row = UI.comparison.rowsById?.[itemId];

  if (!row) {
    throw new Error(
      "Linha da comparação não encontrada."
    );
  }

  const candidate = (
    Array.isArray(row.match_candidates)
      ? row.match_candidates
      : []
  ).find(function (item) {
    return (
      normalizeText(item.source_product_key)
      === normalizeText(sourceProductKey)
    );
  });

  if (!candidate) {
    throw new Error(
      "Candidato não encontrado."
    );
  }

  const confirmed = window.confirm(
    'Rejeitar a correspondência entre "' +
    normalizeText(
      row.site_name,
      "produto PluginTema"
    ) +
    '" e "' +
    normalizeText(
      candidate.source_name,
      "produto Ultrapack"
    ) +
    '"?\n\nEsse candidato não será sugerido novamente para este produto.'
  );

  if (!confirmed) return;

  return saveComparisonRelationship({
    relationship_state: "manual_rejected",

    site_product_key:
      row.site_product_key,

    source_product_key:
      candidate.source_product_key,

    site_id:
      row.site_id || "",

    site_name:
      row.site_name || "",

    site_official_url:
      row.site_official_url || "",

    source_name:
      candidate.source_name || "",

    source_product_url:
      candidate.source_product_url || "",

    source_official_url:
      candidate.source_official_url || "",

    note:
      "Candidato rejeitado manualmente pelo painel.",
  });
}

async function searchComparisonLinkProducts(
  itemId,
  query
) {

  const row = UI.comparison.rowsById?.[itemId];

  if (!row) {
    throw new Error(
      "Linha da comparação não encontrada."
    );
  }

  const sourceId = normalizeText(
    byId("comparison_source_catalog")?.value
  );

  const targetId = normalizeText(
    byId("comparison_target_catalog")?.value
  );

  let role = "";

  if (
    normalizeText(row.site_product_key)
    && !normalizeText(row.source_product_key)
  ) {
    role = "source";
  } else if (
    normalizeText(row.source_product_key)
    && !normalizeText(row.site_product_key)
  ) {
    role = "site";
  }

  if (!role) {
    throw new Error(
      "Esta linha já possui os dois produtos associados."
    );
  }

  const params = new URLSearchParams({
    source_id: sourceId,
    target_id: targetId,
    role,
    q: normalizeText(query),
  });

  const result = await getJson(
    (
      UI.endpoints.comparisonProducts
      || "/comparacao/produtos"
    )
    + "?"
    + params.toString()
  );

  if (result?.ok === false) {
    throw new Error(
      normalizeText(
        result?.message,
        "Falha ao buscar produtos."
      )
    );
  }

  return {
    role,
    products: Array.isArray(result?.products)
      ? result.products
      : [],
  };
}


async function confirmManualComparisonRelationship(
  itemId,
  selectedProduct,
  relationshipState = "manual_confirmed"
) {
  const row = UI.comparison.rowsById?.[itemId];

  if (!row) {
    throw new Error(
      "Linha da comparação não encontrada."
    );
  }

  const selected = selectedProduct || {};
  const selectedRole = normalizeText(
    selected.role
  );

  let payload;

  if (selectedRole === "source") {
    payload = {
      site_product_key:
        row.site_product_key,
      source_product_key:
        selected.product_key,

      site_id:
        row.site_id || "",
      site_name:
        row.site_name || "",
      site_official_url:
        row.site_official_url || "",

      source_name:
        selected.name || "",
      source_product_url:
        selected.product_url || "",
      source_official_url:
        selected.official_url || "",
    };

  } else if (selectedRole === "site") {
    payload = {
      site_product_key:
        selected.product_key,
      source_product_key:
        row.source_product_key,

      site_id:
        selected.site_id || "",
      site_name:
        selected.name || "",
      site_official_url:
        selected.official_url || "",

      source_name:
        row.source_name || "",
      source_product_url:
        row.source_product_url || "",
      source_official_url:
        row.source_official_url || "",
    };

  } else {
    throw new Error(
      "Produto selecionado inválido."
    );
  }

  const isRejection = relationshipState === "manual_rejected";
  const confirmed = window.confirm(isRejection
    ? "Rejeitar este candidato e registrar que os produtos são diferentes?"
    : "Confirmar vínculo e definir que estes registros representam o mesmo produto?\n\nSe um deles já tiver outro vínculo manual confirmado, o vínculo anterior será substituído."
  );

  if (!confirmed) return;

  return saveComparisonRelationship(Object.assign(payload, {
    relationship_state: relationshipState,
    note: isRejection
      ? "Candidato rejeitado manualmente pelo modal."
      : "Vínculo confirmado manualmente pelo modal.",
  }));
}

function showCatalogoContexts(slotName) {
  const filter = byId("catalogos_filter_slot");
  const search = byId("catalogos_search");
  const normalizedSlot = normalizeText(slotName);
  const isAlreadyActive = normalizeText(filter?.value) === normalizedSlot;
  if (filter) filter.value = isAlreadyActive ? "" : normalizedSlot;
  if (search) search.value = "";
  UI.catalogPage = 1;
  refreshCatalogos();
  byId("catalogos_table_body")?.closest(".table-wrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function closePluginTemaUpdateModal() {
  const modal = byId("plugintema_update_modal");
  if (modal) modal.classList.add("hidden");
}

async function openPluginTemaUpdateModal() {
  const modal = byId("plugintema_update_modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  const status = byId("plugintema_update_status");
  if (status) { status.classList.remove("is-success","is-danger"); status.classList.add("is-loading"); status.setAttribute("aria-busy","true"); status.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span><span><strong>Carregando opções...</strong><br>Aguarde enquanto consultamos as categorias do WooCommerce.</span>'; }
  try {
    const payload = await getJson(UI.endpoints.plugintemaCatalogOptions || "/plugintema/catalogo/opcoes");
    const categories = Array.isArray(payload?.categories) ? payload.categories : [];
    const select = byId("plugintema_custom_categories");
    if (select) select.innerHTML = categories.map((item) => `<option value="${escapeHtml(normalizeText(item?.name))}">${escapeHtml(normalizeText(item?.name))}</option>`).join("");
    if (status) { status.classList.remove("is-loading"); status.setAttribute("aria-busy","false"); status.textContent = "Pronto para atualizar."; }
  } catch (error) {
    if (status) { status.classList.remove("is-loading"); status.classList.add("is-danger"); status.setAttribute("aria-busy","false"); status.textContent = `Falha ao carregar categorias: ${normalizeText(error?.message)}`; }
  }
  syncPluginTemaCatalogMode();
  byId("plugintema_update_submit")?.focus();
}

function pluginTemaUpdatePayload() {
  const custom = Boolean(qs('input[name="plugintema_custom_mode"]:checked'));
  const presetKinds = qsa('input[name="plugintema_preset_kind"]:checked').map((input) => input.value);
  if (!custom && !presetKinds.length) throw new Error("Selecione Plugins, Temas ou Templates.");
  return {
    mode: custom ? "custom" : "selection",
    kinds: presetKinds,
    catalog_name: byId("plugintema_custom_name")?.value || "",
    kind: byId("plugintema_custom_kind")?.value || "plugin",
    status: byId("plugintema_custom_status")?.value || "publish",
    categories: Array.from(byId("plugintema_custom_categories")?.selectedOptions || []).map((option) => option.value),
    query: byId("plugintema_custom_query")?.value || "",
    product_ids: [
      byId("plugintema_custom_ids")?.value || "",
      Array.from(UI.plugintemaSelectedProducts.keys()).join(","),
    ].filter(Boolean).join(","),
    version: byId("plugintema_custom_version")?.value || "all",
  };

}

function syncPluginTemaCatalogMode(changedInput = null) {
  const customInput = qs('input[name="plugintema_custom_mode"]');
  const presetInputs = qsa('input[name="plugintema_preset_kind"]');
  if (changedInput?.name === "plugintema_custom_mode" && changedInput.checked) {
    presetInputs.forEach((input) => { input.checked = false; });
  } else if (changedInput?.name === "plugintema_preset_kind") {
    if (changedInput.checked && customInput) customInput.checked = false;
  }
  const custom = Boolean(customInput?.checked);
  byId("plugintema_custom_filters")?.classList.toggle("hidden", !custom);
  byId("plugintema_product_picker")?.classList.toggle("hidden", !custom);
}

function renderPluginTemaSelectedProducts() {
  const wrap = byId("plugintema_selected_products");
  const count = byId("plugintema_selected_count");
  const products = Array.from(UI.plugintemaSelectedProducts.values());
  if (count) count.textContent = `${products.length} item(ns)`;
  if (!wrap) return;
  wrap.innerHTML = products.length ? products.map((product) => `<div class="plugintema-picked-product"><span><strong>${escapeHtml(product.name)}</strong><small>#${escapeHtml(product.id)} · ${escapeHtml(product.kind === "theme" ? "Tema" : product.kind === "template" ? "Template" : "Plugin")}</small></span><button type="button" class="btn-secondary btn-sm" data-remove-plugintema-product="${escapeHtml(product.id)}" aria-label="Remover ${escapeHtml(product.name)}">×</button></div>`).join("") : '<div class="small">Nenhum item adicionado.</div>';
}

async function searchPluginTemaProducts() {
  const term = normalizeText(byId("plugintema_product_search")?.value);
  const wrap = byId("plugintema_search_results");
  if (!term) { if (wrap) wrap.innerHTML = '<div class="small">Digite um nome, termo ou ID.</div>'; return; }
  if (wrap) wrap.innerHTML = '<div class="small">Pesquisando no WooCommerce...</div>';
  try {
    const payload = await getJson(`${UI.endpoints.plugintemaProductSearch || "/plugintema/catalogo/pesquisar"}?q=${encodeURIComponent(term)}`);
    const products = Array.isArray(payload?.products) ? payload.products : [];
    if (wrap) wrap.innerHTML = products.length ? products.map((product) => `<div class="plugintema-search-product"><span><strong>${escapeHtml(product.name)}</strong><small>#${escapeHtml(product.id)} · ${escapeHtml(product.kind === "theme" ? "Tema" : product.kind === "template" ? "Template" : "Plugin")}</small></span><button type="button" class="btn-secondary btn-sm" data-add-plugintema-product='${escapeHtml(JSON.stringify(product))}'>Adicionar</button></div>`).join("") : '<div class="small">Nenhum plugin, tema ou template encontrado.</div>';
  } catch (error) {
    if (wrap) wrap.innerHTML = `<div class="notice">Falha na pesquisa: ${escapeHtml(normalizeText(error?.message))}</div>`;
  }
}

async function generatePluginTemaComparisonCatalog() {
  const button = byId("plugintema_update_submit");
  const status = byId("plugintema_update_status");
  const originalButtonText = button?.textContent || "Atualizar catálogo";
  if (button) { button.disabled = true; button.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span> Gerando catálogo...'; }
  try {
    if (status) { status.classList.remove("is-success","is-danger"); status.classList.add("is-loading"); status.setAttribute("aria-busy","true"); status.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span><span><strong>Gerando catálogo PluginTema...</strong><br>Aguarde enquanto consultamos e processamos os produtos do WooCommerce.</span>'; }
    const result = await postJson(
      UI.endpoints.plugintemaCatalogGenerate || "/plugintema/catalogo/gerar",
      pluginTemaUpdatePayload()
    );
    await loadComparisonSources({ preferredTarget: result.catalog_id });
    if (status) { status.classList.remove("is-loading"); status.classList.add("is-success"); status.setAttribute("aria-busy","false"); status.innerHTML = `<span class="loading-success-mark" aria-hidden="true">✓</span><span><strong>Catálogo concluído.</strong><br>${escapeHtml(result?.products_count ?? 0)} produtos foram processados com sucesso.</span>`; }
    await new Promise(resolve=>setTimeout(resolve,650));
    closePluginTemaUpdateModal();
    notify(result?.message || "Catálogo PluginTema atualizado.");
  } catch (error) {
    if (status) { status.classList.remove("is-loading"); status.classList.add("is-danger"); status.setAttribute("aria-busy","false"); status.textContent = `Falha ao gerar catálogo: ${normalizeText(error?.message, "erro desconhecido")}`; }
  } finally {
    if (button) { button.disabled = false; button.textContent = originalButtonText; }
  }
}

function closePluginTemaManageModal() {
  byId("plugintema_manage_modal")?.classList.add("hidden");
}

function renderPluginTemaManagedRows() {
  const query = normalizeText(byId("plugintema_manage_search")?.value).toLowerCase();
  const type = normalizeText(byId("plugintema_manage_type")?.value).toLowerCase();
  const status = normalizeText(byId("plugintema_manage_status")?.value).toLowerCase();
  const catalogKind = (row) => {
    const categories = normalizeText(row.Categorias).toLowerCase();
    if (/\btemplates?\b|\bmodelos?\b/.test(categories)) return "template";
    if (/\btemas?\b|\bthemes?\b/.test(categories)) return "theme";
    if (/\bplugins?\b/.test(categories)) return "plugin";
    return "";
  };
  const rows = UI.plugintemaManageRows.filter((row) =>
    (!query || Object.values(row).join(" ").toLowerCase().includes(query))
    && (!type || catalogKind(row) === type)
    && (!status || normalizeText(row.Status).toLowerCase() === status)
  );
  const requestedPageSize = byId("plugintema_manage_page_size")?.value || UI.plugintemaManagePageSize;
  const pageSize = normalizeListingPageSize(requestedPageSize, LISTING_DEFAULT_PAGE_SIZE);
  UI.plugintemaManagePageSize = pageSize;
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  UI.plugintemaManagePage = Math.min(Math.max(1, UI.plugintemaManagePage), totalPages);
  const pageRows = rows.slice((UI.plugintemaManagePage - 1) * pageSize, UI.plugintemaManagePage * pageSize);
  const body = byId("plugintema_manage_rows");
  if (byId("plugintema_manage_count")) byId("plugintema_manage_count").textContent = `${rows.length} item(ns)`;
  const rangeStart = rows.length ? ((UI.plugintemaManagePage - 1) * pageSize) + 1 : 0;
  const rangeEnd = Math.min(UI.plugintemaManagePage * pageSize, rows.length);
  if (byId("plugintema_manage_range")) byId("plugintema_manage_range").textContent = listingRangeText(rows.length, UI.plugintemaManagePage, pageSize);
  if (byId("plugintema_manage_page_status")) byId("plugintema_manage_page_status").textContent = `Página ${UI.plugintemaManagePage} de ${totalPages}`;
  if (byId("plugintema_manage_prev")) byId("plugintema_manage_prev").disabled = UI.plugintemaManagePage <= 1;
  if (byId("plugintema_manage_next")) byId("plugintema_manage_next").disabled = UI.plugintemaManagePage >= totalPages;
  if (!body) return;
  body.innerHTML = pageRows.length ? pageRows.map((row) => `<tr><td>${escapeHtml(row.ID)}</td><td>${escapeHtml(row.Nome)}</td><td>${escapeHtml(catalogKind(row) === "theme" ? "Tema" : catalogKind(row) === "template" ? "Template" : catalogKind(row) === "plugin" ? "Plugin" : row.Tipo)}</td><td>${escapeHtml(row["Metadado: pt_versao"])}</td><td>${escapeHtml(row.Categorias)}</td><td>${escapeHtml(row.Status)}</td></tr>`).join("") : '<tr><td colspan="6">Nenhum item encontrado.</td></tr>';
}

function renderPluginTemaCatalogCards(catalogs, selectedId) {
  const wrap = byId("plugintema_manage_catalog_cards");
  if (!wrap) return;
  wrap.innerHTML = catalogs.length ? catalogs.map((item) => `
    <article class="plugintema-catalog-card${normalizeText(item.id) === selectedId ? " is-selected" : ""}" data-plugintema-catalog-id="${escapeHtml(item.id)}">
      <div class="plugintema-catalog-card-head"><strong>${escapeHtml(item.label)}</strong><span class="badge">${escapeHtml(item.items_count || 0)} itens</span></div>
      <div class="plugintema-catalog-counts"><span>Plugins <strong>${escapeHtml(item.plugin_count || 0)}</strong></span><span>Temas <strong>${escapeHtml(item.theme_count || 0)}</strong></span><span>Templates <strong>${escapeHtml(item.template_count || 0)}</strong></span></div>
      <div class="small">Atualizado em ${escapeHtml(item.updated_at || "-")}</div>
      <div class="plugintema-catalog-actions">
        <button class="btn-success btn-sm" type="button" data-catalog-action="select">📂 Selecionar</button>
        <button class="btn-secondary btn-sm" type="button" data-catalog-action="download">⬇️ Baixar</button>
        <button class="btn-secondary btn-sm" type="button" data-catalog-action="rename">✏️ Renomear</button>
        <button class="btn-danger btn-sm" type="button" data-catalog-action="delete">🗑️ Apagar</button>
      </div>
    </article>`).join("") : '<div class="notice">Nenhum catálogo PluginTema disponível.</div>';
}

async function loadPluginTemaManagedCatalog(catalogId = "") {
  const select = byId("plugintema_manage_catalog");
  const id = catalogId || normalizeText(select?.value);
  const suffix = id ? `?catalog_id=${encodeURIComponent(id)}` : "";
  const payload = await getJson(`${UI.endpoints.plugintemaCatalogManage || "/plugintema/catalogo/gerenciar"}${suffix}`);
  const catalogs = Array.isArray(payload?.catalogs) ? payload.catalogs : [];
  UI.plugintemaManageCatalogs = catalogs;
  const selectedId = id || normalizeText(select?.value) || normalizeText(catalogs[0]?.id);
  renderPluginTemaCatalogCards(catalogs, selectedId);
  if (select) {
    const selected = id || normalizeText(select.value);
    select.innerHTML = catalogs.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
    if (catalogs.some((item) => item.id === selected)) select.value = selected;
  }
  if (!id && catalogs.length) return loadPluginTemaManagedCatalog(catalogs[0].id);
  UI.plugintemaManageRows = Array.isArray(payload?.rows) ? payload.rows : [];
  UI.plugintemaManagePage = 1;
  renderPluginTemaManagedRows();
  if (byId("plugintema_manage_delete")) byId("plugintema_manage_delete").disabled = !id;
  if (byId("plugintema_manage_download")) byId("plugintema_manage_download").disabled = !id;
}

async function renamePluginTemaManagedCatalog(catalogId) {
  const current = UI.plugintemaManageCatalogs?.find((item) => normalizeText(item.id) === catalogId);
  const name = window.prompt("Novo nome do catálogo:", normalizeText(current?.label).replace(/ atualizados em .*$/, ""));
  if (!normalizeText(name)) return;
  const result = await postJson(UI.endpoints.plugintemaCatalogManage || "/plugintema/catalogo/gerenciar", {catalog_id: catalogId, action: "rename", name});
  await loadComparisonSources({preferredTarget: result.catalog_id});
  await loadPluginTemaManagedCatalog(result.catalog_id);
  notify(result?.message || "Catálogo renomeado.", "ok");
}

function downloadPluginTemaManagedCatalog() {
  const catalogId = normalizeText(byId("plugintema_manage_catalog")?.value);
  if (!catalogId) return;
  const endpoint = UI.endpoints.plugintemaCatalogDownload || "/plugintema/catalogo/baixar";
  window.location.href = `${endpoint}?catalog_id=${encodeURIComponent(catalogId)}`;
}

async function openPluginTemaManageModal() {
  const modal = byId("plugintema_manage_modal");
  const card = modal?.querySelector(".plugintema-manage-modal-card");
  modal?.classList.remove("hidden");
  modal?.setAttribute("aria-busy", "true");
  const overlay = document.createElement("div");
  overlay.className = "modal-loading-overlay";
  overlay.setAttribute("role", "status");
  overlay.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando catálogos e produtos...</span>';
  card?.appendChild(overlay);
  if (byId("plugintema_manage_catalog_cards")) byId("plugintema_manage_catalog_cards").innerHTML = '<div class="modal-inline-loading" role="status"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando catálogos PluginTema...</span></div>';
  if (byId("plugintema_manage_rows")) byId("plugintema_manage_rows").innerHTML = '<tr><td colspan="6"><span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando itens...</span></span></td></tr>';
  try { await loadPluginTemaManagedCatalog(); }
  catch (error) { notify(normalizeText(error?.message, "Falha ao carregar catÃ¡logos PluginTema.")); }
  finally { overlay.remove(); modal?.setAttribute("aria-busy", "false"); }
}

async function deletePluginTemaManagedCatalog() {
  const select = byId("plugintema_manage_catalog");
  const catalogId = normalizeText(select?.value);
  const label = normalizeText(select?.selectedOptions?.[0]?.textContent, "catÃ¡logo selecionado");
  if (!catalogId || !window.confirm(`Apagar o catÃ¡logo "${label}"?`)) return;
  try {
    const result = await postJson(UI.endpoints.plugintemaCatalogManage || "/plugintema/catalogo/gerenciar", { catalog_id: catalogId });
    notify(result?.message || "Catálogo apagado.");
    await loadComparisonSources();
    await loadPluginTemaManagedCatalog();
  } catch (error) { notify(normalizeText(error?.message, "Falha ao apagar catÃ¡logo.")); }
}

function closeCatalogosModal() {
  const modal = byId("tab_panel_catalogos");
  if (!modal) return;
  modal.classList.add("hidden");
  byId("open_catalogos_modal_btn")?.focus();
}

async function openCatalogosModal() {
  const modal = byId("tab_panel_catalogos");
  if (!modal) return;
  modal.classList.remove("hidden");
  await refreshCatalogos({ showLoading: true });
  modal.querySelector("button, select, input")?.focus();
}

function organizeCollectionUi() {
  const principal = byId("tab_panel_principal");
  const catalogModal = byId("tab_panel_catalogos");
  const queuePanel = byId("tab_panel_fila");
  const operationsGroup = byId("collection_operations_group");

  if (catalogModal && !catalogModal.dataset.organized) {
    catalogModal.dataset.organized = "1";
    catalogModal.className = "collection-modal hidden";
    catalogModal.setAttribute("role", "dialog");
    catalogModal.setAttribute("aria-modal", "true");
    catalogModal.setAttribute("aria-labelledby", "catalogos_modal_title");
    const card = catalogModal.querySelector(":scope > .card");
    card?.classList.add("collection-modal-card");
    const title = card?.querySelector(".section-title");
    if (title) title.id = "catalogos_modal_title";
    const backdrop = document.createElement("div");
    backdrop.className = "collection-modal-backdrop";
    backdrop.addEventListener("click", closeCatalogosModal);
    catalogModal.prepend(backdrop);
    const close = document.createElement("button");
    close.type = "button";
    close.className = "comparison-link-modal-close collection-modal-close";
    close.setAttribute("aria-label", "Fechar ferramentas de catálogos");
    close.textContent = "×";
    close.addEventListener("click", closeCatalogosModal);
    card?.prepend(close);

  }

  if (principal && queuePanel && !queuePanel.dataset.organized) {
    queuePanel.dataset.organized = "1";
    const sourceCard = queuePanel.querySelector(":scope > .card");
    const details = document.createElement("details");
    details.className = "card runs-manager-card collect-queue-accordion";
    const summary = document.createElement("summary");
    summary.className = "runs-manager-header";
    summary.innerHTML = '<span><strong>Fila</strong><span class="small"> Encadeamento automático entre catálogos e contextos</span></span><span class="runs-manager-chevron" aria-hidden="true"></span>';
    const content = document.createElement("div");
    content.className = "runs-manager-content collect-queue-content";
    while (sourceCard?.firstChild) content.appendChild(sourceCard.firstChild);
    details.append(summary, content);
    details.addEventListener("toggle", () => {
      if (details.open && !details.dataset.loaded) {
        details.dataset.loaded = "1";
        refreshFila();
      }
    });
    (operationsGroup || principal).appendChild(details);
    queuePanel.remove();
  }

  const results = byId("comparison_results_card");
  const filters = qs(".comparison-filter-grid");
  const actions = qs(".comparison-actions-grid");
  const bulk = byId("comparison_bulk_toolbar");
  if (results && bulk && filters && actions && filters.parentElement !== results) {
    filters.classList.add("comparison-results-filter-row");
    actions.classList.add("comparison-results-action-row");
    results.insertBefore(filters, bulk);
    results.insertBefore(actions, bulk);
  }
}

function comparisonModalProductLinks(product) {
  const productUrl = normalizeText(product?.product_url || product?.source_product_url);
  const officialUrl = normalizeText(product?.official_url || product?.source_official_url || product?.site_official_url);
  const links = [];
  if (productUrl) links.push(`<a href="${escapeHtml(productUrl)}" target="_blank" rel="noopener noreferrer">Abrir produto</a>`);
  if (officialUrl) links.push(`<a href="${escapeHtml(officialUrl)}" target="_blank" rel="noopener noreferrer">Abrir URL oficial</a>`);
  return links.length ? `<div class="comparison-link-result-links">${links.join("")}</div>` : "";
}

function comparisonModalCandidateHtml(product, itemId, { suggested = false } = {}) {
  const score = suggested ? `<span class="badge">${Math.max(0, toInt(product?.match_score, 0))}%</span>` : "";
  const normalized = suggested ? {
    role: "source",
    product_key: product?.source_product_key,
    name: product?.source_name,
    version: product?.source_version,
    category: product?.source_category,
    product_url: product?.source_product_url,
    official_url: product?.source_official_url,
  } : product;
  const encoded = escapeHtml(JSON.stringify(normalized || {}));
  return `<article class="comparison-link-result">
    <div class="comparison-link-result-info">
      <div class="comparison-candidate-head"><strong>${escapeHtml(normalizeText(normalized?.name, "Produto sem nome"))}</strong>${score}</div>
      <div class="comparison-cell-meta">Versão: ${escapeHtml(normalizeText(normalized?.version, "-"))}</div>
      <div class="comparison-cell-meta">Categoria: ${escapeHtml(normalizeText(normalized?.category, "-"))}</div>
      ${comparisonModalProductLinks(normalized)}
    </div>
    <div class="comparison-link-result-actions">
      <button type="button" class="btn-success comparison-modal-confirm" data-comparison-item-id="${escapeHtml(itemId)}" data-product="${encoded}">Confirmar vínculo</button>
      <button type="button" class="btn-danger comparison-modal-reject" data-comparison-item-id="${escapeHtml(itemId)}" data-product="${encoded}">Rejeitar candidato</button>
    </div>
  </article>`;
}

function setComparisonModalStatus(message, type = "info") {
  const node = byId("comparison_link_modal_status");
  if (!node) return;
  node.className = `comparison-link-modal-status is-${type}`;
  node.textContent = normalizeText(message);
  node.hidden = !normalizeText(message);
}

function comparisonDiagnosticField(label, value, { html = false } = {}) {
  const content = html ? value : escapeHtml(normalizeText(value, "Não informado"));
  return `<div class="comparison-diagnostic-field"><dt>${escapeHtml(label)}</dt><dd>${content}</dd></div>`;
}

function closeComparisonDiagnosticModal() {
  const modal = byId("comparison_diagnostic_modal");
  if (!modal || modal.classList.contains("hidden")) return;
  const state = UI.comparison.diagnosticModal;
  modal.classList.add("hidden");
  if (byId("comparison_link_modal")?.classList.contains("hidden")) {
    document.body.classList.remove("comparison-modal-open");
  }
  const opener = state.opener;
  state.itemId = "";
  state.opener = null;
  if (opener && document.contains(opener)) opener.focus();
}

function openComparisonDiagnosticModal(itemId, opener) {
  const row = UI.comparison.rowsById?.[itemId];
  const modal = byId("comparison_diagnostic_modal");
  if (!row || !modal) throw new Error("Linha da comparação não encontrada.");
  const state = UI.comparison.diagnosticModal;
  state.itemId = itemId;
  state.opener = opener || document.activeElement;
  const candidates = Array.isArray(row.match_candidates) ? row.match_candidates : [];
  const candidate = candidates[0] || {};
  const favorable = Array.isArray(row.match_favorable_signals) && row.match_favorable_signals.length
    ? row.match_favorable_signals.join(" / ") : "Nenhum sinal favorável informado.";
  const conflicting = Array.isArray(row.match_conflicting_signals) && row.match_conflicting_signals.length
    ? row.match_conflicting_signals.join(" / ") : "Nenhum sinal conflitante identificado.";
  const productLink = (url, label) => normalizeText(url)
    ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
    : "Não informado";
  const candidateDescription = normalizeText(candidate.source_name)
    ? `${normalizeText(candidate.source_name)} · ${Math.max(0, toInt(candidate.match_score, 0))}% · ${normalizeText(candidate.match_level_label, "Sem nível")}`
    : "Nenhum candidato aproximado";
  const candidatesDescription = candidates.length ? candidates.map((item, index) =>
    `${index + 1}. ${normalizeText(item.source_name, "-")} · ${Math.max(0, toInt(item.match_score, 0))}% · ${normalizeText(item.match_level_label, "Sem nível")}`
  ).join(" / ") : "Nenhum candidato aproximado encontrado.";
  const disputedDescription = candidates.some((item) => Boolean(item.is_disputed))
    ? "Há candidato também sugerido para outro produto da PluginTema."
    : "Nenhum candidato disputado nesta linha.";
  const confidence = { high: "Alta", medium: "Média", low: "Baixa", none: "Sem correspondência" }[normalizeText(row.match_confidence, "none")] || normalizeText(row.match_confidence, "none");

  byId("comparison_diagnostic_modal_subtitle").textContent = [row.site_name, row.source_name].map((value) => normalizeText(value)).filter(Boolean).join(" × ") || "Linha selecionada";
  byId("comparison_diagnostic_modal_content").innerHTML = `
    <section class="comparison-diagnostic-section"><h3>Situação e recomendação</h3><dl class="comparison-diagnostic-grid">
      ${comparisonDiagnosticField("Situação", normalizeText(row.status_label, row.status))}
      ${comparisonDiagnosticField("Motivo da situação", row.status_reason)}
      ${comparisonDiagnosticField("Recomendação", row.recommended_action_label)}
      ${comparisonDiagnosticField("Decisão atual", normalizeText(row.decision_label, "Pendente"))}
    </dl></section>
    <section class="comparison-diagnostic-section"><h3>Produtos e versões</h3><dl class="comparison-diagnostic-grid">
      ${comparisonDiagnosticField("Produto PluginTema", row.site_name)}
      ${comparisonDiagnosticField("Produto da origem", row.source_name)}
      ${comparisonDiagnosticField("Versão PluginTema", normalizeText(row.site_version) || "Não informada")}
      ${comparisonDiagnosticField("Qualidade PluginTema", `${normalizeText(row.site_version_quality, "-")} — ${normalizeText(row.site_version_reason, "Motivo não informado.")}`)}
      ${comparisonDiagnosticField("Versão da origem", normalizeText(row.source_version) || "Não informada")}
      ${comparisonDiagnosticField("Qualidade da origem", `${normalizeText(row.source_version_quality, "-")} — ${normalizeText(row.source_version_reason, "Motivo não informado.")}`)}
      ${comparisonDiagnosticField("Categoria PluginTema", row.site_categories)}
      ${comparisonDiagnosticField("Categoria da origem", row.source_category)}
    </dl></section>
    <section class="comparison-diagnostic-section"><h3>Correspondência</h3><dl class="comparison-diagnostic-grid">
      ${comparisonDiagnosticField("Candidato principal", candidateDescription)}
      ${comparisonDiagnosticField("Candidatos aproximados", candidatesDescription)}
      ${comparisonDiagnosticField("Candidato disputado", disputedDescription)}
      ${comparisonDiagnosticField("Método", normalizeText(row.match_method_label, comparisonMethodLabel(row.match_method)))}
      ${comparisonDiagnosticField("Confiança", confidence)}
      ${comparisonDiagnosticField("Nível", row.match_level_label)}
      ${comparisonDiagnosticField("Pontuação", `${Math.max(0, toInt(row.match_score, 0))}%`)}
      ${comparisonDiagnosticField("Motivo da correspondência", favorable)}
      ${comparisonDiagnosticField("Sinais favoráveis", favorable)}
      ${comparisonDiagnosticField("Conflitos ou sinais", conflicting)}
    </dl></section>
    <section class="comparison-diagnostic-section"><h3>Links dos produtos</h3><dl class="comparison-diagnostic-grid">
      ${comparisonDiagnosticField("PluginTema oficial", productLink(row.site_official_url, "Abrir URL oficial"), { html: true })}
      ${comparisonDiagnosticField("Origem", productLink(row.source_product_url, "Abrir produto"), { html: true })}
      ${comparisonDiagnosticField("Site oficial da origem", productLink(row.source_official_url, "Abrir URL oficial"), { html: true })}
      ${comparisonDiagnosticField("Candidato principal", productLink(candidate.source_product_url, "Abrir candidato"), { html: true })}
    </dl></section>`;
  modal.classList.remove("hidden");
  document.body.classList.add("comparison-modal-open");
  modal.focus();
}

function trapComparisonModalFocus(event, modal) {
  if (event.key !== "Tab") return;
  const focusable = qsa('button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]', modal);
  if (!focusable.length) { event.preventDefault(); modal.focus(); return; }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function closeComparisonLinkModal() {
  const modal = byId("comparison_link_modal");
  if (!modal || modal.classList.contains("hidden")) return;
  const state = UI.comparison.linkModal;
  clearTimeout(state.searchTimer);
  state.searchSequence += 1;
  modal.classList.add("hidden");
  if (byId("comparison_diagnostic_modal")?.classList.contains("hidden")) {
    document.body.classList.remove("comparison-modal-open");
  }
  const opener = state.opener;
  state.itemId = "";
  state.opener = null;
  state.saving = false;
  if (opener && document.contains(opener)) opener.focus();
}

function openComparisonLinkModal(itemId, opener) {
  const row = UI.comparison.rowsById?.[itemId];
  const modal = byId("comparison_link_modal");
  if (!row || !modal) throw new Error("Linha da comparação não encontrada.");
  const state = UI.comparison.linkModal;
  state.itemId = itemId;
  state.opener = opener || document.activeElement;
  state.saving = false;
  const activeIsSite = !!normalizeText(row.site_product_key);
  const name = activeIsSite ? row.site_name : row.source_name;
  const version = activeIsSite ? row.site_version : row.source_version;
  const category = activeIsSite ? row.site_categories : row.source_category;
  const product = activeIsSite
    ? { official_url: row.site_official_url }
    : { product_url: row.source_product_url, official_url: row.source_official_url };
  byId("comparison_link_modal_product").innerHTML = `<strong>${escapeHtml(normalizeText(name, "Produto selecionado"))}</strong><div>Versão: ${escapeHtml(normalizeText(version, "-"))} · Categoria: ${escapeHtml(normalizeText(category, "-"))}</div>${comparisonModalProductLinks(product)}`;
  const candidates = Array.isArray(row.match_candidates) ? row.match_candidates : [];
  byId("comparison_link_modal_suggestions").innerHTML = candidates.length
    ? candidates.map((candidate) => comparisonModalCandidateHtml(candidate, itemId, { suggested: true })).join("")
    : '<div class="comparison-candidate-empty">Nenhum candidato aproximado encontrado.</div>';
  const query = byId("comparison_link_modal_query");
  query.value = "";
  byId("comparison_link_modal_results").innerHTML = '<div class="comparison-candidate-empty">Digite um termo para localizar outro produto.</div>';
  setComparisonModalStatus("");
  modal.classList.remove("hidden");
  document.body.classList.add("comparison-modal-open");
  modal.focus();
}

async function runComparisonModalSearch() {
  const state = UI.comparison.linkModal;
  if (!state.itemId) return;
  const sequence = ++state.searchSequence;
  const results = byId("comparison_link_modal_results");
  const button = byId("comparison_link_modal_search");
  results.innerHTML = '<div class="comparison-link-loading modal-inline-loading" role="status"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Pesquisando produtos...</span></div>';
  button.disabled = true;
  setComparisonModalStatus("");
  try {
    const result = await searchComparisonLinkProducts(state.itemId, byId("comparison_link_modal_query")?.value || "");
    if (sequence !== state.searchSequence) return;
    results.innerHTML = result.products.length
      ? result.products.map((product) => comparisonModalCandidateHtml(product, state.itemId)).join("")
      : '<div class="comparison-candidate-empty">Nenhum produto encontrado para esta pesquisa.</div>';
  } catch (error) {
    if (sequence !== state.searchSequence) return;
    results.innerHTML = '<div class="comparison-candidate-empty">Não foi possível carregar os resultados.</div>';
    setComparisonModalStatus(normalizeText(error?.message, "Falha ao pesquisar produtos."), "error");
  } finally {
    if (sequence === state.searchSequence) button.disabled = false;
  }
}

async function handleComparisonModalRelationship(button, stateName) {
  const state = UI.comparison.linkModal;
  if (state.saving) return;
  let product;
  try { product = JSON.parse(button.dataset.product || "{}"); }
  catch (_error) { throw new Error("Dados do produto selecionado inválidos."); }
  state.saving = true;
  qsa(".comparison-modal-confirm, .comparison-modal-reject").forEach((node) => { node.disabled = true; });
  setComparisonModalStatus(stateName === "manual_confirmed" ? "Salvando vínculo..." : "Registrando rejeição...", "loading");
  try {
    const result = await confirmManualComparisonRelationship(state.itemId, product, stateName);
    if (!result) return;
    setComparisonModalStatus(result?.message || "Relacionamento atualizado.", "success");
    if (stateName === "manual_confirmed") closeComparisonLinkModal();
    else {
      const itemId = state.itemId;
      const opener = state.opener;
      openComparisonLinkModal(itemId, opener);
      setComparisonModalStatus(result?.message || "Candidato rejeitado.", "success");
    }
  } catch (error) {
    setComparisonModalStatus(normalizeText(error?.message, "Falha ao salvar o relacionamento."), "error");
    throw error;
  } finally {
    state.saving = false;
    qsa(".comparison-modal-confirm, .comparison-modal-reject").forEach((node) => { node.disabled = false; });
  }
}

function renderComparison(payload) {
  const summary = payload?.summary || {};
  const reconciliation =
  summary?.reconciliation &&
  typeof summary.reconciliation === "object"
    ? summary.reconciliation
    : {};
  const counts = summary?.counts || {};
  const candidateMetrics = summary?.candidate_metrics || {};
  const decisionSummary = summary?.decision_summary || {};
  const decisionCounts = decisionSummary?.counts || {};
  const savedDecisionSummary = summary?.saved_decision_summary || {};
  const pagination = payload?.pagination || {};
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  UI.comparison.lastPayload = payload;
  UI.comparison.loaded = true;
  UI.comparison.page = Math.max(1, toInt(pagination.page, 1));
  UI.comparison.pageSize = Math.max(1, toInt(pagination.page_size, 100));
  UI.comparison.totalPages = Math.max(1, toInt(pagination.total_pages, 1));

  showElement("comparison_summary_card", true);

  showElement("comparison_results_card", true);
  const values = {
    comparison_source_total: summary.source_total,
    comparison_site_total: summary.site_total,
    comparison_matched_total: summary.matched_total,
    comparison_update_total: counts.update_available,
    comparison_updated_total: counts.updated,
    comparison_review_total: counts.version_review,
    comparison_new_source_total: counts.new_source,
    comparison_site_only_total: counts.site_only,
    comparison_site_version_missing_total: counts.site_version_missing,
    comparison_source_version_missing_total: counts.source_version_missing,
    comparison_site_ahead_total: counts.site_ahead,
    comparison_match_url_total: summary?.match_method_counts?.official_url,
    comparison_match_name_total: summary?.match_method_counts?.normalized_name,
    comparison_suspicious_site_versions_total: summary.suspicious_site_versions,
    comparison_suspicious_source_versions_total: summary.suspicious_source_versions,
    comparison_missing_site_versions_total: summary.missing_site_versions,
    comparison_missing_source_versions_total: summary.missing_source_versions,
    comparison_candidate_rows_total: candidateMetrics.rows_with_candidates,
    comparison_candidate_none_total: candidateMetrics.rows_without_candidates,
    comparison_candidate_exact_total: candidateMetrics.exact_suggestions,
    comparison_candidate_probable_total: candidateMetrics.probable_suggestions,
    comparison_candidate_ambiguous_total: candidateMetrics.ambiguous_suggestions,
    comparison_candidate_total: candidateMetrics.total_candidates,
    comparison_decision_pending_total: decisionSummary.pending_total,
    comparison_decision_approved_total: decisionSummary.approved_total,
    comparison_decision_ignored_total: decisionSummary.ignored_total,
    comparison_decision_review_total: decisionSummary.review_total,
    comparison_decision_same_product_total: decisionCounts.same_product,
    comparison_decision_different_total: decisionCounts.different_products,
    comparison_decision_new_product_total: decisionCounts.approve_new_product,
    comparison_decision_saved_total: savedDecisionSummary.total,
  };
  Object.entries(values).forEach(([id, value]) => setText(id, value ?? 0, "0"));
  setText("comparison_missing_versions_total", Math.max(0, toInt(summary.missing_site_versions, 0)) + Math.max(0, toInt(summary.missing_source_versions, 0)), "0");

  const notice = byId("comparison_file_notice");
  if (notice) notice.innerHTML = `<strong>Arquivos carregados.</strong><br>Ultrapack: ${escapeHtml(normalizeText(summary.source_file, "arquivo não informado"))}<br>PluginTema: ${escapeHtml(normalizeText(summary.site_file, "arquivo não informado"))}<br>Versões do site com padrão suspeito de planilha: <strong>${escapeHtml(Math.max(0, toInt(summary.suspicious_site_versions, 0)))}</strong>`;

  const totalRows = Math.max(0, toInt(pagination.total_rows, 0));
  setText("comparison_result_meta", listingRangeText(totalRows, UI.comparison.page, UI.comparison.pageSize, "resultados"), "Mostrando 0 de 0 resultados");
  setText("comparison_page_label", `Página ${UI.comparison.page} de ${UI.comparison.totalPages}`, "Página 1 de 1");
  const prev = byId("comparison_prev_btn");
  const next = byId("comparison_next_btn");
  if (prev) prev.disabled = UI.comparison.page <= 1 || UI.comparison.loading;
  if (next) next.disabled = UI.comparison.page >= UI.comparison.totalPages || UI.comparison.loading;

  const reconciliationLabel = (
  calculated,
  expected,
  ok
) => {
  const symbol = ok ? "✓" : "✕";
  return `${calculated} de ${expected} ${symbol}`;
};

setText(
  "comparison_reconciliation_matches",
  reconciliationLabel(
    toInt(reconciliation.matched_status_total, 0),
    toInt(reconciliation.matched_total, 0),
    !!reconciliation.matched_ok
  ),
  "-"
);

setText(
  "comparison_reconciliation_source",
  reconciliationLabel(
    toInt(reconciliation.source_reconciled_total, 0),
    toInt(reconciliation.source_total, 0),
    !!reconciliation.source_ok
  ),
  "-"
);

setText(
  "comparison_reconciliation_site",
  reconciliationLabel(
    toInt(reconciliation.site_reconciled_total, 0),
    toInt(reconciliation.site_total, 0),
    !!reconciliation.site_ok
  ),
  "-"
);

setText(
  "comparison_reconciliation_methods",
  reconciliationLabel(
    toInt(reconciliation.match_method_total, 0),
    toInt(reconciliation.matched_total, 0),
    !!reconciliation.match_method_ok
  ),
  "-"
);

const wrap = byId("comparison_rows");
if (!wrap) return;

if (!rows.length) {
  UI.comparison.rowsById = {};
  wrap.innerHTML = '<tr><td colspan="7">Nenhum item encontrado com este filtro.</td></tr>';
  updateComparisonBulkControls();
  return;
}

  UI.comparison.rowsById = Object.fromEntries(
    rows.map(function (row) {
      return [normalizeText(row.comparison_item_id), row];
    })
  );
  rows.forEach((row) => {
    const itemId = normalizeText(row?.comparison_item_id);
    if (itemId && UI.comparison.selectedItemIds.has(itemId)) {
      UI.comparison.selectedRowsById[itemId] = row;
    }
  });

  wrap.innerHTML = rows.map((row) => {
    const status = normalizeText(row.status);
    const sourceUrl = normalizeText(row.source_product_url);
    const siteProductUrl = normalizeText(row.site_product_url) || (row.site_id ? `https://plugintema.com.br/?p=${encodeURIComponent(row.site_id)}` : "");
    const link = (url, label) => url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>` : "Não informada";
    const confidence = {high:"Alta", medium:"Média", low:"Baixa", none:"Sem correspondência"}[normalizeText(row.match_confidence, "none")] || normalizeText(row.match_confidence, "none");
    const matchScore = Math.max(0, toInt(row.match_score, 0));
    const matchLevel = normalizeText(row.match_level_label, "Sem correspondência");
    const matchCandidates = Array.isArray(row.match_candidates) ? row.match_candidates : [];
    const favorableSignals = Array.isArray(row.match_favorable_signals) ? row.match_favorable_signals : [];
    const conflictingSignals = Array.isArray(row.match_conflicting_signals) ? row.match_conflicting_signals : [];
    const favorableText = favorableSignals.length ? favorableSignals.join(" / ") : "Nenhum sinal favoravel informado.";
    const conflictingText = conflictingSignals.length ? conflictingSignals.join(" / ") : "Nenhum sinal conflitante identificado.";
    const candidatesText = matchCandidates.length ? matchCandidates.map(function (candidate, index) { return String(index + 1) + ". " + normalizeText(candidate.source_name, "-") + " - " + String(Math.max(0, toInt(candidate.match_score, 0))) + "% - " + normalizeText(candidate.match_level_label, "Sem nivel"); }).join(" / ") : "Nenhum candidato aproximado encontrado.";
   
const itemId = normalizeText(row.comparison_item_id);

const primaryCandidate = matchCandidates.length
  ? matchCandidates[0]
  : null;

const primaryCandidateKey = normalizeText(
  primaryCandidate?.source_product_key
);

const primaryCandidateName = normalizeText(
  primaryCandidate?.source_name,
  "-"
);

const primaryCandidateVersion = normalizeText(
  primaryCandidate?.source_version,
  "-"
);

const primaryCandidateScore = Math.max(
  0,
  toInt(primaryCandidate?.match_score, 0)
);

const primaryCandidateLevel = normalizeText(
  primaryCandidate?.match_level_label,
  "Sem nível"
);

const primaryCandidateUrl = normalizeText(
  primaryCandidate?.source_product_url
);

const candidatesHtml = matchCandidates.length

? matchCandidates.map(function (candidate, index) {

      const candidateUrl = normalizeText(
        candidate.source_product_url
      );

      const officialUrl = normalizeText(
        candidate.source_official_url
      );

      const candidateKey = normalizeText(
        candidate.source_product_key
      );

      return `
        <div class="comparison-candidate">
          <div class="comparison-candidate-head">
            <strong>
              ${escapeHtml(
                String(index + 1)
                + ". "
                + normalizeText(
                    candidate.source_name,
                    "-"
                  )
              )}
            </strong>

            <span class="badge">
              ${escapeHtml(
                String(
                  Math.max(
                    0,
                    toInt(candidate.match_score, 0)
                  )
                ) + "%"
              )}
            </span>
          </div>

          <div class="comparison-cell-meta">
            Nível:
            ${escapeHtml(
              normalizeText(
                candidate.match_level_label,
                "Sem nível"
              )
            )}
          </div>

          <div class="comparison-cell-meta">
            Versão:
            ${escapeHtml(
              normalizeText(
                candidate.source_version,
                "-"
              )
            )}
          </div>

          <div class="comparison-cell-meta">
            Categoria:
            ${escapeHtml(
              normalizeText(
                candidate.source_category,
                "-"
              )
            )}
          </div>

          <div class="comparison-candidate-links">
            ${
              candidateUrl
                ? link(candidateUrl, "Abrir produto")
                : ""
            }

            ${
              candidateUrl && officialUrl
                ? " / "
                : ""
            }

            ${
              officialUrl
                ? link(
                    officialUrl,
                    "Abrir URL oficial"
                  )
                : ""
            }
          </div>

                ${
        candidateKey
          ? `
            <div class="comparison-candidate-actions">
              <button
                type="button"
                class="btn-success comparison-confirm-candidate"
                data-comparison-item-id="${escapeHtml(itemId)}"
                data-source-product-key="${escapeHtml(candidateKey)}"
              >
                Confirmar vínculo
              </button>

              <button
                type="button"
                class="btn-danger comparison-reject-candidate"
                data-comparison-item-id="${escapeHtml(itemId)}"
                data-source-product-key="${escapeHtml(candidateKey)}"
              >
                Rejeitar candidato
              </button>
            </div>
          `
          : ""
      }

        </div>
      `;
    }).join("")
  : `
      <div class="comparison-candidate-empty">
        Nenhum candidato aproximado encontrado.
      </div>
    `;

const primaryCandidateConfidence = normalizeText(
  primaryCandidate?.match_confidence,
  primaryCandidateScore >= 90
    ? "Alta"
    : (primaryCandidateScore >= 75 ? "Média" : "Baixa")
);

const primaryCandidateHtml = primaryCandidate
  ? `
    <div class="comparison-primary-candidate">
      <strong>${escapeHtml(primaryCandidateName)}</strong>

      <div class="comparison-cell-meta">
        Versão: ${escapeHtml(primaryCandidateVersion)}
      </div>

      <div class="comparison-cell-meta">
        Confiança: ${escapeHtml(primaryCandidateConfidence)}
      </div>

      <div class="comparison-cell-meta">
        Nível: ${escapeHtml(primaryCandidateLevel)}
      </div>

      <div class="comparison-cell-meta">
        Pontuação: ${escapeHtml(primaryCandidateScore)}%
      </div>

      ${
        primaryCandidateUrl
          ? `<div class="comparison-cell-meta">${link(primaryCandidateUrl, "Abrir produto")}</div>`
          : ""
      }

      ${
        primaryCandidateKey
          ? `
            <div class="comparison-candidate-actions">
              <button
                type="button"
                class="comparison-icon-action comparison-icon-action-confirm comparison-confirm-candidate"
                data-comparison-item-id="${escapeHtml(itemId)}"
                data-source-product-key="${escapeHtml(primaryCandidateKey)}"
                aria-label="Confirmar vínculo com o candidato principal"
                title="Confirmar vínculo com o candidato principal"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>
              </button>

              <button
                type="button"
                class="comparison-icon-action comparison-icon-action-reject comparison-reject-candidate"
                data-comparison-item-id="${escapeHtml(itemId)}"
                data-source-product-key="${escapeHtml(primaryCandidateKey)}"
                aria-label="Rejeitar candidato principal"
                title="Rejeitar candidato principal"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
              </button>

              <button
                type="button"
                class="comparison-view-candidates comparison-view-candidates-link"
                data-comparison-item-id="${escapeHtml(itemId)}"
              >
                Ver outros
              </button>
            </div>
          `
          : ""
      }
    </div>
  `
  : `
    <div class="comparison-candidate-empty">
      Nenhum candidato
    </div>
  `;
   
const disputedCandidateCount = matchCandidates.filter(function (candidate) { return Boolean(candidate.is_disputed); }).length;
    const disputedCandidateText = disputedCandidateCount ? "Atencao: este candidato tambem foi sugerido para outro produto da PluginTema. Nao confirme automaticamente." : "Nenhum candidato disputado nesta linha.";
    
    const currentDecision = normalizeText(row.decision, "pending");
    const decisionOptions = [
      ["pending", "Pendente"],
      ["approve_update", "Aprovar atualização"],
      ["ignore", "Ignorar"],
      ["review_later", "Revisar depois"],
      ["same_product", "Mesmo produto"],
      ["different_products", "Produtos diferentes"],
      ["approve_new_product", "Aprovar cadastro novo"],
    ];
    const decisionOptionsHtml = decisionOptions.map(function (option) {
      const value = option[0];
      const label = option[1];
      const selected = value === currentDecision ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(label)}</option>`;
    }).join("");
    
return `<tr>
  <td class="comparison-status-cell">
    <input
      type="checkbox"
      class="comparison-row-select"
      data-comparison-item-id="${escapeHtml(itemId)}"
      aria-label="Selecionar produto"
      ${UI.comparison.selectedItemIds.has(itemId) ? "checked" : ""}
    >
    <span class="badge comparison-status ${comparisonStatusClass(status)}">
      ${escapeHtml(normalizeText(row.status_label, status || "-"))}
    </span>
  </td>

  <td class="comparison-products-cell">
    <div class="comparison-pair comparison-products-pair">
      <div class="comparison-product-side">
        <span class="comparison-pair-label">PluginTema</span>
        <strong>${escapeHtml(normalizeText(row.site_name, "— Não encontrado no catálogo PluginTema"))}</strong>
        ${row.site_id ? `<div class="comparison-cell-meta comparison-product-id" title="ID PluginTema: ${escapeHtml(row.site_id)}">ID ${escapeHtml(row.site_id)}</div>` : ""}
        ${siteProductUrl ? `<div class="comparison-cell-meta">${link(siteProductUrl, "Abrir produto")}</div>` : ""}
      </div>
      <span class="comparison-pair-arrow" aria-hidden="true">→</span>
      <div class="comparison-product-side">
        <span class="comparison-pair-label">Origem</span>
        <strong>${escapeHtml(normalizeText(row.source_name, "— Não encontrado no catálogo de origem"))}</strong>
        ${row.source_product_key ? `<div class="comparison-cell-meta comparison-product-id" title="ID na origem: ${escapeHtml(row.source_product_key)}">ID ${escapeHtml(row.source_product_key)}</div>` : ""}
        ${sourceUrl ? `<div class="comparison-cell-meta">${link(sourceUrl, "Abrir produto")}</div>` : ""}
      </div>
    </div>
  </td>

      <td class="comparison-versions-cell">
        <div class="comparison-pair comparison-versions" aria-label="PluginTema: ${escapeHtml(normalizeText(row.site_version, "não informada"))}; Origem: ${escapeHtml(normalizeText(row.source_version, "não informada"))}">
          <span title="Versão PluginTema: ${escapeHtml(normalizeText(row.site_version, "não informada"))}">${escapeHtml(normalizeText(row.site_version, "—"))}</span>
          <span class="comparison-pair-arrow" aria-hidden="true">→</span>
          <span title="Versão da origem: ${escapeHtml(normalizeText(row.source_version, "não informada"))}">${escapeHtml(normalizeText(row.source_version, "—"))}</span>
        </div>
        <button type="button" class="comparison-version-info comparison-diagnostic-open" data-comparison-item-id="${escapeHtml(itemId)}" aria-label="Ver qualidade e motivos das versões" title="PluginTema: ${escapeHtml(normalizeText(row.site_version_quality, "-"))} — ${escapeHtml(normalizeText(row.site_version_reason, "-") )}. Origem: ${escapeHtml(normalizeText(row.source_version_quality, "-"))} — ${escapeHtml(normalizeText(row.source_version_reason, "-"))}">Qualidade das versões</button>
      </td>

      <td>${primaryCandidateHtml}</td>

      <td><strong>${escapeHtml(normalizeText(row.match_method_label, comparisonMethodLabel(row.match_method)))}</strong><div class="comparison-cell-meta">Confiança: ${escapeHtml(confidence)}</div><div class="comparison-cell-meta">Nível: ${escapeHtml(matchLevel)}</div><div class="comparison-cell-meta">Pontuação: ${escapeHtml(matchScore)}%</div></td>
      <td><div class="comparison-row-decision"><span class="badge comparison-decision ${comparisonDecisionClass(row.decision)}">${escapeHtml(normalizeText(row.decision_label, "Pendente"))}</span><select class="comparison-row-decision-select" data-comparison-item-id="${escapeHtml(itemId)}">${decisionOptionsHtml}</select><div class="comparison-row-decision-actions"><button type="button" class="btn-secondary comparison-decision-save" data-comparison-item-id="${escapeHtml(itemId)}">Salvar</button><button type="button" class="btn-secondary comparison-decision-reset" data-comparison-item-id="${escapeHtml(itemId)}">Restaurar</button></div></div></td>
      <td class="comparison-recommendation"><strong>${escapeHtml(normalizeText(row.recommended_action_label, "Revisar manualmente."))}</strong><button type="button" class="comparison-diagnostic-open" data-comparison-item-id="${escapeHtml(itemId)}">Diagnóstico</button></td>
    </tr>`;
  }).join("");
  updateComparisonBulkControls();
}

function getSelectedComparisonItemIds() {
  return Array.from(UI.comparison.selectedItemIds);
}

function updateComparisonBulkControls() {
  const selectedIds = getSelectedComparisonItemIds();
  const selectedCount = selectedIds.length;
  const countNode = byId("comparison_selected_count");
  const applyButton = byId("comparison_bulk_apply_btn");
  const bulkDecision = normalizeText(
    byId("comparison_bulk_decision")?.value
  );
  const selectPage = byId("comparison_select_page");
  const selectAllResults = byId("comparison_select_all_results");
  const pageCheckboxes = qsa(".comparison-row-select");
  const checkedCount = pageCheckboxes.filter(function (node) {
    return node.checked;
  }).length;

  if (countNode) {
    countNode.textContent = selectedCount === 1
      ? "1 selecionado"
      : String(selectedCount) + " selecionados";
  }

  if (applyButton) {
    applyButton.disabled = !selectedCount || !bulkDecision;
  }

  if (selectPage) {
    selectPage.checked = (
      pageCheckboxes.length > 0
      && checkedCount === pageCheckboxes.length
    );
    selectPage.indeterminate = (
      checkedCount > 0
      && checkedCount < pageCheckboxes.length
    );
  }

  if (selectAllResults) {
    selectAllResults.checked = Boolean(UI.comparison.allResultsSelected);
    selectAllResults.indeterminate = !UI.comparison.allResultsSelected && selectedCount > 0;
  }

  return selectedIds;
}


async function applyComparisonBulkDecision() {
  const selectedIds = getSelectedComparisonItemIds();
  const decision = normalizeText(
    byId("comparison_bulk_decision")?.value
  );

  if (!selectedIds.length) {
    throw new Error("Selecione pelo menos um produto.");
  }

  if (!decision) {
    throw new Error("Escolha uma decisão para aplicar.");
  }

  const items = selectedIds
    .map(function (itemId) {
      return UI.comparison.selectedRowsById?.[itemId] || UI.comparison.rowsById?.[itemId];
    })
    .filter(Boolean)
    .map(function (row) {
      return {
        comparison_item_id: row.comparison_item_id,
        site_id: row.site_id || "",
        site_name: row.site_name || "",
        source_name: row.source_name || "",
        status: row.status || "",
        recommended_action: row.recommended_action || "",
        woo_product_id: row.woo_product_id || row.site_id || "",
        site_version: row.site_version || "",
        site_product_url: row.site_product_url || "",
        site_official_url: row.site_official_url || row.official_url || "",
        source_version: row.source_version || "",
        source_product_url: row.source_product_url || "",
        source_official_url: row.source_official_url || "",
        relationship_state: row.relationship_state || "",
        relationship_label: row.relationship_label || "",
      };
    });

  const note = window.prompt(
    "Observação para os itens selecionados:",
    ""
  );

  if (note === null) return;

  const confirmed = window.confirm(
    "Aplicar esta decisão a "
    + String(items.length)
    + " produto(s)?"
  );

  if (!confirmed) return;

  const result = await postJson(
    "/comparacao/decisao/lote",
    {
      items,
      decision,
      note,
      operator: "local",
    }
  );

  byId("comparison_select_page").checked = false;
  byId("comparison_bulk_decision").value = "";
  clearComparisonSelection();

  await refreshComparison({ page: UI.comparison.page });
  notify(result?.message || "Decisões aplicadas com sucesso.");
}


async function saveComparisonRowDecision(itemId) {
  const row = UI.comparison.rowsById?.[itemId];
  if (!row) throw new Error("Linha da comparação não encontrada.");

  const select = qsa(".comparison-row-decision-select").find(function (node) {
    return normalizeText(node.dataset.comparisonItemId) === itemId;
  });

  if (!select) throw new Error("Seletor de decisão não encontrado.");

  const decision = normalizeText(select.value, "pending");
  const note = window.prompt("Observação da decisão:", normalizeText(row.decision_note)) ?? normalizeText(row.decision_note);

  await postJson("/comparacao/decisao/salvar", {
    comparison_item_id: itemId,
    decision,
    note,
    operator: "local",
    site_id: row.site_id || "",
    site_name: row.site_name || "",
    source_name: row.source_name || "",
    status: row.status || "",
    recommended_action: row.recommended_action || "",
    woo_product_id: row.woo_product_id || row.site_id || "",
    site_version: row.site_version || "",
    site_product_url: row.site_product_url || "",
    site_official_url: row.site_official_url || row.official_url || "",
    source_version: row.source_version || "",
    source_product_url: row.source_product_url || "",
    source_official_url: row.source_official_url || "",
    relationship_state: row.relationship_state || "",
    relationship_label: row.relationship_label || "",
  });

  await refreshComparison({ page: UI.comparison.page });
  notify("Decisão salva com sucesso.");
}

async function resetComparisonRowDecision(itemId) {
  await postJson("/comparacao/decisao/restaurar", {
    comparison_item_id: itemId,
    note: "Decisão restaurada manualmente para pendente.",
    operator: "local",
  });

  await refreshComparison({ page: UI.comparison.page });
  notify("Decisão restaurada para pendente.");
}


async function refreshComparison({ force = false, page = null } = {}) {
  if (UI.comparison.loading) return;
  const requestedPage = page == null ? Math.max(1, toInt(UI.comparison.page, 1)) : Math.max(1, toInt(page, 1));
  const sourceId = normalizeText(byId("comparison_source_catalog")?.value);
  const targetId = normalizeText(byId("comparison_target_catalog")?.value);

  const status = normalizeText(byId("comparison_status_filter")?.value, "all");
const decision = normalizeText(byId("comparison_decision_filter")?.value, "all");
const query = String(byId("comparison_query")?.value || "").trim();

const candidateFilter = String(
  byId("comparison_candidate_filter")?.value || ""
).trim();

const candidateCountMin = String(
  byId("comparison_candidate_count_min")?.value || ""
).trim();

const candidateCountMax = String(
  byId("comparison_candidate_count_max")?.value || ""
).trim();

const scoreMin = String(
  byId("comparison_score_min")?.value || ""
).trim();

const scoreMax = String(
  byId("comparison_score_max")?.value || ""
).trim();

const pageSize = Math.max(
  1,
  toInt(byId("comparison_page_size")?.value, 5)
);

  const resultSignature = JSON.stringify(comparisonFilterSnapshot());
  if (UI.comparison.resultSignature && UI.comparison.resultSignature !== resultSignature) {
    UI.comparison.selectedItemIds.clear();
    UI.comparison.selectedRowsById = {};
    UI.comparison.allResultsSelected = false;
  }
  UI.comparison.resultSignature = resultSignature;

  const runButton = byId("comparison_run_btn");
  UI.comparison.loading = true;
  appendComparisonLog(`Comparação iniciada${force ? " com recálculo forçado" : ""}.`);
  if (runButton) {
    runButton.disabled = true;
    runButton.setAttribute("aria-busy", "true");
    runButton.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span><span>Comparando, aguarde...</span>';
  }
  try {
    if (!sourceId || !targetId) throw new Error("Selecione o catálogo salvo e o catálogo importado.");
    const params = new URLSearchParams({
  source_id: sourceId,
  target_id: targetId,
  status,
  decision,
  q: query,

  candidate_filter: candidateFilter,
  candidate_count_min: candidateCountMin,
  candidate_count_max: candidateCountMax,

  score_min: scoreMin,
  score_max: scoreMax,
  page: String(requestedPage),
  page_size: String(pageSize),
  force: force ? "1" : "0",
});
    const payload = await getJson(`${UI.endpoints.comparisonData || "/comparacao/data"}?${params.toString()}`);
    if (payload?.ok === false) throw new Error(normalizeText(payload.message, "Falha ao comparar catálogos."));
    UI.comparison.status = status;
    UI.comparison.decision = decision;
    UI.comparison.query = query;
    renderComparison(payload);
    saveComparisonCache(payload);
    appendComparisonLog(`Comparação concluída: ${Math.max(0, toInt(payload?.pagination?.total_rows, 0))} resultado(s).`);
  } catch (error) {
    const notice = byId("comparison_file_notice");
    if (notice) notice.textContent = `Falha na comparação: ${normalizeText(error?.message, "erro desconhecido")}`;
    console.error("[panel.js] Falha na comparação:", error);
    appendComparisonLog(`Falha na comparação: ${normalizeText(error?.message, "erro desconhecido")}.`, "ERRO");
  } finally {
    UI.comparison.loading = false;
    if (runButton) {
      runButton.disabled = false;
      runButton.setAttribute("aria-busy", "false");
      runButton.textContent = "Comparar agora";
    }
    const prev = byId("comparison_prev_btn");
    const next = byId("comparison_next_btn");
    if (prev) prev.disabled = UI.comparison.page <= 1;
    if (next) next.disabled = UI.comparison.page >= UI.comparison.totalPages;
  }
}

function comparisonFilterSnapshot() {
  return {
    source_id: normalizeText(byId("comparison_source_catalog")?.value),
    target_id: normalizeText(byId("comparison_target_catalog")?.value),
    status: normalizeText(byId("comparison_status_filter")?.value, "all"),
    decision: normalizeText(byId("comparison_decision_filter")?.value, "all"),
    q: String(byId("comparison_query")?.value || "").trim(),
    candidate_filter: String(byId("comparison_candidate_filter")?.value || "").trim(),
    candidate_count_min: String(byId("comparison_candidate_count_min")?.value || "").trim(),
    candidate_count_max: String(byId("comparison_candidate_count_max")?.value || "").trim(),
    score_min: String(byId("comparison_score_min")?.value || "").trim(),
    score_max: String(byId("comparison_score_max")?.value || "").trim(),
  };
}

async function setAllComparisonResultsSelected(checked) {
  const checkbox = byId("comparison_select_all_results");
  if (!checked) {
    clearComparisonSelection();
    return;
  }
  const snapshot = comparisonFilterSnapshot();
  if (!snapshot.source_id || !snapshot.target_id) throw new Error("Selecione os dois catálogos antes de selecionar o resultado.");
  if (checkbox) checkbox.disabled = true;
  try {
    let page = 1;
    let totalPages = 1;
    const selectedRows = {};
    do {
      const params = new URLSearchParams({...snapshot, page: String(page), page_size: "1000", force: "0"});
      const payload = await getJson(`${UI.endpoints.comparisonData || "/comparacao/data"}?${params.toString()}`);
      if (payload?.ok === false) throw new Error(normalizeText(payload.message, "Falha ao carregar o resultado completo."));
      (Array.isArray(payload?.rows) ? payload.rows : []).forEach((row) => {
        const itemId = normalizeText(row?.comparison_item_id);
        if (itemId) selectedRows[itemId] = row;
      });
      totalPages = Math.max(1, toInt(payload?.pagination?.total_pages, 1));
      page += 1;
    } while (page <= totalPages);
    UI.comparison.selectedRowsById = selectedRows;
    UI.comparison.selectedItemIds = new Set(Object.keys(selectedRows));
    UI.comparison.allResultsSelected = true;
    qsa(".comparison-row-select").forEach((node) => { node.checked = UI.comparison.selectedItemIds.has(normalizeText(node.dataset.comparisonItemId)); });
    updateComparisonBulkControls();
  } finally {
    if (checkbox) checkbox.disabled = false;
  }
}

function clearComparisonSelection() {
  UI.comparison.selectedItemIds.clear();
  UI.comparison.selectedRowsById = {};
  UI.comparison.allResultsSelected = false;
  qsa(".comparison-row-select").forEach((node) => { node.checked = false; });
  const allResults = byId("comparison_select_all_results");
  if (allResults) { allResults.checked = false; allResults.indeterminate = false; }
  updateComparisonBulkControls();
}

function bindComparisonControls() {
  const modal = byId("comparison_link_modal");
  const modalCard = modal?.querySelector(".comparison-link-modal-card");
  const diagnosticModal = byId("comparison_diagnostic_modal");
  const diagnosticCard = diagnosticModal?.querySelector(".comparison-link-modal-card");
  byId("comparison_link_modal_close")?.addEventListener("click", closeComparisonLinkModal);
  modal?.querySelector(".comparison-link-modal-backdrop")?.addEventListener("click", closeComparisonLinkModal);
  modalCard?.addEventListener("click", function (event) { event.stopPropagation(); });
  byId("comparison_diagnostic_modal_close")?.addEventListener("click", closeComparisonDiagnosticModal);
  diagnosticModal?.querySelector(".comparison-link-modal-backdrop")?.addEventListener("click", closeComparisonDiagnosticModal);
  diagnosticCard?.addEventListener("click", function (event) { event.stopPropagation(); });
  byId("comparison_link_modal_search")?.addEventListener("click", runComparisonModalSearch);
  byId("comparison_link_modal_query")?.addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); clearTimeout(UI.comparison.linkModal.searchTimer); runComparisonModalSearch(); }
  });
  byId("comparison_link_modal_query")?.addEventListener("input", function () {
    clearTimeout(UI.comparison.linkModal.searchTimer);
    UI.comparison.linkModal.searchTimer = setTimeout(runComparisonModalSearch, 350);
  });
  modal?.addEventListener("click", async function (event) {
    const confirmButton = event.target.closest(".comparison-modal-confirm");
    const rejectButton = event.target.closest(".comparison-modal-reject");
    if (!confirmButton && !rejectButton) return;
    try {
      await handleComparisonModalRelationship(confirmButton || rejectButton, confirmButton ? "manual_confirmed" : "manual_rejected");
    } catch (error) {
      notify(normalizeText(error?.message, "Falha ao salvar o relacionamento."));
    }
  });
  document.addEventListener("keydown", function (event) {
    if (!modal || modal.classList.contains("hidden")) return;
    if (event.key === "Escape") { event.preventDefault(); closeComparisonLinkModal(); return; }
    trapComparisonModalFocus(event, modal);
  });
  document.addEventListener("keydown", function (event) {
    if (!diagnosticModal || diagnosticModal.classList.contains("hidden")) return;
    if (event.key === "Escape") { event.preventDefault(); closeComparisonDiagnosticModal(); return; }
    trapComparisonModalFocus(event, diagnosticModal);
  });
  byId("comparison_reload_sources_btn")?.addEventListener("click", loadComparisonSources);
  byId("comparison_copy_log")?.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(UI.comparison.logs.join("\n")); notify("Log da comparação copiado."); }
    catch (_error) { notify("Não foi possível copiar o log da comparação."); }
  });
  byId("comparison_run_btn")?.addEventListener("click", async () => { UI.comparison.page = 1; await refreshComparison({force:true, page:1}); });
  byId("comparison_status_filter")?.addEventListener("change", async () => { UI.comparison.page = 1; await refreshComparison({page:1}); });
  byId("comparison_decision_filter")?.addEventListener("change", async () => { UI.comparison.page = 1; await refreshComparison({page:1}); });
  byId("comparison_page_size")?.addEventListener("change", async () => { UI.comparison.page = 1; await refreshComparison({page:1}); });
  
byId("comparison_score_min")?.addEventListener("change", async () => {
  UI.comparison.page = 1;
  await refreshComparison({ page: 1 });
});

byId("comparison_score_max")?.addEventListener("change", async () => {
  UI.comparison.page = 1;
  await refreshComparison({ page: 1 });
});

byId("comparison_candidate_filter")?.addEventListener("change", async () => {
  UI.comparison.page = 1;
  await refreshComparison({ page: 1 });
});

byId("comparison_candidate_count_min")?.addEventListener("change", async () => {
  UI.comparison.page = 1;
  await refreshComparison({ page: 1 });
});

byId("comparison_candidate_count_max")?.addEventListener("change", async () => {
  UI.comparison.page = 1;
  await refreshComparison({ page: 1 });
});

byId("comparison_query")?.addEventListener("keydown", async (event) => {if (event.key === "Enter") { event.preventDefault(); UI.comparison.page = 1; await refreshComparison({page:1}); } });
  byId("comparison_prev_btn")?.addEventListener("click", async () => refreshComparison({page:Math.max(1, UI.comparison.page - 1)}));
  byId("comparison_next_btn")?.addEventListener("click", async () => refreshComparison({page:Math.min(UI.comparison.totalPages, UI.comparison.page + 1)}));
  byId("comparison_select_page")?.addEventListener("change", function (event) {
    const checked = Boolean(event.target.checked);
    qsa(".comparison-row-select").forEach(function (node) {
      node.checked = checked;
      const itemId = normalizeText(node.dataset.comparisonItemId);
      if (!itemId) return;
      if (checked) {
        UI.comparison.selectedItemIds.add(itemId);
        if (UI.comparison.rowsById[itemId]) UI.comparison.selectedRowsById[itemId] = UI.comparison.rowsById[itemId];
      } else {
        UI.comparison.allResultsSelected = false;
        UI.comparison.selectedItemIds.delete(itemId);
        delete UI.comparison.selectedRowsById[itemId];
      }
    });
    updateComparisonBulkControls();
  });

  byId("comparison_select_all_results")?.addEventListener("change", async function (event) {
    try {
      await setAllComparisonResultsSelected(Boolean(event.target.checked));
    } catch (error) {
      UI.comparison.allResultsSelected = false;
      event.target.checked = false;
      notify(normalizeText(error?.message, "Falha ao selecionar todo o resultado."));
    }
  });
  byId("comparison_clear_selection")?.addEventListener("click", clearComparisonSelection);

  byId("comparison_bulk_decision")?.addEventListener("change", function () {
    updateComparisonBulkControls();
  });

  byId("comparison_bulk_apply_btn")?.addEventListener("click", async function (event) {
    const button = event.currentTarget;
    button.disabled = true;

    try {
      await applyComparisonBulkDecision();
    } catch (error) {
      notify(
        normalizeText(
          error?.message,
          "Falha ao aplicar a decisão em lote."
        )
      );
    } finally {
      updateComparisonBulkControls();
    }
  });

  byId("comparison_rows")?.addEventListener("change", function (event) {
    if (event.target.matches(".comparison-row-select")) {
      const itemId = normalizeText(event.target.dataset.comparisonItemId);
      if (event.target.checked) {
        UI.comparison.selectedItemIds.add(itemId);
        if (UI.comparison.rowsById[itemId]) UI.comparison.selectedRowsById[itemId] = UI.comparison.rowsById[itemId];
      } else {
        UI.comparison.allResultsSelected = false;
        UI.comparison.selectedItemIds.delete(itemId);
        delete UI.comparison.selectedRowsById[itemId];
      }
      updateComparisonBulkControls();
    }
  });
  byId("comparison_rows")?.addEventListener("click", async function (event) {
    const saveButton = event.target.closest(".comparison-decision-save");
    const resetButton = event.target.closest(".comparison-decision-reset");
    const diagnosticButton = event.target.closest(".comparison-diagnostic-open");

const candidateButton = event.target.closest(
  ".comparison-confirm-candidate"
);

const rejectCandidateButton = event.target.closest(
  ".comparison-reject-candidate"
);

const viewCandidatesButton = event.target.closest(
  ".comparison-view-candidates"
);

    try {

if (diagnosticButton) {
  openComparisonDiagnosticModal(normalizeText(diagnosticButton.dataset.comparisonItemId), diagnosticButton);
  return;
}

       if (candidateButton) {
  candidateButton.disabled = true;

  await confirmSuggestedComparisonCandidate(
    normalizeText(
      candidateButton.dataset.comparisonItemId
    ),
    normalizeText(
      candidateButton.dataset.sourceProductKey
    )
  );

  return;
}


if (rejectCandidateButton) {
  rejectCandidateButton.disabled = true;

  await rejectSuggestedComparisonCandidate(
    normalizeText(
      rejectCandidateButton.dataset.comparisonItemId
    ),
    normalizeText(
      rejectCandidateButton.dataset.sourceProductKey
    )
  );

  return;
}

if (viewCandidatesButton) {
  openComparisonLinkModal(normalizeText(viewCandidatesButton.dataset.comparisonItemId), viewCandidatesButton);
  return;
}

      if (saveButton) {
        saveButton.disabled = true;
        await saveComparisonRowDecision(
          normalizeText(saveButton.dataset.comparisonItemId)
        );
        return;
      }

      if (resetButton) {
        resetButton.disabled = true;
        await resetComparisonRowDecision(
          normalizeText(resetButton.dataset.comparisonItemId)
        );
      }
    } catch (error) {
      notify(normalizeText(error?.message, "Falha ao alterar decisão."));
    } finally {
      if (saveButton) saveButton.disabled = false;
      if (resetButton) resetButton.disabled = false;
      if (candidateButton && document.contains(candidateButton)) candidateButton.disabled = false;
      if (rejectCandidateButton && document.contains(rejectCandidateButton)) rejectCandidateButton.disabled = false;
    }
  });
}

async function refreshFila() {
  const wrap = byId("fila_rules_wrap");
  if (wrap) {
    wrap.setAttribute("aria-busy", "true");
    wrap.innerHTML = '<div class="fila-loading" role="status"><span class="inline-loading-spinner" aria-hidden="true"></span><span><strong>Carregando fila...</strong><br>Aguarde enquanto buscamos as regras e os contextos disponíveis.</span></div>';
  }
  try {
    const [queuePayload, catalogosPayload] = await Promise.all([
      getJson(UI.endpoints.queueGet),
      getJson(UI.endpoints.catalogosData),
    ]);
    UI.filaRules = normalizeFilaRules(queuePayload?.queue_rules || queuePayload?.result || []);
    UI.filaCatalogOptions = buildFilaCatalogOptions(catalogosPayload?.catalogos || []);
    renderFilaRules();
  } catch (error) {
    if (wrap) wrap.innerHTML = `<div class="notice is-danger">Falha ao carregar a fila: ${escapeHtml(normalizeText(error?.message, "erro desconhecido"))}</div>`;
    notify(normalizeText(error?.message, "Falha ao carregar a fila."));
  } finally {
    wrap?.setAttribute("aria-busy", "false");
  }
}

function addFilaRule() {
  const options = Array.isArray(UI.filaCatalogOptions) ? UI.filaCatalogOptions : [];
  const sourceContext = options[0]?.context || {};
  const targetContext = options[1]?.context || options[0]?.context || {};

  UI.filaRules = normalizeFilaRules([
    ...UI.filaRules,
    {
      id: `fila-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
      enabled: true,
      source: sourceContext,
      target: targetContext,
    },
  ]);

  renderFilaRules();
}

async function saveFila() {
  return runAction(async () => {
    const rules = normalizeFilaRules(collectFilaRulesFromDom());
    const result = await postJson(UI.endpoints.queueSave, { rules });

    UI.filaRules = normalizeFilaRules(result?.queue_rules || result?.result || []);
    renderFilaRules();
    notify(result?.message || "Fila salva.");
    return result;
  });
}

function updateValidationRow(item) {
  const marker = item?.ok ? "OK" : "DIVERGÊNCIA";
  const stateClass = item?.ok ? (item?.level === "info" ? "is-info" : "is-ok") : "is-error";
  return `<li class="update-check ${stateClass}"><strong>${marker} — ${escapeHtml(item?.label || "Validação")}</strong><span>${escapeHtml(item?.detail || "")}</span></li>`;
}

function planValue(value) {
  if (Array.isArray(value)) return value.map(item => escapeHtml(typeof item === "object" ? JSON.stringify(item) : item)).join("<br>") || "-";
  if (value && typeof value === "object") return escapeHtml(JSON.stringify(value));
  return escapeHtml(value ?? "-");
}

function planSection(title, rows) {
  return `<section class="execution-plan-section"><h4>${escapeHtml(title)}</h4><dl>${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${planValue(value)}</dd></div>`).join("")}</dl></section>`;
}

function renderExecutionPlan(plan) {
  if (!plan) return "";
  const current = plan.current_zip || {}, fresh = plan.new_zip || {}, woo = plan.woocommerce || {};
  const rollback = plan.rollback || {};
  return `<article class="execution-plan" aria-labelledby="execution_plan_title">
    <h3 id="execution_plan_title">Plano de execução</h3>
    <div class="execution-plan-grid">
      ${planSection("Origem", [["Tipo", plan.origin?.type], ["Staging local", plan.origin?.local_staging_path]])}
      ${planSection("Destino", [["Tipo", plan.destination?.type], ["WooCommerce ID", plan.woo_product_id], ["Caminho remoto", plan.destination?.remote_path]])}
      ${planSection("Versões", [["PluginTema atual", plan.site_version], ["Comparação", plan.approved_source_version], ["Efetiva", plan.effective_source_version]])}
      ${planSection("Arquivo atual", [["Nome", current.name], ["Tamanho", current.size], ["SHA-256", current.sha256], ["Proprietário / grupo / permissão", `${current.owner || "-"} / ${current.group || "-"} / ${current.mode || "-"}`]])}
      ${planSection("Novo arquivo", [["Nome", fresh.name], ["Tamanho", fresh.size], ["SHA-256", fresh.sha256], ["Entradas", fresh.entries]])}
      ${planSection("WooCommerce", [["Variações", woo.variation_ids], ["IDs dos downloads", woo.download_ids], ["Nomes dos downloads", woo.download_names], ["Arquivo atual", woo.current_file], ["Arquivo futuro", woo.future_file]])}
      ${planSection("Backup", [["Caminho", plan.backup?.path], ["Nome", plan.backup?.name], ["SHA original esperado", plan.backup?.expected_original_sha256]])}
    </div>
    <section class="execution-plan-section"><h4>Pré-condições</h4><ul>${(plan.preconditions || []).map(item => `<li><strong>OK — ${escapeHtml(item.label || item.key)}</strong><span>Esperado: ${planValue(item.expected)}</span></li>`).join("")}</ul></section>
    <section class="execution-plan-section"><h4>Etapas planejadas</h4><ol>${(plan.planned_steps || []).map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ol></section>
    <section class="execution-plan-section"><h4>Rollback</h4><ul>${(rollback.checklist || []).map(item => `<li><strong>${item.ok ? "OK" : "FALTA"} — ${escapeHtml(item.label)}</strong></li>`).join("")}</ul><ol>${(rollback.steps || []).map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ol></section>
    <div class="execution-plan-ready" role="status">✓ ${escapeHtml(plan.status_label || "Plano pronto para homologação")}</div>
    <div class="updates-lock" role="status">${escapeHtml(plan.execution_label || "Execução real ainda bloqueada para homologação")}</div>
  </article>`;
}

function renderUpdatePreview(preview, executionPlan = null) {
  const current = preview?.current_zip || {}, fresh = preview?.new_zip || {};
  const downloads = Array.isArray(preview?.downloads) ? preview.downloads : [];
  const notices = Array.isArray(preview?.notices) ? preview.notices : [];
  return `<div class="update-preview ${preview?.ready ? "is-ready" : "has-divergence"}">
    <div class="update-preview-grid hidden" aria-hidden="true">
      <div><span>Produto</span><strong>${escapeHtml(preview?.product?.name || "-")} (#${escapeHtml(preview?.product?.id || "-")})</strong></div>
      <div><span>Versão PluginTema atual</span><strong>${escapeHtml(preview?.versions?.site_version || preview?.versions?.plugintema || "-")}</strong></div>
      <div><span>Versão na comparação</span><strong>${escapeHtml(preview?.versions?.approved_source_version || preview?.versions?.ultrapack_approved || "-")}</strong></div>
      <div><span>Versão atual na fonte</span><strong>${escapeHtml(preview?.versions?.effective_source_version || preview?.versions?.ultrapack_found || preview?.versions?.ultrapack || "-")}</strong></div>
      <div><span>Arquivo atual</span><strong>${escapeHtml(preview?.physical_path || "-")}</strong></div>
      <div><span>Tamanho atual</span><strong>${escapeHtml(current.size ?? "-")}</strong></div>
      <div><span>SHA-256 atual</span><code>${escapeHtml(current.sha256 || "-")}</code></div>
      <div><span>Novo ZIP</span><strong>${escapeHtml(fresh.file_name || fresh.path || "-")}</strong></div>
      <div><span>Tamanho novo</span><strong>${escapeHtml(fresh.size ?? "-")}</strong></div>
      <div><span>SHA-256 novo</span><code>${escapeHtml(fresh.sha256 || "-")}</code></div>
    </div>
    ${notices.map(message => `<div class="update-source-notice" role="status">ℹ ${escapeHtml(message)}</div>`).join("")}
    <div class="update-downloads"><strong>Variações afetadas:</strong> ${escapeHtml((preview?.variations || []).join(", ") || "-")}${downloads.map(item => `<div><code>${escapeHtml(item.id || "-")}</code> · ${escapeHtml(item.name || "-")} · ${escapeHtml(item.file || "-")}</div>`).join("")}</div>
    <ol class="update-checks">${(preview?.validations || []).map(updateValidationRow).join("")}</ol>
    <div class="execution-plan-slot">${renderExecutionPlan(executionPlan)}</div>
    <button class="btn-danger update-execute" type="button" disabled aria-disabled="true">${escapeHtml(preview?.execution_label || "Execução real ainda bloqueada para homologação")}</button>
  </div>`;
}

function openConfigModal() {
  const modal = byId("config_modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  byId("verify_mode")?.focus();
}

function closeConfigModal() {
  byId("config_modal")?.classList.add("hidden");
  byId("open_config_modal_btn")?.focus();
}

const UPDATE_STATUS_LABELS = Object.freeze({
  approved: "Aprovado", pending: "Pendente", validating: "Validando",
  downloading: "Baixando", staging: "Preparando staging", prepared: "Preparado",
  planned: "Planejado", plan_ready: "Plano pronto", installing: "Instalando",
  queued: "Na fila", canceled: "Cancelado",
  filesystem_validated: "Sistema de arquivos validado",
  updating_wordpress: "Atualizando WordPress", validating_wordpress: "Validando WordPress",
  validated: "Validado", dry_run_ready: "Simulação pronta", blocked: "Bloqueado",
  executing: "Executando", completed: "Concluído", failed: "Falhou", error: "Erro",
  interrupted: "Interrompido", rollback_required: "Rollback necessário",
  rolling_back: "Executando rollback", rolled_back: "Rollback concluído",
});

const UPDATE_RELATIONSHIP_LABELS = Object.freeze({
  safe_auto: "Vinculação automática", candidate: "Candidato",
  manual_confirmed: "Vinculação manual confirmada",
  manual_rejected: "Vinculação manual rejeitada",
  confirmed_not_in_source: "Confirmado como ausente na fonte",
  pending_review: "Revisão pendente",
});

function updateStatusLabel(value) {
  const normalized = normalizeText(value, "approved");
  return UPDATE_STATUS_LABELS[normalized] || "Estado não reconhecido";
}

function updateBlockedReason(jobOrPreview) {
  const preview = jobOrPreview?.preview || jobOrPreview || {};
  const failed = (preview.validations || []).find(item => item && item.ok === false);
  const log = [...(preview.update_logs || [])].reverse().find(entry => /falha|bloquead|expirad|sessão|sessao/i.test(entry));
  return normalizeText(log || failed?.detail || jobOrPreview?.execution_error || "Preparação bloqueada. Abra os detalhes para ver como corrigir.");
}

function updateRelationshipLabel(value) {
  const normalized = normalizeText(value);
  return UPDATE_RELATIONSHIP_LABELS[normalized] || (normalized ? "Outro relacionamento" : "Não informado");
}

const UPDATE_QUEUE = {jobs: [], filtered: [], workingFiltered: [], selected: new Set(), cancel: false, modalJob: null, page: 1, pageSize: LISTING_DEFAULT_PAGE_SIZE, queue: {status:"stopped",queued:[],executing:[]}, queuePage:1, queuePageSize:LISTING_DEFAULT_PAGE_SIZE, historyMode:"completed", historyPage:1, historyPageSize:LISTING_DEFAULT_PAGE_SIZE, poll:null, renameQueueName:"", previewQueueName:"", previewItems:[], previewMetadata:null, previewPage:1, previewPageSize:LISTING_DEFAULT_PAGE_SIZE};

function updateFilteredJobs() {
  const status = byId("updates_status_filter")?.value || "", type = byId("updates_type_filter")?.value || "";
  const search = normalizeText(byId("updates_search_filter")?.value).toLowerCase();
  const version = byId("updates_version_filter")?.value || "", relationship = byId("updates_relationship_filter")?.value || "";
  UPDATE_QUEUE.filtered = UPDATE_QUEUE.jobs.filter(job => {
    const effective = normalizeText(job.effective_source_version || job.ultrapack_version);
    const approved = normalizeText(job.approved_source_version || job.ultrapack_version);
    const versionOk = !version || (version === "update" && effective !== normalizeText(job.plugintema_version)) ||
      (version === "advanced" && effective !== approved) || (version === "equal" && effective === approved);
    const relationOk = !relationship || job.relationship === relationship ||
      (relationship === "other" && !["safe_auto", "manual_confirmed"].includes(job.relationship));
    return (!status || job.state === status) && (!type || job.queue_type === type) && versionOk && relationOk &&
      (!search || `${job.name} ${job.woo_product_id}`.toLowerCase().includes(search));
  });
}

function renderUpdateSummary() {
  const groups={waiting:["approved","pending"],prepared:["prepared","plan_ready"],queued:["queued"],executing:["executing"],completed:["completed","rolled_back"],error:["error","failed","rollback_required"]};
  const counts=Object.fromEntries(Object.entries(groups).map(([key,states])=>[key,UPDATE_QUEUE.jobs.filter(j=>states.includes(j.state)).length]));
  const labels = {waiting:"Aguardando",prepared:"Preparados",queued:"Na fila",executing:"Executando",completed:"Concluídos",error:"Erros"};
  const help = {total:"Todos os produtos materializados para atualização.",waiting:"Produtos aprovados que ainda aguardam preparação.",prepared:"Produtos preparados ou com plano pronto.",queued:"Produtos adicionados à fila ativa e ainda não iniciados.",executing:"Produto atualmente em execução sequencial.",completed:"Atualizações concluídas ou com rollback concluído.",error:"Itens bloqueados ou encerrados com falha que exigem atenção."};
  const summaryCard=(key,label,value)=>`<div><strong>${value}</strong><span>${label} <button type="button" class="comparison-help" aria-label="Ajuda sobre ${label}" data-tooltip="${escapeHtml(help[key])}">?</button></span></div>`;
  byId("updates_summary").innerHTML = summaryCard("total","Total",UPDATE_QUEUE.jobs.length) + Object.entries(labels).map(([key,label]) => summaryCard(key,label,counts[key])).join("");
  byId("updates_selected_count").textContent = `${UPDATE_QUEUE.selected.size} selecionados`;
  const selectedJobs = UPDATE_QUEUE.jobs.filter(job => UPDATE_QUEUE.selected.has(job.job_id));
  const enqueueSelected = byId("updates_enqueue_selected");
  const selectedEligible = selectedJobs.filter(job => job.state === "plan_ready" && job.execution_eligible === true);
  if (enqueueSelected) {
    enqueueSelected.disabled = selectedEligible.length === 0;
    enqueueSelected.title = selectedJobs.length && !selectedEligible.length
      ? "Os itens selecionados precisam de plano pronto e autorização de execução."
      : "";
  }
  const activeQueueName=normalizeText(UPDATE_QUEUE.queue?.active_queue,"default");
  const activeQueueJobs=UPDATE_QUEUE.jobs.filter(job=>normalizeText(job.queue_name)===activeQueueName);
  const terminalStates=new Set(["completed","rolled_back","error","failed","rollback_required","blocked","canceled","interrupted"]);
  const done=activeQueueJobs.filter(job=>terminalStates.has(job.state)).length,total=activeQueueJobs.length,percent=total?Math.round(done*100/total):0;
  byId("updates_progress_percent").textContent=`${percent}%`;byId("updates_progress_label").textContent=`${done} de ${total} processados`;byId("updates_progress_bar").style.width=`${percent}%`;byId("updates_progress_bar").parentElement.setAttribute("aria-valuenow",String(percent));
  const active=UPDATE_QUEUE.jobs.find(j=>j.state==="executing");byId("updates_now").innerHTML=active?`<strong>Executando agora:</strong> ${escapeHtml(active.name)} <span>${escapeHtml(active.plugintema_version)} → ${escapeHtml(active.effective_source_version||active.ultrapack_version)}</span>`:"Nenhuma atualização em execução";
  const enabled = UPDATE_QUEUE.jobs.some(job => job.execution_enabled);
  const allowAll = UPDATE_QUEUE.jobs.some(job => job.execution_allow_all_products === true);
  const allowedIds = [...new Set(UPDATE_QUEUE.jobs.flatMap(job => job.execution_allowed_product_ids || []))].sort((a,b)=>a-b);
  if (byId("updates_execution_lock")) byId("updates_execution_lock").textContent = enabled ? `Execução habilitada · produtos permitidos: ${allowAll ? "todos com plano válido" : (allowedIds.map(id=>`#${id}`).join(", ") || "nenhum")}` : "Execução real bloqueada para homologação";
}

function renderUpdateJobs(jobs = UPDATE_QUEUE.jobs) {
  UPDATE_QUEUE.jobs = Array.isArray(jobs) ? jobs : [];
  updateFilteredJobs(); renderUpdateSummary();
  const wrap = byId("updates_jobs");
  if (!wrap) return;
  renderOperationalQueue(); renderUpdateHistory();
  const excludedStates=["queued","executing","completed","rolled_back","error","failed","rollback_required","canceled","interrupted"];
  const baseWorking=UPDATE_QUEUE.jobs.filter(j=>!excludedStates.includes(j.state));
  const working=UPDATE_QUEUE.filtered.filter(j=>!excludedStates.includes(j.state));
  UPDATE_QUEUE.workingFiltered=working;
  byId("updates_working_controls")?.classList.toggle("hidden",baseWorking.length===0);
  byId("updates_found_count").textContent=`${working.length} itens encontrados`;
  if (!working.length) { wrap.innerHTML = `<div class="notice">${baseWorking.length ? "Nenhum item corresponde aos filtros atuais." : "Nenhum job aguardando preparação."}</div>`; return; }
  UPDATE_QUEUE.pageSize=normalizeListingPageSize(byId("updates_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);const pages=Math.max(1,Math.ceil(working.length/UPDATE_QUEUE.pageSize));UPDATE_QUEUE.page=Math.min(Math.max(1,UPDATE_QUEUE.page),pages);const start=(UPDATE_QUEUE.page-1)*UPDATE_QUEUE.pageSize;const visible=working.slice(start,start+UPDATE_QUEUE.pageSize);byId("updates_found_count").textContent=listingRangeText(working.length,UPDATE_QUEUE.page,UPDATE_QUEUE.pageSize);byId("updates_page_label").textContent=`Página ${UPDATE_QUEUE.page} de ${pages}`;byId("updates_prev_page").disabled=UPDATE_QUEUE.page<=1;byId("updates_next_page").disabled=UPDATE_QUEUE.page>=pages;
  wrap.innerHTML = visible.map(job => {
    const completed = job.state === "completed";
    const canExecute = job.execution_eligible === true;
    const legacyError = job.state === "error" && Array.isArray(job.diagnostics) ? job.diagnostics.at(-1) : "";
    const errorMessage = job.execution_error || legacyError;
    const executionError = errorMessage ? `<div class="updates-error" role="alert">${escapeHtml(errorMessage)}</div>` : "";
    const completedAt = completed && job.completed_at ? `<div class="small">Atualizado em: ${escapeHtml(job.completed_at)}</div>` : "";
    const allowedIds = Array.isArray(job.execution_allowed_product_ids) ? job.execution_allowed_product_ids : [];
    const eligibilityHelp = canExecute ? "" : (job.execution_enabled && allowedIds.length && !allowedIds.includes(Number(job.woo_product_id))
      ? `WooCommerce #${job.woo_product_id} não está na lista de produtos autorizados para execução`
      : "Produto sem autorização individual ou com pré-condições pendentes");
    const enqueueAction = job.state === "plan_ready" ? `<button class="btn-success update-enqueue-one" type="button" ${canExecute?"":`disabled title="${eligibilityHelp}"`}>Adicionar à fila</button>` : "";
    const executeAction = job.state === "plan_ready" ? `<button class="btn-danger update-execute" type="button" ${canExecute?"":`disabled title="${eligibilityHelp}"`}>Executar individualmente</button>` : "";
    const prepareAction = job.state === "plan_ready" ? "" : '<button class="btn-success update-prepare" type="button">Preparar e gerar plano</button>';
    const cycleActions = completed ? "" : `${prepareAction}${enqueueAction}${executeAction}`;
    return `<article class="update-job update-job-compact${completed?' is-completed':''}" data-update-job-id="${escapeHtml(job.job_id)}"><input class="update-select" type="checkbox" aria-label="Selecionar ${escapeHtml(job.name)}" ${completed?'disabled':(UPDATE_QUEUE.selected.has(job.job_id)?"checked":"")}><div class="update-job-main"><strong>${escapeHtml(job.name || "Produto sem nome")}</strong><div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version || "-")} → ${escapeHtml(job.effective_source_version || job.ultrapack_version || "-")}</div><div class="small">Relacionamento: ${escapeHtml(updateRelationshipLabel(job.relationship))}</div>${completedAt}${executionError}</div><span class="badge">${escapeHtml(updateStatusLabel(job.state))}</span><div class="update-row-actions"><button class="btn-secondary update-details" type="button" aria-expanded="false">Detalhes</button>${cycleActions}</div><div class="update-preview-slot hidden"></div></article>`;
  }).join("");
  qsa(".update-select", wrap).forEach(input => input.addEventListener("change", () => { const id=input.closest("[data-update-job-id]").dataset.updateJobId; input.checked?UPDATE_QUEUE.selected.add(id):UPDATE_QUEUE.selected.delete(id); renderUpdateSummary(); }));
  qsa(".update-details", wrap).forEach(button => button.addEventListener("click", () => { const card=button.closest("[data-update-job-id]"), job=UPDATE_QUEUE.jobs.find(j=>j.job_id===card.dataset.updateJobId), slot=qs(".update-preview-slot",card), open=slot.classList.toggle("hidden"); button.setAttribute("aria-expanded",String(!open)); if(!open && !slot.dataset.rendered){const history=(job.execution_history||[]).at(-1)||{};const completedSummary=job.state==='completed'?planSection('Resultado concluído', [['Versão anterior',history.previous_site_version||job.plugintema_version],['Versão instalada',history.effective_source_version||job.effective_source_version],['Versão da comparação',history.approved_source_version||job.approved_source_version],['SHA anterior',history.previous_sha256],['SHA novo',history.new_sha256],['Backup',history.backup_path],['Identificador do plano',history.plan_id],['Conclusão',history.completed_at||job.completed_at]]):'';const completedLogs=job.state==='completed'?`<section class="execution-plan-section"><h4>Logs finais</h4><pre>${escapeHtml((job.execution_logs||[]).join('\n')||'Sem logs persistidos.')}</pre><div class="log-copy-row"><button class="btn-success" type="button" data-copy-update-job-log="${escapeHtml(job.job_id)}">📋 Copiar log completo</button></div></section>`:'';slot.innerHTML=completedSummary+completedLogs+(job.preview?renderUpdatePreview(job.preview,job.execution_plan):'<div class="notice">Sem preview detalhado.</div>');slot.dataset.rendered="1";} }));
  if (!wrap.dataset.copyLogBound) {
    wrap.addEventListener("click", async event => {
      const button = event.target.closest("[data-copy-update-job-log]");
      if (!button) return;
      const job = UPDATE_QUEUE.jobs.find(item => item.job_id === button.dataset.copyUpdateJobLog);
      try {
        await navigator.clipboard.writeText((job?.execution_logs || []).join("\n"));
        notify("Log completo copiado.", "ok");
      } catch (error) {
        notify(`Não foi possível copiar o log: ${error.message}`, "error");
      }
    });
    wrap.dataset.copyLogBound = "1";
  }
  qsa(".update-prepare", wrap).forEach(button => button.addEventListener("click", async () => {
    const card = button.closest("[data-update-job-id]"); button.disabled = true; button.setAttribute("aria-busy", "true"); button.innerHTML = '<span class="inline-loading-spinner" aria-hidden="true"></span><span>Preparando e gerando plano...</span>';
    const slot = qs(".update-preview-slot", card);
    slot.classList.remove("hidden");
    slot.dataset.rendered = "";
    slot.innerHTML = '<div class="notice" role="status">Validando dados e preparando o download...</div>';
    renderUpdateLogs([`Preparando ${qs(".update-job-main strong", card)?.textContent || "produto"}...`, "Validando fonte e iniciando download seguro."]);
    try { const result = await postJson("/atualizacoes/preparar", {job_id: card.dataset.updateJobId}); const preview=result.preview||{};renderUpdateLogs(preview.update_logs || result.update_logs || []);if(preview.ready!==true){const reason=updateBlockedReason(preview);slot.innerHTML=`<div class="updates-error" role="alert"><strong>Preparação bloqueada.</strong><br>${escapeHtml(reason)}</div>`;notify(reason,"error");}else{slot.innerHTML='<div class="notice" role="status"><span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Download validado. Gerando plano de execução...</span></span></div>';const planned=await postJson("/atualizacoes/plano",{job_id:card.dataset.updateJobId});renderUpdateLogs([...(preview.update_logs||[]),...(planned.plan?.update_logs||[])]);notify("Preparação e plano concluídos.","ok");}await refreshUpdateJobs(); }
    catch (error) {
      slot.innerHTML = `<div class="updates-error" role="alert">${escapeHtml(error?.message || error)}</div>`;
      const state = normalizeText(error?.responseData?.state);
      const badge = qs(".badge", card);
      if (badge && state) badge.textContent = updateStatusLabel(state);
      renderUpdateLogs(error?.responseData?.update_logs || []);
    }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); button.textContent = "Preparar e gerar plano"; }
  }));
  qsa(".update-enqueue-one", wrap).forEach(button => button.addEventListener("click", async()=>{const card=button.closest("[data-update-job-id]");button.disabled=true;button.textContent="Adicionando...";try{const result=await postJson("/atualizacoes/fila/adicionar",{job_ids:[card.dataset.updateJobId]});if(!(result.added||[]).length)throw new Error("O job não pôde ser adicionado à fila.");notify("Produto adicionado à fila de atualização.","ok");await refreshUpdateJobs();}catch(error){notify(error?.message||String(error),"error");button.disabled=false;button.textContent="Adicionar à fila";}}));
  qsa(".update-execute", wrap).forEach(button => button.addEventListener("click",()=>openUpdateExecuteModal(UPDATE_QUEUE.jobs.find(j=>j.job_id===button.closest("[data-update-job-id]").dataset.updateJobId))));
}

function compactUpdateRow(job, position="") { const reason=job.state==="blocked"?updateBlockedReason(job):job.execution_error;return `<article class="update-queue-row"><div class="update-queue-position">${position?`#${position}`:""}</div><div><strong>${escapeHtml(job.name)}</strong><div class="small">Woo #${escapeHtml(job.woo_product_id)} · ${escapeHtml(job.plugintema_version||"-")} → ${escapeHtml(job.effective_source_version||job.ultrapack_version||"-")}</div>${reason?`<div class="updates-error">${escapeHtml(reason)}</div>`:""}</div><span class="badge">${escapeHtml(updateStatusLabel(job.state))}</span><button class="btn-secondary update-history-details" data-update-detail="${escapeHtml(job.job_id)}" aria-expanded="false" type="button">Detalhes</button><div class="update-operational-detail hidden"></div></article>`; }
function bindOperationalDetails(scope){qsa("[data-update-detail]",scope).forEach(button=>button.addEventListener("click",()=>{const job=UPDATE_QUEUE.jobs.find(j=>j.job_id===button.dataset.updateDetail),slot=qs(".update-operational-detail",button.parentElement),hidden=slot.classList.toggle("hidden");button.setAttribute("aria-expanded",String(!hidden));if(!hidden&&!slot.dataset.rendered){slot.innerHTML=planSection("Resumo",[["Produto",job.name],["WooCommerce",`#${job.woo_product_id}`],["Versão",`${job.plugintema_version} → ${job.effective_source_version||job.ultrapack_version}`],["Relacionamento",updateRelationshipLabel(job.relationship)],["Tentativas",job.attempts||0],["Última etapa",job.last_completed_step||"-"]])+renderExecutionPlan(job.execution_plan)+(job.execution_logs?.length?`<details><summary>Ver log técnico</summary><pre>${escapeHtml(job.execution_logs.join("\n"))}</pre></details>`:"");slot.dataset.rendered="1";}}));}
function updateQueueDisplayName(name){return normalizeText(name)==="default"?"Padrão":normalizeText(name);}
function renderOperationalQueue(){
  const queueName=normalizeText(UPDATE_QUEUE.queue?.active_queue,"default"), queued=UPDATE_QUEUE.jobs.filter(j=>j.state==="queued"&&normalizeText(j.queue_name,"default")===queueName).sort((a,b)=>(a.queue_position||0)-(b.queue_position||0)),active=UPDATE_QUEUE.jobs.filter(j=>j.state==="executing"&&normalizeText(j.queue_name,"default")===queueName),status=UPDATE_QUEUE.queue?.status||"stopped",label={running:"Executando",paused:"Pausada",stopped:"Fila parada"}[status],wrap=byId("updates_queue_jobs");
  const allItems=[...active,...queued],query=normalizeText(byId("updates_queue_search")?.value).toLowerCase(),stateFilter=normalizeText(byId("updates_queue_status_filter")?.value);
  const filtered=allItems.filter(job=>(!stateFilter||job.state===stateFilter)&&(!query||`${job.name} ${job.woo_product_id}`.toLowerCase().includes(query)));
  UPDATE_QUEUE.queuePageSize=normalizeListingPageSize(byId("updates_queue_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);
  const pages=Math.max(1,Math.ceil(filtered.length/UPDATE_QUEUE.queuePageSize));UPDATE_QUEUE.queuePage=Math.min(Math.max(1,UPDATE_QUEUE.queuePage),pages);
  const visible=filtered.slice((UPDATE_QUEUE.queuePage-1)*UPDATE_QUEUE.queuePageSize,UPDATE_QUEUE.queuePage*UPDATE_QUEUE.queuePageSize);
  byId("updates_queue_list_controls")?.classList.toggle("hidden",allItems.length===0);
  setText("updates_queue_found_count",listingRangeText(filtered.length,UPDATE_QUEUE.queuePage,UPDATE_QUEUE.queuePageSize));setText("updates_queue_page",`Página ${UPDATE_QUEUE.queuePage} de ${pages}`);setDisabled("updates_queue_prev",UPDATE_QUEUE.queuePage<=1);setDisabled("updates_queue_next",UPDATE_QUEUE.queuePage>=pages);
  byId("updates_queue_meta").textContent=`${allItems.length} produtos · ${label} · ${updateQueueDisplayName(queueName)}`;
  wrap.innerHTML=visible.map(job=>compactUpdateRow(job,job.state==="executing"?"Agora":job.queue_position||queued.indexOf(job)+1)).join("")||`<div class="notice">${allItems.length?"Nenhum produto corresponde aos filtros da fila.":"Nenhum produto na fila ativa."}</div>`;bindOperationalDetails(wrap);
  const select=byId("updates_queue_select"), queues=Array.isArray(UPDATE_QUEUE.queue?.queues)?UPDATE_QUEUE.queue.queues:[];
  if(select){select.innerHTML=queues.map(item=>`<option value="${escapeHtml(item.name)}" ${item.name===queueName?"selected":""}>${escapeHtml(updateQueueDisplayName(item.name))} (${item.completed}/${item.total})</option>`).join("")||'<option value="default">Padrão</option>';select.disabled=status==="running";}
  const metadata=queues.find(item=>item.name===queueName),total=Number(metadata?.total||0);setText("updates_queue_checkpoint",`${formatPtBrDateTime(metadata?.last_completed_at,"Sem conclusão registrada")} | ${formatPtBrInteger(total)} itens`);
  byId("updates_queue_start").textContent=status==="paused"?"Continuar fila":"Executar fila";byId("updates_queue_pause").disabled=status!=="running";
  renderUpdateListsManager();
}

function renderUpdateListsManager(){
  const wrap=byId("update_lists_rows");if(!wrap)return;
  const queues=Array.isArray(UPDATE_QUEUE.queue?.queues)?UPDATE_QUEUE.queue.queues:[],active=normalizeText(UPDATE_QUEUE.queue?.active_queue,"default"),running=UPDATE_QUEUE.queue?.status==="running";
  wrap.innerHTML=queues.map(item=>{const name=normalizeText(item.name),displayName=updateQueueDisplayName(name),isActive=name===active,isDefault=name==="default",empty=Number(item.total||0)===0;return `<article class="update-list-row" data-update-list-name="${escapeHtml(name)}"><div class="update-list-copy"><strong>${escapeHtml(displayName)}</strong><span class="small">${item.total||0} itens · ${item.completed||0} concluídos · ${item.pending||0} pendentes</span><span class="small">Última conclusão: ${escapeHtml(item.last_completed_at||"Não registrada")} · ${escapeHtml(item.file||"")}</span></div><div class="row"><button class="btn-secondary btn-sm" data-update-list-action="preview" type="button">Visualizar</button><button class="btn-secondary btn-sm" data-update-list-action="rename" type="button" ${isDefault||running?"disabled":""}>Renomear</button><button class="btn-success btn-sm" data-update-list-action="activate" type="button" ${isActive||running?"disabled":""}>${isActive?"Ativa":"Ativar"}</button><button class="btn-secondary btn-sm" data-update-list-action="clear" type="button" ${empty||running?"disabled":""}>Limpar itens</button><button class="btn-danger btn-sm" data-update-list-action="delete" type="button" ${isDefault||running?"disabled":""}>Apagar</button></div></article>`;}).join("")||'<div class="notice">Nenhuma lista disponível.</div>';
}

function openUpdateListsModal(){byId("update_lists_modal")?.classList.remove("hidden");renderUpdateListsManager();byId("update_lists_new_name")?.focus();}
function closeUpdateListsModal(){byId("update_lists_modal")?.classList.add("hidden");byId("open_update_lists_modal")?.focus();}

async function createManagedUpdateList(){const input=byId("update_lists_new_name"),name=normalizeText(input?.value);if(!name){notify("Informe o nome da nova lista.","error");return;}const result=await postJson("/atualizacoes/filas/criar",{name});UPDATE_QUEUE.queue=result.queue;if(input)input.value="";renderOperationalQueue();notify(`Lista ${name} criada e ativada.`,"ok");}

function openUpdateListRenameModal(name){UPDATE_QUEUE.renameQueueName=name;const displayName=updateQueueDisplayName(name),modal=byId("update_list_rename_modal"),input=byId("update_list_rename_name");setText("update_list_rename_help",`Renomeando a lista "${displayName}".`);if(input)input.value=displayName;modal?.classList.remove("hidden");input?.focus();input?.select();}
function closeUpdateListRenameModal(){byId("update_list_rename_modal")?.classList.add("hidden");UPDATE_QUEUE.renameQueueName="";}
async function confirmUpdateListRename(){const name=UPDATE_QUEUE.renameQueueName,newName=normalizeText(byId("update_list_rename_name")?.value);if(!name||!newName){notify("Informe o novo nome.","error");return;}const button=byId("update_list_rename_confirm");if(button)button.disabled=true;try{const result=await postJson("/atualizacoes/filas/renomear",{name,new_name:newName});UPDATE_QUEUE.queue=result.queue;closeUpdateListRenameModal();await refreshUpdateJobs();renderUpdateListsManager();notify(`Lista renomeada para ${newName}.`,"ok");}finally{if(button)button.disabled=false;}}

function renderUpdateListPreview(){const query=normalizeText(byId("update_list_preview_search")?.value).toLowerCase(),all=UPDATE_QUEUE.previewItems||[],items=all.filter(item=>!query||`${item.name} ${item.woo_product_id} ${item.state}`.toLowerCase().includes(query));UPDATE_QUEUE.previewPageSize=normalizeListingPageSize(byId("update_list_preview_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);const pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.previewPageSize));UPDATE_QUEUE.previewPage=Math.min(Math.max(1,UPDATE_QUEUE.previewPage),pages);const visible=items.slice((UPDATE_QUEUE.previewPage-1)*UPDATE_QUEUE.previewPageSize,UPDATE_QUEUE.previewPage*UPDATE_QUEUE.previewPageSize),body=byId("update_list_preview_rows");if(body)body.innerHTML=visible.map(item=>`<tr><td>${escapeHtml(item.position||"-")}</td><td>#${escapeHtml(item.woo_product_id)}</td><td><strong>${escapeHtml(item.name)}</strong>${item.execution_error?`<div class="updates-error">${escapeHtml(item.execution_error)}</div>`:""}</td><td>${escapeHtml(updateStatusLabel(item.state))}</td><td>${escapeHtml(item.plugintema_version||"-")} → ${escapeHtml(item.source_version||"-")}</td><td>${escapeHtml(item.completed_at||item.updated_at||item.queued_at||"-")}</td><td>${escapeHtml(item.last_completed_step||"-")}</td></tr>`).join("")||'<tr><td colspan="7">Nenhum item encontrado nesta lista.</td></tr>';setText("update_list_preview_count",`${items.length} de ${all.length} itens`);setText("update_list_preview_result_meta",listingRangeText(items.length,UPDATE_QUEUE.previewPage,UPDATE_QUEUE.previewPageSize));setText("update_list_preview_page",`Página ${UPDATE_QUEUE.previewPage} de ${pages}`);setDisabled("update_list_preview_prev",UPDATE_QUEUE.previewPage<=1);setDisabled("update_list_preview_next",UPDATE_QUEUE.previewPage>=pages);}
async function openUpdateListPreviewModal(name){UPDATE_QUEUE.previewQueueName=name;UPDATE_QUEUE.previewPage=1;UPDATE_QUEUE.previewItems=[];const modal=byId("update_list_preview_modal");modal?.classList.remove("hidden");modal?.setAttribute("aria-busy","true");setText("update_list_preview_title",`Lista: ${updateQueueDisplayName(name)}`);byId("update_list_preview_rows").innerHTML='<tr><td colspan="7"><span class="modal-inline-loading" role="status"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando dados da lista...</span></span></td></tr>';try{const result=await getJson(`/atualizacoes/filas/detalhes?name=${encodeURIComponent(name)}`);UPDATE_QUEUE.previewItems=Array.isArray(result.items)?result.items:[];UPDATE_QUEUE.previewMetadata=result.queue||null;const meta=result.queue||{};byId("update_list_preview_summary").innerHTML=`<span><strong>${escapeHtml(meta.total||0)}</strong> itens</span><span><strong>${escapeHtml(meta.completed||0)}</strong> concluídos</span><span><strong>${escapeHtml(meta.pending||0)}</strong> pendentes</span><span>Arquivo: <strong>${escapeHtml(meta.file||"-")}</strong></span><span>Última conclusão: <strong>${escapeHtml(meta.last_completed_at||"Não registrada")}</strong></span>`;renderUpdateListPreview();}finally{modal?.setAttribute("aria-busy","false");}}
function closeUpdateListPreviewModal(){byId("update_list_preview_modal")?.classList.add("hidden");UPDATE_QUEUE.previewQueueName="";}

async function handleUpdateListAction(button){const row=button.closest("[data-update-list-name]"),name=normalizeText(row?.dataset.updateListName),displayName=updateQueueDisplayName(name),action=button.dataset.updateListAction;if(!name)return;if(action==="rename"){openUpdateListRenameModal(name);return;}if(action==="preview"){await openUpdateListPreviewModal(name);return;}button.disabled=true;try{let result;if(action==="activate")result=await postJson("/atualizacoes/filas/selecionar",{name});else if(action==="clear"){if(!confirm(`Limpar todos os itens da lista "${displayName}"? A lista será mantida e ficará com 0 itens.`))return;result=await postJson("/atualizacoes/filas/limpar",{name});notify(`Lista ${displayName} limpa.`,"ok");}else if(action==="delete"){if(!confirm(`Apagar a lista de atualização "${displayName}"? Os itens pendentes nela serão cancelados.`))return;result=await postJson("/atualizacoes/filas/apagar",{name});}if(result?.queue)UPDATE_QUEUE.queue=result.queue;await refreshUpdateJobs();renderUpdateListsManager();}finally{if(document.contains(button))button.disabled=false;}}
function renderUpdateHistory(){
  const states=UPDATE_QUEUE.historyMode==="completed"?["completed","rolled_back"]:["error","failed","blocked","rollback_required","canceled","interrupted"];
  const allHistoryStates=["completed","rolled_back","error","failed","blocked","rollback_required","canceled","interrupted"];
  const query=normalizeText(byId("updates_history_search")?.value).toLowerCase();
  const statusFilter=normalizeText(byId("updates_history_status_filter")?.value);
  const items=UPDATE_QUEUE.jobs.filter(j=>states.includes(j.state)&&(!statusFilter||j.state===statusFilter)&&(!query||`${j.name} ${j.woo_product_id}`.toLowerCase().includes(query)));
  UPDATE_QUEUE.historyPageSize=normalizeListingPageSize(byId("updates_history_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);
  const pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.historyPageSize));
  UPDATE_QUEUE.historyPage=Math.min(Math.max(1,UPDATE_QUEUE.historyPage),pages);
  const start=(UPDATE_QUEUE.historyPage-1)*UPDATE_QUEUE.historyPageSize, visible=items.slice(start,start+UPDATE_QUEUE.historyPageSize),wrap=byId("updates_history");
  wrap.innerHTML=visible.map(j=>compactUpdateRow(j)).join("")||'<div class="notice">Nenhum item neste histórico.</div>';
  setText("updates_history_result_meta",listingRangeText(items.length,UPDATE_QUEUE.historyPage,UPDATE_QUEUE.historyPageSize));
  setText("updates_history_page",`Página ${UPDATE_QUEUE.historyPage} de ${pages}`);
  setText("updates_history_summary",`${items.length} item(ns)`);
  setDisabled("updates_history_prev",UPDATE_QUEUE.historyPage<=1);setDisabled("updates_history_next",UPDATE_QUEUE.historyPage>=pages);
  const completedTab=byId("updates_history_completed"),errorsTab=byId("updates_history_errors"),completedActive=UPDATE_QUEUE.historyMode==="completed";
  const completedCount=UPDATE_QUEUE.jobs.filter(job=>["completed","rolled_back"].includes(job.state)).length;
  const errorCount=UPDATE_QUEUE.jobs.filter(job=>["error","failed","blocked","rollback_required","canceled","interrupted"].includes(job.state)).length;
  if(completedTab)completedTab.textContent=`Concluídos (${completedCount})`;if(errorsTab)errorsTab.textContent=`Erros (${errorCount})`;
  completedTab?.classList.toggle("is-active",completedActive);errorsTab?.classList.toggle("is-active",!completedActive);
  completedTab?.setAttribute("aria-selected",String(completedActive));errorsTab?.setAttribute("aria-selected",String(!completedActive));
  const hasHistory=UPDATE_QUEUE.jobs.some(job=>allHistoryStates.includes(job.state));
  byId("updates_history_controls")?.classList.toggle("hidden",!hasHistory);
  setDisabled("updates_history_download",!hasHistory);setDisabled("updates_history_delete",!hasHistory);
  bindOperationalDetails(wrap);
}

async function deleteUpdateHistory(){
  if(!confirm("Apagar todo o histórico de atualizações? Os registros concluídos e com erro serão removidos dos cards e das contagens. Esta ação não pode ser desfeita."))return;
  const button=byId("updates_history_delete");if(button)button.disabled=true;
  try{const result=await postJson("/atualizacoes/historico/apagar",{});UPDATE_QUEUE.selected.clear();UPDATE_QUEUE.historyPage=1;await refreshUpdateJobs();notify(`${result.removed||0} registro(s) removido(s) do histórico.`,"ok");}finally{renderUpdateHistory();}
}

function renderUpdateLogs(logs) {
  const target = byId("updates_log");
  if (!target) return;
  target.textContent = logs?.length ? logs.join("\n") : "Nenhum evento nesta sessão.";
  target.scrollTop = target.scrollHeight;
}

async function refreshUpdateJobs() {
  const result = await postJson("/atualizacoes/materializar", {comparison_rows: Object.values(UI.comparison.rowsById || {})});
  UPDATE_QUEUE.queue=result?.queue||UPDATE_QUEUE.queue;
  renderUpdateJobs(result?.jobs || []);
}

function startUpdateQueuePolling(){if(UPDATE_QUEUE.poll)return;UPDATE_QUEUE.poll=setInterval(async()=>{try{const result=await getJson("/atualizacoes/jobs");UPDATE_QUEUE.queue=result?.queue||UPDATE_QUEUE.queue;renderUpdateJobs(result?.jobs||[]);if(!["running"].includes(UPDATE_QUEUE.queue?.status)){clearInterval(UPDATE_QUEUE.poll);UPDATE_QUEUE.poll=null;}}catch(_error){clearInterval(UPDATE_QUEUE.poll);UPDATE_QUEUE.poll=null;}},2000);}

async function runUpdateBatch(action) {
  UPDATE_QUEUE.cancel=false;
  const ids=[...UPDATE_QUEUE.selected], stats={total:ids.length,processed:0,success:0,blocked:0,errors:0};
  const button=byId("updates_prepare_selected"),progress=byId("updates_batch_progress"),original=button?.textContent||"";
  progress?.classList.remove("is-complete");
  if(button){button.disabled=true;button.setAttribute("aria-busy","true");button.innerHTML='<span class="inline-loading-spinner" aria-hidden="true"></span><span>Preparando e gerando planos...</span>';}
  const showProgress=()=>{if(progress)progress.innerHTML=`<span class="inline-loading-spinner" aria-hidden="true"></span><span>${stats.processed}/${stats.total} processados · ${stats.success} sucesso · ${stats.blocked} bloqueados · ${stats.errors} erros · ${stats.total-stats.processed} restantes</span>`;};
  showProgress();
  try{for(const id of ids){if(UPDATE_QUEUE.cancel)break;try{const job=UPDATE_QUEUE.jobs.find(j=>j.job_id===id);if(job?.state==="plan_ready"&&job?.execution_plan?.ready===true){stats.success++;continue;}const prepared=await postJson("/atualizacoes/preparar",{job_id:id});if(prepared?.preview?.ready!==true){stats.blocked++;continue;}const planned=await postJson("/atualizacoes/plano",{job_id:id});if(planned?.plan?.ready===true)stats.success++;else stats.blocked++;}catch(error){(normalizeText(error?.responseData?.state)==="blocked"?stats.blocked++:stats.errors++);}finally{stats.processed++;showProgress();}}await refreshUpdateJobs();}
  finally{if(button){button.disabled=false;button.removeAttribute("aria-busy");button.textContent=original;}if(progress){progress.textContent=`${stats.processed}/${stats.total} processados · ${stats.success} sucesso · ${stats.blocked} bloqueados · ${stats.errors} erros · ${Math.max(0,stats.total-stats.processed)} restantes`;progress.classList.add("is-complete");}renderUpdateSummary();}
}

function openUpdateExecuteModal(job){UPDATE_QUEUE.modalJob=job;const modal=byId("update_execute_modal"), expected=`EXECUTAR ${job.woo_product_id}`,plan=job.execution_plan||{};byId("update_execute_summary").innerHTML=`<h3>${escapeHtml(job.name)}</h3><p>WooCommerce #${escapeHtml(job.woo_product_id)}</p><dl class="update-confirm-grid"><div><dt>Versão atual</dt><dd>${escapeHtml(job.plugintema_version)}</dd></div><div><dt>Versão efetiva</dt><dd>${escapeHtml(job.effective_source_version)}</dd></div><div><dt>Arquivo de produção</dt><dd>${escapeHtml(plan.current_zip?.remote_path||"-")}</dd></div><div><dt>SHA atual</dt><dd>${escapeHtml(plan.current_zip?.sha256||"-")}</dd></div><div><dt>SHA novo</dt><dd>${escapeHtml(plan.new_zip?.sha256||"-")}</dd></div><div><dt>Backup planejado</dt><dd>${escapeHtml(plan.backup?.path||"-")}</dd></div></dl>`;byId("update_execute_instruction").textContent=`Digite: ${expected}`;byId("update_execute_confirmation").value="";byId("update_execute_confirm").disabled=true;modal.classList.remove("hidden");byId("update_execute_confirmation").focus();}

async function confirmUpdateExecution(){const job=UPDATE_QUEUE.modalJob,confirmation=byId("update_execute_confirmation").value;await postJson("/atualizacoes/executar",{job_id:job.job_id,plan_id:job.execution_plan.plan_id,confirmation});byId("update_execute_modal").classList.add("hidden");const poll=setInterval(async()=>{try{const logs=await getJson(`/atualizacoes/logs?job_id=${encodeURIComponent(job.job_id)}`);renderUpdateLogs(logs.logs||[]);const jobs=await getJson("/atualizacoes/jobs");renderUpdateJobs(jobs.jobs||[]);const current=(jobs.jobs||[]).find(j=>j.job_id===job.job_id);if(current&&!['executing'].includes(current.state))clearInterval(poll);}catch(_error){clearInterval(poll);}},1000);}

function renderUpdatePrerequisites(items) {
  const rows = [
    ["WooCommerce", items?.woocommerce, "Loja de destino: produto, versão, variações e downloads atuais."],
    ["Fonte autenticada", items?.ultrapack, "Origem do arquivo definida pelo produto: PluginTheme ou UltraPackV2. As sessões permanecem separadas."],
    ["SSH leitura", items?.ssh_read, "Leitura do ZIP atual e conferência de integridade no servidor."],
    ["Execução individual", items?.update_execution, "Libera apenas produtos explicitamente autorizados para execução controlada."],
    ["WooCommerce escrita", items?.woocommerce_write, "Permite alterar a versão somente após validações e confirmação final."],
  ];
  const blocked=rows.filter(([,item])=>(item?.status||"")!=="OK");
  byId("updates_environment_chips").innerHTML=rows.map(([label,item,help])=>`<span class="environment-chip ${(item?.status||"")==="OK"?"is-ok":"is-blocked"}">${escapeHtml(label)} <strong>${escapeHtml(item?.status||"AGUARDANDO")}</strong><button class="comparison-help" type="button" aria-label="Sobre ${escapeHtml(label)}" data-tooltip="${escapeHtml(help)}">?</button></span>`).join("");
  byId("updates_environment_summary").textContent=blocked.length?`${blocked.length} requisito(s) exigem atenção`:"Todos os pré-requisitos estão OK";
  const cookieStatus = items?.plugintheme_cookies || {};
  const cookieNode = byId("plugintheme_cookie_status");
  if (cookieNode) {
    const status = normalizeText(cookieStatus.status, "AUSENTES");
    const count = Math.max(0, toInt(cookieStatus.count, 0));
    cookieNode.classList.toggle("is-ok", cookieStatus.ok === true);
    cookieNode.classList.toggle("is-blocked", cookieStatus.ok !== true);
    cookieNode.textContent = `Cookies necessários: ${status}${count ? ` (${count} cookie(s) do domínio)` : ""}.`;
  }
}

async function refreshUpdatePrerequisites() {
  const button = byId("updates_prerequisites_btn");
  if (button) { button.disabled = true; button.textContent = "Verificando..."; }
  try {
    const result = await postJson("/atualizacoes/prerequisitos", {check_ssh_connection: false});
    renderUpdatePrerequisites(result?.prerequisites || {});
  } finally {
    if (button) { button.disabled = false; button.textContent = "Verificar pré-requisitos"; }
  }
}

function updateSourceLabel(job) {
  const explicit = normalizeText(job?.source_site || job?.source_site_key || job?.origin_site || job?.origin || "");
  if (explicit) {
    const normalized = explicit.toLowerCase();
    if (normalized.includes("plugintheme") || normalized.includes("plugin_theme")) return "PluginTheme";
    if (normalized.includes("ultrapack")) return "UltraPackV2";
    return explicit;
  }
  const sourceUrl = normalizeText(job?.ultrapack_url || job?.source_product_url || job?.source_url || "").toLowerCase();
  if (sourceUrl.includes("plugintheme")) return "PluginTheme";
  if (sourceUrl.includes("ultrapack")) return "UltraPackV2";
  return "Origem não informada";
}

window.__crapscraperPagination = Object.assign(window.__crapscraperPagination || {}, {
  catalogs(page) {
    UI.catalogPage = Math.max(1, toInt(page, 1));
    refreshCatalogos();
  },
  comparison(page) {
    UI.comparison.page = Math.max(1, toInt(page, 1));
    refreshComparison({ page: UI.comparison.page });
  },
  updatesWaiting(page) {
    UPDATE_QUEUE.page = Math.max(1, toInt(page, 1));
    renderUpdateJobs();
  },
  updatesQueue(page) {
    UPDATE_QUEUE.queuePage = Math.max(1, toInt(page, 1));
    renderOperationalQueue();
  },
  updatesHistory(page) {
    UPDATE_QUEUE.historyPage = Math.max(1, toInt(page, 1));
    renderUpdateHistory();
  },
  updateListPreview(page) {
    UPDATE_QUEUE.previewPage = Math.max(1, toInt(page, 1));
    renderUpdateListPreview();
  },
  pluginTemaManager(page) {
    UI.plugintemaManagePage = Math.max(1, toInt(page, 1));
    renderPluginTemaManagedRows();
  },
  catalogPreview(page) {
    setCatalogPreviewPage(page);
  },
});

function selectedStoreKinds() {
  return qsa('input[name="store_kind"]:checked').map(node => node.value);
}

function storePriceSummary(rows) {
  if (!Array.isArray(rows) || !rows.length) return "Nenhum preço encontrado";
  return rows.map(item => {
    const money = value => {
      const parsed = Number.parseFloat(String(value || "").replace(",", "."));
      return Number.isFinite(parsed)
        ? parsed.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
        : "não informado";
    };
    const regular = `Original: ${money(item.regular_price)}`;
    const sale = item.sale_price ? `Promocional: ${money(item.sale_price)}` : "Sem promocional";
    return `${regular}<br>${sale}<br><small>${Number(item.count || 0)} variação(ões)</small>`;
  }).join("<br>");
}

function storeKindPriceCard(kind, summary) {
  const label = kind === "theme" ? "Temas" : "Plugins";
  return `<section class="store-kind-prices" aria-label="Preços atuais de ${label}">
    <div class="store-kind-prices-head"><strong>${label}</strong><span>${Number(summary?.product_count || 0)} produtos · ${Number(summary?.variation_count || 0)} variações</span></div>
    <div class="store-current-prices">
      <div><strong>Anual</strong><span>${storePriceSummary(summary?.distribution?.annual)}</span></div>
      <div><strong>Vitalício</strong><span>${storePriceSummary(summary?.distribution?.lifetime)}</span></div>
    </div>
  </section>`;
}

async function refreshStorePricing() {
  const preview = byId("store_preview");
  const kinds = selectedStoreKinds();
  if (!preview) return;
  if (!kinds.length) {
    preview.innerHTML = '<strong>Selecione Plugins e/ou Temas.</strong>';
    return;
  }
  preview.setAttribute("aria-busy", "true");
  preview.innerHTML = '<span class="modal-inline-loading"><span class="inline-loading-spinner" aria-hidden="true"></span><span>Carregando valores atuais de Plugins e Temas…</span></span>';
  try {
    const query = kinds.map(kind => `tipo=${encodeURIComponent(kind)}`).join("&");
    const data = await getJsonWithTimeout(`${UI.endpoints.storePricing || "/loja/precos"}?${query}`, 45000);
    preview.innerHTML = `<div class="store-readonly-note">Valores atuais no WooCommerce · Somente leitura</div><div class="store-kind-price-grid">${kinds.map(kind => storeKindPriceCard(kind, data.by_kind?.[kind])).join("")}</div>`;
  } catch (error) {
    preview.innerHTML = `<div class="updates-error" role="alert"><strong>Não foi possível carregar a prévia.</strong><br>${escapeHtml(error?.message || String(error))}<br><button class="btn-secondary btn-sm" type="button" id="store_retry_btn">Tentar novamente</button></div>`;
    byId("store_retry_btn")?.addEventListener("click", refreshStorePricing, { once: true });
  } finally {
    preview.setAttribute("aria-busy", "false");
  }
}

function updateStoreSubmitState() {
  const button = byId("store_apply_btn");
  if (button) button.disabled = byId("store_confirmation")?.value !== "ALTERAR PRECOS";
}

async function waitForStorePriceJob(jobId, resultNode) {
  const startedAt = Date.now();
  const maxWaitMs = 60 * 60 * 1000;
  while (true) {
    if (Date.now() - startedAt > maxWaitMs) {
      throw new Error("A atualização excedeu 60 minutos. Verifique a conexão com o WooCommerce e tente novamente.");
    }
    const status = await getJsonWithTimeout(`${UI.endpoints.storePricing || "/loja/precos"}/status?job_id=${encodeURIComponent(jobId)}`, 15000);
    if (status.job_id !== jobId || status.status === "idle") {
      throw new Error("O servidor perdeu o acompanhamento desta atualização. Recarregue a página e tente novamente.");
    }
    const completed = Number(status.completed || 0);
    const total = Number(status.total || 0);
    const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
    if (resultNode) {
      resultNode.classList.remove("hidden");
      resultNode.className = "store-progress";
      resultNode.setAttribute("aria-busy", "true");
      const phaseLabel = status.phase === "updating" ? "Aplicando novos preços" : "Lendo dados dos produtos";
      resultNode.innerHTML = `<div class="store-progress-phase">${escapeHtml(phaseLabel)}</div><div class="store-progress-copy"><strong>${escapeHtml(status.message || "Processando alteração de preços…")}</strong><span>${percent}%</span></div><div class="store-progress-track" role="progressbar" aria-label="Progresso da atualização de preços" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><span style="transform:scaleX(${percent / 100})"></span></div><div class="small">${completed} de ${total} produtos concluídos nesta etapa</div>`;
    }
    if (status.status === "completed") return status;
    if (status.status === "error") throw Object.assign(new Error(status.message || "A alteração de preços falhou."), { responseData: status });
    await new Promise(resolve => window.setTimeout(resolve, 750));
  }
}

async function submitStorePricing(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = byId("store_apply_btn");
  const resultNode = byId("store_result");
  const kinds = selectedStoreKinds();
  if (!kinds.length) { notify("Selecione Plugins e/ou Temas.", "error"); return; }
  const payload = { kinds };
  ["annual_regular", "annual_sale", "lifetime_regular", "lifetime_sale", "confirmation"].forEach(name => {
    payload[name] = form.elements[name]?.value || "";
  });
  if (button) { button.disabled = true; button.textContent = "Aplicando preços..."; }
  if (resultNode) { resultNode.classList.add("hidden"); resultNode.textContent = ""; }
  try {
    const started = await postJson(UI.endpoints.storePricing || "/loja/precos", payload);
    const result = await waitForStorePriceJob(started.job_id, resultNode);
    if (resultNode) { resultNode.className = "notice is-success"; resultNode.removeAttribute("aria-busy"); resultNode.textContent = result.message; }
    form.elements.confirmation.value = "";
    notify(result.message, "ok");
    await refreshStorePricing();
  } catch (error) {
    const detail = error?.responseData?.message || error?.message || String(error);
    if (resultNode) { resultNode.className = "notice is-danger"; resultNode.removeAttribute("aria-busy"); resultNode.innerHTML = `<strong>Atualização incompleta.</strong><br>${escapeHtml(detail)}<br><span class="small">Revise a conexão ou atualize o catálogo antes de tentar novamente.</span>`; }
    notify(detail, "error");
  } finally {
    if (button) { button.textContent = "Aplicar preços em lote"; }
    updateStoreSubmitState();
  }
}

function bindMainTabs() {
  const principalBtn = byId("tab_btn_principal");
  const catalogosBtn = byId("tab_btn_catalogos");
  const filaBtn = byId("tab_btn_fila");
  const comparacaoBtn = byId("tab_btn_comparacao");
  const atualizacoesBtn = byId("tab_btn_atualizacoes");
  const adicoesBtn = byId("tab_btn_adicoes");
  const lojaBtn = byId("tab_btn_loja");
  const filterNode = byId("catalogos_filter_slot");

  byId("open_catalogos_modal_btn")?.addEventListener("click", openCatalogosModal);
  qsa("[data-catalog-rename-close]").forEach((node) => node.addEventListener("click", closeCatalogRenameModal));
  byId("catalog_rename_confirm")?.addEventListener("click", confirmCatalogRename);
  byId("catalog_rename_name")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); confirmCatalogRename(); }
  });
  byId("open_config_modal_btn")?.addEventListener("click", openConfigModal);
  qsa("[data-config-modal-close]").forEach((node) => node.addEventListener("click", closeConfigModal));
  byId("comparison_update_plugintema_btn")?.addEventListener("click", openPluginTemaUpdateModal);
  byId("comparison_manage_plugintema_btn")?.addEventListener("click", openPluginTemaManageModal);
  byId("plugintema_manage_close")?.addEventListener("click", closePluginTemaManageModal);
  qs("[data-plugintema-manage-close]")?.addEventListener("click", closePluginTemaManageModal);
  byId("plugintema_manage_catalog")?.addEventListener("change", (event) => loadPluginTemaManagedCatalog(event.target.value));
  byId("plugintema_manage_search")?.addEventListener("input", () => { UI.plugintemaManagePage = 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_type")?.addEventListener("change", () => { UI.plugintemaManagePage = 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_status")?.addEventListener("change", () => { UI.plugintemaManagePage = 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_page_size")?.addEventListener("change", (event) => { UI.plugintemaManagePageSize = Number.parseInt(event.target.value, 10) || 100; UI.plugintemaManagePage = 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_prev")?.addEventListener("click", () => { UI.plugintemaManagePage -= 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_next")?.addEventListener("click", () => { UI.plugintemaManagePage += 1; renderPluginTemaManagedRows(); });
  byId("plugintema_manage_delete")?.addEventListener("click", deletePluginTemaManagedCatalog);
  byId("plugintema_manage_download")?.addEventListener("click", downloadPluginTemaManagedCatalog);
  byId("plugintema_manage_catalog_cards")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-catalog-action]");
    const card = button?.closest("[data-plugintema-catalog-id]");
    if (!button || !card) return;
    const catalogId = normalizeText(card.dataset.plugintemaCatalogId);
    const select = byId("plugintema_manage_catalog");
    if (select) select.value = catalogId;
    if (button.dataset.catalogAction === "select") {
      await loadPluginTemaManagedCatalog(catalogId);
      const target = byId("comparison_target_catalog");
      if (target) target.value = catalogId;
    } else if (button.dataset.catalogAction === "download") {
      await loadPluginTemaManagedCatalog(catalogId);
      downloadPluginTemaManagedCatalog();
    } else if (button.dataset.catalogAction === "rename") {
      await renamePluginTemaManagedCatalog(catalogId);
    } else if (button.dataset.catalogAction === "delete") {
      await deletePluginTemaManagedCatalog();
    }
  });
  byId("plugintema_update_modal_close")?.addEventListener("click", closePluginTemaUpdateModal);
  byId("plugintema_update_cancel")?.addEventListener("click", closePluginTemaUpdateModal);
  qs("[data-plugintema-close]")?.addEventListener("click", closePluginTemaUpdateModal);
  byId("plugintema_update_submit")?.addEventListener("click", generatePluginTemaComparisonCatalog);
  byId("plugintema_product_search_btn")?.addEventListener("click", searchPluginTemaProducts);
  byId("plugintema_product_search")?.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); searchPluginTemaProducts(); } });
  byId("plugintema_search_results")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-add-plugintema-product]");
    if (!button) return;
    const product = JSON.parse(button.dataset.addPlugintemaProduct || "{}");
    if (product.id) {
      UI.plugintemaSelectedProducts.set(String(product.id), product);
      if (byId("plugintema_custom_kind")) byId("plugintema_custom_kind").value = "all";
    }
    renderPluginTemaSelectedProducts();
  });
  byId("plugintema_selected_products")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-remove-plugintema-product]");
    if (!button) return;
    UI.plugintemaSelectedProducts.delete(String(button.dataset.removePlugintemaProduct));
    renderPluginTemaSelectedProducts();
  });
  qsa('input[name="plugintema_preset_kind"], input[name="plugintema_custom_mode"]').forEach((input) => input.addEventListener("change", () => syncPluginTemaCatalogMode(input)));
  byId("catalogos_remove_zero_btn")?.addEventListener("click", removeZeroCatalogoContexts);
  byId("updates_copy_log")?.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(byId("updates_log")?.textContent || ""); notify("Logs copiados."); }
    catch (_error) { notify("Não foi possível copiar os logs."); }
  });
  byId("catalogos_preview_copy_log_btn")?.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(UI.catalogPreview.rawText || ""); notify("Log completo copiado."); }
    catch (_error) { notify("Não foi possível copiar o log."); }
  });

  if (principalBtn) {
    principalBtn.addEventListener("click", () => {
      activateMainTab("principal");
    });
  }

  if (catalogosBtn) {
    catalogosBtn.addEventListener("click", async () => {
      activateMainTab("catalogos");
      await refreshCatalogos();
    });
  }

  if (filaBtn) {
    filaBtn.addEventListener("click", async () => {
      activateMainTab("fila");
      await refreshFila();
    });
  }

  if (comparacaoBtn) {
    comparacaoBtn.addEventListener("click", async () => {
      activateMainTab("comparacao");
      await loadComparisonSources();
    });
  }

  if (atualizacoesBtn) {
    atualizacoesBtn.addEventListener("click", async function () {
      activateMainTab("atualizacoes");
      await refreshUpdatePrerequisites();
      await refreshUpdateJobs();
    });
  }

  const updatesRefresh = byId("updates_refresh_btn");
  if (updatesRefresh) updatesRefresh.addEventListener("click", refreshUpdateJobs);
  const prerequisitesRefresh = byId("updates_prerequisites_btn");
  if (prerequisitesRefresh) prerequisitesRefresh.addEventListener("click", refreshUpdatePrerequisites);
  byId("plugintheme_session_renew")?.addEventListener("click", async event => {
    const button = event.currentTarget, message = byId("plugintheme_session_message");
    const cookieStatus = byId("plugintheme_cookie_status");
    button.disabled = true;
    button.textContent = "Abrindo Chrome...";
    if (message) message.textContent = "Abrindo o perfil exclusivo do PluginTheme...";
    if (cookieStatus) cookieStatus.textContent = "Cookies necessários: revalidação pendente enquanto o Chrome estiver aberto.";
    try {
      const result = await postJson("/atualizacoes/plugintheme/renovar-sessao", {});
      if (message) message.textContent = result.message || "Chrome aberto. Faça login e feche a janela ao concluir.";
      renderUpdateLogs(["🔐 Renovação manual iniciada.", "Use somente a janela aberta, confirme a área da conta e feche o Chrome antes de preparar."]);
    } catch (error) {
      if (message) message.textContent = error?.message || String(error);
    } finally {
      button.disabled = false;
      button.textContent = "🔐 Renovar sessão PluginTheme";
    }
  });
  ["updates_status_filter","updates_type_filter","updates_version_filter","updates_relationship_filter"].forEach(id=>byId(id)?.addEventListener("change",()=>{UPDATE_QUEUE.page=1;renderUpdateJobs();}));
  byId("updates_search_filter")?.addEventListener("input",()=>{UPDATE_QUEUE.page=1;renderUpdateJobs();});
  byId("updates_clear_filters")?.addEventListener("click",()=>{["updates_status_filter","updates_type_filter","updates_search_filter","updates_version_filter","updates_relationship_filter"].forEach(id=>{if(byId(id))byId(id).value="";});renderUpdateJobs();});
  const bulkSelectable=j=>!["queued","executing","completed","rolled_back","canceled"].includes(j.state);
  byId("updates_select_page")?.addEventListener("click",()=>{const start=(UPDATE_QUEUE.page-1)*UPDATE_QUEUE.pageSize;UPDATE_QUEUE.workingFiltered.slice(start,start+UPDATE_QUEUE.pageSize).filter(bulkSelectable).forEach(j=>UPDATE_QUEUE.selected.add(j.job_id));renderUpdateJobs();});
  byId("updates_select_filtered")?.addEventListener("click",()=>{UPDATE_QUEUE.workingFiltered.filter(bulkSelectable).forEach(j=>UPDATE_QUEUE.selected.add(j.job_id));renderUpdateJobs();});
  byId("updates_clear_selection")?.addEventListener("click",()=>{UPDATE_QUEUE.selected.clear();renderUpdateJobs();});
  byId("updates_prepare_selected")?.addEventListener("click",()=>runUpdateBatch("prepare_and_plan"));
  byId("updates_enqueue_selected")?.addEventListener("click",async()=>{const selected=[...UPDATE_QUEUE.selected].map(id=>UPDATE_QUEUE.jobs.find(j=>j.job_id===id)).filter(Boolean),job_ids=selected.filter(j=>j.state==="plan_ready"&&j.execution_eligible===true).map(j=>j.job_id),rejected=selected.length-job_ids.length;if(!job_ids.length){notify("Nenhum item selecionado está com plano pronto e autorizado para execução.","error");return;}const result=await postJson("/atualizacoes/fila/adicionar",{job_ids});const added=(result.added||[]).length;if(rejected)notify(`${added} adicionado(s); ${rejected} ignorado(s) por não estarem elegíveis.`,"warning");else notify(`${added} produto(s) adicionado(s) à fila.`,"ok");UPDATE_QUEUE.selected.clear();await refreshUpdateJobs();});
  byId("updates_queue_start")?.addEventListener("click",async()=>{const path=UPDATE_QUEUE.queue?.status==="paused"?"/atualizacoes/fila/continuar":"/atualizacoes/fila/iniciar";await postJson(path,{});await refreshUpdateJobs();startUpdateQueuePolling();});
  byId("updates_queue_pause")?.addEventListener("click",async()=>{await postJson("/atualizacoes/fila/pausar",{});await refreshUpdateJobs();});
  byId("updates_queue_cancel")?.addEventListener("click",async()=>{if(!confirm("Cancelar todos os jobs que ainda não iniciaram?"))return;await postJson("/atualizacoes/fila/cancelar-pendentes",{});await refreshUpdateJobs();});
  byId("updates_queue_select")?.addEventListener("change",async event=>{const result=await postJson("/atualizacoes/filas/selecionar",{name:event.target.value});UPDATE_QUEUE.queue=result.queue;await refreshUpdateJobs();});
  byId("updates_queue_search")?.addEventListener("input",()=>{UPDATE_QUEUE.queuePage=1;renderOperationalQueue();});
  byId("updates_queue_status_filter")?.addEventListener("change",()=>{UPDATE_QUEUE.queuePage=1;renderOperationalQueue();});
  byId("updates_queue_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.queuePage=1;renderOperationalQueue();});
  byId("updates_history_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});
  byId("update_list_preview_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.previewPage=1;renderUpdateListPreview();});
  byId("updates_queue_prev")?.addEventListener("click",()=>{UPDATE_QUEUE.queuePage=Math.max(1,UPDATE_QUEUE.queuePage-1);renderOperationalQueue();});
  byId("updates_queue_next")?.addEventListener("click",()=>{UPDATE_QUEUE.queuePage+=1;renderOperationalQueue();});
  byId("updates_queue_create")?.addEventListener("click",async()=>{const input=byId("updates_queue_new_name"),name=normalizeText(input?.value);if(!name){notify("Informe o nome da nova fila.","error");return;}const result=await postJson("/atualizacoes/filas/criar",{name});if(input)input.value="";UPDATE_QUEUE.queue=result.queue;await refreshUpdateJobs();notify(`Fila ${name} criada e selecionada.`,"ok");});
  byId("open_update_lists_modal")?.addEventListener("click",openUpdateListsModal);
  qsa("[data-update-lists-close]").forEach(node=>node.addEventListener("click",closeUpdateListsModal));
  byId("update_lists_create")?.addEventListener("click",createManagedUpdateList);
  byId("update_lists_new_name")?.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();createManagedUpdateList();}});
  byId("update_lists_rows")?.addEventListener("click",event=>{const button=event.target.closest("[data-update-list-action]");if(button)handleUpdateListAction(button).catch(error=>notify(error?.message||String(error),"error"));});
  qsa("[data-update-list-rename-close]").forEach(node=>node.addEventListener("click",closeUpdateListRenameModal));
  qsa("[data-update-list-preview-close]").forEach(node=>node.addEventListener("click",closeUpdateListPreviewModal));
  byId("update_list_rename_confirm")?.addEventListener("click",()=>confirmUpdateListRename().catch(error=>notify(error?.message||String(error),"error")));
  byId("update_list_rename_name")?.addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();confirmUpdateListRename().catch(error=>notify(error?.message||String(error),"error"));}});
  byId("update_list_preview_search")?.addEventListener("input",()=>{UPDATE_QUEUE.previewPage=1;renderUpdateListPreview();});
  byId("update_list_preview_prev")?.addEventListener("click",()=>{UPDATE_QUEUE.previewPage=Math.max(1,UPDATE_QUEUE.previewPage-1);renderUpdateListPreview();});
  byId("update_list_preview_next")?.addEventListener("click",()=>{UPDATE_QUEUE.previewPage+=1;renderUpdateListPreview();});
  byId("updates_environment_toggle")?.addEventListener("click",()=>{const details=byId("updates_environment_details"),hidden=details.classList.toggle("hidden"),button=byId("updates_environment_toggle");button.setAttribute("aria-expanded",String(!hidden));button.textContent=hidden?"Ver diagnóstico":"Ocultar diagnóstico";});
  byId("updates_history_completed")?.addEventListener("click",()=>{UPDATE_QUEUE.historyMode="completed";if(byId("updates_history_status_filter"))byId("updates_history_status_filter").value="";UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});
  byId("updates_history_errors")?.addEventListener("click",()=>{UPDATE_QUEUE.historyMode="errors";if(byId("updates_history_status_filter"))byId("updates_history_status_filter").value="";UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});
  byId("updates_history_status_filter")?.addEventListener("change",()=>{UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});
  byId("updates_history_download")?.addEventListener("click",()=>{window.location.href="/atualizacoes/historico/baixar";});
  byId("updates_history_delete")?.addEventListener("click",()=>deleteUpdateHistory().catch(error=>notify(error?.message||String(error),"error")));
  qsa("[data-update-modal-close]").forEach(node=>node.addEventListener("click",()=>byId("update_execute_modal")?.classList.add("hidden")));
  byId("update_execute_confirmation")?.addEventListener("input",event=>{const job=UPDATE_QUEUE.modalJob;byId("update_execute_confirm").disabled=!job||event.target.value!==`EXECUTAR ${job.woo_product_id}`;});
  byId("update_execute_confirm")?.addEventListener("click",confirmUpdateExecution);
  byId("updates_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.page=1;renderUpdateJobs();});
  byId("updates_prev_page")?.addEventListener("click",()=>{UPDATE_QUEUE.page=Math.max(1,UPDATE_QUEUE.page-1);renderUpdateJobs();});
  byId("updates_next_page")?.addEventListener("click",()=>{UPDATE_QUEUE.page+=1;renderUpdateJobs();});

  if (adicoesBtn) {
    adicoesBtn.addEventListener("click", function () {
      activateMainTab("adicoes");
    });
  }

  if (lojaBtn) {
    lojaBtn.addEventListener("click", async function () {
      activateMainTab("loja");
      await refreshStorePricing();
    });
  }
  qsa('input[name="store_kind"]').forEach(node => node.addEventListener("change", refreshStorePricing));
  byId("store_confirmation")?.addEventListener("input", updateStoreSubmitState);
  byId("store_pricing_form")?.addEventListener("submit", submitStorePricing);

  if (filterNode) {
    filterNode.addEventListener("change", async () => {
      UI.catalogPage = 1;
      await refreshCatalogos();
    });
  }
  byId("catalogos_search")?.addEventListener("input",()=>{UI.catalogPage=1;refreshCatalogos();});
  byId("catalogos_prev_page")?.addEventListener("click",()=>{UI.catalogPage=Math.max(1,toInt(UI.catalogPage,1)-1);refreshCatalogos();});
  byId("catalogos_next_page")?.addEventListener("click",()=>{UI.catalogPage=toInt(UI.catalogPage,1)+1;refreshCatalogos();});
  byId("updates_history_search")?.addEventListener("input",()=>{UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});
  byId("updates_history_prev")?.addEventListener("click",()=>{UPDATE_QUEUE.historyPage=Math.max(1,UPDATE_QUEUE.historyPage-1);renderUpdateHistory();});
  byId("updates_history_next")?.addEventListener("click",()=>{UPDATE_QUEUE.historyPage+=1;renderUpdateHistory();});

  activateMainTab("principal");
}

function init() {
  exposeGlobals();
  bindFormDirtyTracking();
  bindContextChaining();
  bindVisibilityRefresh();
  organizeCollectionUi();
  bindMainTabs();
  bindComparisonControls();
  bindCatalogPreviewSearch();
  hydrateFromBoot();
  loadState({ forceConfigWrite: false, forceRunsRefresh: true });

  if (isManagerMode()) {
    refreshRunsList({ force: true });
  }

  startPolling();
}

if (window.__CRAPSCRAPER_COMPARISON_TEST__) {
  window.__comparisonUiTest = Object.freeze({
    renderComparison,
    bindComparisonControls,
    openComparisonLinkModal,
    closeComparisonLinkModal,
    openComparisonDiagnosticModal,
    closeComparisonDiagnosticModal,
  });
}

document.addEventListener("change", (event) => {
  if (event.target?.id === "catalogos_page_size") {
    UI.catalogPage = 1;
    loadCatalogosData();
  }
});
document.addEventListener("DOMContentLoaded", init);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !byId("catalog_rename_modal")?.classList.contains("hidden")) {
    closeCatalogRenameModal();
    return;
  }
  if (event.key === "Escape" && !byId("config_modal")?.classList.contains("hidden")) {
    closeConfigModal();
    return;
  }
  if (event.key === "Escape" && !byId("update_list_rename_modal")?.classList.contains("hidden")) { closeUpdateListRenameModal(); return; }
  if (event.key === "Escape" && !byId("update_list_preview_modal")?.classList.contains("hidden")) { closeUpdateListPreviewModal(); return; }
  if (event.key === "Escape" && !byId("update_lists_modal")?.classList.contains("hidden")) {
    closeUpdateListsModal();
    return;
  }
  if (event.key === "Escape" && !byId("tab_panel_catalogos")?.classList.contains("hidden")) {
    closeCatalogosModal();
  }
});
})();
