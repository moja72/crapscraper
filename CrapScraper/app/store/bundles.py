from app.store.woocommerce import is_pack
from app.store.pricing import money

class StoreBundleService:
    def __init__(self,gateway):self.gateway=gateway
    def list(self,products):
        return [{"product_id":int(p["id"]),"product_name":str(p.get("name") or ""),"product_type":str(p.get("type") or ""),"regular_price":str(p.get("regular_price") or ""),"sale_price":str(p.get("sale_price") or ""),"variations":self.gateway.variations(p["id"]) if p.get("type")=="variable" else []} for p in products if is_pack(p)]
    def preview(self,payload):
        product=self.gateway.product(int(payload.get("product_id") or 0))
        if not is_pack(product):raise ValueError("O produto selecionado não é pack/bundle")
        regular,sale=money(payload.get("regular_price")),money(payload.get("sale_price"),False);unchanged=str(product.get("regular_price") or "")==regular and str(product.get("sale_price") or "")==sale
        return {"ok":True,"product_id":int(product["id"]),"product_name":product.get("name",""),"product_type":product.get("type",""),"regular_price":regular,"sale_price":sale,"status":"unchanged" if unchanged else "change"}
    def apply(self,payload,write_enabled):
        if not write_enabled:raise PermissionError("Escrita da Loja desabilitada por SCRAPER_STORE_WRITE_ENABLED")
        if payload.get("confirmation")!="ALTERAR PACK":raise ValueError('Digite "ALTERAR PACK" para confirmar')
        preview=self.preview(payload)
        if preview["status"]=="unchanged":return {**preview,"updated":False}
        self.gateway.update_product_price(preview["product_id"],preview["regular_price"],preview["sale_price"]);return {**preview,"updated":True,"status":"changed"}
