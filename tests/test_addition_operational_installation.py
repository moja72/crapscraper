from pathlib import Path


def test_operational_installation_contract():
    source = Path("app/addition_official_resolution_fallback_policy.py").read_text(encoding="utf-8")
    assert "install_addition_operational_ui_policy()" in source
    assert "install_addition_operational_legacy_suppression_policy()" in source
    assert "install_addition_processes_bridge_policy()" in source
