from __future__ import annotations
from decimal import Decimal,InvalidOperation
from app.store.woocommerce import is_pack,product_kind

def money(value,required=True):
    raw=str(value or "").replace("R$","").strip().replace(",",".")
    if not raw and not required:return ""
    try:amount=Decimal(raw)
    except InvalidOperation:raise ValueError("Preço inválido") from None
    if amount<0:raise ValueError("Preço não pode ser negativo")
    return format(amount.quantize(Decimal("0.01")),"f")
def period(variation):
    text=" ".join(str(a.get("option") or "").lower() for a in variation.get("attributes",[]) or [])+" "+str(variation.get("name") or "").lower()
    return "lifetime" if "vital" in text or "lifetime" in text else "annual" if "anual" in text or "annual" in text else ""

class StorePricingService:
    def __init__(self,gateway,repository,write_enabled=False):self.gateway=gateway;self.repository=repository;self.write_enabled=write_enabled
    def preview(self,payload,products):
        kinds=set(payload.get("kinds") or []);selected=[p for p in products if product_kind(p) in kinds and not is_pack(p)];changes=[]
        prices={f"{p}_{k}":money(payload.get(f"{p}_{k}"),k=="regular") for p in ("annual","lifetime") for k in ("regular","sale")}
        for product in selected:
            for variation in self.gateway.variations(product["id"]):
                p=period(variation)
                if not p:continue
                target_regular,target_sale=prices[f"{p}_regular"],prices[f"{p}_sale"];unchanged=str(variation.get("regular_price") or "")==target_regular and str(variation.get("sale_price") or "")==target_sale;changes.append({"product_id":int(product["id"]),"product_name":product.get("name",""),"variation_id":int(variation["id"]),"period":p,"current_regular":str(variation.get("regular_price") or ""),"current_sale":str(variation.get("sale_price") or ""),"regular_price":target_regular,"sale_price":target_sale,"status":"unchanged" if unchanged else "change"})
        return {"ok":True,"affected":sum(x["status"]=="change" for x in changes),"unchanged":sum(x["status"]=="unchanged" for x in changes),"changes":changes,"prices":prices,"kinds":sorted(kinds)}
    def apply(self,payload,products):
        if not self.write_enabled:raise PermissionError("Escrita da Loja desabilitada por SCRAPER_STORE_WRITE_ENABLED")
        if payload.get("confirmation")!="ALTERAR PRECOS":raise ValueError('Digite "ALTERAR PRECOS" para confirmar')
        preview=self.preview(payload,products);grouped={}
        for row in preview["changes"]:
            if row["status"]=="change":grouped.setdefault(row["product_id"],[]).append({"id":row["variation_id"],"regular_price":row["regular_price"],"sale_price":row["sale_price"]})
        changed=0;errors=[]
        for pid,updates in grouped.items():
            try:changed+=len(self.gateway.update_variations(pid,updates))
            except Exception as exc:errors.append({"product_id":pid,"message":str(exc)})
        result={"ok":not errors,"changed":changed,"unchanged":preview["unchanged"],"errors":errors};self.repository.pricing_run("success" if not errors else "partial",payload,result);return result
