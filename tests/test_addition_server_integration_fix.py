from __future__ import annotations

from pathlib import Path


def test_addition_routes_patch_the_server_used_by_web_serve() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "addition_server_integration_fix.py"
    ).read_text(encoding="utf-8")

    assert "web.PTThreadingHTTPServer" in source
    assert 'path == "/adicoes/data"' in source
    assert 'path == "/adicoes/sincronizar"' in source
    assert 'result["approved_total"]' in source


def test_main_installs_addition_routes_after_workflow_policy() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    workflow = source.index("install_new_product_workflow_policy()")
    integration = source.index("install_addition_server_integration_fix()")
    assert workflow < integration
