from __future__ import annotations
import hashlib,json,os,sqlite3,threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from app.updates.repository import source_kind
from app.additions.models import utc_now
from app.additions.state import GROUP_STATES

class AdditionRepository:
    def __init__(self,data_dir:Path,database_path:Path|None=None):
        configured=os.getenv("SCRAPER_ADDITION_DB_PATH","").strip();self.path=Path(configured).resolve() if configured else (database_path or data_dir/"consolidated_additions.sqlite3");self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.initialize()
    @contextmanager
    def connection(self):
        with self.lock:
            db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
            try:db.execute("PRAGMA journal_mode=WAL");db.execute("PRAGMA foreign_keys=ON");yield db;db.commit()
            except Exception:db.rollback();raise
            finally:db.close()
    def initialize(self):
        with self.connection() as db:db.executescript("""
        CREATE TABLE IF NOT EXISTS addition_jobs(job_id TEXT PRIMARY KEY,comparison_item_id TEXT NOT NULL UNIQUE,source_kind TEXT NOT NULL,source_name TEXT NOT NULL,source_url TEXT NOT NULL,source_product_id TEXT NOT NULL DEFAULT '',source_version TEXT NOT NULL,product_name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'plugin',developer TEXT NOT NULL DEFAULT '',official_url TEXT NOT NULL DEFAULT '',source_download_url TEXT NOT NULL DEFAULT '',published_download_url TEXT NOT NULL DEFAULT '',artifact_path TEXT NOT NULL DEFAULT '',artifact_sha256 TEXT NOT NULL DEFAULT '',short_description TEXT NOT NULL DEFAULT '',content TEXT NOT NULL DEFAULT '',categories TEXT NOT NULL DEFAULT '[]',tags TEXT NOT NULL DEFAULT '[]',image_state TEXT NOT NULL DEFAULT 'pending',image_path TEXT NOT NULL DEFAULT '',image_error TEXT NOT NULL DEFAULT '',media_id INTEGER NOT NULL DEFAULT 0,woo_product_id INTEGER NOT NULL DEFAULT 0,woo_variation_ids TEXT NOT NULL DEFAULT '[]',publication_state TEXT NOT NULL DEFAULT 'draft',public_state TEXT NOT NULL DEFAULT 'ready',stage TEXT NOT NULL DEFAULT 'prepared',attempts INTEGER NOT NULL DEFAULT 0,current_error TEXT,logs TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,started_at TEXT NOT NULL DEFAULT '',finished_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS addition_attempts(attempt_id TEXT PRIMARY KEY,job_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,started_at TEXT NOT NULL,finished_at TEXT NOT NULL DEFAULT '',source TEXT NOT NULL,result TEXT NOT NULL DEFAULT 'running',stage_history TEXT NOT NULL DEFAULT '[]',error TEXT,logs TEXT NOT NULL DEFAULT '[]',FOREIGN KEY(job_id) REFERENCES addition_jobs(job_id),UNIQUE(job_id,attempt_number));
        CREATE INDEX IF NOT EXISTS idx_addition_state ON addition_jobs(public_state);
        """)
        with self.connection() as db:
            columns={str(row["name"]) for row in db.execute("PRAGMA table_info(addition_jobs)")}
            for name,declaration in (("source_download_url","TEXT NOT NULL DEFAULT ''"),("published_download_url","TEXT NOT NULL DEFAULT ''"),("media_id","INTEGER NOT NULL DEFAULT 0")):
                if name not in columns:db.execute(f"ALTER TABLE addition_jobs ADD COLUMN {name} {declaration}")
    @staticmethod
    def job_id(item):return "add-"+hashlib.sha256(item.encode()).hexdigest()[:20]
    def materialize(self,approvals):
        created=0
        with self.connection() as db:
            for item in approvals:
                key=str(item.get("comparison_item_id") or "").strip()
                if not key or db.execute("SELECT 1 FROM addition_jobs WHERE comparison_item_id=?",(key,)).fetchone():continue
                kind=source_kind(item);name=str(item.get("product_name") or item.get("source_product_name") or item.get("source_name") or key);provider=str(item.get("source_provider_name") or ("PluginTheme" if kind=="plugintheme" else "UltraPackV2"));url=str(item.get("source_product_url") or item.get("source_official_url") or "");now=utc_now();explicit_kind=str(item.get("kind") or item.get("product_type") or item.get("item_type") or "").strip().lower();product_kind="theme" if explicit_kind in {"theme","tema"} or any(x in (url+" "+name).lower() for x in ("/theme","tema"," theme")) else "plugin"
                db.execute("INSERT INTO addition_jobs(job_id,comparison_item_id,source_kind,source_name,source_url,source_product_id,source_version,product_name,kind,official_url,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(self.job_id(key),key,kind,provider,url,str(item.get("source_product_id") or ""),str(item.get("source_version") or ""),name,product_kind,str(item.get("source_official_url") or ""),now,now));created+=1
        return {"created":created,"total":self.count()}
    def count(self):
        with self.connection() as db:return int(db.execute("SELECT COUNT(*) FROM addition_jobs").fetchone()[0])
    def decode(self,row):
        if not row:return None
        x=dict(row);x["state"]=x.pop("public_state");x["error"]=json.loads(x.pop("current_error") or "null")
        for key in ("logs","categories","tags","woo_variation_ids"):x[key]=json.loads(x[key] or "[]")
        x["group"]={v:k for k,v in GROUP_STATES.items()}[x["state"]];return x
    def get(self,job_id):
        with self.connection() as db:row=db.execute("SELECT * FROM addition_jobs WHERE job_id=?",(job_id,)).fetchone()
        item=self.decode(row)
        if not item:raise KeyError(job_id)
        return item
    def list(self,query="",group="",stage="",page=1,page_size=30):
        filters=[];values=[]
        if query:filters.append("(product_name LIKE ? OR source_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ?)");values += [f"%{query}%"]*3
        if group:
            if group not in GROUP_STATES:raise ValueError("Grupo operacional inválido")
            filters.append("public_state=?");values.append(GROUP_STATES[group])
        if stage:filters.append("stage=?");values.append(stage)
        where=" WHERE "+" AND ".join(filters) if filters else "";page=max(1,int(page));page_size=max(1,min(100,int(page_size)))
        with self.connection() as db:
            total=int(db.execute("SELECT COUNT(*) FROM addition_jobs"+where,values).fetchone()[0]);rows=db.execute("SELECT * FROM addition_jobs"+where+" ORDER BY created_at LIMIT ? OFFSET ?",values+[page_size,(page-1)*page_size]).fetchall();counts={"total":int(db.execute("SELECT COUNT(*) FROM addition_jobs").fetchone()[0])}
            for group_name,state in GROUP_STATES.items():counts[group_name]=int(db.execute("SELECT COUNT(*) FROM addition_jobs WHERE public_state=?",(state,)).fetchone()[0])
        return {"items":[self.decode(r) for r in rows],"total":total,"page":page,"page_size":page_size,"pages":max(1,(total+page_size-1)//page_size),"counts":counts}
    def patch(self,job_id,**values):
        encoded={k:(json.dumps(v,ensure_ascii=False) if k in {"categories","tags","woo_variation_ids","logs","current_error"} and not isinstance(v,str) else v) for k,v in values.items()};encoded["updated_at"]=utc_now()
        with self.connection() as db:db.execute("UPDATE addition_jobs SET "+",".join(f"{k}=?" for k in encoded)+" WHERE job_id=?",tuple(encoded.values())+(job_id,))
        return self.get(job_id)
    def begin(self,job_id):
        now=utc_now()
        with self.connection() as db:
            row=db.execute("SELECT attempts,source_kind FROM addition_jobs WHERE job_id=?",(job_id,)).fetchone()
            if not row:raise KeyError(job_id)
            number=int(row["attempts"])+1;aid=f"{job_id}-a{number}";db.execute("UPDATE addition_jobs SET public_state='running',stage='validating',attempts=?,current_error=NULL,logs='[]',started_at=?,finished_at='',updated_at=? WHERE job_id=?",(number,now,now,job_id));db.execute("INSERT INTO addition_attempts(attempt_id,job_id,attempt_number,started_at,source) VALUES(?,?,?,?,?)",(aid,job_id,number,now,row["source_kind"]))
        return {"attempt_id":aid,"number":number}
    def progress(self,job_id,aid,stage,message):
        now=utc_now()
        with self.connection() as db:
            j=db.execute("SELECT logs FROM addition_jobs WHERE job_id=?",(job_id,)).fetchone();a=db.execute("SELECT logs,stage_history FROM addition_attempts WHERE attempt_id=?",(aid,)).fetchone();logs=json.loads(j["logs"]);logs.append(message);alogs=json.loads(a["logs"]);alogs.append(message);history=json.loads(a["stage_history"]);history.append({"stage":stage,"at":now});db.execute("UPDATE addition_jobs SET stage=?,logs=?,updated_at=? WHERE job_id=?",(stage,json.dumps(logs,ensure_ascii=False),now,job_id));db.execute("UPDATE addition_attempts SET logs=?,stage_history=? WHERE attempt_id=?",(json.dumps(alogs,ensure_ascii=False),json.dumps(history),aid))
    def finish(self,job_id,aid,success,stage,error=None):
        now=utc_now();state="success" if success else "error"
        with self.connection() as db:db.execute("UPDATE addition_jobs SET public_state=?,stage=?,current_error=?,finished_at=?,updated_at=? WHERE job_id=?",(state,stage,json.dumps(error,ensure_ascii=False) if error else None,now,now,job_id));db.execute("UPDATE addition_attempts SET result=?,finished_at=?,error=? WHERE attempt_id=?",(state,now,json.dumps(error,ensure_ascii=False) if error else None,aid))
    def history(self,job_id):
        with self.connection() as db:rows=db.execute("SELECT * FROM addition_attempts WHERE job_id=? ORDER BY attempt_number DESC",(job_id,)).fetchall()
        out=[]
        for row in rows:
            x=dict(row)
            for k,d in (("logs",[]),("stage_history",[]),("error",None)):x[k]=json.loads(x[k] or json.dumps(d))
            out.append(x)
        return out
    def migrate_legacy(self,path:Path):
        if not path.is_file():return {"created":0,"total":self.count()}
        source=sqlite3.connect(path);source.row_factory=sqlite3.Row
        try:rows=[dict(r) for r in source.execute("SELECT * FROM addition_jobs")]
        except sqlite3.Error:rows=[]
        finally:source.close()
        approvals=[]
        for r in rows:
            approvals.append({"comparison_item_id":r.get("comparison_item_id"),"source_name":r.get("source_name"),"source_version":r.get("source_version"),"source_product_url":r.get("source_product_url"),"source_official_url":r.get("source_official_url")})
        result=self.materialize(approvals)
        with self.connection() as db:
            for r in rows:
                key=str(r.get("comparison_item_id") or "");row=db.execute("SELECT attempts,public_state FROM addition_jobs WHERE comparison_item_id=?",(key,)).fetchone()
                if not row or row["attempts"] or row["public_state"]!="ready":continue
                legacy_state=str(r.get("state") or "");state="success" if legacy_state in {"completed","published"} else "error" if legacy_state in {"error","blocked"} else "ready";db.execute("UPDATE addition_jobs SET public_state=?,stage=?,developer=?,official_url=?,artifact_path=?,artifact_sha256=?,short_description=?,content=?,tags=?,image_state=?,image_path=?,image_error=?,woo_product_id=?,publication_state=?,current_error=? WHERE comparison_item_id=?",(state,"completed" if state=="success" else "legacy_error" if state=="error" else "prepared",str(r.get("developer") or ""),str(r.get("source_official_url") or ""),str(r.get("zip_path") or ""),str(r.get("zip_sha256") or ""),str(r.get("short_description") or ""),str(r.get("description") or ""),json.dumps([x.strip() for x in str(r.get("tags") or "").split(",") if x.strip()],ensure_ascii=False),"ready" if r.get("image_path") else "pending",str(r.get("image_path") or ""),"",int(r.get("woo_product_id") or 0),"publish" if legacy_state in {"completed","published"} else "draft",json.dumps({"message":str(r.get("error") or ""),"code":"legacy_error"}) if state=="error" else None,key))
        return result
