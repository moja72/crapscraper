from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Protocol

import requests
from urllib.parse import urlparse


class WooCommerceRequestError(RuntimeError):
    """Falha HTTP sanitizada; nunca carrega Authorization ou credenciais."""
    def __init__(self, *, method: str, endpoint: str, status: int, code: str = "", response_message: str = "", final_url: str = "", content_type: str = "", server: str = "", redirects: list[dict[str,Any]] | None = None):
        self.method=method; self.endpoint=endpoint; self.status=status; self.code=code; self.response_message=response_message; self.final_url=final_url; self.content_type=content_type; self.server=server; self.redirects=redirects or []
        detail=f"WooCommerce HTTP {status} em {method} {endpoint}"
        if code: detail+=f" ({code})"
        if response_message: detail+=f": {response_message}"
        super().__init__(detail)


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
        # Compartilha a configuração canônica usada por Loja/Adicionar, mantendo
        # os nomes antigos como fallback para instalações já existentes.
        base=(os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").rstrip("/")
        self.base=base+"/wp-json/wc/v3" if base and "/wp-json/" not in base else base
        self.auth=(os.getenv("SCRAPER_WC_CONSUMER_KEY") or os.getenv("SCRAPER_WOOCOMMERCE_KEY", ""),os.getenv("SCRAPER_WC_CONSUMER_SECRET") or os.getenv("SCRAPER_WOOCOMMERCE_SECRET", ""));self.timeout=45;self.session=requests.Session()
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.base or not all(self.auth):
            missing=[]
            if not self.base: missing.append("SCRAPER_WP_BASE_URL/SCRAPER_WOOCOMMERCE_URL")
            if not self.auth[0]: missing.append("SCRAPER_WC_CONSUMER_KEY/SCRAPER_WOOCOMMERCE_KEY")
            if not self.auth[1]: missing.append("SCRAPER_WC_CONSUMER_SECRET/SCRAPER_WOOCOMMERCE_SECRET")
            raise RuntimeError("Credenciais WooCommerce não configuradas (ausente: " + ", ".join(missing) + ")")
        endpoint=self.base+path
        headers={"Accept":"application/json","User-Agent":"CrapScraper-update/1.0",**dict(kwargs.pop("headers",{}) or {})}
        response=self.session.request(method,endpoint,auth=self.auth,headers=headers,timeout=self.timeout,allow_redirects=True,**kwargs)
        if response.status_code>=400:
            code=""; response_message=""
            try:
                payload=response.json()
                if isinstance(payload,dict):
                    code=str(payload.get("code") or "")
                    response_message=str(payload.get("message") or "")
            except (ValueError,requests.exceptions.JSONDecodeError):
                response_message="Resposta não-JSON (HTML ou proxy)"
            redirects=[{"status":h.status_code,"location":h.headers.get("Location"),"host":h.url.split("/",3)[2] if "/" in h.url else ""} for h in getattr(response,"history",[]) ]
            response_headers=getattr(response,"headers",{}) or {}
            raise WooCommerceRequestError(method=method,endpoint=path,status=response.status_code,code=code,response_message=response_message,final_url=response.url,content_type=str(response_headers.get("Content-Type") or ""),server=str(response_headers.get("Server") or ""),redirects=redirects)
        return response.json()
    def get_product(self, product_id: int) -> dict[str,Any]: return self._request("GET",f"/products/{product_id}")
    def check_connection(self) -> dict[str, Any]:
        payload=self._request("GET","/products",params={"per_page":1,"page":1})
        return {"ok":isinstance(payload,list),"readable":isinstance(payload,list)}
    def set_version(self, product_id: int, version: str) -> None:
        product=self.get_product(product_id);meta=list(product.get("meta_data",[]) or []);found=False
        for item in meta:
            if item.get("key")=="pt_versao": item["value"]=version;found=True
        if not found: meta.append({"key":"pt_versao","value":version})
        self._request("PUT",f"/products/{product_id}",json={"meta_data":meta})
    def prepare_job(self, job: dict[str,Any]) -> None:
        variations=self._request("GET",f"/products/{int(job['woo_product_id'])}/variations",params={"per_page":100})
        files={os.path.basename(urlparse(str(download.get("file") or "")).path) for variation in variations for download in (variation.get("downloads") or []) if urlparse(str(download.get("file") or "")).path.lower().endswith(".zip")}
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
    def check(self) -> dict[str, Any]:
        if self.root is None:return {"ok":False,"message":"SCRAPER_UPDATE_TARGET_DIR não configurado"}
        return {"ok":self.root.is_dir() and os.access(self.root,os.R_OK|os.W_OK),"message":str(self.root)}


class SFTPInstaller:
    """Troca atômica via SFTP, com backup local por tentativa e rollback verificável."""
    def __init__(self):
        self.host=os.getenv("SCRAPER_SSH_HOST","");self.port=int(os.getenv("SCRAPER_SSH_PORT","22"));self.user=os.getenv("SCRAPER_SSH_USERNAME") or os.getenv("SCRAPER_SSH_USER","");self.password=os.getenv("SCRAPER_SSH_PASSWORD","");self.key=os.getenv("SCRAPER_SSH_KEY_PATH","");self.root=(os.getenv("SCRAPER_SSH_DOWNLOAD_ROOT") or "/home/plugintema.com/downloads").rstrip("/")
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
        try:
            sftp.put(str(artifact),temporary)
            if not hasattr(sftp,"posix_rename"):raise RuntimeError("Servidor SFTP não oferece substituição atômica POSIX")
            sftp.posix_rename(temporary,remote)
        finally:
            try:sftp.remove(temporary)
            except OSError:pass
            sftp.close();client.close()
    def rollback(self,job,backup):
        remote=self._remote(job);temporary=remote+".rollback";client,sftp=self._connect()
        try:
            sftp.put(str(backup),temporary)
            if not hasattr(sftp,"posix_rename"):raise RuntimeError("Servidor SFTP não oferece rollback atômico POSIX")
            sftp.posix_rename(temporary,remote)
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
    def check(self) -> dict[str, Any]:
        client,sftp=self._connect()
        try:
            attrs=sftp.stat(self.root)
            return {"ok":attrs is not None,"message":self.root}
        finally:sftp.close();client.close()


def build_installer() -> Installer:
    return SFTPInstaller() if os.getenv("SCRAPER_SSH_HOST","").strip() else FilesystemInstaller()
