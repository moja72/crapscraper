from __future__ import annotations
import hashlib,struct,zlib,zipfile
from pathlib import Path
from app.updates.sources import DownloadArtifact,SourceFailure

def approval(item="new-1",source="PluginTheme"):
    host="plugintheme.net" if source=="PluginTheme" else "ultrapackv2.com"
    return {"comparison_item_id":item,"source_name":source,"source_version":"2.0","source_product_url":f"https://{host}/item/{item}","source_official_url":"https://developer.example/product"}

def png(path:Path):
    raw=b"\x89PNG\r\n\x1a\n";pixel=zlib.compress(b"\x00\xff\x00\x00\xff")
    def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    path.write_bytes(raw+chunk(b"IHDR",struct.pack(">IIBBBBB",1,1,8,6,0,0,0))+chunk(b"IDAT",pixel)+chunk(b"IEND",b"")+b"x"*1200);return path

class FakeSource:
    def __init__(self,kind="plugintheme",fail=None):self.kind=kind;self.display_name="PluginTheme" if kind=="plugintheme" else "UltraPackV2";self.calls=[];self.fail=fail
    def validate_authentication(self):self.calls.append("auth")
    def confirm_version(self,job):self.calls.append("version");return job["source_version"]
    def download(self,job,target):
        self.calls.append("download")
        if self.fail:raise self.fail
        target.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(target,"w") as archive:archive.writestr("plugin/main.php","ok")
        raw=target.read_bytes();return DownloadArtifact(target,hashlib.sha256(raw).hexdigest(),len(raw),job["source_url"],job["source_url"]+"?download=1","application/zip")
class Sources:
    def __init__(self,*sources):self.items={s.kind:s for s in sources}
    def source(self,job):return self.items[job["source_kind"]]
class Research:
    def resolve(self,job):return {"official_url":job.get("official_url") or "https://developer.example/product","developer":"Developer Ltd"}
class Content:
    def __init__(self):self.calls=0
    def generate(self,job):self.calls+=1;return {"product_name":job["product_name"],"short_description":"Descrição comercial verificada. "*12,"content":"<p>Conteúdo completo e verificável.</p>"*15,"categories":["Plugins"],"tags":["WordPress","Plugin"]}
class Images:
    def __init__(self,root):self.root=root;self.calls=0
    def valid(self,path):return bool(path) and Path(path).is_file()
    def generate(self,job):self.calls+=1;self.root.mkdir(parents=True,exist_ok=True);return png(self.root/f"{job['job_id']}.png")
class Publisher:
    def __init__(self):self.calls=0
    def publish(self,job,path):self.calls+=1;return f"https://store.example/downloads/{job['job_id']}.zip"
class Store:
    def __init__(self,fail_validate=False,lose_response=False):self.product_id=0;self.create_calls=0;self.media_calls=0;self.variation_options=[];self.fail_validate=fail_validate;self.lose_response=lose_response
    def reconcile(self,job):return self.product_id
    def upload_media(self,path,title):self.media_calls+=1;return 77
    def create_parent(self,job,media,download):
        self.create_calls+=1;self.product_id=501
        if self.lose_response:self.lose_response=False;raise RuntimeError("response lost")
        return {"id":self.product_id}
    def ensure_variations(self,pid,job,download):self.variation_options=["Anual","Vitalício"];return [601,602]
    def validate(self,pid,job,ids):return not self.fail_validate
    def set_status(self,pid,status):pass
