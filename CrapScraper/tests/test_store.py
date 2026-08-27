from pathlib import Path
from app.store.repository import StoreRepository
from app.store.service import StoreService
from app.store.wordpress import FixtureManualQueue
from app.store.woocommerce import FixtureStoreGateway

class Updates:
    def __init__(self):self.executed=[]
    def list(self,payload):return {"items":[{"job_id":"upd-1","woo_product_id":101,"source_name":"PluginTheme","current_version":"1.0","source_version":"2.0"}]}
    def execute(self,job_id):self.executed.append(job_id);return {"ok":True}

def service(tmp_path):return StoreService(tmp_path,Updates(),repository=StoreRepository(tmp_path),gateway=FixtureStoreGateway(),queue=FixtureManualQueue())

def test_summary_products_categories_quality(tmp_path):
    store=service(tmp_path);summary=store.summary();assert summary["counts"]=={"products":16,"plugins":8,"themes":7,"packs":1};assert len(store.categories()["items"])==3;assert store.quality({})["total"]==3

def test_summary_does_not_fetch_variations_per_product(tmp_path):
    store=service(tmp_path);calls=0;original=store.gateway.variations
    def counted(product_id):
        nonlocal calls;calls+=1;return original(product_id)
    store.gateway.variations=counted;store.summary();assert calls==0

def test_product_details_reuse_variations_for_quality(tmp_path):
    store=service(tmp_path);calls=0;original=store.gateway.variations
    def counted(product_id):
        nonlocal calls;calls+=1;return original(product_id)
    store.gateway.variations=counted;store.product(101);assert calls==1

def test_product_filters_and_pagination(tmp_path):
    store=service(tmp_path);page=store.list_products({"type":"plugin","page_size":3,"page":2});assert page["total"]==8 and page["page"]==2 and len(page["items"])==3

def test_product_details_are_real_gateway_data(tmp_path):
    value=service(tmp_path).product(101);assert value["item"]["id"]==101 and len(value["variations"])==2 and value["issues"]

def test_bundles_preserve_bundle_type(tmp_path):
    rows=service(tmp_path).bundles()["items"];assert len(rows)==1 and rows[0]["product_type"]=="bundle"

def test_bundle_preview_and_apply_are_gated_idempotent(tmp_path):
    store=service(tmp_path);pack=store.gateway.product(200);pack.update(regular_price="299.00",sale_price="249.00");payload={"product_id":200,"regular_price":"299","sale_price":"249"};assert store.bundle_preview(payload)["status"]=="unchanged"
    try:store.bundle_apply({**payload,"confirmation":"ALTERAR PACK"})
    except PermissionError:pass
    else:raise AssertionError("gate de pack não bloqueou escrita")
