from pathlib import Path

import requests

from app.additions.wordpress import AdditionStoreGateway, ArtifactPublisher


def test_create_parent_accepts_public_image_url(monkeypatch):
    gateway = AdditionStoreGateway(session=object())
    monkeypatch.setattr(gateway, "_term", lambda kind, name: 1)
    calls = []

    def wc(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"id": 123}

    monkeypatch.setattr(gateway, "_wc", wc)
    job = {
        "product_name": "Demo Theme",
        "kind": "theme",
        "content": "content",
        "short_description": "short",
        "categories": ["Temas"],
        "tags": [],
        "source_version": "1.0",
        "official_url": "https://example.com",
        "developer": "Developer",
        "job_id": "add-demo",
        "source_name": "UltraPackV2",
    }
    gateway.create_parent(job, 0, "https://plugintema.com.br/downloads/file.zip", image_url="https://plugintema.com.br/downloads/demo.png")
    payload = calls[-1][2]["json"]
    assert payload["images"] == [{"src": "https://plugintema.com.br/downloads/demo.png"}]


def test_media_403_is_identified_as_fallback_candidate():
    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError("403 Client Error", response=response)
    assert AdditionStoreGateway.media_upload_fallback_allowed(error) is True


def test_publisher_can_publish_image_with_stable_public_url(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"png")
    target = tmp_path / "published"
    monkeypatch.setenv("SCRAPER_ADDITION_DOWNLOAD_DIR", str(target))
    monkeypatch.setenv("SCRAPER_DOWNLOAD_PUBLIC_BASE_URL", "https://plugintema.com.br/downloads")
    publisher = ArtifactPublisher()
    url = publisher.publish_image({"job_id": "add-demo"}, source)
    assert url == "https://plugintema.com.br/downloads/add-demo-source.png"
    assert (target / "add-demo-source.png").read_bytes() == b"png"
