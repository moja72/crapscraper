from app.additions.wordpress import AdditionStoreGateway
class Gateway(AdditionStoreGateway):
    def __init__(self):self.calls=[];self.variations=[{"id":10,"attributes":[{"id":4,"option":"Anual"}],"virtual":True,"downloadable":True,"downloads":[{"file":"x"}]}]
    def _term(self,kind,name):self.calls.append(("term",kind,name));return len(self.calls)
    def _wc(self,method,path,**kwargs):
        self.calls.append((method,path,kwargs.get("json")))
        if path.endswith("/variations") and method=="GET":return self.variations
        if path.endswith("/variations") and method=="POST":return {"id":11}
        if path=="/products" and method=="POST":return {"id":99,"payload":kwargs["json"]}
        return []
def job():return {"job_id":"add-x","product_name":"Produto","kind":"plugin","content":"full","short_description":"short","categories":["Plugins"],"tags":["WordPress"],"source_version":"2.0","official_url":"https://official","developer":"Dev","source_name":"PluginTheme"}
def test_parent_contract_metadata_categories_tags():
    gateway=Gateway();gateway.create_parent(job(),77,"https://files/x.zip");payload=[x[2] for x in gateway.calls if x[0]=="POST" and x[1]=="/products"][0];meta={m["key"]:m["value"] for m in payload["meta_data"]}
    assert payload["type"]=="variable" and payload["status"]=="draft" and payload["images"]==[{"id":77}] and payload["categories"] and payload["tags"]
    assert meta=={"pt_versao":"2.0","site_oficial":"https://official","desenvolvedor":"Dev","crapscraper_addition_job":"add-x","fonte_crapscraper":"PluginTheme"}
def test_partial_variations_only_creates_missing_lifetime():
    gateway=Gateway();ids=gateway.ensure_variations(99,job(),"https://files/x.zip");posts=[x for x in gateway.calls if x[0]=="POST"]
    assert ids==[10,11] and len(posts)==1 and posts[0][2]["attributes"][0]["option"]=="Vitalício" and posts[0][2]["virtual"] and posts[0][2]["downloadable"] and len(posts[0][2]["downloads"])==1
