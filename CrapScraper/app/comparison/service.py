from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.comparison import decisions, matching
from app.comparison.models import DECISIONS, RELATIONSHIPS, STATUSES
from app.comparison.repository import ComparisonRepository


class ComparisonService:
    def __init__(self,data_dir:Path): self.repository=ComparisonRepository(data_dir);self.lock=threading.RLock();self.source_id="";self.site_id="";self.revision=0;self.last_run={};self._signature=None
    def catalogs(self)->dict[str,Any]:
        catalogs=self.repository.catalogs();sources=[x for x in catalogs if x["role"]=="source"];sites=[x for x in catalogs if x["role"]=="site"]
        if not self.source_id and sources:self.source_id=sources[0]["id"]
        if not self.site_id and sites:self.site_id=sites[0]["id"]
        return {"ok":True,"catalogs":catalogs,"source_id":self.source_id,"site_id":self.site_id,"statuses":STATUSES,"decisions":DECISIONS,"relationships":RELATIONSHIPS,"database":str(decisions.get_database_path())}
    def run(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            self.source_id=str(payload.get("source_id") or self.source_id);self.site_id=str(payload.get("site_id") or self.site_id)
            source=self.repository.resolve(self.source_id);site=self.repository.resolve(self.site_id);signature=((source.stat().st_mtime_ns,source.stat().st_size),(site.stat().st_mtime_ns,site.stat().st_size));cached=not bool(payload.get("force")) and signature==self._signature;started=time.perf_counter()
            optional=lambda key:int(payload[key]) if str(payload.get(key,""))!="" else None
            result=matching.build_comparison_payload(source_path=source,site_path=site,status=str(payload.get("status", "")),query=str(payload.get("query", "")),decision=str(payload.get("decision", "")),candidate_filter=str(payload.get("confidence", "")),candidate_count_min=optional("candidate_count_min"),candidate_count_max=optional("candidate_count_max"),score_min=optional("score_min"),score_max=optional("score_max"),page=int(payload.get("page",1)),page_size=int(payload.get("page_size",5)),force=bool(payload.get("force")))
            elapsed=round(time.perf_counter()-started,3);self._signature=signature;self.last_run={"at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"duration_seconds":elapsed,"cached":cached,"source_id":self.source_id,"site_id":self.site_id,"processed":result.get("summary",{}).get("total_rows",0),"filtered":result.get("pagination",{}).get("total_rows",0),"log":[f"Fonte: {self.source_id}",f"Site: {self.site_id}",f"Processados: {result.get('summary',{}).get('total_rows',0)}",f"Filtrados: {result.get('pagination',{}).get('total_rows',0)}",f"Duração: {elapsed:.3f}s",f"Cache: {'reutilizado' if cached else 'recalculado'}"]}
            result.update(source_id=self.source_id,site_id=self.site_id,revision=self.revision,operation=self.last_run);return result
    def save_decision(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            row=dict(payload.get("snapshot") or {})
            snapshot={key:row.get(key,"") for key in ("woo_product_id","site_version","site_product_url","site_official_url","source_version","source_product_url","source_official_url","relationship_state","relationship_label")}
            saved=decisions.save_decision(payload.get("comparison_item_id"),payload.get("decision"),note=payload.get("note",""),operator="consolidated-ui",site_id=row.get("site_id",""),site_name=row.get("site_name",""),source_name=row.get("source_name",""),status=row.get("status",""),recommended_action=row.get("recommended_action",""),**snapshot);self.revision+=1;return {"ok":True,"item":saved,"revision":self.revision}
    def save_decisions_bulk(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            result=decisions.save_decisions_bulk(payload.get("items"),payload.get("decision"),note=payload.get("note",""),operator="consolidated-ui-bulk");self.revision+=1;return {"ok":True,**result,"revision":self.revision}
    def selection(self,payload:dict[str,Any])->dict[str,Any]:
        selected=[];page=1
        while True:
            result=self.run({**payload,"page":page,"page_size":100,"force":False});selected.extend(result["rows"])
            if page>=result["pagination"]["total_pages"]:break
            page+=1
        return {"ok":True,"items":selected,"total":len(selected)}
    def reset_decision(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            saved=decisions.reset_decision(payload.get("comparison_item_id"),operator="consolidated-ui");self.revision+=1;return {"ok":True,"item":saved,"revision":self.revision}
    def decision_history(self,payload:dict[str,Any])->dict[str,Any]: return {"ok":True,"items":decisions.get_decision_history(payload.get("comparison_item_id"))}
    def candidates(self,payload:dict[str,Any])->dict[str,Any]:
        role=str(payload.get("role") or "source");catalog=self.source_id if role=="source" else self.site_id
        return {"ok":True,"items":matching.search_comparison_catalog_products(self.repository.resolve(catalog),role=role,query=str(payload.get("query", "")),limit=50)}
    def search_catalog(self,catalog_id:str,role:str,query:str,limit:int=30)->dict[str,Any]:
        catalog=next((x for x in self.repository.catalogs() if x["id"]==catalog_id and x["role"]==role),None)
        if not catalog:raise ValueError("Catálogo/funcão inválidos para a sincronização")
        return {"ok":True,"catalog":catalog,"items":matching.search_comparison_catalog_products(self.repository.resolve(catalog_id),role=role,query=query,limit=min(50,max(1,int(limit))))}
    def save_relationship(self,payload:dict[str,Any])->dict[str,Any]:
        saved=decisions.save_relationship(payload.get("site_product_key"),payload.get("source_product_key",""),payload.get("relationship_state"),site_id=payload.get("site_id",""),site_name=payload.get("site_name",""),source_name=payload.get("source_name",""),note=payload.get("note",""),operator="consolidated-ui");self.revision+=1;return {"ok":True,"item":saved,"revision":self.revision}
    def approvals(self)->dict[str,Any]: return {"ok":True,"updates":decisions.list_approved_updates(),"additions":decisions.list_approved_additions()}
