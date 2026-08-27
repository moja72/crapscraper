from __future__ import annotations
import json,os,sqlite3,threading
from contextlib import contextmanager
from pathlib import Path
from app.store.models import utc_now

class StoreRepository:
    def __init__(self,data_dir:Path,database_path:Path|None=None):
        configured=os.getenv("SCRAPER_STORE_DB_PATH","");self.path=Path(configured).resolve() if configured else (database_path or data_dir/"consolidated_store.sqlite3");self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.initialize()
    @contextmanager
    def connection(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
            try:db.execute("PRAGMA journal_mode=WAL");yield db;db.commit()
            except Exception:db.rollback();raise
            finally:db.close()
    def initialize(self):
        with self.connection() as db:db.executescript("""
        CREATE TABLE IF NOT EXISTS store_monitor(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'idle',stage TEXT NOT NULL DEFAULT 'idle',last_run_at TEXT NOT NULL DEFAULT '',next_check_at TEXT NOT NULL DEFAULT '',current_product TEXT NOT NULL DEFAULT '',woo_product_id INTEGER NOT NULL DEFAULT 0,current_version TEXT NOT NULL DEFAULT '',found_version TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT '',current_error TEXT,logs TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS store_monitor_runs(run_id TEXT PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT 'running',product TEXT NOT NULL DEFAULT '',woo_product_id INTEGER NOT NULL DEFAULT 0,current_version TEXT NOT NULL DEFAULT '',found_version TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT '',action TEXT NOT NULL DEFAULT 'poll',error TEXT,logs TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS store_pricing_runs(run_id TEXT PRIMARY KEY,created_at TEXT NOT NULL,result TEXT NOT NULL,payload TEXT NOT NULL,summary TEXT NOT NULL);
        """);db.execute("INSERT OR IGNORE INTO store_monitor(id,updated_at) VALUES(1,?)",(utc_now(),))
    def monitor(self):
        with self.connection() as db:row=dict(db.execute("SELECT * FROM store_monitor WHERE id=1").fetchone())
        row["enabled"]=bool(row["enabled"]);row["logs"]=json.loads(row["logs"] or "[]");row["error"]=json.loads(row.pop("current_error") or "null");return row
    def patch_monitor(self,**values):
        for key in ("logs","current_error"):
            if key in values and not isinstance(values[key],str):values[key]=json.dumps(values[key],ensure_ascii=False) if values[key] is not None else None
        values["updated_at"]=utc_now()
        with self.connection() as db:db.execute("UPDATE store_monitor SET "+",".join(f"{k}=?" for k in values)+" WHERE id=1",tuple(values.values()))
        return self.monitor()
    def begin_run(self,run_id):
        now=utc_now()
        with self.connection() as db:
            db.execute("INSERT INTO store_monitor_runs(run_id,started_at) VALUES(?,?)",(run_id,now));db.execute("UPDATE store_monitor SET state='running',stage='polling',last_run_at=?,current_error=NULL,logs='[]',updated_at=? WHERE id=1",(now,now))
    def finish_run(self,run_id,result,logs,error=None,**fields):
        now=utc_now();encoded=json.dumps(error,ensure_ascii=False) if error else None
        with self.connection() as db:
            db.execute("UPDATE store_monitor_runs SET finished_at=?,result=?,error=?,logs=?,product=?,woo_product_id=?,current_version=?,found_version=?,source=? WHERE run_id=?",(now,result,encoded,json.dumps(logs,ensure_ascii=False),fields.get("product",""),int(fields.get("woo_product_id") or 0),fields.get("current_version",""),fields.get("found_version",""),fields.get("source",""),run_id));db.execute("UPDATE store_monitor SET state=?,stage=?,current_error=?,logs=?,current_product=?,woo_product_id=?,current_version=?,found_version=?,source=?,updated_at=? WHERE id=1",("success" if result=="success" else "error","completed" if result=="success" else "failed",encoded,json.dumps(logs,ensure_ascii=False),fields.get("product",""),int(fields.get("woo_product_id") or 0),fields.get("current_version",""),fields.get("found_version",""),fields.get("source",""),now))
    def history(self,limit=30):
        with self.connection() as db:rows=[dict(x) for x in db.execute("SELECT * FROM store_monitor_runs ORDER BY started_at DESC LIMIT ?",(limit,))]
        for row in rows:
            row["logs"]=json.loads(row["logs"] or "[]");row["error"]=json.loads(row["error"] or "null")
        return rows
    def pricing_run(self,result,payload,summary):
        run_id="price-"+utc_now().replace(":","").replace("+","");
        with self.connection() as db:db.execute("INSERT INTO store_pricing_runs VALUES(?,?,?,?,?)",(run_id,utc_now(),result,json.dumps(payload,ensure_ascii=False),json.dumps(summary,ensure_ascii=False)))
