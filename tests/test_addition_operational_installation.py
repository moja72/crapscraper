from pathlib import Path


def test_operational_installation_contract():
    fallback = Path("app/addition_official_resolution_fallback_policy.py").read_text(encoding="utf-8")
    suppression = Path("app/addition_operational_legacy_suppression_policy.py").read_text(encoding="utf-8")

    assert "install_addition_operational_ui_policy()" in fallback
    assert "install_addition_operational_legacy_suppression_policy()" in fallback
    assert "data-new-product-workflow" in suppression
    assert "data-addition-one-click" in suppression
    assert "install_addition_operational_performance_policy()" in suppression
    assert "install_addition_processes_bridge_policy()" in suppression


def test_performance_policy_uses_short_read_cache_and_sync_deduplication():
    source = Path("app/addition_operational_performance_policy.py").read_text(encoding="utf-8")
    assert "_READ_TTL_SECONDS = 1.25" in source
    assert "_SYNC_DEDUP_SECONDS = 8.0" in source
    assert "_SYNC_LOCK.acquire(blocking=False)" in source
    assert "operational._operations_payload = _cached_operations_payload" in source
    assert "operational._sync_approved_operational = _deduplicated_sync" in source
