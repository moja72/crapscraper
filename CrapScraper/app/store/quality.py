from __future__ import annotations
from app.store.woocommerce import is_pack,product_kind

class StoreQualityService:
    def inspect(self,products,gateway=None,variations_by_product=None,check_variations=True):
        issues=[]
        def add(product,code,field,message,severity="warning",fixable=False):issues.append({"code":code,"severity":severity,"product_id":int(product.get("id") or 0),"product_name":str(product.get("name") or ""),"field":field,"message":message,"diagnosis":message,"recoverable":fixable,"fixable":fixable})
        for product in products:
            if not str(product.get("short_description") or "").strip():add(product,"missing_short_description","short_description","Breve descrição sobre o produto ausente.","error",True)
            meta={str(x.get("key")):str(x.get("value") or "") for x in product.get("meta_data",[]) or []}
            if not meta.get("pt_versao") and not is_pack(product):add(product,"missing_version","pt_versao","Versão do produto ausente.")
            if not meta.get("site_oficial") and not is_pack(product):add(product,"missing_official_url","site_oficial","Página oficial ausente.")
            if not meta.get("desenvolvedor") and not is_pack(product):add(product,"missing_developer","desenvolvedor","Desenvolvedor ausente.")
            if not product.get("images"):add(product,"missing_image","images","Imagem principal ausente.")
            if check_variations and str(product.get("type"))=="variable":
                variations=(variations_by_product or {}).get(int(product["id"])) if variations_by_product is not None else gateway.variations(product["id"]);periods={" ".join(str(a.get("option") or "").lower().split()) for v in variations for a in v.get("attributes",[]) or []}
                if not any("anual" in x or "annual" in x or "1 ano" in x or "12 meses" in x for x in periods) or not any("vital" in x or "lifetime" in x for x in periods):add(product,"invalid_variations","variations","Variações Anual/Vitalícia incompletas.","error")
                if any(v.get("downloadable") and not v.get("downloads") for v in variations):add(product,"missing_download","downloads","Variação baixável sem arquivo.","error")
        return issues
