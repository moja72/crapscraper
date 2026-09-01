from app.store.woocommerce import is_pack,is_plan
from app.store.pricing import money

class StoreBundleService:
    def __init__(self,gateway):self.gateway=gateway
    def list(self,products,group="pack"):
        predicate=is_plan if group=="plan" else is_pack
        return [{"product_id":int(p["id"]),"product_name":str(p.get("name") or ""),"product_type":str(p.get("type") or ""),"price_group":group,"regular_price":str(p.get("regular_price") or ""),"sale_price":str(p.get("sale_price") or ""),"variations":self.gateway.variations(p["id"]) if str(p.get("type") or "").startswith("variable") else []} for p in products if predicate(p)]
    def preview(self,payload):
        product=self.gateway.product(int(payload.get("product_id") or 0))
        group=str(payload.get("price_group") or "pack")
        if group not in {"pack","plan"}:raise ValueError("Grupo de preço inválido")
        if not (is_plan(product) if group=="plan" else is_pack(product)):raise ValueError("O produto selecionado não pertence ao grupo informado")
        targets=list(payload.get("variations") or [])
        if targets:
            current={int(item["id"]):item for item in self.gateway.variations(product["id"])};changes=[]
            for target in targets:
                variation_id=int(target.get("id") or 0)
                if variation_id not in current:raise ValueError(f"Variação #{variation_id} não pertence ao produto")
                regular,sale=money(target.get("regular_price")),money(target.get("sale_price"),False);row=current[variation_id];unchanged=str(row.get("regular_price") or "")==regular and str(row.get("sale_price") or "")==sale;changes.append({"id":variation_id,"name":str(row.get("name") or f"Variação #{variation_id}"),"regular_price":regular,"sale_price":sale,"status":"unchanged" if unchanged else "change"})
            return {"ok":True,"product_id":int(product["id"]),"product_name":product.get("name",""),"product_type":product.get("type",""),"price_group":group,"variation_changes":changes,"status":"unchanged" if all(item["status"]=="unchanged" for item in changes) else "change"}
        if str(product.get("type") or "").startswith("variable"):
            raise ValueError("Informe os preços das variações deste produto")
        regular,sale=money(payload.get("regular_price")),money(payload.get("sale_price"),False);unchanged=str(product.get("regular_price") or "")==regular and str(product.get("sale_price") or "")==sale
        return {"ok":True,"product_id":int(product["id"]),"product_name":product.get("name",""),"product_type":product.get("type",""),"price_group":group,"regular_price":regular,"sale_price":sale,"variation_changes":[],"status":"unchanged" if unchanged else "change"}
    def apply(self,payload,write_enabled):
        if not write_enabled:raise PermissionError("Escrita da Loja desabilitada por SCRAPER_STORE_WRITE_ENABLED")
        if payload.get("confirmation") not in {"ALTERAR PACK","ALTERAR PRECO"}:raise ValueError('Digite "ALTERAR PRECO" para confirmar')
        preview=self.preview(payload)
        if preview["status"]=="unchanged":return {**preview,"updated":False,"changed":0}
        variation_updates=[{"id":item["id"],"regular_price":item["regular_price"],"sale_price":item["sale_price"]} for item in preview.get("variation_changes",[]) if item["status"]=="change"]
        if variation_updates:changed=len(self.gateway.update_variations(preview["product_id"],variation_updates))
        else:self.gateway.update_product_price(preview["product_id"],preview["regular_price"],preview["sale_price"]);changed=1
        return {**preview,"updated":True,"changed":changed,"status":"changed"}
