from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.collection.service import CollectionService
from app.collection.legacy_core import settings as legacy_settings


@dataclass
class Context:
    site_key: str = "ultrapackv2"
    item_type_key: str = "plugin"
    account_key: str = "coproducaolancamentos"
    slot_name: str = "default"
    def to_dict(self): return vars(self)


class FakeEngine:
    def __init__(self): self.context=Context(); self.calls=[]; self.current={"status":"Pronto","logs":[]}
    def set_context(self, value): self.context=Context(**value); self.calls.append(("context",value)); return {}
    def snapshot(self): return self.current
    def start(self, mode, options, resume=False): self.calls.append(("start",mode,options,resume)); self.current={"status":"Rodando","logs":["real"]}; return {"ok":True}
    def pause(self): self.current["status"]="Pausado"; return {"ok":True}
    def resume(self): self.current["status"]="Rodando"; return {"ok":True}
    def stop(self): self.current["status"]="Parando"; return {"ok":True}


class FakeRepository:
    def __init__(self): self.names=["default"]; self.default="default"; self.active="default"
    def slots(self): return [{"name":n,"is_default":n==self.default,"is_active":n==self.active} for n in self.names]
    def create_slot(self,n): self.names.append(n); return n
    def select_slot(self,n): self.active=n; return n
    def default_slot(self,n): self.default=n; return n
    def delete_slot(self,n):
        if n==self.default:return False,"default protegido"
        self.names.remove(n);return True,"ok"
    def clear_slot(self,n): return True,"ok"
    def categories(self,c): return [{"nome":"Plugins","url":"/plugins/","total":2}]
    def catalog(self,c): return [{"nome":"A"}]
    def config(self,c): return {"scope_mode":"all"}
    def progress(self,c): return {"can_continue":True}
    def catalog_management(self):
        return {"slots": [{"name": "default", "label": "Padrão", "items_count": 1}], "contexts": [{"slot_name": "default", "catalog_available": True}]}
    def context_file(self,c,kind): return f"conteúdo {kind}"


def service(tmp_path: Path): return CollectionService(tmp_path,engine=FakeEngine(),repository=FakeRepository())


def test_legacy_collection_core_uses_canonical_data_directory():
    expected = (Path(__file__).resolve().parents[2] / "data").resolve()
    assert legacy_settings.DATA_DIR == expected


def test_context_registry_categories_and_catalog(tmp_path):
    value=service(tmp_path).context_payload()
    assert {x["key"] for x in value["sites"]} >= {"ultrapackv2","plugintheme"}
    assert value["categories"][0]["nome"]=="Plugins" and value["catalog_count"]==1


def test_catalog_management_and_context_preview_delegate_to_repository(tmp_path):
    item = service(tmp_path)
    assert item.catalogs()["slots"][0]["label"] == "Padrão"
    assert item.catalog_file({**Context().to_dict(), "kind": "log"})["content"] == "conteúdo log"


def test_slot_lifecycle_and_default_protection(tmp_path):
    item=service(tmp_path); item.slot_action("create",{"name":"novo"}); item.slot_action("select",{"name":"novo"}); item.slot_action("default",{"name":"novo"})
    assert item.context_payload()["context"]["slot_name"]=="novo"
    try:item.slot_action("delete",{"name":"novo"})
    except ValueError as error: assert "protegido" in str(error)
    else: raise AssertionError("default foi excluído")


def test_start_pause_resume_stop_and_scope(tmp_path):
    item=service(tmp_path); payload={"site_key":"ultrapackv2","item_type_key":"plugin","account_key":"coproducaolancamentos","slot_name":"default","mode":"existing_review","options":{"scope_mode":"selected","selected_categories":["/plugins/"]}}
    item.start(payload); assert item.state()["state"]["status"]=="Rodando"; assert item.engine.calls[-1][2]["scope_mode"]=="selected"
    item.control("pause"); assert item.state()["state"]["status"]=="Pausado"
    item.control("resume"); assert item.state()["state"]["status"]=="Rodando"
    item.control("stop"); assert item.state()["state"]["status"]=="Parando"


def test_resume_is_delegated_to_persisted_engine(tmp_path):
    item=service(tmp_path); item.start({"site_key":"ultrapackv2","item_type_key":"plugin","account_key":"coproducaolancamentos","slot_name":"default","mode":"full_sync","resume":True,"options":{}})
    assert item.engine.calls[-1][-1] is True


def test_multirun_start_sets_and_starts_only_requested_run(tmp_path):
    class MultiEngine(FakeEngine):
        def runs(self):return [{"run_id":"primary"},{"run_id":"secondary"}]
        def queue_rules(self):return []
        def set_context(self,value,run_id=None):self.context=Context(**value);self.calls.append(("context",run_id,value));return {}
        def start(self,mode,options,resume=False,run_id=None):self.calls.append(("start",run_id,mode,options,resume));return {"ok":True}
    engine=MultiEngine();item=CollectionService(tmp_path,engine=engine,repository=FakeRepository());item.start({"run_id":"secondary","site_key":"plugintheme","item_type_key":"plugin_theme","account_key":"coproducaolancamentos","slot_name":"default","mode":"full_sync","options":{}})
    assert engine.calls[-2][1]=="secondary" and engine.calls[-1][1]=="secondary"


def test_multirun_controls_and_state_are_isolated_by_run_id(tmp_path):
    class MultiEngine(FakeEngine):
        def __init__(self):
            super().__init__();self.states={"primary":{"status":"Pronto","logs":["A"]},"secondary":{"status":"Pronto","logs":["B"]}}
        def runs(self):return [{"run_id":key,"status":value["status"]} for key,value in self.states.items()]
        def set_context(self,value,run_id=None):self.calls.append(("context",run_id,value));return {}
        def snapshot(self,run_id=None):return dict(self.states[run_id or "primary"])
        def start(self,mode,options,resume=False,run_id=None):self.states[run_id]["status"]="Rodando";return {"ok":True}
        def pause(self,run_id=None):self.states[run_id]["status"]="Pausado";return {"ok":True}
        def stop(self,run_id=None):self.states[run_id]["status"]="Parando";return {"ok":True}
    engine=MultiEngine();item=CollectionService(tmp_path,engine=engine,repository=FakeRepository())
    item.start({"run_id":"secondary",**Context(site_key="plugintheme",item_type_key="plugin_theme").to_dict(),"mode":"full_sync","options":{}})
    assert item.state({"run_id":"secondary"})["state"]["status"]=="Rodando"
    assert item.state({"run_id":"primary"})["state"]=={"status":"Pronto","logs":["A"]}
    item.control("pause",{"run_id":"secondary"});assert item.state({"run_id":"secondary"})["state"]["status"]=="Pausado"
    item.control("stop",{"run_id":"secondary"});assert item.state({"run_id":"secondary"})["state"]["status"]=="Parando"
    assert item.state({"run_id":"primary"})["state"]=={"status":"Pronto","logs":["A"]}
