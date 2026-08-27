from pathlib import Path

def test_sync_is_orchestrator_without_third_engine():
    root=Path(__file__).parents[1];source=(root/"app/sync/service.py").read_text(encoding="utf-8");assert "class ManualSyncExecutor" not in source and "class ProductSyncExecutor" not in source and ".download(" not in source and ".install(" not in source and ".create_parent(" not in source
def test_each_frontend_has_single_owner_and_central_polling():
    root=Path(__file__).parents[1];names=("collect","compare","update","add","store","sync")
    for name in names:
        text=(root/f"app/static/js/{name}.js").read_text(encoding="utf-8");assert "setInterval(" not in text and "MutationObserver" not in text
    app=(root/"app/static/js/app.js").read_text(encoding="utf-8")
    for name in names:assert f'import "./{name}.js"' in app
    assert "DomainService" not in "\n".join(p.read_text(encoding="utf-8") for p in (root/"app").rglob("*.py"))
def test_manual_sync_dialog_exists_once():
    html=(Path(__file__).parents[1]/"app/web/templates/panel.html").read_text(encoding="utf-8");assert html.count('id="manual-sync-modal"')==1
