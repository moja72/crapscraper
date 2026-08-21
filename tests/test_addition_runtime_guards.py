from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def test_shared_environment_uses_explicit_tab_events_without_mutation_observer():
    source = (STATIC / "shared_environment_panel.js").read_text(encoding="utf-8")
    assert "new MutationObserver" not in source
    assert "tab_btn_adicoes" in source
    assert "requestAnimationFrame(placeEnvironment)" in source


def test_process_bridge_does_not_redecorate_on_subsecond_interval():
    source = (STATIC / "addition_processes_bridge.js").read_text(encoding="utf-8")
    assert "setInterval(decorate" not in source
    assert "modalVisible()" in source
    assert "signature === renderedSignature" in source


def test_legacy_chatgpt_assist_is_the_old_data_poller_we_suppress():
    source = (STATIC / "addition_chatgpt_assist.js").read_text(encoding="utf-8")
    assert 'get("/adicoes/data")' in source
    assert "new MutationObserver" in source
    assert "setInterval(decorate,1800)" in source
