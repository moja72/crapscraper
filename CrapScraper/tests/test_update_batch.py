import time
from app.updates.batch import UpdateBatchService

class Executor:
    def execute(self,job_id):
        if job_id=="B":return {"ok":False,"job_id":job_id}
        return {"ok":True,"job_id":job_id}

def test_batch_continues_after_individual_failure():
    batch=UpdateBatchService(Executor());batch.start(["A","B","C"])
    for _ in range(100):
        if not batch.state()["running"]:break
        time.sleep(.01)
    state=batch.state();assert state["success"]==2 and state["errors"]==1 and state["processed"]==3
