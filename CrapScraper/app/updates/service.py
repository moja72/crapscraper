from __future__ import annotations

import threading
import os
import json
from pathlib import Path
from typing import Any

from app.comparison import decisions
from app.updates.batch import UpdateBatchService
from app.updates.executor import UpdateExecutor
from app.updates.repository import UpdateRepository
from app.updates.source_auth import get_source_session, set_source_state, source_state


class UpdateService:
    def __init__(self, data_dir: Path, *, repository: UpdateRepository|None=None, executor: UpdateExecutor|None=None):
        self.repository=repository or UpdateRepository(data_dir);self.executor=executor or UpdateExecutor(self.repository);self.batch=UpdateBatchService(self.executor);self.lock=threading.RLock();self.environment_validation:dict[str,Any]={}
        if os.getenv("SCRAPER_UPDATE_IMPORT_LEGACY","1").strip().lower() not in {"0","false","no","off"}: self.repository.migrate_legacy_runtime(data_dir/"update_runtime.json")
        self.materialize()
        self.repository.backfill_history_events()
        history=getattr(self.executor,"history",None)
        if history is not None and getattr(history.client,"configured",False):
            threading.Thread(target=history.sync_pending,name="update-history-outbox",daemon=True).start()
    def materialize(self)->dict[str,Any]:
        with self.lock:return {"ok":True,**self.repository.materialize(decisions.list_approved_updates())}
    def materialize_manual(self,approval:dict[str,Any])->dict[str,Any]:
        with self.lock:
            self.repository.materialize([approval]);job_id=self.repository._job_id(str(approval["comparison_item_id"]));return {"ok":True,"item":self.repository.get(job_id)}
    def list(self,payload:dict[str,Any]|None=None)->dict[str,Any]:
        payload=payload or {};self.materialize();result=self.repository.list(query=str(payload.get("query") or ""),group=str(payload.get("group") or ""),stage=str(payload.get("stage") or ""),page=int(payload.get("page") or 1),page_size=int(payload.get("page_size") or 5));return {"ok":True,**result,"batch":self.batch.state(),"database":str(self.repository.path)}
    def environment(self)->dict[str,Any]:
        executor=self.executor;woo=executor.woo;installer=executor.installer
        cookie_count=0
        try:
            cookies=json.loads(os.getenv("SCRAPER_PLUGINTHEME_COOKIES_JSON","{}") or "{}")
            cookie_count=len(cookies) if isinstance(cookies,dict) else 0
        except json.JSONDecodeError: pass
        woo_configured=bool(getattr(woo,"base","") and all(getattr(woo,"auth",("",""))))
        ssh=bool(getattr(installer,"host","") and getattr(installer,"user","") and getattr(installer,"root",""))
        local=bool(getattr(installer,"root",None)) if not hasattr(installer,"host") else False
        ultrapack_state=source_state("ultrapackv2")
        plugintheme_session=get_source_session("plugintheme")
        source_configured=bool(get_source_session("ultrapackv2") is not None or plugintheme_session is not None or cookie_count or os.getenv("SCRAPER_PLUGINTHEME_HEADERS_JSON","").strip() or os.getenv("SCRAPER_ULTRAPACK_COOKIES_JSON","").strip() or os.getenv("SCRAPER_ULTRAPACK_HEADERS_JSON","").strip())
        validated=self.environment_validation
        woo_valid=bool(validated.get("woocommerce",{}).get("ok"));storage_valid=bool(validated.get("storage",{}).get("ok"))
        source_valid=bool(validated.get("source",{}).get("ok"));source_expired=validated.get("source",{}).get("status")=="expired"
        checks=[{"key":"woocommerce","label":"WooCommerce","state":"ok" if woo_valid else "attention","value":"VALIDADO" if woo_valid else "CONFIGURADO / NÃO VALIDADO" if woo_configured else "NÃO CONFIGURADO","detail":validated.get("woocommerce",{}).get("message","")},{"key":"source","label":"Fonte autenticada","state":"ok" if source_valid else "attention","value":"VALIDADA" if source_valid else "EXPIRADA" if source_expired else "CONFIGURADA / NÃO VALIDADA" if source_configured else "NÃO CONFIGURADA","detail":validated.get("source",{}).get("message","")},{"key":"storage","label":"Armazenamento de destino","state":"ok" if storage_valid else "blocked","value":"VALIDADO" if storage_valid else "CONFIGURADO / NÃO VALIDADO" if ssh or local else "NÃO CONFIGURADO","detail":validated.get("storage",{}).get("message","")},{"key":"individual","label":"Execução individual","state":"ok" if executor.enabled else "blocked","value":"HABILITADA" if executor.enabled else "DESABILITADA"},{"key":"woo_write","label":"WooCommerce escrita","state":"ok" if woo_valid and storage_valid and executor.enabled else "blocked","value":"HABILITADA" if woo_valid and storage_valid and executor.enabled else "DESABILITADA"}]
        plugintheme_configured=bool(plugintheme_session is not None or cookie_count)
        return {"ok":True,"checks":checks,"attention_count":sum(x["state"]!="ok" for x in checks),"plugintheme":{"configured":plugintheme_configured,"cookie_count":len(plugintheme_session.cookies) if plugintheme_session is not None and hasattr(plugintheme_session,"cookies") else cookie_count,"status":"VALIDADA" if source_state("plugintheme")=="validated" else "CONFIGURADA" if plugintheme_configured else "NÃO VALIDADA","renewal_available":False},"allowed_product_count":len(executor.allowed_product_ids)}
    def verify_environment(self)->dict[str,Any]:
        validation:dict[str,Any]={}
        try:
            result=self.executor.woo.check_connection()
            validation["woocommerce"]={"ok":bool(result.get("ok")),"message":"Leitura autenticada do WooCommerce confirmada."}
        except Exception as error:
            validation["woocommerce"]={"ok":False,"message":str(error)}
        try:
            result=self.executor.installer.check()
            validation["storage"]={"ok":bool(result.get("ok")),"message":str(result.get("message") or "")}
        except Exception as error:
            validation["storage"]={"ok":False,"message":str(error)}
        candidates=self.repository.list(group="prepared",page=1,page_size=100)["items"]
        source_results=[]
        for kind in sorted({str(item.get("source_kind") or "") for item in candidates if item.get("source_kind")}):
            job=next(item for item in candidates if item.get("source_kind")==kind)
            try:
                source=self.executor.sources.get(kind);probe=getattr(source,"validate_access",None)
                if not callable(probe):
                    source.validate_authentication();raise RuntimeError("A fonte não oferece preflight autenticado de leitura")
                details=probe(job);source_results.append({"source":kind,"ok":True,"version":details.get("version"),"message":"Acesso autenticado confirmado."})
            except Exception as error:
                message=str(error);code=str(getattr(getattr(error,"error",None),"code","") or "")
                missing=code=="authentication_missing" or "não configurada" in message.lower()
                expired=not missing and any(term in message.lower() for term in ("login","expir","401","403"))
                status="not_configured" if missing else "expired" if expired else "invalid"
                set_source_state(kind,status)
                source_results.append({"source":kind,"ok":False,"status":status,"message":message})
        if source_results:
            source_ok=all(item["ok"] for item in source_results)
            validation["source"]={"ok":source_ok,"status":"validated" if source_ok else next((item.get("status") for item in source_results if not item["ok"]),"invalid"),"message":"; ".join(f"{item['source']}: {item['message']}" for item in source_results)}
        else:
            validation["source"]={"ok":False,"status":"not_validated","message":"Nenhum job preparado disponível para validar a fonte sem consumir crédito."}
        self.environment_validation=validation
        return self.environment()
    def selection(self,payload:dict[str,Any])->dict[str,Any]:
        base={"query":str(payload.get("query") or ""),"group":str(payload.get("group") or ""),"stage":str(payload.get("stage") or "")};first=self.repository.list(**base,page=1,page_size=100);items=list(first["items"])
        for page in range(2,first["pages"]+1):items.extend(self.repository.list(**base,page=page,page_size=100)["items"])
        return {"ok":True,"items":items,"total":len(items)}
    def job(self,job_id:str)->dict[str,Any]: return {"ok":True,"item":self.repository.get(job_id),"history":self.repository.history(job_id)}
    def execute(self,job_id:str)->dict[str,Any]: return self.executor.execute(job_id)
    def retry(self,job_id:str)->dict[str,Any]: return self.executor.execute(job_id)
    def batch_start(self,job_ids:list[str]|None=None)->dict[str,Any]:
        ids=job_ids or [x["job_id"] for x in self.repository.list(group="prepared",page_size=100)["items"]]
        return {"ok":True,"batch":self.batch.start(ids)}
    def batch_control(self,action:str)->dict[str,Any]:
        method={"pause":self.batch.pause,"resume":self.batch.resume,"cancel":self.batch.cancel}[action];return {"ok":True,"batch":method()}
