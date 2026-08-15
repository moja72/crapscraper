from pathlib import Path

source = Path('tools/standardize_listings_v2.py').read_text(encoding='utf-8')
old = '''# O catálogo já tem prev/next; adiciona mudança de tamanho usando delegação, evitando depender do nome da função de render.
if 'catalogos_page_size")?.addEventListener' not in js:
    dom_anchor = '  document.addEventListener("DOMContentLoaded", () => {'
    js = replace_once(js, dom_anchor, '  document.addEventListener("change", (event) => {\\n    if (event.target?.id === "catalogos_page_size") { UI.catalogPage = 1; loadCatalogosData(); }\\n  });\\n\\n' + dom_anchor, 'evento de catálogo/page size')
'''
new = '''# O catálogo já tem prev/next; adiciona mudança de tamanho por delegação global.
if 'event.target?.id === "catalogos_page_size"' not in js:
    dom_anchor = 'document.addEventListener("DOMContentLoaded", init);'
    js = replace_once(js, dom_anchor, 'document.addEventListener("change", (event) => {\\n  if (event.target?.id === "catalogos_page_size") {\\n    UI.catalogPage = 1;\\n    loadCatalogosData();\\n  }\\n});\\n' + dom_anchor, 'evento de catálogo/page size')
'''
if old not in source:
    raise RuntimeError('Bloco de evento não encontrado no script v2.')
source = source.replace(old, new, 1)
exec(compile(source, 'standardize_listings_v3_runtime.py', 'exec'))
