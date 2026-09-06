from pathlib import Path

from app.addition_execution_recovery import _configure_addition_download_destination
from app.additions.catalog_taxonomy_runtime import canonicalize_job_taxonomy
from app.additions.chatgpt_playwright_image import (
    _candidate_generation_complete,
    _candidate_is_after_marker,
    image_fingerprint,
    image_reusable,
)
from app.additions.wordpress import AdditionStoreGateway, ArtifactPublisher


class ContractGateway(AdditionStoreGateway):
    def __init__(self, existing=None):
        self.calls = []
        self.existing = list(existing or [])

    def _wc(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "GET" and path.endswith("/variations"):
            return self.existing
        if method == "PUT" and "/variations/" in path:
            return {"id": int(path.rsplit("/", 1)[-1])}
        if method == "POST" and path.endswith("/variations"):
            return {"id": 900 + len(self.calls)}
        return {"id": 1}


def job():
    return {
        "job_id": "add-product-1",
        "product_name": "Produto Teste WordPress Theme",
        "source_version": "1.2.3",
        "source_url": "https://example.test/source",
        "official_url": "https://example.test/official",
        "kind": "theme",
    }


def variation(variation_id, option):
    return {
        "id": variation_id,
        "attributes": [{"id": 4, "option": option}],
    }


def test_existing_variations_are_repaired_with_prices_expiry_and_product_download_name(monkeypatch):
    monkeypatch.delenv("SCRAPER_ADDITION_ANNUAL_REGULAR_PRICE", raising=False)
    monkeypatch.delenv("SCRAPER_ADDITION_ANNUAL_SALE_PRICE", raising=False)
    monkeypatch.delenv("SCRAPER_ADDITION_ANNUAL_PRICE", raising=False)
    monkeypatch.delenv("SCRAPER_ADDITION_LIFETIME_REGULAR_PRICE", raising=False)
    monkeypatch.delenv("SCRAPER_ADDITION_LIFETIME_SALE_PRICE", raising=False)
    monkeypatch.delenv("SCRAPER_ADDITION_LIFETIME_PRICE", raising=False)

    gateway = ContractGateway([variation(101, "Anual"), variation(102, "Vitalício")])
    ids = gateway.ensure_variations(77, job(), "https://plugintema.com.br/downloads/Produto%20Teste.zip")

    assert ids == [101, 102]
    puts = [(path, kwargs["json"]) for method, path, kwargs in gateway.calls if method == "PUT"]
    assert [path for path, _ in puts] == [
        "/products/77/variations/101",
        "/products/77/variations/102",
    ]

    annual = puts[0][1]
    lifetime = puts[1][1]
    assert annual["regular_price"] == "33.90"
    assert annual["sale_price"] == "19.90"
    assert annual["download_expiry"] == 365
    assert annual["downloads"][0]["name"] == job()["product_name"]
    assert lifetime["regular_price"] == "39.90"
    assert lifetime["sale_price"] == "24.90"
    assert lifetime["download_expiry"] == -1
    assert lifetime["downloads"][0]["name"] == job()["product_name"]


def test_download_filename_is_product_name_not_job_artifact():
    assert ArtifactPublisher.download_filename(job()) == "Produto Teste WordPress Theme.zip"


def test_remote_destination_disables_legacy_local_copy(monkeypatch):
    monkeypatch.setenv("SCRAPER_SSH_HOST", "187.77.54.169")
    monkeypatch.setenv("SCRAPER_SSH_USERNAME", "adminpt")
    monkeypatch.setenv("SCRAPER_ADDITION_DOWNLOAD_DIR", r"C:\fake\downloads")
    monkeypatch.delenv("SCRAPER_SSH_USER", raising=False)
    monkeypatch.delenv("SCRAPER_SSH_DOWNLOAD_ROOT", raising=False)

    _configure_addition_download_destination()

    assert "SCRAPER_ADDITION_DOWNLOAD_DIR" not in __import__("os").environ
    assert __import__("os").environ["SCRAPER_SSH_DOWNLOAD_ROOT"] == "/home/plugintema.com/downloads"


def test_image_cache_requires_exact_product_fingerprint(monkeypatch, tmp_path):
    import app.additions.chatgpt_playwright_image as runtime

    image = tmp_path / "image.png"
    image.write_bytes(b"valid-test-image")
    current = job()
    expected = image_fingerprint(current)

    monkeypatch.setattr(runtime, "image_valid", lambda path: Path(path).is_file())
    monkeypatch.setattr(
        runtime,
        "_job_state",
        lambda _job_id: {
            "image_ready": True,
            "image_fingerprint": expected,
            "image_prompt_marker": "CSIMG-current",
            "image_sha256": __import__("hashlib").sha256(b"valid-test-image").hexdigest(),
            "image_path": str(image),
            "cache_until": 4102444800,
        },
    )
    current["image_path"] = str(image)
    assert image_reusable(current)

    other = dict(current)
    other["product_name"] = "Outro Produto"
    assert not image_reusable(other)
    image.write_bytes(b"image-from-another-product")
    assert not image_reusable(current)


def test_taxonomy_is_exactly_one_type_category_and_no_tags():
    theme = canonicalize_job_taxonomy({"kind": "theme", "categories": ["Marketing", "Plugin"], "tags": ["SEO"]})
    plugin = canonicalize_job_taxonomy({"kind": "plugin", "categories": ["Tema", "WooCommerce"], "tags": ["Loja"]})

    assert theme["categories"] == ["Tema"]
    assert theme["tags"] == []
    assert plugin["categories"] == ["Plugin"]
    assert plugin["tags"] == []


class _MarkerLocator:
    def __init__(self, result):
        self.result = result
        self.seen_marker = ""

    def evaluate(self, _script, marker=None):
        self.seen_marker = marker or ""
        return self.result


def test_image_candidate_must_be_after_current_prompt_marker():
    marker = "CSIMG-911THEME"
    previous = _MarkerLocator(False)
    current = _MarkerLocator(True)

    assert not _candidate_is_after_marker({"locator": previous}, marker)
    assert _candidate_is_after_marker({"locator": current}, marker)
    assert current.seen_marker == marker


def test_image_candidate_must_report_its_turn_as_complete():
    loading = _MarkerLocator(False)
    ready = _MarkerLocator(True)

    assert not _candidate_generation_complete({"locator": loading})
    assert _candidate_generation_complete({"locator": ready})
