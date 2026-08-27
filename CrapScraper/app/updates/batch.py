from __future__ import annotations

import threading
from typing import Any

from app.updates.executor import UpdateExecutor
from app.updates.models import utc_now


class UpdateBatchService:
    def __init__(self, executor: UpdateExecutor):
        self.executor=executor;self.lock=threading.RLock();self.condition=threading.Condition(self.lock);self.thread:threading.Thread|None=None
        self.ids:list[str]=[];self.position=0;self.paused=False;self.cancelled=False;self.results:list[dict[str,Any]]=[];self.started_at="";self.finished_at=""
    def start(self, job_ids: list[str]) -> dict[str,Any]:
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError("Já existe um lote em execução")
            self.ids=list(dict.fromkeys(job_ids));self.position=0;self.paused=False;self.cancelled=False;self.results=[];self.started_at=utc_now();self.finished_at=""
            self.thread=threading.Thread(target=self._run,name="update-batch",daemon=True);self.thread.start();return self.state()
    def _run(self) -> None:
        while True:
            with self.condition:
                while self.paused and not self.cancelled:self.condition.wait()
                if self.cancelled or self.position>=len(self.ids):break
                job_id=self.ids[self.position];self.position+=1
            try: result=self.executor.execute(job_id)
            except Exception as error: result={"ok":False,"job_id":job_id,"error":{"message":str(error)}}
            with self.lock:self.results.append(result)
        with self.lock:self.finished_at=utc_now()
    def pause(self)->dict[str,Any]:
        with self.lock:self.paused=True;return self.state()
    def resume(self)->dict[str,Any]:
        with self.condition:self.paused=False;self.condition.notify_all();return self.state()
    def cancel(self)->dict[str,Any]:
        with self.condition:self.cancelled=True;self.paused=False;self.condition.notify_all();return self.state()
    def state(self)->dict[str,Any]:
        alive=bool(self.thread and self.thread.is_alive());success=sum(1 for r in self.results if r.get("ok"));errors=len(self.results)-success
        return {"running":alive,"paused":self.paused,"cancelled":self.cancelled,"total":len(self.ids),"processed":len(self.results),"pending":max(0,len(self.ids)-self.position),"success":success,"errors":errors,"started_at":self.started_at,"finished_at":self.finished_at}
