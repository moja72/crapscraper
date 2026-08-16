(() => {
  "use strict";

  const STYLE_ID = "crapscraper-select-indicator-style";
  const previous = document.getElementById(STYLE_ID);
  if (previous) previous.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    select:not([multiple]) {
      -webkit-appearance: none !important;
      appearance: none !important;
      padding-right: 42px !important;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='10' viewBox='0 0 14 10'%3E%3Ctext x='0' y='9' font-size='11' fill='%23cbd5e1'%3E%E2%96%BC%3C/text%3E%3C/svg%3E") !important;
      background-repeat: no-repeat !important;
      background-position: right 14px center !important;
      background-size: 14px 10px !important;
    }

    select:not([multiple]):disabled {
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='10' viewBox='0 0 14 10'%3E%3Ctext x='0' y='9' font-size='11' fill='%2371717a'%3E%E2%96%BC%3C/text%3E%3C/svg%3E") !important;
    }

    #updates_queue_checkpoint.cs-queue-checkpoint-standardized {
      display: flex !important;
      align-items: center !important;
      min-height: 46px !important;
      margin: 0 !important;
      line-height: 1.35 !important;
    }
  `;
  document.head.appendChild(style);
})();

(() => {
  "use strict";

  const PT_NUMBER = new Intl.NumberFormat("pt-BR");
  const PT_DATE = new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  let metadataPromise = null;
  let metadataLoadedAt = 0;
  let timer = null;

  function normalize(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function displayCatalogName(value) {
    const name = normalize(value);
    return name.toLowerCase() === "default" ? "Padrão" : name;
  }

  function formatCount(value) {
    const parsed = Number.parseInt(String(value ?? "0"), 10);
    return PT_NUMBER.format(Number.isFinite(parsed) ? Math.max(0, parsed) : 0);
  }

  function formatDate(value) {
    const raw = normalize(value);
    if (!raw || /^não registrad/i.test(raw)) return "Data não registrada";

    const parsed = new Date(raw);
    if (!Number.isNaN(parsed.getTime())) {
      return PT_DATE.format(parsed).replace(",", "");
    }

    const match = raw.match(/(\d{2}\/\d{2}\/\d{4})(?:\s+(\d{2}:\d{2}))?/);
    if (match) return `${match[1]}${match[2] ? ` ${match[2]}` : ""}`;
    return raw;
  }

  async function getJson(url) {
    const response = await fetch(url, {
      cache: "no-store",
      headers: {Accept: "application/json"},
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function loadMetadata() {
    const now = Date.now();
    if (metadataPromise && now - metadataLoadedAt < 30000) return metadataPromise;

    metadataLoadedAt = now;
    metadataPromise = Promise.all([
      getJson("/comparacao/fontes").catch(() => ({})),
      getJson("/catalogos/data").catch(() => ({})),
    ]).then(([sources, catalogs]) => ({
      imported: Array.isArray(sources?.imported_catalogs) ? sources.imported_catalogs : [],
      rows: Array.isArray(catalogs?.catalogos) ? catalogs.catalogos : [],
    }));
    return metadataPromise;
  }

  function sourceParts(value) {
    const parts = normalize(value).split("|");
    if (parts[0] !== "saved" || parts.length < 5) return null;
    return {
      slot: parts[1],
      site: parts[2],
      itemType: parts[3],
      account: parts.slice(4).join("|"),
    };
  }

  async function formatComparisonSelectors() {
    const source = document.getElementById("comparison_source_catalog");
    const target = document.getElementById("comparison_target_catalog");
    if (!source && !target) return;

    const meta = await loadMetadata();

    if (source) {
      for (const option of source.options) {
        if (!normalize(option.value)) continue;
        const parts = sourceParts(option.value);
        if (!parts) continue;

        const row = meta.rows.find(item =>
          normalize(item?.slot_name || item?.catalogo_nome) === parts.slot &&
          normalize(item?.site_key) === parts.site &&
          normalize(item?.item_type_key) === parts.itemType &&
          normalize(item?.account_key) === parts.account
        );

        const oldLabel = normalize(option.textContent);
        const fallbackCount = oldLabel.match(/\(([\d.]+)\s+itens?\)/i)?.[1]?.replace(/\./g, "") || 0;
        const itemCount = row?.items_count ?? fallbackCount;
        const updated = row?.updated_at || row?.updated_at_iso || row?.modified_at || "";
        const core = [displayCatalogName(parts.slot), parts.site, parts.itemType, parts.account]
          .filter(Boolean)
          .join(" • ");
        const nextLabel = `${core} | ${formatDate(updated)} | ${formatCount(itemCount)} itens`;

        if (oldLabel !== nextLabel) option.textContent = nextLabel;
      }
    }

    if (target) {
      const importedById = new Map(meta.imported.map(item => [normalize(item?.id), item]));

      for (const option of target.options) {
        if (!normalize(option.value)) continue;

        const item = importedById.get(normalize(option.value)) || {};
        const oldLabel = normalize(option.textContent);
        const original = normalize(item?.label || oldLabel);
        const explicitName = normalize(item?.name || item?.catalog_name || item?.title);
        const baseName = explicitName || original
          .replace(/\s+atualizados?\s+em\s+\d{2}\/\d{2}\/\d{4}.*$/i, "")
          .replace(/\s*\([\d.]+\s+itens?\)\s*$/i, "")
          .trim();
        const dateMatch = original.match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
        const countMatch = original.match(/\(([\d.]+)\s+itens?\)/i);
        const updated = item?.updated_at || item?.created_at || item?.generated_at || dateMatch?.[1] || "";
        const itemCount = item?.items_count ?? item?.products_count ?? item?.total ?? countMatch?.[1]?.replace(/\./g, "") ?? 0;
        const nextLabel = `${normalize(baseName).toUpperCase()} | ${formatDate(updated)} | ${formatCount(itemCount)} itens`;

        if (oldLabel !== nextLabel) option.textContent = nextLabel;
      }
    }
  }

  function formatQueueCheckpoint() {
    const node = document.getElementById("updates_queue_checkpoint");
    const select = document.getElementById("updates_queue_select");
    if (!node) return;

    const raw = normalize(node.textContent);
    const selectedLabel = normalize(select?.selectedOptions?.[0]?.textContent);
    const totalMatch = selectedLabel.match(/\(\s*\d+\s*\/\s*(\d+)\s*\)/);
    const total = totalMatch ? Number.parseInt(totalMatch[1], 10) : 0;

    let dateLabel = "";
    const sourceDate = raw.match(/Última conclusão:\s*([^·]+?)(?:\s*·|$)/i)?.[1];
    if (sourceDate) {
      dateLabel = formatDate(sourceDate);
    } else {
      const alreadyFormatted = raw.match(/^(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})\s*\|/);
      if (alreadyFormatted) dateLabel = alreadyFormatted[1];
      else if (/nenhum item concluído|sem conclusão registrada/i.test(raw)) dateLabel = "Sem conclusão registrada";
      else dateLabel = "Data não registrada";
    }

    const nextLabel = `${dateLabel} | ${formatCount(total)} itens`;
    if (raw !== nextLabel) node.textContent = nextLabel;
    node.classList.add("cs-queue-checkpoint-standardized");
  }

  function run() {
    formatComparisonSelectors().catch(() => {});
    formatQueueCheckpoint();
  }

  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(run, 90);
  }

  document.addEventListener("DOMContentLoaded", schedule);
  document.addEventListener("change", event => {
    if (["comparison_source_catalog", "comparison_target_catalog", "updates_queue_select"].includes(event.target?.id)) {
      schedule();
    }
  });

  new MutationObserver(schedule).observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
  });

  schedule();
})();
