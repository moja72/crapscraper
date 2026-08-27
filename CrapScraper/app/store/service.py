from __future__ import annotations
import os,threading,time
from pathlib import Path
from app.store.repository import StoreRepository
from app.store.wordpress import WordPressManualQueueClient,FixtureManualQueue
from app.store.woocommerce import StoreWooCommerceGateway,FixtureStoreGateway,is_pack,product_kind
from app.store.monitor import StoreMonitorService
from app.store.pricing import StorePricingService
from app.store.bundles import StoreBundleService
from app.store.quality import StoreQualityService

def enabled(name):return os.getenv(name,"").strip().lower() in {"1","true","yes","on"}

class StoreService:
    def __init__(self,data_dir:Path,updates,*,repository=None,gateway=None,queue=None):
        fixture=enabled("SCRAPER_STORE_E2E_FIXTURES");self.repository=repository or StoreRepository(data_dir);self.gateway=gateway or (FixtureStoreGateway() if fixture else StoreWooCommerceGateway());self.queue=queue or (FixtureManualQueue() if fixture else WordPressManualQueueClient());self.monitor_service=StoreMonitorService(self.repository,self.queue,updates);self.write_enabled=enabled("SCRAPER_STORE_WRITE_ENABLED");self.pricing=StorePricingService(self.gateway,self.repository,self.write_enabled);self.bundles_service=StoreBundleService(self.gateway);self.quality_service=StoreQualityService();self._cache=[];self._cached_at=0.0;self._issues=[];self._issues_at=0.0;self.lock=threading.RLock()
    def _products(self,refresh=False):
        with self.lock:
            if refresh or not self._cache or time.monotonic()-self._cached_at>60:self._cache=list(self.gateway.products(status="publish"));self._cached_at=time.monotonic()
            return list(self._cache)
    def _quality(self):
        with self.lock:
            if not self._issues or time.monotonic()-self._issues_at>300:self._issues=self.quality_service.inspect(self._products(),self.gateway);self._issues_at=time.monotonic()
            return list(self._issues)
    def summary(self):
        products=self._products();issues=self._quality();counts={"products":len(products),"plugins":sum(product_kind(x)=="plugin" for x in products),"themes":sum(product_kind(x)=="theme" for x in products),"packs":sum(is_pack(x) for x in products),"quality":len(issues)};return {"ok":True,"counts":counts,"monitor":self.monitor_service.snapshot()}
    def list_products(self,payload):
        query=str(payload.get("query") or "").casefold();kind=str(payload.get("type") or "");category=str(payload.get("category") or "").casefold();page=max(1,int(payload.get("page") or 1));size=max(1,min(100,int(payload.get("page_size") or 20)));rows=[]
        for p in self._products():
            pk=product_kind(p)
            if query and query not in (str(p.get("id"))+" "+str(p.get("name"))).casefold():continue
            if kind and pk!=kind:continue
            if category and not any(category==str(x.get("id")) or category==str(x.get("name","")).casefold() for x in p.get("categories",[]) or []):continue
            rows.append({"product_id":int(p["id"]),"product_name":p.get("name",""),"type":pk,"status":p.get("status",""),"categories":[x.get("name","") for x in p.get("categories",[]) or []],"short_description":bool(str(p.get("short_description") or "").strip()),"pack":is_pack(p)})
        return {"ok":True,"items":rows[(page-1)*size:page*size],"total":len(rows),"page":page,"page_size":size,"pages":max(1,(len(rows)+size-1)//size)}
    def product(self,product_id):
        product=self.gateway.product(int(product_id));return {"ok":True,"item":product,"variations":self.gateway.variations(product_id) if product.get("type")=="variable" else [],"issues":[x for x in self.quality_service.inspect([product],self.gateway) if x["product_id"]==int(product_id)]}
    def categories(self):return {"ok":True,"items":self.gateway.categories()}
    def bundles(self):return {"ok":True,"items":self.bundles_service.list(self._products())}
    def quality(self,payload):
        query=str(payload.get("query") or "").casefold();code=str(payload.get("code") or "");page=max(1,int(payload.get("page") or 1));size=max(1,min(100,int(payload.get("page_size") or 20)));rows=[x for x in self._quality() if (not query or query in (str(x["product_id"])+" "+x["product_name"]).casefold()) and (not code or x["code"]==code)];return {"ok":True,"items":rows[(page-1)*size:page*size],"total":len(rows),"page":page,"page_size":size,"pages":max(1,(len(rows)+size-1)//size)}
    def monitor(self):return {"ok":True,"monitor":self.monitor_service.snapshot()}
    def monitor_enable(self,value):return {"ok":True,"monitor":self.monitor_service.enable(value)}
    def monitor_run(self):return self.monitor_service.run(force=True)
    def pricing_preview(self,payload):return self.pricing.preview(payload,self._products())
    def pricing_apply(self,payload):result=self.pricing.apply(payload,self._products());self._cached_at=0;return result
    def bundle_preview(self,payload):return self.bundles_service.preview(payload)
    def bundle_apply(self,payload):result=self.bundles_service.apply(payload,self.write_enabled);self._cached_at=0;return result
