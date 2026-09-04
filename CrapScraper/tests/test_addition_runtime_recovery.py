from __future__ import annotations

from pathlib import Path

from app.addition_runtime_recovery import _extract_image_url, _fallback_content, install_addition_runtime_recovery
from app.additions.content import valid_content
from app.additions.repository import AdditionRepository


def approval(key: str, name: str):
    return {
        "comparison_item_id": key,
        "source_name": "UltraPackV2",
        "source_version": "1.2.3",
        "source_product_url": f"https://www.ultrapackv2.com/item/{key}/",
        "source_official_url": "https://developer.example/product",
        "product_name": name,
    }


def test_fallback_content_is_publishable_without_inventing_features():
    result = _fallback_content({
        "product_name": "Admin Columns Pro JetEngine",
        "kind": "plugin",
        "source_name": "UltraPackV2",
        "source_version": "1.1.3",
        "developer": "Developer",
        "official_url": "https://developer.example/product",
    })
    assert valid_content(result)
    assert result["categories"] == ["Plugins"]
    assert result["content_origin"] == "deterministic_fallback"
    assert "1.1.3" in result["content"]


def test_source_image_prefers_open_graph_image():
    html = '<html><head><meta property="og:image" content="/media/product.webp"></head><body><img src="/logo.png"></body></html>'
    assert _extract_image_url("https://example.test/item/a/", html) == "https://example.test/media/product.webp"


def test_queue_listing_defaults_to_newest_first(tmp_path: Path):
    install_addition_runtime_recovery()
    repository = AdditionRepository(tmp_path)
    repository.materialize([approval("old", "Old"), approval("new", "New")])
    with repository.connection() as db:
        db.execute("UPDATE addition_jobs SET created_at='2026-09-01T10:00:00+00:00' WHERE comparison_item_id='old'")
        db.execute("UPDATE addition_jobs SET created_at='2026-09-04T10:00:00+00:00' WHERE comparison_item_id='new'")
    items = repository.list(page=1, page_size=10)["items"]
    assert [item["comparison_item_id"] for item in items] == ["new", "old"]


def test_chatgpt_missing_key_uses_deterministic_fallback():
    install_addition_runtime_recovery()
    from app.additions.chatgpt import ChatGPTContentService

    service = ChatGPTContentService(api_key="")
    result = service.generate({
        "product_name": "8Degree Fly Menu",
        "kind": "plugin",
        "source_name": "UltraPackV2",
        "source_version": "1.0.8",
        "developer": "Developer",
        "official_url": "https://developer.example/product",
    })
    assert valid_content(result)
    assert result["content_origin"] == "deterministic_fallback"
