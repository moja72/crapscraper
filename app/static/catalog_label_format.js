(() => {
  "use strict";

  const STYLE_ID = "cs-catalog-label-format-style";
  const existingStyle = document.getElementById(STYLE_ID);
  if (existingStyle) existingStyle.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #updates_queue_checkpoint.cs-queue-checkpoint-standardized{
      display:flex!important;
      align-items:center!important;
      min-height:46px!important;
      margin:0!important;
      line-height:1.35!important;
    }
  `;
  document.head.appendChild(style);

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
  const METADATA_TTL = 30_000;

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
    const text = normalize(value);
    if (!text || /^não registrad/i.test(text)) return "Data não registrada";

    const parsed = new Date(text);
    if (!Number.isNaN(parsed.getTime())) return PT_DATE.format(parsed).replace(",", "");

    const br = text.match(/(\d{2}\/\d{2}\/\d{4})(?:\s+(\d{2}:\d{2}))?/);
    if (br) return `${br[1]}${br[2] ? ` ${br[2]}` : ""}`;

    return text;
  }

  async function getJson(url) {
    const response = await fetch(url, {cache: "no-store", headers: {Accept: "application/json"}});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async function loadMetadata() {
    const now = Date.now();
    if (metadataPromise && now - metadataLoadedAt < METADATA_TTL) return metadataPromise;
    metadataLoadedAt = now;
    metadataPromise = Promise.all([
      getJson("/comparacao/fontes").catch(() => ({})),
      getJson("/catalogos/data").catch(() => ({})),
    ]).then(([sources, catalogs]) => ({
      saved: Array.isArray(sources?.saved_catalogs) ? sources.saved_catalogs : [],
      imported: Array.isArray(sources?.imported_catalogs) ? sources.imported_catalogs : [],
      rows: Array.isArray(catalogs?.catalogos) ? catalogs.catalogos : [],
    }));
    return metadataPromise;
  }

  function sourcePartsFromId(id) {
    const parts = normalize(id).split("|");
    if (parts[0] !== "saved" || parts.length < 5) return null;
    return {
      slot: parts[1],
      site: parts[2],
      itemType: parts[3],
      account: parts.slice(4).join("|"),
    };
  }

  function findSavedRow(meta, sourceId) {
    const parts = sourcePartsFromId(sourceId);
    if (!parts) return null;
    return meta.rows.find(row =>
      normalize(row?.slot_name || row?.catalogo_nome) === parts.slot &&
      normalize(row?.site_key) === parts.site &&
      normalize(row?.item_type_key) === parts.itemType &&
      normalize(row?.account_key) === parts.account
    ) || null;
  }

  function baseImportedName(item, optionText) {
    const explicit = normalize(item?.name || item?.catalog_name || item?.title);
    if (explicit) return explicit.toUpperCase();
    const label = normalize(item?.label || optionText);
    const stripped = label
      .replace(/\s+atualizados?\s+em\s+\d{2}\/\d{2}\/\d{4}.*$/i, "")
      .replace(/\s*\(\s*[\d.]+\s+itens?\s*\)\s*$/i, "")
      .trim();
    return (stripped || label || "CATÁLOGO PLUGINTEMA").toUpperCase();
  }

  function extractImportedDate(item, optionText) {
    const direct = normalize(item?.updated_at || item?.created_at || item?.generated_at);
    if (direct) return direct;
    const match = normalize(item?.label || optionText).match(/(\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2})/);
    return match?.[1] || "";
  }

  function extractImportedCount(item, optionText) {
    const direct = item?.items_count ?? item?.products_count ?? item?.total;
    if (direct != null && direct !== "") return direct;
    const match = normalize(item?.label || optionText).match(/\(([\d.]+)\s+itens?\)/i);
    return match ? match[1].replace(/\./g, "") : 0;
  }

  async function formatComparisonCatalogs() {
    const source = document.getElementById("comparison_source_catalog");
    const target = document.getElementById("comparison_target_catalog");
    if (!source && !target) return;

    const meta = await loadMetadata();

    if (source) {
      Array.from(source.options).forEach(option => {
        if (!normalize(option.value)) return;
        const parts = sourcePartsFromId(option.value);
        if (!parts) return;
        const row = findSavedRow(meta, option.value);
        const count = row?.items_count ?? normalize(option.textContent).match(/\(([\d.]+)\s+itens?\)/i)?.[1]?.replace(/\./g, "") ?? 0;
        const updated = row?.updated_at || row?.updated_at_iso || row?.modified_at || "";
        const core = [displayCatalogName(parts.slot), parts.site, parts.itemType, parts.account].filter(Boolean).join(" • ");
        option.textContent = `${core} | ${formatDate(updated)} | ${formatCount(count)} itens`;
      });
    }

    if (target) {
      const importedById = new Map(meta.imported.map(item => [normalize(item?.id), item]));
      Array.from(target.options).forEach(option => {
        if (!normalize(option.value)) return;
        const item = importedById.get(normalize(option.value)) || {};
        const name = baseImportedName(item, option.textContent);
        const date = formatDate(extractImportedDate(item, option.textContent));
        const count = extractImportedCount(item, option.textContent);
        option.textContent = `${name} | ${date} | ${formatCount(count)} itens`;
      });
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

    const isoMatch = raw.match(/Última conclusão:\s*([^·]+?)(?:\s*·|$)/i);
    const date = isoMatch ? formatDate(isoMatch[1]) : (/nenhum item concluído/i.test(raw) ? "Sem conclusão registrada" : "Data não registrada");

    node.textContent = `${date} | ${formatCount(total)} itens`;
    node.classList.add("cs-queue-checkpoint-standardized");
  }

  let timer = null;
  function schedule() {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      formatComparisonCatalogs().catch(() => {});
      formatQueueCheckpoint();
    }, 80);
  }

  document.addEventListener("DOMContentLoaded", schedule);
  document.addEventListener("change", event => {
    if (["comparison_source_catalog", "comparison_target_catalog", "updates_queue_select"].includes(event.target?.id)) schedule();
  });

  const observer = new MutationObserver(schedule);
  observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true});
  schedule();
})();
