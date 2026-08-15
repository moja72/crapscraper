from pathlib import Path
import re

WEB = Path('app/web.py')
JS = Path('app/static/panel.js')
CSS = Path('app/static/panel.css')

web = WEB.read_text(encoding='utf-8')
js = JS.read_text(encoding='utf-8')
css = CSS.read_text(encoding='utf-8')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f'Trecho não encontrado: {label}')
    return text.replace(old, new, 1)


# ---------- HTML ----------
web = web.replace('Linhas por página', 'Itens por página')


def replace_select(text: str, select_id: str, selected: int) -> str:
    options = ''.join(
        f'<option value="{value}"{(" selected" if value == selected else "")}>{value}</option>'
        for value in (10, 25, 50, 100, 250)
    )
    pattern = rf'(<select id=\\"{re.escape(select_id)}\\">).*?(</select>)'
    updated, count = re.subn(pattern, rf'\1{options}\2', text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'Select não encontrado: {select_id}')
    return updated


web = replace_select(web, 'comparison_page_size', 100)
web = replace_select(web, 'plugintema_manage_page_size', 25)
web = replace_select(web, 'updates_page_size', 25)
web = replace_select(web, 'updates_queue_page_size', 25)

catalog_marker = '        <div class=\\"listing-pagination catalogos-pagination\\">'
catalog_meta = '''        <div class=\\"listing-meta-row catalogos-listing-meta\\">\n          <div class=\\"small\\" id=\\"catalogos_result_meta\\">Mostrando 0 de 0 itens</div>\n          <div class=\\"listing-page-size\\"><label for=\\"catalogos_page_size\\" class=\\"small\\">Itens por página</label><select id=\\"catalogos_page_size\\"><option value=\\"10\\">10</option><option value=\\"25\\" selected>25</option><option value=\\"50\\">50</option><option value=\\"100\\">100</option><option value=\\"250\\">250</option></select></div>\n        </div>\n\n'''
if 'id=\\"catalogos_page_size\\"' not in web:
    web = replace_once(web, catalog_marker, catalog_meta + catalog_marker, 'catálogos/paginação')

history_marker = '      <div class=\\"listing-pagination\\"><button class=\\"btn-secondary\\" id=\\"updates_history_prev\\"'
history_meta = '''      <div class=\\"listing-meta-row updates-history-listing-meta\\">\n        <div class=\\"small\\" id=\\"updates_history_result_meta\\">Mostrando 0 de 0 itens</div>\n        <div class=\\"listing-page-size\\"><label for=\\"updates_history_page_size\\" class=\\"small\\">Itens por página</label><select id=\\"updates_history_page_size\\"><option value=\\"10\\">10</option><option value=\\"25\\" selected>25</option><option value=\\"50\\">50</option><option value=\\"100\\">100</option><option value=\\"250\\">250</option></select></div>\n      </div>\n'''
if 'id=\\"updates_history_page_size\\"' not in web:
    web = replace_once(web, history_marker, history_meta + history_marker, 'histórico/paginação')

preview_marker = '    <div class=\\"listing-pagination\\"><button class=\\"btn-secondary\\" id=\\"update_list_preview_prev\\"'
preview_meta = '''    <div class=\\"listing-meta-row update-list-preview-listing-meta\\">\n      <div class=\\"small\\" id=\\"update_list_preview_result_meta\\">Mostrando 0 de 0 itens</div>\n      <div class=\\"listing-page-size\\"><label for=\\"update_list_preview_page_size\\" class=\\"small\\">Itens por página</label><select id=\\"update_list_preview_page_size\\"><option value=\\"10\\">10</option><option value=\\"25\\" selected>25</option><option value=\\"50\\">50</option><option value=\\"100\\">100</option><option value=\\"250\\">250</option></select></div>\n    </div>\n'''
if 'id=\\"update_list_preview_page_size\\"' not in web:
    web = replace_once(web, preview_marker, preview_meta + preview_marker, 'preview/paginação')

# Setas consistentes.
web = re.sub(r'>(?:← )?Anterior</button>', '>← Anterior</button>', web)
web = re.sub(r'>Próxima(?: →)?</button>', '>Próxima →</button>', web)

# ---------- JS ----------
anchor = '  const POLL_INTERVAL_MS = Math.max(500, Number(BOOT.poll_interval_ms || 1200));\n'
helpers = '''\n  const LISTING_PAGE_SIZE_OPTIONS = [10, 25, 50, 100, 250];\n  const LISTING_DEFAULT_PAGE_SIZE = 25;\n\n  function normalizeListingPageSize(value, fallback = LISTING_DEFAULT_PAGE_SIZE) {\n    const parsed = toInt(value, fallback);\n    return LISTING_PAGE_SIZE_OPTIONS.includes(parsed) ? parsed : fallback;\n  }\n\n  function listingRangeText(total, page, pageSize, noun = "itens") {\n    const safeTotal = Math.max(0, toInt(total, 0));\n    const safeSize = Math.max(1, toInt(pageSize, LISTING_DEFAULT_PAGE_SIZE));\n    const safePage = Math.max(1, toInt(page, 1));\n    if (!safeTotal) return `Mostrando 0 de 0 ${noun}`;\n    const start = ((safePage - 1) * safeSize) + 1;\n    const end = Math.min(safePage * safeSize, safeTotal);\n    return `Mostrando ${start}–${end} de ${safeTotal} ${noun}`;\n  }\n'''
if 'LISTING_PAGE_SIZE_OPTIONS' not in js:
    js = replace_once(js, anchor, anchor + helpers, 'helpers de paginação')

js = js.replace('plugintemaManagePageSize: 100,', 'plugintemaManagePageSize: 25,', 1)
js = js.replace('pageSize: 50,\n      pageSizeOptions: [25, 50, 100, 250, 500, 1000, 5000, 10000],', 'pageSize: 25,\n      pageSizeOptions: LISTING_PAGE_SIZE_OPTIONS,')
js = js.replace('pageSize: 50,\n    pageSizeOptions: [25, 50, 100, 250, 500, 1000, 5000, 10000],', 'pageSize: 25,\n    pageSizeOptions: LISTING_PAGE_SIZE_OPTIONS,')
js = js.replace(': [25, 50, 100, 250, 500, 1000, 5000, 10000];', ': LISTING_PAGE_SIZE_OPTIONS;')
js = js.replace('const nextSize = toInt(pageSize, 50);', 'const nextSize = normalizeListingPageSize(pageSize, LISTING_DEFAULT_PAGE_SIZE);')
js = js.replace('UI.catalogPreview.pageSize = allowed.includes(nextSize) ? nextSize : 50;', 'UI.catalogPreview.pageSize = allowed.includes(nextSize) ? nextSize : LISTING_DEFAULT_PAGE_SIZE;')
js = js.replace('toInt(UI.catalogPreview?.pageSize, 50)', 'toInt(UI.catalogPreview?.pageSize, LISTING_DEFAULT_PAGE_SIZE)')

js = replace_once(
    js,
    '    const pageSize = 10;\n    const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));',
    '    const pageSize = normalizeListingPageSize(byId("catalogos_page_size")?.value, LISTING_DEFAULT_PAGE_SIZE);\n    UI.catalogPageSize = pageSize;\n    const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));',
    'catálogos/page size',
)
js = replace_once(
    js,
    '    setText("catalogos_page_label", `Página ${UI.catalogPage} de ${totalPages}`);',
    '    setText("catalogos_result_meta", listingRangeText(filteredRows.length, UI.catalogPage, pageSize));\n    setText("catalogos_page_label", `Página ${UI.catalogPage} de ${totalPages}`);',
    'catálogos/meta',
)

js = re.sub(
    r'const requestedPageSize = Number\.parseInt\(byId\("plugintema_manage_page_size"\)\?\.value \|\| UI\.plugintemaManagePageSize, 10\);\s*const pageSize = \[25, 50, 100, 250, 500, 1000, 5000, 10000\]\.includes\(requestedPageSize\) \? requestedPageSize : 100;',
    'const requestedPageSize = byId("plugintema_manage_page_size")?.value || UI.plugintemaManagePageSize;\n  const pageSize = normalizeListingPageSize(requestedPageSize, LISTING_DEFAULT_PAGE_SIZE);',
    js,
    count=1,
)
js = re.sub(
    r'if \(byId\("plugintema_manage_range"\)\) byId\("plugintema_manage_range"\)\.textContent = `Mostrando .*?`;',
    'if (byId("plugintema_manage_range")) byId("plugintema_manage_range").textContent = listingRangeText(rows.length, UI.plugintemaManagePage, pageSize);',
    js,
    count=1,
)

js = replace_once(
    js,
    '  setText("comparison_result_meta", `${totalRows} resultado${totalRows === 1 ? "" : "s"} com o filtro atual`, "0 resultados");',
    '  setText("comparison_result_meta", listingRangeText(totalRows, UI.comparison.page, UI.comparison.pageSize, "resultados"), "Mostrando 0 de 0 resultados");',
    'comparação/meta',
)

js = js.replace('pageSize: 5, queue: {status:"stopped",queued:[],executing:[]}, queuePage:1, queuePageSize:10, historyMode:"completed", historyPage:1, historyPageSize:10,', 'pageSize: LISTING_DEFAULT_PAGE_SIZE, queue: {status:"stopped",queued:[],executing:[]}, queuePage:1, queuePageSize:LISTING_DEFAULT_PAGE_SIZE, historyMode:"completed", historyPage:1, historyPageSize:LISTING_DEFAULT_PAGE_SIZE,', 1)
js = js.replace('previewPage:1, previewPageSize:15', 'previewPage:1, previewPageSize:LISTING_DEFAULT_PAGE_SIZE', 1)
js = js.replace('UPDATE_QUEUE.pageSize=Number(byId("updates_page_size")?.value||5);', 'UPDATE_QUEUE.pageSize=normalizeListingPageSize(byId("updates_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);', 1)
js = js.replace('UPDATE_QUEUE.queuePageSize=Math.max(1,toInt(byId("updates_queue_page_size")?.value,10));', 'UPDATE_QUEUE.queuePageSize=normalizeListingPageSize(byId("updates_queue_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);', 1)
js = js.replace('setText("updates_queue_found_count",`${filtered.length} de ${allItems.length} itens`);', 'setText("updates_queue_found_count",listingRangeText(filtered.length,UPDATE_QUEUE.queuePage,UPDATE_QUEUE.queuePageSize));', 1)
js = replace_once(js, 'byId("updates_page_label").textContent=`Página ${UPDATE_QUEUE.page} de ${pages}`;', 'byId("updates_found_count").textContent=listingRangeText(working.length,UPDATE_QUEUE.page,UPDATE_QUEUE.pageSize);byId("updates_page_label").textContent=`Página ${UPDATE_QUEUE.page} de ${pages}`;', 'atualizar/meta')

js = replace_once(js, '  const pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.historyPageSize));', '  UPDATE_QUEUE.historyPageSize=normalizeListingPageSize(byId("updates_history_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);\n  const pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.historyPageSize));', 'histórico/page size')
js = replace_once(js, '  setText("updates_history_page",`Página ${UPDATE_QUEUE.historyPage} de ${pages}`);', '  setText("updates_history_result_meta",listingRangeText(items.length,UPDATE_QUEUE.historyPage,UPDATE_QUEUE.historyPageSize));\n  setText("updates_history_page",`Página ${UPDATE_QUEUE.historyPage} de ${pages}`);', 'histórico/meta')

js = replace_once(
    js,
    'function renderUpdateListPreview(){const query=normalizeText(byId("update_list_preview_search")?.value).toLowerCase(),all=UPDATE_QUEUE.previewItems||[],items=all.filter(item=>!query||`${item.name} ${item.woo_product_id} ${item.state}`.toLowerCase().includes(query)),pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.previewPageSize));',
    'function renderUpdateListPreview(){const query=normalizeText(byId("update_list_preview_search")?.value).toLowerCase(),all=UPDATE_QUEUE.previewItems||[],items=all.filter(item=>!query||`${item.name} ${item.woo_product_id} ${item.state}`.toLowerCase().includes(query));UPDATE_QUEUE.previewPageSize=normalizeListingPageSize(byId("update_list_preview_page_size")?.value,LISTING_DEFAULT_PAGE_SIZE);const pages=Math.max(1,Math.ceil(items.length/UPDATE_QUEUE.previewPageSize));',
    'preview/page size',
)
js = replace_once(js, 'setText("update_list_preview_count",`${items.length} de ${all.length} itens`);setText("update_list_preview_page",`Página ${UPDATE_QUEUE.previewPage} de ${pages}`);', 'setText("update_list_preview_count",`${items.length} de ${all.length} itens`);setText("update_list_preview_result_meta",listingRangeText(items.length,UPDATE_QUEUE.previewPage,UPDATE_QUEUE.previewPageSize));setText("update_list_preview_page",`Página ${UPDATE_QUEUE.previewPage} de ${pages}`);', 'preview/meta')

js = replace_once(
    js,
    '  byId("updates_queue_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.queuePage=1;renderOperationalQueue();});',
    '  byId("updates_queue_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.queuePage=1;renderOperationalQueue();});\n  byId("updates_history_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.historyPage=1;renderUpdateHistory();});\n  byId("update_list_preview_page_size")?.addEventListener("change",()=>{UPDATE_QUEUE.previewPage=1;renderUpdateListPreview();});',
    'eventos atualizar/page size',
)

# Tenta ligar o seletor de catálogos sem depender da posição exata do bloco.
if 'catalogos_page_size")?.addEventListener' not in js:
    marker = '  byId("catalogos_next_page")?.addEventListener'
    pos = js.find(marker)
    if pos != -1:
        end = js.find('\n', pos)
        js = js[:end + 1] + '  byId("catalogos_page_size")?.addEventListener("change",()=>{UI.catalogPage=1;loadCatalogosData();});\n' + js[end + 1:]

# ---------- CSS ----------
css_marker = '/* ===== Padrão global de listagens: filtros, resultados e paginação ===== */'
if css_marker not in css:
    css += '''\n\n/* ===== Padrão global de listagens: filtros, resultados e paginação ===== */\n.listing-meta-row,\n.comparison-listing-meta,\n.catalogos-listing-meta,\n.updates-history-listing-meta,\n.update-list-preview-listing-meta {\n  display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; margin:12px 0;\n}\n.listing-page-size { display:inline-flex; align-items:center; justify-content:flex-end; gap:8px; flex-wrap:wrap; }\n.listing-page-size label { margin:0; color:var(--text-muted); white-space:nowrap; }\n.listing-page-size select { width:auto; min-width:92px; padding:8px 30px 8px 10px; }\n.listing-pagination { display:flex; flex-wrap:wrap; align-items:center; justify-content:center; gap:10px; margin:14px 0; }\n.listing-pagination .badge { min-width:112px; justify-content:center; text-align:center; }\n.comparison-filter-grid, .plugintema-manage-filters, .updates-list-controls, .updates-history-filter-group, .update-list-preview-toolbar { gap:12px; }\n@media (max-width:700px) {\n  .listing-meta-row { flex-direction:column; align-items:stretch; }\n  .listing-page-size { width:100%; justify-content:space-between; }\n  .listing-pagination > button { flex:1 1 120px; }\n}\n'''

WEB.write_text(web, encoding='utf-8')
JS.write_text(js, encoding='utf-8')
CSS.write_text(css, encoding='utf-8')
print('Padronização aplicada com sucesso.')
