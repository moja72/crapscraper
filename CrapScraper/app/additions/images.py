from __future__ import annotations
import base64,imghdr,os
from pathlib import Path
import requests
from app.additions.creative import image_prompt

class ImageService:
    def __init__(self,root:Path,api_key:str|None=None,session=None):self.root=root;self.api_key=api_key if api_key is not None else os.getenv("OPENAI_API_KEY","");self.session=session or requests.Session()
    def valid(self,path:str)->bool:
        p=Path(path) if path else Path("-");return p.is_file() and p.stat().st_size>1024 and imghdr.what(p) in {"png","jpeg","webp"}
    def generate(self,job):
        if not self.api_key:raise RuntimeError("OPENAI_API_KEY não configurada para gerar imagem")
        response=self.session.post("https://api.openai.com/v1/images/generations",headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"},json={"model":os.getenv("SCRAPER_IMAGE_MODEL","gpt-image-1"),"prompt":image_prompt(job),"size":"1024x1024","background":"transparent"},timeout=300);response.raise_for_status();item=response.json()["data"][0]
        if item.get("b64_json"):raw=base64.b64decode(item["b64_json"])
        elif item.get("url"):raw=self.session.get(item["url"],timeout=120).content
        else:raise RuntimeError("A geração não retornou bytes de imagem")
        self.root.mkdir(parents=True,exist_ok=True);path=self.root/f"{job['job_id']}.png";path.write_bytes(raw)
        if not self.valid(str(path)):path.unlink(missing_ok=True);raise RuntimeError("Imagem gerada inválida")
        return path
