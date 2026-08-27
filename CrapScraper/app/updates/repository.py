from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

from app.updates.models import UpdateJob, utc_now
from app.updates.state import GROUP_BY_STATE


def source_kind(value: dict[str, Any]) -> str:
    text = " ".join(str(value.get(key) or "") for key in ("source_name", "source_product_url", "source_official_url")).lower()
    if "plugintheme" in text or "plugin tema" in text:
        return "plugintheme"
    if "ultrapack" in text or "ultra pack" in text:
        return "ultrapackv2"
    name = str(value.get("source_name") or "").strip().lower().replace(" ", "")
    if name in {"plugintheme", "ultrapackv2", "ultrapack"}:
        return "ultrapackv2" if name.startswith("ultra") else "plugintheme"
    raise ValueError(f"Origem da aprovação não reconhecida: {value.get('source_name') or value.get('source_product_url')}")


def normalize_woo_product_id(value: Any) -> int:
    """Accept integral IDs emitted by legacy CSV/SQLite serializers."""
    text = str(value if value is not None else "").strip()
    if not text:
        return 0
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"Woo ID inválido: {value!r}") from error
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError(f"Woo ID inválido: {value!r}")
    return int(number)


class UpdateRepository:
    def __init__(self, data_dir: Path, database_path: Path | None = None):
        configured = os.getenv("SCRAPER_UPDATE_DB_PATH", "").strip()
        self.path = Path(configured).resolve() if configured else (database_path or data_dir / "consolidated_updates.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self.lock:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA foreign_keys=ON")
                yield db
                db.commit()
            except Exception:
                db.rollback(); raise
            finally:
                db.close()

    def initialize(self) -> None:
        with self.connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS update_jobs(
              job_id TEXT PRIMARY KEY, comparison_item_id TEXT NOT NULL UNIQUE,
              woo_product_id INTEGER NOT NULL, product_name TEXT NOT NULL,
              current_version TEXT NOT NULL, source_version TEXT NOT NULL,
              source_kind TEXT NOT NULL, source_name TEXT NOT NULL,
              source_url TEXT NOT NULL, source_product_id TEXT NOT NULL DEFAULT '',
              public_state TEXT NOT NULL DEFAULT 'ready', stage TEXT NOT NULL DEFAULT 'prepared',
              queue_name TEXT NOT NULL DEFAULT 'updates', queue_position INTEGER NOT NULL DEFAULT 0,
              attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT '',
              current_error TEXT, logs TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS update_attempts(
              attempt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, attempt_number INTEGER NOT NULL,
              started_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT '', source TEXT NOT NULL,
              version TEXT NOT NULL, result TEXT NOT NULL DEFAULT 'running', stages TEXT NOT NULL DEFAULT '[]',
              error TEXT, logs TEXT NOT NULL DEFAULT '[]', artifact_sha256 TEXT NOT NULL DEFAULT '',
              FOREIGN KEY(job_id) REFERENCES update_jobs(job_id), UNIQUE(job_id, attempt_number)
            );
            CREATE INDEX IF NOT EXISTS idx_update_jobs_state ON update_jobs(public_state);
            CREATE INDEX IF NOT EXISTS idx_update_attempts_job ON update_attempts(job_id, attempt_number DESC);
            """)

    @staticmethod
    def _job_id(item_id: str) -> str:
        return "upd-" + hashlib.sha256(item_id.encode()).hexdigest()[:20]

    def materialize(self, approvals: list[dict[str, Any]]) -> dict[str, int]:
        created = 0
        with self.connection() as db:
            position = int(db.execute("SELECT COALESCE(MAX(queue_position),0) FROM update_jobs").fetchone()[0])
            for item in approvals:
                item_id = str(item.get("comparison_item_id") or "").strip()
                if not item_id: continue
                job_id = self._job_id(item_id)
                if db.execute("SELECT 1 FROM update_jobs WHERE comparison_item_id=?", (item_id,)).fetchone():
                    continue
                kind = source_kind(item); provider=str(item.get("source_provider_name") or ("PluginTheme" if kind=="plugintheme" else "UltraPackV2"))
                position += 1; now = utc_now()
                db.execute("""INSERT INTO update_jobs(job_id,comparison_item_id,woo_product_id,product_name,current_version,
                    source_version,source_kind,source_name,source_url,source_product_id,queue_position,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (job_id,item_id,normalize_woo_product_id(item.get("woo_product_id") or item.get("site_id") or 0),
                    str(item.get("site_name") or item.get("source_name") or item_id),str(item.get("site_version") or ""),
                    str(item.get("source_version") or ""),kind,provider,
                    str(item.get("source_product_url") or item.get("source_official_url") or ""),str(item.get("source_product_id") or ""),position,now,now))
                created += 1
        return {"created": created, "total": self.count()}

    def migrate_legacy_runtime(self, path: Path) -> dict[str,int]:
        """Importa uma vez, sem alterar o JSON legado; a chave estável evita duplicação."""
        if not path.is_file(): return {"created":0,"total":self.count()}
        try: payload=json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError,json.JSONDecodeError): return {"created":0,"total":self.count()}
        jobs=list(payload.get("jobs",[])) if isinstance(payload,dict) else []
        approvals=[];legacy={}
        for item in jobs:
            if str(item.get("decision") or "")!="approve_update":continue
            item_id=str(item.get("comparison_item_id") or "").strip()
            url=str(item.get("source_url") or item.get("ultrapack_url") or "")
            if not item_id or not url:continue
            name="PluginTheme" if "plugintheme" in url.lower() else "UltraPackV2"
            approvals.append({"comparison_item_id":item_id,"woo_product_id":item.get("woo_product_id"),"site_name":item.get("name"),"site_version":item.get("plugintema_version"),"source_version":item.get("approved_source_version") or item.get("ultrapack_version"),"source_name":name,"source_product_url":url})
            legacy[item_id]=item
        result=self.materialize(approvals)
        state_map={"completed":"success","error":"error","rolled_back":"error","rollback_required":"error","executing":"ready","downloading":"ready","prepared":"ready","approved":"ready"}
        with self.connection() as db:
            for item_id,item in legacy.items():
                row=db.execute("SELECT attempts,public_state FROM update_jobs WHERE comparison_item_id=?",(item_id,)).fetchone()
                if not row or int(row["attempts"])>0 or row["public_state"]!="ready":continue
                state=state_map.get(str(item.get("state") or "").lower(),"ready");stage="completed" if state=="success" else ("legacy_error" if state=="error" else "prepared")
                logs=list(item.get("diagnostics") or []);error=item.get("execution_error") or item.get("error") or ""
                db.execute("UPDATE update_jobs SET public_state=?,stage=?,logs=?,current_error=?,started_at=?,finished_at=?,updated_at=? WHERE comparison_item_id=?",(state,stage,json.dumps(logs,ensure_ascii=False),json.dumps({"message":str(error),"code":"legacy_error","stage":stage},ensure_ascii=False) if error and state=="error" else None,str(item.get("executing_at") or ""),str(item.get("completed_at") or ""),str(item.get("updated_at") or utc_now()),item_id))
        return result

    def _decode(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None: return None
        item = dict(row); item["state"] = item.pop("public_state")
        item["error"] = json.loads(item.pop("current_error") or "null")
        item["logs"] = json.loads(item.get("logs") or "[]")
        item["group"] = {"ready":"prepared","running":"running","success":"success","error":"error"}[item["state"]]
        return item

    def count(self) -> int:
        with self.connection() as db: return int(db.execute("SELECT COUNT(*) FROM update_jobs").fetchone()[0])

    def get(self, job_id: str) -> dict[str, Any]:
        with self.connection() as db: row = db.execute("SELECT * FROM update_jobs WHERE job_id=?", (job_id,)).fetchone()
        item = self._decode(row)
        if not item: raise KeyError(job_id)
        return item

    def list(self, *, query: str="", group: str="", stage: str="", page: int=1, page_size: int=30) -> dict[str, Any]:
        filters: list[str]=[]; values: list[Any]=[]
        if query:
            filters.append("(product_name LIKE ? OR CAST(woo_product_id AS TEXT) LIKE ? OR source_name LIKE ?)"); values += [f"%{query}%"]*3
        if group:
            states=GROUP_BY_STATE.get(group)
            if not states: raise ValueError("Grupo operacional inválido")
            filters.append("public_state=?"); values.append(states[0])
        if stage: filters.append("stage=?"); values.append(stage)
        where = " WHERE "+" AND ".join(filters) if filters else ""
        page=max(1,int(page)); page_size=max(1,min(100,int(page_size)))
        with self.connection() as db:
            total=int(db.execute("SELECT COUNT(*) FROM update_jobs"+where,values).fetchone()[0])
            rows=db.execute("SELECT * FROM update_jobs"+where+" ORDER BY queue_position,created_at LIMIT ? OFFSET ?", values+[page_size,(page-1)*page_size]).fetchall()
            counts={"total":int(db.execute("SELECT COUNT(*) FROM update_jobs").fetchone()[0])}
            for key,state in (("prepared","ready"),("running","running"),("success","success"),("error","error")):
                counts[key]=int(db.execute("SELECT COUNT(*) FROM update_jobs WHERE public_state=?",(state,)).fetchone()[0])
        return {"items":[self._decode(r) for r in rows],"total":total,"page":page,"page_size":page_size,"pages":max(1,(total+page_size-1)//page_size),"counts":counts}

    def begin_attempt(self, job_id: str) -> dict[str, Any]:
        now=utc_now()
        with self.connection() as db:
            row=db.execute("SELECT attempts,source_kind,source_version FROM update_jobs WHERE job_id=?",(job_id,)).fetchone()
            if not row: raise KeyError(job_id)
            number=int(row["attempts"])+1; attempt_id=f"{job_id}-a{number}"
            db.execute("UPDATE update_jobs SET public_state='running',stage='validating',attempts=?,started_at=?,finished_at='',current_error=NULL,logs='[]',updated_at=? WHERE job_id=?",(number,now,now,job_id))
            db.execute("INSERT INTO update_attempts(attempt_id,job_id,attempt_number,started_at,source,version) VALUES(?,?,?,?,?,?)",(attempt_id,job_id,number,now,row["source_kind"],row["source_version"]))
        return {"attempt_id":attempt_id,"number":number}

    def progress(self, job_id: str, attempt_id: str, stage: str, message: str) -> None:
        now=utc_now()
        with self.connection() as db:
            job=db.execute("SELECT logs FROM update_jobs WHERE job_id=?",(job_id,)).fetchone(); attempt=db.execute("SELECT logs,stages FROM update_attempts WHERE attempt_id=?",(attempt_id,)).fetchone()
            logs=json.loads(job["logs"]); logs.append(message)
            alogs=json.loads(attempt["logs"]); alogs.append(message); stages=json.loads(attempt["stages"]); stages.append({"stage":stage,"at":now})
            db.execute("UPDATE update_jobs SET stage=?,logs=?,updated_at=? WHERE job_id=?",(stage,json.dumps(logs,ensure_ascii=False),now,job_id))
            db.execute("UPDATE update_attempts SET logs=?,stages=? WHERE attempt_id=?",(json.dumps(alogs,ensure_ascii=False),json.dumps(stages),attempt_id))

    def finish(self, job_id: str, attempt_id: str, *, success: bool, stage: str, error: dict[str,Any]|None=None, sha256: str="") -> None:
        now=utc_now(); state="success" if success else "error"; result="success" if success else "error"
        with self.connection() as db:
            db.execute("UPDATE update_jobs SET public_state=?,stage=?,finished_at=?,current_error=?,updated_at=? WHERE job_id=?",(state,stage,now,json.dumps(error,ensure_ascii=False) if error else None,now,job_id))
            db.execute("UPDATE update_attempts SET finished_at=?,result=?,error=?,artifact_sha256=? WHERE attempt_id=?",(now,result,json.dumps(error,ensure_ascii=False) if error else None,sha256,attempt_id))

    def history(self, job_id: str) -> list[dict[str, Any]]:
        with self.connection() as db: rows=db.execute("SELECT * FROM update_attempts WHERE job_id=? ORDER BY attempt_number DESC",(job_id,)).fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            for key,default in (("stages",[]),("logs",[]),("error",None)): item[key]=json.loads(item[key] or json.dumps(default))
            result.append(item)
        return result
