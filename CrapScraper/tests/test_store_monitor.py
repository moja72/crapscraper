import threading
from app.store.monitor import StoreMonitorService
from app.store.repository import StoreRepository

class Queue:
    configured=True
    def __init__(self):self.reports=[];self.rows=[{"request_id":"r1","product_id":42,"product_name":"Demo"}]
    def pending(self):return self.rows
    def report(self,rid,**payload):self.reports.append((rid,payload));return {"ok":True}
class Updates:
    def __init__(self):self.calls=[]
    def list(self,payload):return {"items":[{"job_id":"j1","woo_product_id":42,"source_name":"PluginTheme","current_version":"1","source_version":"2"}]}
    def execute(self,jid):self.calls.append(jid);return {"ok":True}

def test_enable_disable_and_restart(tmp_path):
    repo=StoreRepository(tmp_path);service=StoreMonitorService(repo,Queue(),Updates());assert service.enable(True)["enabled"];assert StoreRepository(tmp_path).monitor()["enabled"];assert not service.enable(False)["enabled"]

def test_run_delegates_to_canonical_update_executor(tmp_path):
    queue,updates=Queue(),Updates();service=StoreMonitorService(StoreRepository(tmp_path),queue,updates);result=service.run(force=True);assert result["ok"] and updates.calls==["j1"];assert queue.reports[-1][1]["status"]=="completed";assert service.snapshot()["history"][0]["result"]=="success"

def test_no_match_preserves_external_contract(tmp_path):
    updates=Updates();updates.list=lambda payload:{"items":[]};queue=Queue();service=StoreMonitorService(StoreRepository(tmp_path),queue,updates);service.run(force=True);assert queue.reports==[("r1",{"status":"no_match","message":"Produto sem aprovação de atualização materializada."})]

def test_concurrent_run_is_not_duplicated(tmp_path):
    service=StoreMonitorService(StoreRepository(tmp_path),Queue(),Updates());service.lock.acquire();assert service.run(force=True)["already_running"];service.lock.release()

def test_new_run_clears_current_error(tmp_path):
    repo=StoreRepository(tmp_path);repo.patch_monitor(current_error={"message":"old"});service=StoreMonitorService(repo,Queue(),Updates());service.run(force=True);assert service.snapshot()["error"] is None and service.snapshot()["history"]
