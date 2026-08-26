from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
UPDATE_POLICY = ROOT / "app" / "update_operational_ui_policy.py"
RECOVERY_POLICY = ROOT / "app" / "update_recovery_policy.py"
PROCESS_POLICY = ROOT / "app" / "process_modal_stability_policy.py"
PANEL_POLICY = ROOT / "app" / "panel_layout_standardization_policy.py"
STAGE1 = STATIC / "update_operational_filters.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_discarded_duplicate_ui_files_are_gone() -> None:
    assert not (STATIC / "update_summary_stability.js").exists()
    assert not (STATIC / "update_technical_log_fix.js").exists()
    assert not (STATIC / "operational_ui_card_parity_v5.js").exists()


def test_update_summary_has_one_visible_owner() -> None:
    policy = _read(UPDATE_POLICY)
    stage1 = _read(STAGE1)

    assert "data-update-summary-single-owner" in policy
    assert "#tab_panel_atualizacoes #updates_summary > div" in policy
    assert "display:none!important" in policy
    assert "data-update-operational-filters" in policy
    assert 'states: Object.freeze(["plan_ready"])' in stage1
    assert 'label: "Em andamento"' in stage1
    assert 'label: "Concluídos"' in stage1
    assert 'label: "Erros"' in stage1
    assert 'label: "Aguardando"' not in stage1


def test_removed_v5_is_not_loaded_anymore() -> None:
    panel = _read(PANEL_POLICY)
    assert "data-operational-ui-card-parity-v5" not in panel


def test_log_returns_to_native_details_without_extra_controller() -> None:
    process = _read(PROCESS_POLICY)
    assert "update_technical_log_fix.js" not in process
    assert "data-update-technical-log-fix" not in process


def test_recovery_keeps_credit_diagnostics_without_second_summary() -> None:
    recovery = _read(RECOVERY_POLICY)
    assert "install_update_credit_diagnostics_policy" in recovery
    assert "update_summary_stability.js" not in recovery
    assert "data-update-summary-stability" not in recovery
