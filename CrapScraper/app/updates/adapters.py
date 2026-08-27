from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Protocol

import requests


class WooGateway(Protocol):
    def get_product(self, product_id: int) -> dict[str,Any]: ...
    def set_version(self, product_id: int, version: str) -> None: ...


class Installer(Protocol):
    def backup(self, job: dict[str,Any], attempt_dir: Path) -> Any: ...
    def install(self, job: dict[str,Any], artifact: Path, backup: Any) -> None: ...
    def rollback(self, job: dict[str,Any], backup: Any) -> None: ...
    def validate(self, job: dict[str,Any], sha256: str) -> bool: ...


def product_version(product: dict[str,Any]) -> str:
    for item in product.get("meta_data",[]) or []:
        if item.get("key")=="pt_versao": return str(item.get("value") or "")
    return ""


class WooCommerceGateway:
    def __init__(self):
        base=os.getenv("SCRAPER_WOOCOMMERCE_URL","").rstrip("/"); self.base=base+"/wp-json/wc/v3" if base and "/wp-json/" not in base else base
        self.auth=(os.getenv("SCRAPER_WOOCOMMERCE_KEY",""),os.getenv("SCRAPER_WOOCOMMERCE_SECRET",""));self.timeout=45
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.base or not all(self.auth): raise RuntimeError("Credenciais WooCommerce não configuradas")
        response=requests.request(method,self.base+path,auth=self.auth,timeout=self.timeout,**kwargs);response.raise_for_status();return response.json()
    def get_product(self, product_id: int) -> dict[str,Any]: return self._request("GET",f"/products/{product_id}")
    def set_version(self, product_id: int, version: str) -> None:
        product=self.get_product(product_id);meta=list(product.get("meta_data",[]) or []);found=False
        for item in meta:
            if item.get("key")=="pt_versao": item["value"]=version;found=True
        if not found: meta.append({"key":"pt_versao","value":version})
        self._request("PUT",f"/products/{product_id}",json={"meta_data":meta})
    def prepare_job(self, job: dict[str,Any]) -> None:
        variations=self._request("GET",f"/products/{int(job['woo_product_id'])}/variations",params={"per_page":100})
        files={os.path.basename(str(download.get("file") or "")) for variation in variations for download in (variation.get("downloads") or []) if str(download.get("file") or "").lower().endswith(".zip")}
        files.discard("")
        if len(files)!=1: raise RuntimeError(f"WooCommerce deve apontar para exatamente um ZIP; encontrados: {sorted(files)}")
        job["target_filename"]=files.pop()


class FilesystemInstaller:
    """Instalador real para um repositório de ZIPs montado/local; SSH pode montar esse diretório."""
    def __init__(self, root: Path | None=None): self.root=(root or Path(os.getenv("SCRAPER_UPDATE_TARGET_DIR",""))).resolve() if (root or os.getenv("SCRAPER_UPDATE_TARGET_DIR")) else None
    def _target(self, job: dict[str,Any]) -> Path:
        if self.root is None: raise RuntimeError("SCRAPER_UPDATE_TARGET_DIR não configurado")
        name=os.path.basename(str(job.get("target_filename") or f"{job['woo_product_id']}.zip"));return self.root/name
    def backup(self, job: dict[str,Any], attempt_dir: Path) -> Path:
        target=self._target(job)
        if not target.is_file(): raise FileNotFoundError(f"ZIP de destino não encontrado: {target}")
        backup=attempt_dir/"backup"/target.name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup);return backup
    def install(self, job: dict[str,Any], artifact: Path, backup: Path) -> None:
        target=self._target(job);temporary=target.with_suffix(target.suffix+".updating");shutil.copy2(artifact,temporary);os.replace(temporary,target)
    def rollback(self, job: dict[str,Any], backup: Path) -> None: shutil.copy2(backup,self._target(job))
    def validate(self, job: dict[str,Any], sha256: str) -> bool:
        target=self._target(job);digest=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "";return digest==sha256


class SFTPInstaller:
    """Troca atômica via SFTP, com backup local por tentativa e rollback verificável."""
    def __init__(self):
        self.host=os.getenv("SCRAPER_SSH_HOST","");self.port=int(os.getenv("SCRAPER_SSH_PORT","22"));self.user=os.getenv("SCRAPER_SSH_USER","");self.password=os.getenv("SCRAPER_SSH_PASSWORD","");self.key=os.getenv("SCRAPER_SSH_KEY_PATH","");self.root=os.getenv("SCRAPER_SSH_DOWNLOAD_ROOT","").rstrip("/")
    def _connect(self):
        import paramiko
        if not self.host or not self.user or not self.root:raise RuntimeError("Configuração SSH incompleta")
        client=paramiko.SSHClient();client.load_system_host_keys();client.set_missing_host_key_policy(paramiko.RejectPolicy());kwargs={"hostname":self.host,"port":self.port,"username":self.user,"timeout":30}
        if self.key:kwargs["key_filename"]=self.key
        elif self.password:kwargs["password"]=self.password
        client.connect(**kwargs);return client,client.open_sftp()
    def _remote(self,job):return f"{self.root}/{os.path.basename(str(job['target_filename']))}"
    def backup(self,job,attempt_dir):
        backup=attempt_dir/"backup"/os.path.basename(self._remote(job));backup.parent.mkdir(parents=True,exist_ok=True);client,sftp=self._connect()
        try:sftp.get(self._remote(job),str(backup))
        finally:sftp.close();client.close()
        return backup
    def install(self,job,artifact,backup):
        remote=self._remote(job);temporary=remote+f".{job['job_id']}.upload";client,sftp=self._connect()
        try:sftp.put(str(artifact),temporary);sftp.rename(temporary,remote)
        finally:
            try:sftp.remove(temporary)
            except OSError:pass
            sftp.close();client.close()
    def rollback(self,job,backup):
        remote=self._remote(job);temporary=remote+".rollback";client,sftp=self._connect()
        try:sftp.put(str(backup),temporary);sftp.rename(temporary,remote)
        finally:sftp.close();client.close()
    def validate(self,job,sha256):
        client,sftp=self._connect();digest=hashlib.sha256()
        try:
            with sftp.open(self._remote(job),"rb") as stream:
                while True:
                    chunk=stream.read(1024*1024)
                    if not chunk:break
                    digest.update(chunk)
        finally:sftp.close();client.close()
        return digest.hexdigest()==sha256


def build_installer() -> Installer:
    return SFTPInstaller() if os.getenv("SCRAPER_SSH_HOST","").strip() else FilesystemInstaller()
