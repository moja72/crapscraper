from pathlib import Path


def source() -> str:
    return (Path(__file__).parents[2] / "deploy/wordpress/crapscraper-manual-update/crapscraper-manual-update.php").read_text(encoding="utf-8")


def test_plugin_exposes_idempotent_history_write_and_readback_routes():
    php = source()
    assert "Version: 2.5.0" in php
    assert "'/update-history'" in php and "'/update-history/(?P<operation_id>" in php
    assert "UNIQUE KEY operation_id" in php
    assert "history_not_confirmed" in php and "history_conflict" in php


def test_last_three_shows_only_completed_for_parent_product_in_descending_order():
    php = source()
    assert "WHERE product_id=%d AND status='completed' ORDER BY completed_at DESC, id DESC LIMIT 3" in php
    assert "'product_variation' === get_post_type($product_id)" in php
    assert "wp_get_post_parent_id($product_id)" in php


def test_manual_request_is_reused_instead_of_duplicating_same_success():
    php = source()
    assert "product_id=%d AND job_id=%s AND status!='completed'" in php
    assert "$wpdb->update($table,$values,array('id'=>absint($manual['id'])))" in php
