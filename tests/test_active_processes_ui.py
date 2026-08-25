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
    assert "/atualizacoes/materializar" in script
    assert "/atualizacoes/prerequisitos" in script
    assert "/loja/precos/status" in script
    assert "/loja/produtos/sem-breve-descricao" in script
    assert "/loja/produtos/campos-ausentes" in script
    assert "/loja/wordpress-manual/status" in script
    assert "/adicoes/automatico/status" in script
    assert "/adicoes/automatico" in script
    assert "/runs" in script
    assert "live_execution_logs" in script
    assert '"/comparacao/", "comparison"' in script
    assert '"/atualizacoes/", "update"' in script
    assert '"/adicoes/", "addition"' in script
    assert '"/loja/", "store"' in script


def test_process_observability_is_installed_at_startup() -> None:
    main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "install_process_observability_policy" in main
    assert "install_process_observability_policy()" in main


def test_processes_header_uses_canonical_subtitle_and_credit_freeze_guard() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "processes_header_position.js"
    ).read_text(encoding="utf-8")

    assert '.page-brand-content .subtitle' in script
    assert "cs_processes_header_group" in script
    assert "cs_download_credits" in script
    assert "__crapScraperProcessCreditFreezeGuardInstalled" in script
    assert 'this?.id === "cs_credit_ultrapack"' in script
    assert 'this?.id === "cs_credit_plugintheme"' in script
    assert "if (current === next) return;" in script
    assert script.index("installCreditFreezeGuard();") < script.index('document.addEventListener("DOMContentLoaded"')
