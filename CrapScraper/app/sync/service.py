from __future__ import annotations
import hashlib,threading,uuid
from typing import Any
from app.comparison import matching
from app.sync.models import SyncSelection

def provider(catalog,item):
    text=" ".join((str(catalog.get("id") or ""),str(catalog.get("label") or ""),str(item.get("product_url") or ""))).lower()
    if "plugintheme" in text:return "PluginTheme"
    if "ultrapack" in text or "ultra-pack" in text:return "UltraPackV2"
    raise ValueError("A origem selecionada não é PluginTheme nem UltraPackV2")

class E2EExecutionRecorder:
    """Executor de registro exclusivo do E2E; não contém lógica operacional."""
    def __init__(self):self.calls=[]
    def execute(self,job_id):self.calls.append(job_id);return {"ok":True,"job_id":job_id,"fixture":True}

class ManualSyncService:
    """Orquestra seleção/materialização e delega toda execução aos serviços canônicos."""
    def __init__(self,comparison,updates,additions):self.comparison=comparison;self.updates=updates;self.additions=additions;self.lock=threading.RLock();self.selections={};self.resolutions={};self.operations={};self.running=set()
    def catalogs(self):
        payload=self.comparison.catalogs();rows=[]
        for catalog in payload["catalogs"]:
            if catalog["role"]=="site":rows.append(catalog);continue
            try:provider(catalog,{})
            except ValueError:continue
            rows.append(catalog)
        return {**payload,"catalogs":rows}
    def search(self,payload):
        role=str(payload.get("role") or "");catalog_id=str(payload.get("catalog_id") or "");result=self.comparison.search_catalog(catalog_id,role,str(payload.get("query") or ""),int(payload.get("limit") or 30));items=[]
        with self.lock:
            for product in result["items"]:
                raw=f"{role}|{catalog_id}|{product.get('product_key')}";selection_id="sel-"+hashlib.sha256(raw.encode()).hexdigest()[:20];source_provider=provider(result["catalog"],product) if role=="source" else "PluginTema";selection=SyncSelection(selection_id,catalog_id,result["catalog"]["label"],role,dict(product),source_provider);self.selections[selection_id]=selection;items.append(selection.to_dict())
        return {"ok":True,"items":items,"catalog":result["catalog"]}
    def resolve(self,payload):
        operation=str(payload.get("operation") or "");source=self.selections.get(str(payload.get("source_selection_id") or ""));site=self.selections.get(str(payload.get("site_selection_id") or ""))
        if operation not in {"update","addition"} or not source or source.role!="source":raise ValueError("Seleção de origem inválida")
        if operation=="update" and (not site or site.role!="site"):raise ValueError("Selecione o produto PluginTema existente")
        if operation=="addition" and site:raise ValueError("Produto novo não pode possuir produto PluginTema selecionado")
        source_data={"source_name":source.product.get("name",""),"source_version":source.product.get("version",""),"source_product_url":source.product.get("product_url",""),"source_official_url":source.product.get("official_url",""),"source_product_id":source.product.get("product_key","")};site_data={"site_id":site.product.get("site_id","") if site else "","site_name":site.product.get("name","") if site else "","site_version":site.product.get("version","") if site else "","site_official_url":site.product.get("official_url","") if site else ""};item_id=matching.build_comparison_item_id(site_data,source_data);resolution_id="sync-"+uuid.uuid4().hex
        approval={"comparison_item_id":item_id,**site_data,**source_data,"woo_product_id":site_data["site_id"],"source_provider_name":source.source_provider,"product_name":source.product.get("name",""),"kind":"theme" if "tema" in str(source.product.get("category","")).lower() or "theme" in str(source.product.get("category","")).lower() else "plugin","relationship_state":"manual_confirmed" if site else "confirmed_not_in_source","relationship_label":"Vínculo confirmado manualmente" if site else "Confirmado como novo"}
        resolution={"resolution_id":resolution_id,"operation":operation,"comparison_item_id":item_id,"site":site.to_dict() if site else None,"source":source.to_dict(),"approval":approval,"action":"Atualizar produto existente" if operation=="update" else "Adicionar novo produto","status":"review"}
        with self.lock:self.resolutions[resolution_id]=resolution
        return {"ok":True,**{k:v for k,v in resolution.items() if k!="approval"}}
    def materialize(self,resolution_id):
        with self.lock:
            resolution=self.resolutions.get(resolution_id)
            if not resolution:raise KeyError(resolution_id)
            if resolution.get("job_id"):return {"ok":True,"operation":resolution["operation"],"job_id":resolution["job_id"],"reused":True}
            approval=dict(resolution["approval"]);operation=resolution["operation"]
            snapshot={"comparison_item_id":approval["comparison_item_id"],"decision":"approve_update" if operation=="update" else "approve_new_product","snapshot":{**approval,"source_name":approval["source_name"],"status":"update_available" if operation=="update" else "new_source"},"note":"Sincronização direta confirmada"};self.comparison.save_decision(snapshot)
            if operation=="update":
                self.comparison.save_relationship({"site_product_key":resolution["site"].get("product_key") or resolution["site"].get("site_id"),"source_product_key":resolution["source"].get("product_key"),"relationship_state":"manual_confirmed","site_id":approval["site_id"],"site_name":approval["site_name"],"source_name":approval["source_name"],"source_product_url":approval["source_product_url"],"source_official_url":approval["source_official_url"],"note":"Sincronização direta"});item=self.updates.materialize_manual(approval)["item"]
            else:item=self.additions.materialize_manual(approval)["item"]
            resolution["job_id"]=item["job_id"];resolution["status"]="materialized";self.operations[item["job_id"]]={"operation":operation,"job_id":item["job_id"],"state":item["state"],"stage":item["stage"],"result":None,"error":None};return {"ok":True,"operation":operation,"job_id":item["job_id"],"reused":False}
    def execute(self,resolution_id):
        materialized=self.materialize(resolution_id);job_id=materialized["job_id"];operation=materialized["operation"]
        with self.lock:
            if job_id in self.running:return {"ok":True,"already_running":True,**self.operations[job_id]}
            current=self.operations.get(job_id,{})
            if current.get("state")=="success":return {"ok":True,"reused":True,**current}
            self.running.add(job_id);self.operations[job_id]={"operation":operation,"job_id":job_id,"state":"running","stage":"delegating","result":None,"error":None}
        try:
            result=(self.updates if operation=="update" else self.additions).execute(job_id);state="success" if result.get("ok") else "error";error=result.get("error");self.operations[job_id].update(state=state,stage="completed" if state=="success" else "failed",result=result,error=error);return {"ok":state=="success",**self.operations[job_id]}
        finally:
            with self.lock:self.running.discard(job_id)
    def status(self,job_id):
        operation=self.operations.get(job_id,{}).get("operation")
        if not operation:raise KeyError(job_id)
        service=self.updates if operation=="update" else self.additions;canonical=service.job(job_id)["item"];calls=getattr(service.executor,"calls",None);return {"ok":True,**self.operations[job_id],"canonical_state":canonical["state"],"canonical_stage":canonical["stage"],"execution_count":calls.count(job_id) if isinstance(calls,list) else None}
