from pathlib import Path

from app.additions.repository import AdditionRepository
from app.updates.repository import UpdateRepository


ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "static" / "js" / "app.js").read_text(encoding="utf-8")
RUNTIME_JS = (ROOT / "app" / "static" / "js" / "runtime-fixes.js").read_text(encoding="utf-8")


def _update_approval(key, source_name, source_url, woo_id):
    return {
        "comparison_item_id": key,
        "woo_product_id": woo_id,
        "site_name": f"Produto {key}",
        "site_version": "1.0",
        "source_version": "2.0",
        "source_name": source_name,
        "source_product_url": source_url,
    }


def _addition_approval(key, source_name, source_url):
    return {
        "comparison_item_id": key,
        "source_name": source_name,
        "source_version": "2.0",
        "source_product_url": source_url,
        "product_name": f"Produto {key}",
    }


def test_update_queue_filters_by_source_and_supports_no_sources(tmp_path):
    repository = UpdateRepository(tmp_path, database_path=tmp_path / "updates.sqlite3")
    repository.materialize([
        _update_approval("plugin", "PluginTheme", "https://plugintheme.net/product/plugin", 101),
        _update_approval("ultra", "UltraPackV2", "https://www.ultrapackv2.com/item/ultra/", 102),
    ])

    plugin = repository.list(sources="plugintheme", page_size=100)
    ultra = repository.list(sources="ultrapackv2", page_size=100)
    none = repository.list(sources="__none__", page_size=100)

    assert [item["source_kind"] for item in plugin["items"]] == ["plugintheme"]
    assert [item["source_kind"] for item in ultra["items"]] == ["ultrapackv2"]
    assert none["items"] == []
    assert none["total"] == 0


def test_addition_queue_filters_by_source_and_supports_both_sources(tmp_path):
    repository = AdditionRepository(tmp_path, database_path=tmp_path / "additions.sqlite3")
    repository.materialize([
        _addition_approval("plugin", "PluginTheme", "https://plugintheme.net/product/plugin"),
        _addition_approval("ultra", "UltraPackV2", "https://www.ultrapackv2.com/item/ultra/"),
    ])

    plugin = repository.list(sources="plugintheme", page_size=100)
    both = repository.list(sources="plugintheme,ultrapackv2", page_size=100)

    assert [item["source_kind"] for item in plugin["items"]] == ["plugintheme"]
    assert {item["source_kind"] for item in both["items"]} == {"plugintheme", "ultrapackv2"}
    assert both["total"] == 2


def test_runtime_fixes_are_loaded_by_the_application():
    assert 'import "./runtime-fixes.js";' in APP_JS


def test_runtime_source_filter_exists_for_update_and_addition_queues():
    for token in (
        'data-queue-source="${scope}"',
        'installSourceFilter("update")',
        'installSourceFilter("add")',
        'parsed.searchParams.set("sources",selected)',
        'parsed.pathname==="/api/updates/jobs"',
        'parsed.pathname==="/api/additions/jobs"',
    ):
        assert token in RUNTIME_JS


def test_compare_loading_spinner_and_update_immediate_feedback_are_present():
    assert ".operation-band.loading::before" in RUNTIME_JS
    assert "@keyframes cs-runtime-spin" in RUNTIME_JS
    assert "Solicitação recebida. Validando pré-requisitos e autenticando a fonte…" in RUNTIME_JS
    assert "Iniciando atualização de ${name}…" in RUNTIME_JS
