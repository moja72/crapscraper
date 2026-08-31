from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from app.bootstrap import create_application
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.collection import CollectionService
from app.web.api import ApplicationServices
from app.web.routes import get_route, post_route


def test_panel_has_five_canonical_tabs() -> None:
    html = (Path(__file__).parents[1] / "app/web/templates/panel.html").read_text(encoding="utf-8")
    for tab in ("collect", "compare", "update", "add", "store"):
        assert html.count(f'data-tab="{tab}"') == 1
        assert html.count(f'data-page="{tab}"') == 1
    assert html.count("app.css") == 1
    assert html.count("app.js") == 1


def test_header_credits_use_backend_endpoint_and_keep_processes_button() -> None:
    root=Path(__file__).parents[1]
    html=(root/"app/web/templates/panel.html").read_text(encoding="utf-8")
    script=(root/"app/static/js/app.js").read_text(encoding="utf-8")
    assert 'id="processes-open"' in html
    assert 'id="credits-ultrapack"' in html and 'id="credits-plugintheme"' in html
    assert 'data-credit-refresh="ultrapackv2"' in html and 'data-credit-refresh="plugintheme"' in html
    assert 'refreshCredit(site,{force:true})' in script
    assert 'polling.register("download-credits"' not in script


def test_application_uses_canonical_services(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCRAPER_STORE_E2E_FIXTURES", "1")
    services = ApplicationServices.build(Settings(tmp_path, tmp_path, "127.0.0.1", 0), JsonStore(tmp_path / "runtime.json"))
    assert services.collection.__class__.__name__ == "CollectionService"
    assert services.store.__class__.__name__ == "StoreService"


def test_domain_service_is_no_longer_part_of_application() -> None:
    assert not (Path(__file__).parents[1] / "app/domains.py").exists()


def test_all_domain_routes_return_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCRAPER_STORE_E2E_FIXTURES", "1")
    services = ApplicationServices.build(Settings(tmp_path, tmp_path, "127.0.0.1", 0), JsonStore(tmp_path / "runtime.json"))
    for path in ("/api/health", "/api/collect", "/api/compare", "/api/update", "/api/add", "/api/store"):
        assert get_route(services, path)["ok"] is True
    assert post_route(services, "/api/store/monitor", {"enabled": True})["monitor"]["enabled"] is True


def test_no_monkey_patch_composition_in_new_python() -> None:
    root = Path(__file__).parents[1] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if "legacy_core" not in path.parts)
    assert "Class.method =" not in source
    assert "install_" not in source
