from __future__ import annotations

import threading
import os
from pathlib import Path
from typing import Any

from app.comparison import decisions
from app.updates.batch import UpdateBatchService
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository


class UpdateService:
    def __init__(self, data_dir: Path, *, repository: UpdateRepository|None=None, executor: UpdateExecutor|None=None):
        self.repository=repository or UpdateRepository(data_dir);self.executor=executor or UpdateExecutor(self.repository);self.batch=UpdateBatchService(self.executor);self.lock=threading.RLock()
        if os.getenv("SCRAPER_UPDATE_IMPORT_LEGACY","1").strip().lower() not in {"0","false","no","off"}: self.repository.migrate_legacy_runtime(data_dir/"update_runtime.json")
        self.materialize()
    def materialize(self)->dict[str,Any]:
        with self.lock:return {"ok":True,**self.repository.materialize(decisions.list_approved_updates())}
    def materialize_manual(self,approval:dict[str,Any])->dict[str,Any]:
        with self.lock:
            self.repository.materialize([approval]);job_id=self.repository._job_id(str(approval["comparison_item_id"]));return {"ok":True,"item":self.repository.get(job_id)}
    def list(self,payload:dict[str,Any]|None=None)->dict[str,Any]:
        payload=payload or {};self.materialize();result=self.repository.list(query=str(payload.get("query") or ""),group=str(payload.get("group") or ""),stage=str(payload.get("stage") or ""),page=int(payload.get("page") or 1),page_size=int(payload.get("page_size") or 30));return {"ok":True,**result,"batch":self.batch.state(),"database":str(self.repository.path)}
    def job(self,job_id:str)->dict[str,Any]: return {"ok":True,"item":self.repository.get(job_id),"history":self.repository.history(job_id)}
    def execute(self,job_id:str)->dict[str,Any]: return self.executor.execute(job_id)
    def retry(self,job_id:str)->dict[str,Any]: return self.executor.execute(job_id)
    def batch_start(self,job_ids:list[str]|None=None)->dict[str,Any]:
        ids=job_ids or [x["job_id"] for x in self.repository.list(group="prepared",page_size=100)["items"]]
        return {"ok":True,"batch":self.batch.start(ids)}
    def batch_control(self,action:str)->dict[str,Any]:
        method={"pause":self.batch.pause,"resume":self.batch.resume,"cancel":self.batch.cancel}[action];return {"ok":True,"batch":method()}
