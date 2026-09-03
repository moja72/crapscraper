from pathlib import Path

from app.additions.repository import AdditionRepository
from app.additions.service import AdditionService
from app.comparison import decisions


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
HEADING_JS = (ROOT / "app" / "static" / "js" / "add-heading.js").read_text(encoding="utf-8")


def approved_addition():
    return {
        "comparison_item_id": "baseline-addition-1",
        "source_name": "PluginTheme",
        "source_provider_name": "PluginTheme",
        "source_product_name": "Produto de teste",
        "source_product_url": "https://plugintheme.net/item/produto-de-teste",
        "source_version": "1.0.0",
    }


def test_existing_addition_records_are_cleared_once_and_sync_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRAPER_ADDITION_IMPORT_LEGACY", "0")
    monkeypatch.delenv("SCRAPER_ADDITION_E2E_FIXTURES", raising=False)
    monkeypatch.setattr(decisions, "list_approved_additions", lambda: [approved_addition()])

    repository = AdditionRepository(tmp_path)
    repository.materialize([approved_addition()])
    assert repository.count() == 1

    service = AdditionService(tmp_path, repository=repository)
    assert service.list()["total"] == 0
    assert service.list()["counts"] == {
        "total": 0,
        "prepared": 0,
        "running": 0,
        "success": 0,
        "error": 0,
    }

    synced = service.materialize()
    assert synced["created"] == 1
    assert service.list()["total"] == 1

    restarted = AdditionService(tmp_path, repository=repository)
    assert restarted.list()["total"] == 1


def test_addition_heading_is_loaded_before_environment_visually():
    assert 'import "./add-heading.js";' in APP_JS
    assert '<h1>Adicionar</h1>' in HEADING_JS
    assert 'Novos produtos aprovados, preparados e publicados com segurança no WooCommerce.' in HEADING_JS
    assert "environment.before(heading)" in HEADING_JS
