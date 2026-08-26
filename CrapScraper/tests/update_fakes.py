from __future__ import annotations
import hashlib, zipfile
from pathlib import Path
from app.updates.sources import DownloadArtifact, SourceFailure
from app.updates.models import UpdateError

def approval(item="cmp-1",kind="PluginTheme",woo=101):
    slug="plugintheme" if kind=="PluginTheme" else "ultrapackv2"
    return {"comparison_item_id":item,"woo_product_id":str(woo),"site_name":f"Produto {item}","site_version":"1.0","source_version":"2.0","source_name":kind,"source_product_url":f"https://{slug}.example/product/{item}"}

class FakeWoo:
    def __init__(self,version="1.0",fail_set=False):self.version=version;self.fail_set=fail_set;self.set_calls=[]
    def get_product(self,pid):return {"id":pid,"meta_data":[{"key":"pt_versao","value":self.version}]}
    def set_version(self,pid,version):
        self.set_calls.append(version)
        if self.fail_set:raise RuntimeError("woo write failed")
        self.version=version

class FakeSource:
    def __init__(self,kind="plugintheme",fail=None):self.kind=kind;self.display_name="PluginTheme" if kind=="plugintheme" else "UltraPackV2";self.calls=[];self.fail=fail
    def validate_authentication(self):self.calls.append("auth")
    def confirm_version(self,job):self.calls.append("version");return job["source_version"]
    def download(self,job,target):
        self.calls.append("download")
        if self.fail:raise self.fail
        target.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(target,"w") as z:z.writestr("plugin/file.php","ok")
        data=target.read_bytes();return DownloadArtifact(target,hashlib.sha256(data).hexdigest(),len(data),job["source_url"],job["source_url"],"application/zip")

class FakeInstaller:
    def __init__(self,fail=False):self.fail=fail;self.installs=0;self.rollbacks=0;self.sha=""
    def backup(self,job,attempt_dir):p=attempt_dir/"backup.zip";p.write_bytes(b"old");return p
    def install(self,job,artifact,backup):self.installs+=1;self.sha=hashlib.sha256(artifact.read_bytes()).hexdigest();
    def validate(self,job,sha):
        if self.fail:raise RuntimeError("install validation failed")
        return self.sha==sha
    def rollback(self,job,backup):self.rollbacks+=1
