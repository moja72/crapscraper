from pathlib import Path


def test_shared_environment_script_reuses_single_card() -> None:
    source = (Path(__file__).parents[1] / "app" / "static" / "shared_environment_panel.js").read_text(encoding="utf-8")

    assert '.updates-environment-card' in source
    assert 'tab_panel_atualizacoes' in source
    assert 'tab_panel_adicoes' in source
    assert 'tab_panel_loja' in source
    assert 'tab_btn_loja' in source
    assert 'insertBefore(card, target.firstElementChild)' in source
    assert 'cloneNode' not in source
    assert 'attributeFilter: ["class"]' in source
