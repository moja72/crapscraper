from pathlib import Path
def test_add_js_central_polling_and_single_dom_owner():
    root=Path(__file__).resolve().parents[1];add=(root/"app/static/js/add.js").read_text(encoding="utf-8");assert "setInterval(" not in add and 'polling.register("addition-state"' in add
    for name in ("add-cards","add-list","add-log"):
        owners=[p.name for p in (root/"app/static/js").glob("*.js") if name in p.read_text(encoding="utf-8")];assert owners==["add.js"]
def test_canonical_additions_has_no_policy_patch_or_monkey_install():
    root=Path(__file__).resolve().parents[1]/"app/additions";text="\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    for forbidden in ("MutationObserver","addition_policy","addition_fix","addition_v2","addition_v3","addition_v8","install_"):assert forbidden not in text
