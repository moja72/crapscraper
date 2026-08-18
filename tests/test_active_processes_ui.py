from __future__ import annotations

from pathlib import Path


def test_active_processes_modal_tracks_main_operational_flows() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "active_processes.js"
    ).read_text(encoding="utf-8")

    assert "Processos ativos" in script
    assert "cs_processes_button" in script
    assert "/comparacao/data" in script
    assert "/atualizacoes/jobs" in script
    assert "/loja/precos/status" in script
    assert "/loja/produtos/sem-breve-descricao" in script
    assert "/runs" in script
    assert "live_execution_logs" in script


def test_process_observability_is_installed_at_startup() -> None:
    main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "install_process_observability_policy" in main
    assert "install_process_observability_policy()" in main
