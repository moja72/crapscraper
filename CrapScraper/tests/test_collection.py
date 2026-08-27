from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.collection.service import CollectionService


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


def service(tmp_path: Path): return CollectionService(tmp_path,engine=FakeEngine(),repository=FakeRepository())


def test_context_registry_categories_and_catalog(tmp_path):
    value=service(tmp_path).context_payload()
    assert {x["key"] for x in value["sites"]} >= {"ultrapackv2","plugintheme"}
    assert value["categories"][0]["nome"]=="Plugins" and value["catalog_count"]==1


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
