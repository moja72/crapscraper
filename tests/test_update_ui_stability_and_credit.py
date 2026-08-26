from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "app" / "static" / "update_summary_stability.js"
LOG = ROOT / "app" / "static" / "update_technical_log_fix.js"
CREDIT = ROOT / "app" / "update_credit_diagnostics_policy.py"
RECOVERY = ROOT / "app" / "update_recovery_policy.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_summary_uses_separate_visible_mount_and_hides_legacy_renderer() -> None:
    source = _read(SUMMARY)

    assert 'const LEGACY_ID = "updates_summary"' in source
    assert 'const CANONICAL_ID = "cs_update_summary_canonical"' in source
    assert '#${LEGACY_ID},' in source
    assert 'display:none!important' in source
    assert 'legacy.dataset.csCompatibilityOnly = "1"' in source
    assert "MutationObserver" not in source


def test_total_is_exact_union_of_public_cards() -> None:
    source = _read(SUMMARY)

    assert 'counts.total = publicJobs(jobs).length' in source
    assert 'states: Object.freeze(["plan_ready"])' in source
    assert 'states: Object.freeze(["blocked", "error", "failed", "interrupted", "rollback_required"])' in source
    assert 'const ORDER = Object.freeze(["total", "prepared", "running", "completed", "errors"])' in source


def test_log_details_is_moved_once_and_polling_only_updates_pre_text() -> None:
    source = _read(LOG)

    assert 'const MOUNT_ID = "updates_technical_log_mount"' in source
    assert 'const STABLE_ATTR = "data-cs-stable-update-log"' in source
    assert 'panel.appendChild(mount)' in source
    assert 'mount.appendChild(original)' in source
    assert "MutationObserver" not in source
    assert 'target.textContent = nextText' in source
    assert 'document.hidden' in source
    assert 'details.addEventListener("toggle"' not in source
    assert 'stableDetails.addEventListener("toggle"' in source


def test_credit_diagnostic_requires_explicit_credit_evidence_and_reaches_log() -> None:
    source = _read(CREDIT)

    assert 'if _credit_failure(_response_payload(response)):' in source
    assert "créditos de download insuficientes" in source
    assert 'status in {401, 403}' in source
    assert '"💳 Download não concluído por falta de créditos no site de origem: "' in source
    assert 'UpdatePreparationService.prepare = _patched_prepare' in source


def test_recovery_bootstrap_installs_credit_policy_and_stable_summary() -> None:
    source = _read(RECOVERY)

    assert "install_update_credit_diagnostics_policy" in source
    assert '"static" / "update_summary_stability.js"' in source
    assert "data-update-summary-stability" in source
