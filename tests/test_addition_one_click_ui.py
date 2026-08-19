from pathlib import Path


def test_one_click_addition_ui_contract():
    script = Path("app/static/addition_one_click.js").read_text(encoding="utf-8")
    assert 'data-addition-one-click' in script
    assert 'Adicionando…' in script
    assert 'addition-auto-log' in script
    assert '#tab_panel_adicoes .addition-actions{display:none!important}' in script
    assert '#tab_panel_adicoes .addition-progress{display:none!important}' in script
    assert '/adicoes/automatico' in script
    assert '/adicoes/automatico/status' in script
    assert 'button.disabled = false' in script
    assert 'button.textContent = "Adicionar"' in script
    assert 'AbortController' in script
