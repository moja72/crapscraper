import time
from app.additions.batch import AdditionBatchService
class Executor:
    def execute(self,item):return {"ok":item!="B","job_id":item}
def test_batch_continues_success_error_success():
    batch=AdditionBatchService(Executor());batch.start(["A","B","C"])
    for _ in range(100):
        if not batch.state()["running"]:break
        time.sleep(.01)
    assert batch.state()["success"]==2 and batch.state()["errors"]==1 and batch.state()["processed"]==3
