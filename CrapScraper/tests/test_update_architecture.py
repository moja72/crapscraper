from pathlib import Path

def test_update_frontend_has_single_owner_and_central_polling():
    root=Path(__file__).resolve().parents[1];update=(root/"app/static/js/update.js").read_text(encoding="utf-8")
    assert "setInterval(" not in update and 'polling.register("update-state"' in update
    for name in ("update-cards","update-list","update-log"):
        owners=[p.name for p in (root/"app/static/js").glob("*.js") if name in p.read_text(encoding="utf-8")]
        assert owners==["update.js"]

def test_no_policy_patch_or_mutation_observer_in_canonical_updates():
    root=Path(__file__).resolve().parents[1]/"app/updates"
    text="\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    for forbidden in ("install_","MutationObserver","update_fix","update_policy","update_v2","update_v3"):
        assert forbidden not in text
