from __future__ import annotations

from pathlib import Path


def test_launcher_targets_nested_current_app_and_validates_health_contract():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "Abrir CrapScraper.bat").read_text(encoding="utf-8")
    assert 'for %%I in ("%~dp0.") do set "CRAPSCRAPER_ROOT=%%~fI"' in launcher
    assert "%CRAPSCRAPER_ROOT%\\main.py" in launcher
    assert "modular-current" in launcher
    assert "CrapScraper/main.py" in launcher
    assert 'for %%I in ("%CRAPSCRAPER_ROOT%\\..") do set "CRAPSCRAPER_REPO=%%~fI"' in launcher


def test_shutdown_only_stops_python_main_from_same_repository():
    root = Path(__file__).resolve().parents[1]
    closer = (root / "Fechar CrapScraper.bat").read_text(encoding="utf-8")
    assert "$repo=[Regex]::Escape('%CRAPSCRAPER_REPO%')" in closer
    assert "$command -notmatch $repo" in closer
    assert "$command -notmatch 'main\\.py'" in closer
