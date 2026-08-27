import json
from app.additions.chatgpt import ChatGPTContentService
class Response:
    def raise_for_status(self):pass
    def json(self):return {"output_text":json.dumps({"product_name":"Produto","short_description":"Descrição comercial. "*25,"content":"<p>Conteúdo confiável.</p>"*20,"categories":["Plugins"],"tags":["WordPress"]})}
class Session:
    def post(self,*args,**kwargs):self.payload=kwargs["json"];return Response()
def test_chatgpt_contract_and_description():
    session=Session();data=ChatGPTContentService("key",session=session).generate({"kind":"plugin","product_name":"Produto","source_version":"2.0","source_url":"https://source","official_url":"https://official","developer":"Dev"})
    assert len(data["short_description"])>=400 and data["categories"]==["Plugins"] and "developer" in session.payload["input"].lower()
