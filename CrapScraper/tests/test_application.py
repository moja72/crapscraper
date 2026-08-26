from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from app.bootstrap import create_application
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.domains import DomainService
from app.web.api import ApplicationServices
from app.web.routes import get_route, post_route


def test_panel_has_five_canonical_tabs() -> None:
    html = (Path(__file__).parents[1] / "app/web/templates/panel.html").read_text(encoding="utf-8")
    for tab in ("collect", "compare", "update", "add", "store"):
        assert html.count(f'data-tab="{tab}"') == 1
        assert html.count(f'data-page="{tab}"') == 1
    assert html.count("app.css") == 1
    assert html.count("app.js") == 1


def test_data_domains_use_real_configured_directory(tmp_path: Path) -> None:
    (tmp_path / "slots" / "Principal").mkdir(parents=True)
    (tmp_path / "catalog.csv").write_text("id,name\n1,Produto\n", encoding="utf-8")
    service = DomainService(tmp_path, JsonStore(tmp_path / "runtime.json"))
    assert service.collection()["slots"] == ["Principal"]
    assert service.collection()["catalogs"] == 1
    assert service.store()["products_sampled"] == 1


def test_collection_actions_persist_without_rebuilding_state(tmp_path: Path) -> None:
    service = DomainService(tmp_path, JsonStore(tmp_path / "runtime.json"))
    service.collection_action("create-slot", {"name": "Novo"})
    service.collection_action("start", {})
    assert service.collection()["state"]["status"] == "running"
    service.collection_action("pause", {})
    assert service.collection()["state"]["status"] == "paused"


def test_all_domain_routes_return_payload(tmp_path: Path) -> None:
    services = ApplicationServices.build(Settings(tmp_path, tmp_path, "127.0.0.1", 0), JsonStore(tmp_path / "runtime.json"))
    for path in ("/api/health", "/api/collect", "/api/compare", "/api/update", "/api/add", "/api/store"):
        assert get_route(services, path)["ok"] is True
    assert post_route(services, "/api/store/monitor", {"enabled": True})["monitor"]["enabled"] is True


def test_no_monkey_patch_composition_in_new_python() -> None:
    root = Path(__file__).parents[1] / "app"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if "legacy_core" not in path.parts)
    assert "Class.method =" not in source
    assert "install_" not in source
