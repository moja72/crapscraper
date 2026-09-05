from pathlib import Path


BRIDGE = Path(__file__).resolve().parents[2] / "deploy" / "wordpress" / "crapscraper-woocommerce-bridge-v2.php"


def source() -> str:
    return BRIDGE.read_text(encoding="utf-8")


def test_bridge_primes_a_real_woocommerce_operator_after_hmac_auth():
    text = source()
    assert "crapscraper_store_bridge_v2_prime_user" in text
    assert "manage_woocommerce" in text
    assert "upload_files" in text
    assert "wp_set_current_user" in text


def test_bridge_accepts_validated_media_bytes_without_rest_sideload():
    text = source()
    assert "Version: 2.3.0" in text
    assert "crapscraper_store_bridge_v2_media" in text
    assert "content_b64" in text
    assert "base64_decode($encoded, true)" in text
    assert "getimagesizefromstring($raw)" in text
    assert "image/png" in text
    assert "image/jpeg" in text
    assert "image/webp" in text
    assert "file_put_contents($target, $raw, LOCK_EX)" in text
    assert "wp_insert_attachment" in text
    assert "wp_generate_attachment_metadata" in text
    assert "crapscraper_source_image_sha256" in text
    assert "bridge_v2_bytes" in text


def test_product_post_requires_attachment_id_and_never_sideloads_src():
    text = source()
    assert "crapscraper_store_bridge_v2_prepare_product_body" in text
    assert "crapscraper_bridge_product_image_id_required" in text
    assert "Envie a mídia pelo bridge antes de criar o produto" in text
    assert "if ($path === '/media')" in text


def test_bridge_resolves_existing_taxonomy_terms_before_insert():
    text = source()
    assert "crapscraper_store_bridge_v2_taxonomy" in text
    assert "get_terms(" in text
    assert "wp_insert_term" in text
    assert "term_exists" in text
    assert "product_cat" in text
    assert "product_tag" in text
