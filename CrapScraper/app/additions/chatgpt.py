from __future__ import annotations
import json,os
from typing import Any
import requests
from app.additions.content import content_prompt,normalize_list,valid_content

class ChatGPTContentService:
    def __init__(self,api_key:str|None=None,model:str|None=None,session=None):self.api_key=api_key if api_key is not None else os.getenv("OPENAI_API_KEY","");self.model=model or os.getenv("SCRAPER_CHATGPT_MODEL","gpt-5-mini");self.session=session or requests.Session()
    def generate(self,job:dict[str,Any])->dict[str,Any]:
        if not self.api_key:raise RuntimeError("OPENAI_API_KEY não configurada para o ChatGPT")
        response=self.session.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"},json={"model":self.model,"input":content_prompt(job),"text":{"format":{"type":"json_object"}}},timeout=180);response.raise_for_status();payload=response.json();text=str(payload.get("output_text") or "")
        if not text:
            text="".join(str(part.get("text") or "") for item in payload.get("output",[]) for part in item.get("content",[]) if isinstance(part,dict))
        data=json.loads(text);data["categories"]=normalize_list(data.get("categories"));data["tags"]=normalize_list(data.get("tags"))
        if not valid_content(data):raise RuntimeError("ChatGPT retornou conteúdo incompleto ou curto demais")
        return data
