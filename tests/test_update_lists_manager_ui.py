from pathlib import Path


def test_update_lists_manager_is_integrated_and_downloadable() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = (root / "app" / "search_ui_policy.py").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "update_lists_manager_ui.js").read_text(encoding="utf-8")
    run_tabs = (root / "app" / "static" / "run_tabs_history_style.js").read_text(encoding="utf-8")

    assert "_UPDATE_LISTS_MANAGER_UI_SCRIPT_PATH" in policy
    assert "data-update-lists-manager-ui" in policy

    assert "update_lists_integrated_preview" in script
    assert "loadDefaultPreview" in script
    assert "preferredQueueName" in script
    assert "/atualizacoes/filas/detalhes?name=" in script
    assert "Pesquisar na lista" in script
    assert "Itens por página" in script
    assert "update-lists-preview-pagination" in script
    assert "update-lists-preview-table" in script

    assert "downloadQueue" in script
    assert "text/csv;charset=utf-8" in script
    assert '"queue_name", "position", "job_id", "woocommerce_id"' in script
    assert "data-update-list-download" in script

    # A implementação problemática anterior movia nós do modal secundário para fora
    # de sua estrutura. O novo fluxo renderiza a prévia diretamente no gerenciador.
    assert "movePreviewInline" not in run_tabs
    assert "getPreviewParts" not in run_tabs
    assert "cs-inline-preview-source" not in run_tabs
