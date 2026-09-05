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


def test_bridge_imports_validated_download_image_bytes_into_media_library():
    text = source()
    assert "Version: 2.2.0" in text
    assert "CRAPSCRAPER_STORE_BRIDGE_V2_VERSION" in text
    assert "crapscraper_store_bridge_v2_image_bytes" in text
    assert "crapscraper_store_bridge_v2_local_image_id" in text
    assert "strpos($path, '/downloads/') !== 0" in text
    assert "is_readable($real)" in text
    assert "wp_safe_remote_get($src" in text
    assert "getimagesizefromstring($bytes)" in text
    assert "image/png" in text
    assert "image/jpeg" in text
    assert "image/webp" in text
    assert "file_put_contents($target, $bytes, LOCK_EX)" in text
    assert "wp_insert_attachment" in text
    assert "wp_generate_attachment_metadata" in text
    assert "crapscraper_source_image_sha256" in text


def test_bridge_never_leaves_failed_image_src_for_woocommerce_sideload():
    text = source()
    assert "if (is_wp_error($attachment_id))" in text
    assert "crapscraper_bridge_image_import_failed" in text
    assert "$images[$index] = ['id' => (int) $attachment_id];" in text
    assert "if (is_wp_error($prepared))" in text
    assert "return crapscraper_store_bridge_v2_response($prepared);" in text


def test_bridge_resolves_existing_taxonomy_terms_before_insert():
    text = source()
    assert "crapscraper_store_bridge_v2_taxonomy" in text
    assert "get_terms([" in text
    assert "wp_insert_term" in text
    assert "term_exists" in text
    assert "product_cat" in text
    assert "product_tag" in text


def test_product_post_rewrites_local_image_src_to_attachment_id():
    text = source()
    assert "crapscraper_store_bridge_v2_prepare_product_body" in text
    assert "$body = $prepared;" in text
    assert "bridge_version" in text
