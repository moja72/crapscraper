(() => {
  "use strict";

  if (window.__crapScraperPreparationUpdateVisibilityV9Installed) return;
  window.__crapScraperPreparationUpdateVisibilityV9Installed = true;

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const normalize = value => String(value ?? "").replace(/\s+/g, " ").trim();

  function installStyles() {
    if ($("#cs-preparation-update-v9-style")) return;
    const style = document.createElement("style");
    style.id = "cs-preparation-update-v9-style";
    style.textContent = `
      /* Hotfix V9: Atualizar usa o mesmo casco visual da Preparação de Adicionar. */
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 {
        display:block!important;
        visibility:visible!important;
        opacity:1!important;
        padding:16px 18px!important;
        border:1px solid var(--line)!important;
        border-radius:14px!important;
        background:linear-gradient(180deg,rgba(255,255,255,.018),rgba(255,255,255,.008)),var(--bg-elev-1)!important;
        box-shadow:var(--shadow-1)!important;
        overflow:visible!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 > .cs-preparation-header {
        display:flex!important;
        align-items:center!important;
        justify-content:space-between!important;
        gap:12px!important;
        width:100%!important;
        min-height:44px!important;
        margin:0!important;
        padding:0!important;
        border:0!important;
        background:none!important;
        box-shadow:none!important;
        color:var(--text)!important;
        cursor:pointer!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 > .cs-preparation-header .standard-update-accordion-toggle-copy {
        display:inline-flex!important;
        align-items:center!important;
        gap:8px!important;
        min-width:0!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 > .cs-preparation-header .standard-update-accordion-title {
        margin:0!important;
        color:var(--text)!important;
        font-size:16px!important;
        font-weight:850!important;
        line-height:1.2!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 > .cs-preparation-header .standard-update-accordion-chevron {
        display:inline-flex!important;
        align-items:center!important;
        justify-content:center!important;
        transform:rotate(90deg);
        transition:transform .15s ease;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9.is-collapsed > .cs-preparation-header .standard-update-accordion-chevron {
        transform:rotate(0deg);
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 > .cs-preparation-canonical-body {
        display:block!important;
        visibility:visible!important;
        opacity:1!important;
        margin:0!important;
        padding:0!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9.is-collapsed > .cs-preparation-canonical-body {
        display:none!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 .cs-preparation-description {
        margin:8px 0 12px!important;
        color:var(--text-muted)!important;
        font-size:11px!important;
        line-height:1.5!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 .updates-subtitle,
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 .cs-v4-preparation-head {
        display:none!important;
      }
      #tab_panel_atualizacoes .updates-working-card.cs-update-preparation-v9 .cs-preparation-table-head {
        display:none!important;
      }
    `;
    document.head.appendChild(style);
  }

  function markField(control) {
    const field = control?.closest?.("label") || control?.closest?.(".field");
    field?.classList.add("cs-preparation-field");
    return field;
  }

  function ensureHeader(root) {
    let header = $(":scope > .standard-update-accordion-toggle", root);
    if (!header) {
      header = document.createElement("button");
      header.type = "button";
      header.className = "standard-update-accordion-toggle cs-preparation-header";
      header.setAttribute("aria-expanded", "true");
      header.innerHTML = `
        <span class="standard-update-accordion-toggle-copy">
          <span class="standard-update-accordion-chevron" aria-hidden="true">▸</span>
          <span class="standard-update-accordion-title">Preparação</span>
        </span>`;
      root.prepend(header);
      header.dataset.csPrepV9OwnToggle = "1";
      header.addEventListener("click", () => {
        const collapsed = root.classList.toggle("is-collapsed");
        header.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    }
    header.hidden = false;
    header.removeAttribute("hidden");
    header.classList.add("cs-preparation-header");
    return header;
  }

  function ensureBody(root) {
    let body = $("#cs_updates_preparation_body", root);
    if (!body) {
      body = document.createElement("div");
      body.id = "cs_updates_preparation_body";
      body.className = "cs-preparation-canonical-body";
      root.appendChild(body);
    }
    body.hidden = false;
    body.removeAttribute("hidden");
    body.classList.add("cs-preparation-canonical-body");
    return body;
  }

  function ensureSummary(root, header) {
    let summary = $("#cs_v4_update_preparation_summary", root);
    if (!summary) {
      summary = document.createElement("span");
      summary.id = "cs_v4_update_preparation_summary";
    }
    summary.classList.add("cs-preparation-summary", "standard-update-accordion-meta");
    const found = normalize($("#updates_found_count", root)?.textContent || "0 itens encontrados");
    if (found) summary.textContent = found;
    if (summary.parentElement !== header) header.appendChild(summary);
  }

  function ensureAdvanced(root, toolbar) {
    let advanced = $(".cs-v4-preparation-advanced", root) || $(".cs-preparation-advanced", root);
    const version = $("#updates_version_filter", root);
    const relationship = $("#updates_relationship_filter", root);
    const clear = $("#updates_clear_filters", root);

    if (!advanced && (version || relationship || clear)) {
      advanced = document.createElement("div");
      advanced.className = "cs-v4-preparation-advanced cs-preparation-advanced";
      toolbar?.insertAdjacentElement("afterend", advanced);
    }
    if (!advanced) return null;
    advanced.classList.add("cs-preparation-advanced");

    const versionField = markField(version);
    const relationshipField = markField(relationship);
    [versionField, relationshipField, clear].forEach(node => {
      if (node && node.parentElement !== advanced) advanced.appendChild(node);
    });
    return advanced;
  }

  function normalizeUpdatePreparation() {
    const root = $("#tab_panel_atualizacoes .updates-working-card");
    if (!root) return false;

    root.hidden = false;
    root.removeAttribute("hidden");
    root.classList.remove("hidden");
    root.style.removeProperty("display");
    root.style.removeProperty("visibility");
    root.style.removeProperty("opacity");
    root.classList.add("cs-preparation-canonical", "cs-preparation-unified", "cs-update-preparation-v9");

    const header = ensureHeader(root);
    if (root.dataset.csPrepV9InitialOpen !== "1") {
      root.dataset.csPrepV9InitialOpen = "1";
      root.classList.remove("is-collapsed");
      header.setAttribute("aria-expanded", "true");
    }

    const body = ensureBody(root);
    const oldControls = $("#updates_working_controls", root);
    if (oldControls) {
      oldControls.hidden = false;
      oldControls.removeAttribute("hidden");
      oldControls.classList.remove("hidden");
    }

    let description = $(".cs-v4-preparation-hint", root)
      || $$(".cs-preparation-description", root).find(node => node !== body && !node.closest("#updates_working_controls"))
      || $$(".cs-preparation-description", root)[0];
    if (!description) {
      description = document.createElement("div");
      description.textContent = "Revise os produtos aprovados, filtre o que precisa de atenção e prepare os planos antes de enviá-los para a fila de atualização.";
    }
    description.classList.add("cs-preparation-description");

    const toolbar = $(".updates-filters", root);
    toolbar?.classList.add("cs-preparation-toolbar");
    const searchField = markField($("#updates_search_filter", root));
    const stateField = markField($("#updates_status_filter", root));
    if (toolbar) {
      [searchField, stateField].forEach(node => {
        if (node && node.parentElement !== toolbar) toolbar.appendChild(node);
      });
      let refresh = $(".cs-v4-preparation-refresh", root);
      if (!refresh) {
        refresh = document.createElement("button");
        refresh.type = "button";
        refresh.className = "btn-secondary cs-v4-preparation-refresh";
        refresh.textContent = "Atualizar";
        refresh.addEventListener("click", () => $("#updates_refresh_btn")?.click());
      }
      refresh.classList.add("cs-preparation-refresh");
      if (refresh.parentElement !== toolbar) toolbar.appendChild(refresh);
    }

    const advanced = ensureAdvanced(root, toolbar);
    const meta = $(".listing-meta-row", root);
    meta?.classList.add("cs-preparation-meta");

    const bulk = $(".updates-bulkbar", root);
    bulk?.classList.add("cs-preparation-bulk");
    $(".cs-preparation-selection", bulk)?.classList.add("cs-preparation-selection");
    $(".cs-preparation-actions", bulk)?.classList.add("cs-preparation-actions");
    $("#updates_selected_count", root)?.classList.add("cs-preparation-selection-count");
    $(".cs-bulk-selection-line", bulk)?.classList.add("cs-preparation-original-bulk-triggers");
    $(".cs-bulk-action-line", bulk)?.classList.add("cs-preparation-original-bulk-triggers");

    const progress = $("#updates_batch_progress", root);
    const list = $("#updates_jobs", root);
    list?.classList.add("cs-preparation-list");
    const pagination = $(".listing-pagination", root);
    pagination?.classList.add("cs-preparation-pagination");

    [description, toolbar, advanced, meta, bulk, progress, list, pagination].forEach(node => {
      if (node && node.parentElement !== body) body.appendChild(node);
    });

    ensureSummary(root, header);

    const legacyHead = $(".cs-v4-preparation-head", root);
    if (legacyHead) legacyHead.hidden = true;
    $$(":scope > .cs-preparation-description", root).forEach(node => {
      if (node !== description && !body.contains(node)) node.remove();
    });

    if (oldControls && oldControls !== body && oldControls.children.length === 0) oldControls.hidden = true;

    if (list) {
      const seen = new Set();
      $$(":scope > .notice", list).forEach(node => {
        const key = normalize(node.textContent);
        if (!key) return;
        if (seen.has(key)) node.remove();
        else seen.add(key);
      });
    }

    return true;
  }

  let timer = null;
  function schedule(delay = 0) {
    window.clearTimeout(timer);
    timer = window.setTimeout(normalizeUpdatePreparation, delay);
  }

  function burst(delays = [0, 80, 250, 700, 1500]) {
    delays.forEach(delay => window.setTimeout(normalizeUpdatePreparation, delay));
  }

  function bindHooks() {
    document.addEventListener("click", event => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#tab_btn_atualizacoes")) {
        burst();
        return;
      }
      if (target.closest("#updates_refresh_btn,#updates_prepare_selected,#updates_enqueue_selected,#updates_clear_filters")) {
        burst([0, 80, 250, 700]);
      }
      if (target.closest("#tab_panel_atualizacoes .updates-working-card > .standard-update-accordion-toggle")) {
        schedule(0);
      }
    }, true);

    document.addEventListener("crapscraper:main-tab-changed", event => {
      const key = String(event?.detail?.key || document.body?.dataset?.activeTab || "");
      if (key === "atualizacoes") burst();
    });
  }

  function start() {
    installStyles();
    bindHooks();
    burst();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once:true});
  else start();
})();
