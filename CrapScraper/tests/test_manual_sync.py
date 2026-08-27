import pytest
from app.sync.service import ManualSyncService
from app.updates.repository import UpdateRepository
from app.additions.repository import AdditionRepository

class Comparison:
    def __init__(self):self.decisions=[];self.relationships=[]
    def catalogs(self):return {"ok":True,"catalogs":[{"id":"plugintema.csv","label":"PluginTema","role":"site"},{"id":"plugintheme.csv","label":"PluginTheme","role":"source"},{"id":"ultrapack.csv","label":"UltraPackV2","role":"source"}]}
    def search_catalog(self,catalog_id,role,query,limit):
        catalog=next(x for x in self.catalogs()["catalogs"] if x["id"]==catalog_id)
        if role=="site":items=[{"role":"site","product_key":"site-42","site_id":"42","name":"Produto Demo","version":"1.0","category":"Plugins","official_url":"https://developer.test/demo"}]
        else:items=[{"role":"source","product_key":"source-7","site_id":"","name":"Produto Demo","version":"2.0","category":"Plugins","product_url":f"https://{catalog_id[:-4]}.test/product/source-7","official_url":"https://developer.test/demo"}]
        return {"ok":True,"catalog":catalog,"items":items}
    def save_decision(self,payload):self.decisions.append(payload);return {"ok":True}
    def save_relationship(self,payload):self.relationships.append(payload);return {"ok":True}

class Recorder:
    def __init__(self,result=None):self.calls=[];self.result=result or {"ok":True}
    def execute(self,job_id):self.calls.append(job_id);return {**self.result,"job_id":job_id}

class Updates:
    def __init__(self,path,executor):self.repository=UpdateRepository(path,database_path=path/"updates.sqlite3");self.executor=executor
    def materialize_manual(self,a):self.repository.materialize([a]);return {"ok":True,"item":self.repository.get(self.repository._job_id(a["comparison_item_id"]))}
    def execute(self,j):return self.executor.execute(j)
    def job(self,j):return {"item":self.repository.get(j)}
class Additions:
    def __init__(self,path,executor):self.repository=AdditionRepository(path,database_path=path/"additions.sqlite3");self.executor=executor
    def materialize_manual(self,a):self.repository.materialize([a]);return {"ok":True,"item":self.repository.get(self.repository.job_id(a["comparison_item_id"]))}
    def execute(self,j):return self.executor.execute(j)
    def job(self,j):return {"item":self.repository.get(j)}

def setup(tmp_path,update_result=None):
    comparison=Comparison();ue,ae=Recorder(update_result),Recorder();service=ManualSyncService(comparison,Updates(tmp_path,ue),Additions(tmp_path,ae));site=service.search({"role":"site","catalog_id":"plugintema.csv","query":"Demo"})["items"][0];source=service.search({"role":"source","catalog_id":"plugintheme.csv","query":"Demo"})["items"][0];return service,comparison,ue,ae,site,source

def test_search_uses_comparison_catalog_and_keeps_traceability(tmp_path):
    service,_,_,_,site,source=setup(tmp_path);assert site["catalog_id"]=="plugintema.csv" and site["site_id"]=="42";assert source["catalog_id"]=="plugintheme.csv" and source["product_key"]=="source-7" and source["product_url"]

def test_existing_materializes_update_and_only_calls_update_executor(tmp_path):
    service,comparison,ue,ae,site,source=setup(tmp_path);resolved=service.resolve({"operation":"update","site_selection_id":site["selection_id"],"source_selection_id":source["selection_id"]});first=service.execute(resolved["resolution_id"]);second=service.execute(resolved["resolution_id"]);assert first["operation"]=="update" and first["state"]=="success" and second["reused"];assert ue.calls==[first["job_id"]] and ae.calls==[];job=service.updates.repository.get(first["job_id"]);assert job["source_kind"]=="plugintheme" and job["woo_product_id"]==42;assert comparison.relationships and comparison.decisions[-1]["decision"]=="approve_update"

def test_new_materializes_addition_and_only_calls_addition_executor(tmp_path):
    service,comparison,ue,ae,_,source=setup(tmp_path);resolved=service.resolve({"operation":"addition","source_selection_id":source["selection_id"]});result=service.execute(resolved["resolution_id"]);assert result["operation"]=="addition" and ae.calls==[result["job_id"]] and ue.calls==[];job=service.additions.repository.get(result["job_id"]);assert job["source_kind"]=="plugintheme" and job["source_product_id"]=="source-7" and job["product_name"]=="Produto Demo";assert comparison.decisions[-1]["decision"]=="approve_new_product"

def test_ambiguity_requires_explicit_site_selection(tmp_path):
    service,_,_,_,_,source=setup(tmp_path)
    with pytest.raises(ValueError):service.resolve({"operation":"update","source_selection_id":source["selection_id"]})

def test_ultrapack_source_remains_immutable(tmp_path):
    service,_,_,_,site,_=setup(tmp_path);source=service.search({"role":"source","catalog_id":"ultrapack.csv","query":"Demo"})["items"][0];resolved=service.resolve({"operation":"update","site_selection_id":site["selection_id"],"source_selection_id":source["selection_id"]});job=service.materialize(resolved["resolution_id"]);assert service.updates.repository.get(job["job_id"])["source_kind"]=="ultrapackv2"

def test_executor_error_is_exposed_and_gate_not_bypassed(tmp_path):
    service,_,ue,_,site,source=setup(tmp_path,{"ok":False,"error":{"code":"execution_disabled","message":"Gate bloqueou"}});resolved=service.resolve({"operation":"update","site_selection_id":site["selection_id"],"source_selection_id":source["selection_id"]});result=service.execute(resolved["resolution_id"]);assert not result["ok"] and result["error"]["message"]=="Gate bloqueou" and len(ue.calls)==1

def test_materialized_jobs_survive_restart_and_are_idempotent(tmp_path):
    service,_,_,_,site,source=setup(tmp_path);resolved=service.resolve({"operation":"update","site_selection_id":site["selection_id"],"source_selection_id":source["selection_id"]});one=service.materialize(resolved["resolution_id"]);two=service.materialize(resolved["resolution_id"]);assert one["job_id"]==two["job_id"] and service.updates.repository.count()==1;assert UpdateRepository(tmp_path,database_path=tmp_path/"updates.sqlite3").get(one["job_id"])["comparison_item_id"]
