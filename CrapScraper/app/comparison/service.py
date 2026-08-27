from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.comparison import decisions, matching
from app.comparison.models import DECISIONS, RELATIONSHIPS, STATUSES
from app.comparison.repository import ComparisonRepository


class ComparisonService:
    def __init__(self,data_dir:Path): self.repository=ComparisonRepository(data_dir);self.lock=threading.RLock();self.source_id="";self.site_id="";self.revision=0
    def catalogs(self)->dict[str,Any]:
        catalogs=self.repository.catalogs();sources=[x for x in catalogs if x["role"]=="source"];sites=[x for x in catalogs if x["role"]=="site"]
        if not self.source_id and sources:self.source_id=sources[0]["id"]
        if not self.site_id and sites:self.site_id=sites[0]["id"]
        return {"ok":True,"catalogs":catalogs,"source_id":self.source_id,"site_id":self.site_id,"statuses":STATUSES,"decisions":DECISIONS,"relationships":RELATIONSHIPS,"database":str(decisions.get_database_path())}
    def run(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            self.source_id=str(payload.get("source_id") or self.source_id);self.site_id=str(payload.get("site_id") or self.site_id)
            result=matching.build_comparison_payload(source_path=self.repository.resolve(self.source_id),site_path=self.repository.resolve(self.site_id),status=str(payload.get("status", "")),query=str(payload.get("query", "")),decision=str(payload.get("decision", "")),candidate_filter=str(payload.get("confidence", "")),page=int(payload.get("page",1)),page_size=int(payload.get("page_size",30)),force=bool(payload.get("force")))
            result.update(source_id=self.source_id,site_id=self.site_id,revision=self.revision);return result
    def save_decision(self,payload:dict[str,Any])->dict[str,Any]:
        with self.lock:
            row=dict(payload.get("snapshot") or {})
            snapshot={key:row.get(key,"") for key in ("woo_product_id","site_version","site_product_url","site_official_url","source_version","source_product_url","source_official_url","relationship_state","relationship_label")}
            saved=decisions.save_decision(payload.get("comparison_item_id"),payload.get("decision"),note=payload.get("note",""),operator="consolidated-ui",site_id=row.get("site_id",""),site_name=row.get("site_name",""),source_name=row.get("source_name",""),status=row.get("status",""),recommended_action=row.get("recommended_action",""),**snapshot);self.revision+=1;return {"ok":True,"item":saved,"revision":self.revision}
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
