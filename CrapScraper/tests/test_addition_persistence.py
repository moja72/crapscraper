import sqlite3
from app.additions.repository import AdditionRepository
from tests.addition_fakes import approval

def test_restart_preserves_job(tmp_path):
    first=AdditionRepository(tmp_path);first.materialize([approval()]);job=first.list()["items"][0];second=AdditionRepository(tmp_path)
    assert second.get(job["job_id"])["comparison_item_id"]=="new-1" and second.materialize([approval()])["total"]==1
def test_legacy_import_is_read_only_and_idempotent(tmp_path):
    path=tmp_path/"addition_jobs.sqlite3";db=sqlite3.connect(path);db.execute("CREATE TABLE addition_jobs(comparison_item_id TEXT,source_name TEXT,source_version TEXT,source_product_url TEXT,source_official_url TEXT,state TEXT,title TEXT,short_description TEXT,description TEXT,tags TEXT,image_path TEXT,zip_path TEXT,zip_sha256 TEXT,woo_product_id INTEGER,error TEXT)");db.execute("INSERT INTO addition_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("legacy","UltraPackV2","2.0","https://ultrapackv2.com/item/x","https://dev.example","completed","Legacy","short","content","a,b","","","",99,""));db.commit();db.close();before=path.read_bytes();repo=AdditionRepository(tmp_path,database_path=tmp_path/"new.sqlite3");repo.migrate_legacy(path);repo.migrate_legacy(path);job=repo.list()["items"][0]
    assert repo.count()==1 and job["state"]=="success" and job["woo_product_id"]==99 and path.read_bytes()==before
