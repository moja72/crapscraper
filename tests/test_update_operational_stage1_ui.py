from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "app" / "static" / "update_operational_filters.js"


def _source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_stage1_uses_one_visible_update_summary() -> None:
    source = _source()

    assert 'const summary = $("#updates_summary")' in source
    assert '$("#cs_update_operational_summary")?.remove()' in source
    assert 'summary.id = "cs_update_operational_summary"' not in source
    assert 'label: "Aguardando"' not in source


def test_stage1_groups_share_the_same_contract_for_cards_and_listing() -> None:
    source = _source()

    assert 'states: Object.freeze(["plan_ready"])' in source
    assert 'states: Object.freeze(["blocked", "error", "failed", "interrupted", "rollback_required"])' in source
    assert 'function jobsForGroup(data, key)' in source
    assert 'const count = jobsForGroup(data, key).length' in source
    assert 'const source = jobsForGroup(data, VIEW.activeGroup)' in source


def test_stage1_never_maps_a_visual_group_to_one_technical_state() -> None:
    source = _source()

    assert 'technical.value = ""' in source
    assert 'select.value = state' not in source
    assert 'window.__crapscraperUpdateOperationalStage1' in source


def test_stage1_polling_preserves_group_until_explicit_filter_change() -> None:
    source = _source()

    assert 'event.target?.id === "updates_queue_status_filter"' in source
    assert 'VIEW.activeGroup = ""' in source
    assert 'Polling não dispara change' in source
    assert 'new MutationObserver(() => schedule([0]))' in source
