from __future__ import annotations
import os,requests
from typing import Any

def _fold(value):return " ".join(str(value or "").lower().replace("í","i").split())
def is_pack(product):return str(product.get("type","")).lower()=="bundle" or any(_fold(x.get("name")) in {"pack","packs","pacote","pacotes"} for x in product.get("categories",[]) or [])
def product_kind(product):
    text=" ".join(_fold(x.get("name")) for x in product.get("categories",[]) or [])
    return "theme" if "tema" in text or "theme" in text else "plugin" if "plugin" in text else "pack" if is_pack(product) else "other"

class StoreWooCommerceGateway:
    def __init__(self,session=None):
        site=(os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").rstrip("/");self.base=site+"/wp-json/wc/v3" if site and "/wp-json/" not in site else site;self.auth=(os.getenv("SCRAPER_WC_CONSUMER_KEY") or os.getenv("SCRAPER_WOOCOMMERCE_KEY", ""),os.getenv("SCRAPER_WC_CONSUMER_SECRET") or os.getenv("SCRAPER_WOOCOMMERCE_SECRET", ""));self.session=session or requests.Session();self.timeout=60
    def _request(self,method,path,**kwargs):
        if not self.base or not all(self.auth):raise RuntimeError("WooCommerce não configurado")
        response=self.session.request(method,self.base+path,auth=self.auth,timeout=self.timeout,**kwargs);response.raise_for_status();return response.json()
    def products(self,**filters):
        rows=[];page=1
        while True:
            batch=self._request("GET","/products",params={"page":page,"per_page":100,**filters});rows.extend(batch)
            if len(batch)<100:return rows
            page+=1
    def product(self,product_id):return self._request("GET",f"/products/{int(product_id)}")
    def variations(self,product_id):return self._request("GET",f"/products/{int(product_id)}/variations",params={"per_page":100})
    def categories(self):return self._request("GET","/products/categories",params={"per_page":100})
    def update_variations(self,product_id,updates):return self._request("POST",f"/products/{int(product_id)}/variations/batch",json={"update":updates}).get("update",[])
    def update_product_price(self,product_id,regular,sale):return self._request("PUT",f"/products/{int(product_id)}",json={"regular_price":regular,"sale_price":sale})

class FixtureStoreGateway:
    """Somente para SCRAPER_STORE_E2E_FIXTURES; nunca selecionado em produção."""
    def __init__(self):
        self.writes=[];self._products=[{"id":100+i,"name":f"E2E Produto {i:02}","type":"variable","status":"publish","categories":[{"id":1,"name":"Plugins" if i%2 else "Temas"}],"tags":[{"name":"WordPress"}],"short_description":"" if i in {1,4} else "Descrição breve","images":[] if i==3 else [{"id":1}],"meta_data":[{"key":"pt_versao","value":"1.0"},{"key":"site_oficial","value":"https://example.test"},{"key":"desenvolvedor","value":"E2E"}]} for i in range(1,16)];self._products.append({"id":200,"name":"E2E Pack","type":"bundle","status":"publish","categories":[{"id":3,"name":"Packs"}],"short_description":"Pack","images":[{"id":2}],"meta_data":[]})
    def products(self,**filters):return list(self._products)
    def product(self,pid):return next(x for x in self._products if x["id"]==int(pid))
    def variations(self,pid):return [{"id":int(pid)*10+1,"name":"Anual","attributes":[{"option":"Anual"}],"regular_price":"99.00","sale_price":"79.00","downloadable":True,"downloads":[{"file":"x.zip"}]},{"id":int(pid)*10+2,"name":"Vitalícia","attributes":[{"option":"Vitalícia"}],"regular_price":"199.00","sale_price":"149.00","downloadable":True,"downloads":[{"file":"x.zip"}]}]
    def categories(self):return [{"id":1,"name":"Plugins","count":8},{"id":2,"name":"Temas","count":7},{"id":3,"name":"Packs","count":1}]
    def update_variations(self,pid,updates):self.writes.append((pid,updates));return updates
    def update_product_price(self,pid,regular,sale):self.writes.append((pid,regular,sale));return self.product(pid)
