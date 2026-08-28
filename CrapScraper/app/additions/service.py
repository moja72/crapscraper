from __future__ import annotations
import os,threading
from pathlib import Path
from app.additions.batch import AdditionBatchService
from app.additions.executor import AdditionExecutor
from app.additions.repository import AdditionRepository
from app.comparison import decisions

class AdditionService:
    def __init__(self,data_dir:Path,*,repository=None,executor=None):
        self.repository=repository or AdditionRepository(data_dir);self.executor=executor or AdditionExecutor(self.repository);self.batch=AdditionBatchService(self.executor);self.lock=threading.RLock()
        if os.getenv("SCRAPER_ADDITION_IMPORT_LEGACY","1").lower() not in {"0","false","no","off"}:self.repository.migrate_legacy(data_dir/"addition_jobs.sqlite3")
        self.materialize()
        if os.getenv("SCRAPER_ADDITION_E2E_FIXTURES","")=="1":self._seed_e2e_fixtures()
    def _seed_e2e_fixtures(self):
        approvals=[{"comparison_item_id":f"e2e-add-{number:02d}","source_name":"PluginTheme","source_version":"2.0","source_product_url":f"https://plugintheme.net/item/e2e-{number:02d}","source_official_url":"https://developer.example/product"} for number in range(12)]
        self.repository.materialize(approvals);items=self.repository.list(page_size=100)["items"]
        if items:self.repository.patch(items[0]["job_id"],public_state="error",stage="fixture_error",current_error={"message":"Erro simulado E2E","code":"fixture_error"})
        if len(items)>1:self.repository.patch(items[1]["job_id"],public_state="success",stage="completed")
    def materialize(self):
        with self.lock:return {"ok":True,**self.repository.materialize(decisions.list_approved_additions())}
    def materialize_manual(self,approval):
        with self.lock:
            self.repository.materialize([approval]);job_id=self.repository.job_id(str(approval["comparison_item_id"]));return {"ok":True,"item":self.repository.get(job_id)}
    def list(self,payload=None):
        p=payload or {};self.materialize();return {"ok":True,**self.repository.list(str(p.get("query") or ""),str(p.get("group") or ""),str(p.get("stage") or ""),int(p.get("page") or 1),int(p.get("page_size") or 5)),"batch":self.batch.state(),"database":str(self.repository.path)}
    def job(self,job_id):return {"ok":True,"item":self.repository.get(job_id),"history":self.repository.history(job_id)}
    def execute(self,job_id):return self.executor.execute(job_id)
    def retry(self,job_id):return self.executor.execute(job_id)
    def batch_start(self,ids=None):return {"ok":True,"batch":self.batch.start(ids or [x["job_id"] for x in self.repository.list(group="prepared",page_size=100)["items"]])}
    def batch_control(self,action):return {"ok":True,"batch":self.batch.control(action)}
