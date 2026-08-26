from app.updates.repository import UpdateRepository
from tests.update_fakes import approval
import json

def test_jobs_survive_repository_restart(tmp_path):
    first=UpdateRepository(tmp_path);first.materialize([approval()]);job=first.list()["items"][0]
    second=UpdateRepository(tmp_path)
    assert second.get(job["job_id"])["comparison_item_id"]=="cmp-1"
    assert second.materialize([approval()])["total"]==1

def test_legacy_runtime_is_read_only_and_idempotently_imported(tmp_path):
    runtime=tmp_path/"update_runtime.json";payload={"jobs":[{"comparison_item_id":"old-1","woo_product_id":9,"name":"Legado","plugintema_version":"1.0","ultrapack_version":"2.0","ultrapack_url":"https://www.ultrapackv2.com/item/legacy/","decision":"approve_update","state":"completed","diagnostics":["concluído"],"completed_at":"2026-01-01T00:00:00+00:00"}]};runtime.write_text(json.dumps(payload),encoding="utf-8");before=runtime.read_bytes()
    repo=UpdateRepository(tmp_path,database_path=tmp_path/"new.sqlite3");repo.migrate_legacy_runtime(runtime);repo.migrate_legacy_runtime(runtime)
    jobs=repo.list()["items"]
    assert len(jobs)==1 and jobs[0]["state"]=="success" and jobs[0]["logs"]==["concluído"] and runtime.read_bytes()==before
