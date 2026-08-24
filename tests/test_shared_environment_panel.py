from pathlib import Path


def _source() -> str:
    return (Path(__file__).parents[1] / "app" / "static" / "shared_environment_panel.js").read_text(encoding="utf-8")


def test_shared_environment_script_reuses_single_card() -> None:
    source = _source()

    assert '.updates-environment-card' in source
    assert 'tab_panel_atualizacoes' in source
    assert 'tab_panel_adicoes' in source
    assert 'tab_panel_loja' in source
    assert 'tab_btn_loja' in source
    assert 'insertBefore(card, target.firstElementChild)' in source
    assert 'cloneNode' not in source
    assert 'attributeFilter: ["class"]' in source


def test_shared_environment_warms_prerequisites_for_all_operational_tabs() -> None:
    source = _source()

    assert 'updates_prerequisites_btn' in source
    assert 'warmEnvironment()' in source
    assert 'scheduleEnvironmentRefresh(false)' in source
    assert '["tab_btn_atualizacoes", "tab_btn_adicoes", "tab_btn_loja"]' in source
    assert 'crapscraper:main-tab-changed' in source


def test_plugin_theme_session_participates_in_environment_summary() -> None:
    source = _source()

    assert 'plugintheme_cookie_status' in source
    assert 'cookie.blocked ? 1 : 0' in source
    assert '1 requisito exige atenção' in source
    assert 'Todos os pré-requisitos estão OK' in source
    assert '"não validada"' in source
    assert '"pendente"' in source
