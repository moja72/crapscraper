from __future__ import annotations
import threading
from app.additions.models import utc_now
class AdditionBatchService:
    def __init__(self,executor):self.executor=executor;self.condition=threading.Condition();self.thread=None;self.ids=[];self.position=0;self.paused=False;self.cancelled=False;self.results=[];self.started_at="";self.finished_at=""
    def start(self,ids):
        with self.condition:
            if self.thread and self.thread.is_alive():raise ValueError("Já existe lote em execução")
            self.ids=list(dict.fromkeys(ids));self.position=0;self.paused=False;self.cancelled=False;self.results=[];self.started_at=utc_now();self.finished_at="";self.thread=threading.Thread(target=self._run,daemon=True,name="addition-batch");self.thread.start();return self.state()
    def _run(self):
        while True:
            with self.condition:
                while self.paused and not self.cancelled:self.condition.wait()
                if self.cancelled or self.position>=len(self.ids):break
                item=self.ids[self.position];self.position+=1
            try:result=self.executor.execute(item)
            except Exception as exc:result={"ok":False,"job_id":item,"error":{"message":str(exc)}}
            with self.condition:self.results.append(result)
        with self.condition:self.finished_at=utc_now()
    def control(self,action):
        with self.condition:
            if action=="pause":self.paused=True
            elif action=="resume":self.paused=False;self.condition.notify_all()
            elif action=="cancel":self.cancelled=True;self.paused=False;self.condition.notify_all()
            return self.state()
    def state(self):
        success=sum(bool(r.get("ok")) for r in self.results);return {"running":bool(self.thread and self.thread.is_alive()),"paused":self.paused,"cancelled":self.cancelled,"total":len(self.ids),"processed":len(self.results),"pending":max(0,len(self.ids)-self.position),"success":success,"errors":len(self.results)-success,"started_at":self.started_at,"finished_at":self.finished_at}
