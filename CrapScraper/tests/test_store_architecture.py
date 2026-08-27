from pathlib import Path

def test_store_has_one_dom_owner_and_central_polling():
    root=Path(__file__).parents[1];store=(root/"app/static/js/store.js").read_text(encoding="utf-8");app=(root/"app/static/js/app.js").read_text(encoding="utf-8");assert 'setInterval(' not in store and "MutationObserver" not in store;assert 'import "./store.js"' in app and "loadStore" not in app
def test_store_has_no_policy_architecture_and_domains_removed():
    root=Path(__file__).parents[1];text="\n".join(p.read_text(encoding="utf-8") for p in (root/"app/store").glob("*.py"));assert not any(x in text for x in ("store_policy","store_fix","store_v2","store_v3","store_v8","monitor_patch","install_"));assert not (root/"app/domains.py").exists();assert "DomainService" not in (root/"app/web/api.py").read_text(encoding="utf-8")
