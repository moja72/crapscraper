from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

import requests
from urllib.parse import unquote, urlparse

from app.updates.logging import safe_text, safe_url


class WooCommerceRequestError(RuntimeError):
    """Falha HTTP sanitizada; nunca carrega Authorization ou credenciais."""
    def __init__(self, *, method: str, endpoint: str, status: int, code: str = "", response_message: str = "", final_url: str = "", content_type: str = "", server: str = "", redirects: list[dict[str,Any]] | None = None):
        self.method=method; self.endpoint=endpoint; self.status=status; self.code=code; self.response_message=response_message; self.final_url=final_url; self.content_type=content_type; self.server=server; self.redirects=redirects or []
        detail=f"WooCommerce HTTP {status} em {method} {endpoint}"
        if code: detail+=f" ({code})"
        if response_message: detail+=f": {response_message}"
        super().__init__(detail)


class WooCommerceConnectivityError(RuntimeError):
    """Bounded, sanitized connectivity failure raised by the canonical gateway."""

    def __init__(
        self,
        *,
        method: str,
        endpoint: str,
        host: str,
        error_type: str,
        attempts: int,
        original_exception: BaseException,
    ) -> None:
        self.method = method.upper()
        self.endpoint = endpoint
        self.host = host
        self.error_type = error_type
        self.attempts = attempts
        self.original_exception = safe_text(repr(original_exception), limit=1600)
        self.diagnosis = (
            f"Não foi possível resolver {host}."
            if error_type == "dns_resolution"
            else f"Não foi possível conectar a {host}."
        )
        super().__init__("Falha de conexão com WooCommerce.")


def _connection_error_type(error: BaseException) -> str:
    evidence = f"{type(error).__name__}: {error}".lower()
    pending = [error]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        evidence += f" {type(item).__name__}: {item}".lower()
        for nested in (getattr(item, "__cause__", None), getattr(item, "__context__", None), getattr(item, "reason", None)):
            if isinstance(nested, BaseException):
                pending.append(nested)
        pending.extend(argument for argument in getattr(item, "args", ()) if isinstance(argument, BaseException))
    if any(marker in evidence for marker in ("nameresolutionerror", "getaddrinfo failed", "failed to resolve", "name resolution")):
        return "dns_resolution"
    if isinstance(error, (requests.ConnectTimeout, requests.ReadTimeout, requests.Timeout)):
        return "timeout"
    return "connection"


class WooGateway(Protocol):
    def get_product(self, product_id: int) -> dict[str,Any]: ...
    def set_version(self, product_id: int, version: str) -> dict[str,Any]: ...
    def confirm_version(self, product_id: int, version: str) -> dict[str,Any]: ...


class Installer(Protocol):
    def backup(self, job: dict[str,Any], attempt_dir: Path) -> Any: ...
    def install(self, job: dict[str,Any], artifact: Path, backup: Any) -> None: ...
    def rollback(self, job: dict[str,Any], backup: Any) -> None: ...
    def validate(self, job: dict[str,Any], sha256: str) -> bool: ...


def normalize_version(value: Any) -> str:
    """Normaliza representação, sem tornar versões diferentes equivalentes."""
    return "" if value is None else str(value).strip()


def version_metadata(product: dict[str,Any]) -> dict[str,Any]:
    entries=[]
    for index,item in enumerate(product.get("meta_data",[]) or []):
        if isinstance(item,dict) and item.get("key")=="pt_versao":
            raw=item.get("value")
            try: meta_id=int(item["id"])
            except (KeyError,TypeError,ValueError): meta_id=None
            entries.append({"index":index,"id":meta_id,"key":"pt_versao","value":normalize_version(raw),"value_type":type(raw).__name__})
    status="missing" if not entries else "single" if len(entries)==1 else "duplicate"
    single=entries[0] if len(entries)==1 else {}
    return {"status":status,"count":len(entries),"entries":entries,"meta_id":single.get("id"),"value":single.get("value","")}


def product_version(product: dict[str,Any]) -> str:
    metadata=version_metadata(product)
    return str(metadata["value"]) if metadata["status"]=="single" else ""


class VersionPersistenceError(RuntimeError):
    """Divergência auditável de ``pt_versao`` sem qualquer dado secreto."""
    def __init__(self, message: str, evidence: dict[str,Any]):
        self.evidence=dict(evidence)
        super().__init__(message)


class WooCommerceGateway:
    def __init__(self, *, confirmation_delays: tuple[float,...]=(0.0,0.15,0.35), network_delays: tuple[float,...]=(0.0,0.2,0.6), sleeper: Any=time.sleep):
        # Compartilha a configuração canônica usada por Loja/Adicionar, mantendo
        # os nomes antigos como fallback para instalações já existentes.
        base=(os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").rstrip("/")
        self.base=base+"/wp-json/wc/v3" if base and "/wp-json/" not in base else base
        self.auth=(os.getenv("SCRAPER_WC_CONSUMER_KEY") or os.getenv("SCRAPER_WOOCOMMERCE_KEY", ""),os.getenv("SCRAPER_WC_CONSUMER_SECRET") or os.getenv("SCRAPER_WOOCOMMERCE_SECRET", ""));self.timeout=45;self.session=requests.Session();self.confirmation_delays=confirmation_delays;self.network_delays=network_delays or (0.0,);self.sleeper=sleeper;self.last_request_diagnostic:dict[str,Any]={}
    def _request_response(self, method: str, path: str, **kwargs: Any) -> tuple[Any,Any]:
        if not self.base or not all(self.auth):
            missing=[]
            if not self.base: missing.append("SCRAPER_WP_BASE_URL/SCRAPER_WOOCOMMERCE_URL")
            if not self.auth[0]: missing.append("SCRAPER_WC_CONSUMER_KEY/SCRAPER_WOOCOMMERCE_KEY")
            if not self.auth[1]: missing.append("SCRAPER_WC_CONSUMER_SECRET/SCRAPER_WOOCOMMERCE_SECRET")
            raise RuntimeError("Credenciais WooCommerce não configuradas (ausente: " + ", ".join(missing) + ")")
        endpoint=self.base+path
        headers={"Accept":"application/json","User-Agent":"CrapScraper-update/1.0",**dict(kwargs.pop("headers",{}) or {})}
        method=method.upper();host=str(urlparse(self.base).hostname or "")
        response=None
        for attempt,delay in enumerate(self.network_delays,1):
            if delay>0:self.sleeper(delay)
            try:
                response=self.session.request(method,endpoint,auth=self.auth,headers=headers,timeout=self.timeout,allow_redirects=True,**kwargs)
                self.last_request_diagnostic={"method":method,"endpoint":path,"host":host,"attempts":attempt,"recovered":attempt>1,"error_type":""}
                break
            except requests.RequestException as error:
                error_type=_connection_error_type(error)
                retryable=error_type=="dns_resolution" or (method in {"GET","HEAD","OPTIONS"} and error_type in {"connection","timeout"})
                if retryable and attempt < len(self.network_delays):
                    continue
                self.last_request_diagnostic={"method":method,"endpoint":path,"host":host,"attempts":attempt,"recovered":False,"error_type":error_type}
                raise WooCommerceConnectivityError(method=method,endpoint=path,host=host,error_type=error_type,attempts=attempt,original_exception=error) from error
        assert response is not None
        if response.status_code>=400:
            code=""; response_message=""
            try:
                payload=response.json()
                if isinstance(payload,dict):
                    code=str(payload.get("code") or "")
                    response_message=str(payload.get("message") or "")
            except (ValueError,requests.exceptions.JSONDecodeError):
                response_message="Resposta não-JSON (HTML ou proxy)"
            redirects=[{"status":h.status_code,"location":safe_url(h.headers.get("Location")),"host":urlparse(h.url).hostname or ""} for h in getattr(response,"history",[]) ]
            response_headers=getattr(response,"headers",{}) or {}
            raise WooCommerceRequestError(method=method,endpoint=path,status=response.status_code,code=code,response_message=safe_text(response_message),final_url=safe_url(response.url),content_type=str(response_headers.get("Content-Type") or ""),server=str(response_headers.get("Server") or ""),redirects=redirects)
        if response.status_code==204 or not getattr(response,"content",getattr(response,"text",b"")):
            return response,None
        try:payload=response.json()
        except (ValueError,requests.exceptions.JSONDecodeError) as error:
            raise RuntimeError(f"WooCommerce retornou JSON inválido em {method} {path}") from error
        return response,payload
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._request_response(method,path,**kwargs)[1]
    def get_product(self, product_id: int) -> dict[str,Any]: return self._request("GET",f"/products/{product_id}")
    def get_product_fresh(self, product_id: int) -> dict[str,Any]:
        return self._request("GET",f"/products/{product_id}",params={"context":"edit","_crapscraper_fresh":uuid.uuid4().hex},headers={"Cache-Control":"no-cache"})
    def check_connection(self) -> dict[str, Any]:
        payload=self._request("GET","/products",params={"per_page":1,"page":1})
        return {"ok":isinstance(payload,list),"readable":isinstance(payload,list),**self.last_request_diagnostic,"trust_env":bool(self.session.trust_env)}
    @staticmethod
    def _response_cache(response: Any) -> dict[str,Any]:
        headers=getattr(response,"headers",{}) or {}
        return {key:headers.get(key) for key in ("Cache-Control","Age","X-Cache","X-LiteSpeed-Cache","Server")}
    def set_version(self, product_id: int, version: str) -> dict[str,Any]:
        requested=normalize_version(version)
        if not requested:raise ValueError("pt_versao solicitado está vazio")
        product=self.get_product_fresh(product_id);before=version_metadata(product)
        evidence={"method":"PUT","endpoint":f"/products/{int(product_id)}","product_id":int(product_id),"previous_pt_versao":before.get("value","") if before["status"]=="single" else None,"requested_pt_versao":requested,"before":before,"payload":None,"http_status":None,"put":None,"gets":[],"confirmation_status":"preparing"}
        if int(product.get("id") or 0)!=int(product_id):
            evidence["confirmation_status"]="wrong_product_before_put"
            raise VersionPersistenceError("WooCommerce retornou produto diferente antes da escrita",evidence)
        if before["status"]=="duplicate":
            evidence["confirmation_status"]="duplicate_before_put"
            raise VersionPersistenceError("pt_versao duplicado; escrita bloqueada para não atualizar o registro incorreto",evidence)
        item={"key":"pt_versao","value":requested}
        if before["status"]=="single":
            if before["meta_id"] is None:
                evidence["confirmation_status"]="missing_meta_id_before_put"
                raise VersionPersistenceError("pt_versao existente não possui meta ID editável",evidence)
            item={"id":before["meta_id"],**item}
        payload={"meta_data":[item]};evidence["payload"]=payload
        response,body=self._request_response("PUT",f"/products/{int(product_id)}",json=payload,headers={"Content-Type":"application/json","Cache-Control":"no-cache"})
        evidence["http_status"]=int(response.status_code);evidence["put_cache"]=self._response_cache(response)
        if body is None:
            evidence["put"]={"status":"body_absent","count":None,"entries":[]};evidence["confirmation_status"]="put_body_absent"
            return evidence
        if not isinstance(body,dict):
            evidence["put"]={"status":"invalid","count":None,"entries":[]};evidence["confirmation_status"]="put_json_invalid"
            raise VersionPersistenceError("WooCommerce retornou estrutura inválida no PUT de pt_versao",evidence)
        returned=version_metadata(body);evidence["put"]={"product_id":body.get("id"),**returned}
        if int(body.get("id") or 0)!=int(product_id):
            evidence["confirmation_status"]="wrong_product_in_put"
            raise VersionPersistenceError("WooCommerce retornou produto diferente no PUT de pt_versao",evidence)
        if returned["status"]=="duplicate":
            evidence["confirmation_status"]="duplicate_in_put"
            raise VersionPersistenceError("PUT retornou pt_versao duplicado",evidence)
        if returned["status"]!="single" or normalize_version(returned["value"])!=requested:
            evidence["confirmation_status"]="put_diverged"
            # O corpo do PUT é a primeira evidência, mas não autoriza um
            # rollback prematuro. O executor ainda fará leituras frescas e
            # limitadas para distinguir resposta anômala de não persistência.
            return evidence
        evidence["confirmation_status"]="put_confirmed"
        return evidence
    def confirm_version(self, product_id: int, version: str) -> dict[str,Any]:
        expected=normalize_version(version);gets=[]
        for number,delay in enumerate(self.confirmation_delays,1):
            if delay>0:self.sleeper(delay)
            response,product=self._request_response("GET",f"/products/{int(product_id)}",params={"context":"edit","_crapscraper_fresh":uuid.uuid4().hex},headers={"Cache-Control":"no-cache"})
            metadata=version_metadata(product) if isinstance(product,dict) else {"status":"invalid","count":0,"entries":[],"meta_id":None,"value":""}
            observed=metadata.get("value") if metadata["status"]=="single" else metadata["status"]
            item={"number":number,"http_status":int(response.status_code),"product_id":product.get("id") if isinstance(product,dict) else None,"observed_pt_versao":observed,"cache_busted":True,"cache":self._response_cache(response),**metadata};gets.append(item)
            if metadata["status"]=="duplicate":break
            if isinstance(product,dict) and int(product.get("id") or 0)==int(product_id) and metadata["status"]=="single" and normalize_version(metadata["value"])==expected:
                return {"expected_pt_versao":expected,"observed_pt_versao":normalize_version(metadata["value"]),"gets":gets,"confirmation_status":"confirmed"}
        observed=gets[-1].get("observed_pt_versao") if gets else "ausente"
        evidence={"method":"GET","endpoint":f"/products/{int(product_id)}","product_id":int(product_id),"requested_pt_versao":expected,"expected_pt_versao":expected,"observed_pt_versao":observed,"gets":gets,"confirmation_status":"duplicate" if gets and gets[-1].get("status")=="duplicate" else "diverged"}
        raise VersionPersistenceError(f"Validação final do pt_versao divergiu. Esperado: {expected}. Encontrado: {observed}.",evidence)
    def prepare_job(self, job: dict[str,Any]) -> None:
        variations=self._request("GET",f"/products/{int(job['woo_product_id'])}/variations",params={"per_page":100})
        files=set()
        for variation in variations:
            for download in variation.get("downloads") or []:
                raw=str(download.get("file") or "")
                path=urlparse(raw).path
                if not path.lower().endswith(".zip"):continue
                name=os.path.basename(unquote(path).replace("\\","/"))
                if name:files.add(name)
        if len(files)!=1: raise RuntimeError(f"WooCommerce deve apontar para exatamente um ZIP; encontrados: {sorted(files)}")
        job["target_filename"]=files.pop();job["woocommerce_version_scope"]={"write_target":"parent","parent_product_id":int(job["woo_product_id"]),"variations_read_only":[{"variation_id":int(variation.get("id") or 0),"parent_id":int(variation.get("parent_id") or 0),"pt_versao":version_metadata(variation)} for variation in variations]}


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
    @staticmethod
    def _sftp_sha(sftp,path):
        digest=hashlib.sha256()
        with sftp.open(path,"rb") as stream:
            while True:
                chunk=stream.read(1024*1024)
                if not chunk:break
                digest.update(chunk)
        return digest.hexdigest()
    def _artifacts(self,job):
        name=os.path.basename(str(job["target_filename"]));job_id=str(job["job_id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",job_id):raise ValueError("job_id invalido para o helper")
        if not name or len(name)>204 or name in {".",".."} or "\x00" in name or "/" in name or "\\" in name or not name.lower().endswith(".zip"):raise ValueError("Nome ZIP invalido para o helper")
        prefix=f"{name}.crapscraper.{job_id}"
        return {"production":f"{self.root}/{name}","upload":f"{self.root}/{prefix}.upload","new":f"{self.root}/{prefix}.new","backup":f"{self.root}/{prefix}.bak"}
    def _helper(self,client,operation,job,*,old_sha="",new_sha=""):
        artifacts=self._artifacts(job);name=os.path.basename(artifacts["production"]);job_id=str(job["job_id"])
        def sha(value):
            normalized=str(value or "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}",normalized):raise ValueError("SHA-256 invalido para o helper")
            return normalized
        args=["sudo","-n","-u","plugi2090","/usr/local/sbin/crapscraper-zip-helper",operation,"--file",name,"--job-id",job_id]
        if operation=="backup":args += ["--expected-sha256",sha(old_sha)]
        elif operation=="prepare":args += ["--expected-new-sha256",sha(new_sha)]
        elif operation=="install":args += ["--expected-old-sha256",sha(old_sha),"--expected-new-sha256",sha(new_sha)]
        elif operation=="rollback":args += ["--expected-sha256",sha(old_sha)]
        else:raise ValueError("Operacao do helper nao autorizada")
        _stdin,stdout,stderr=client.exec_command(shlex.join(args),timeout=90);status=stdout.channel.recv_exit_status();raw=stdout.read().decode("utf-8","replace");failure=stderr.read().decode("utf-8","replace").strip()
        if status!=0:raise RuntimeError("Helper remoto recusou a operacao: "+(failure or raw.strip() or "falha sem detalhe"))
        try:result=json.loads(raw)
        except json.JSONDecodeError as error:raise RuntimeError("Helper remoto retornou resposta invalida") from error
        if not isinstance(result,dict) or result.get("ok") is not True:raise RuntimeError("Helper remoto nao confirmou sucesso")
        return result
    def backup(self,job,attempt_dir):
        backup=attempt_dir/"backup"/os.path.basename(self._remote(job));backup.parent.mkdir(parents=True,exist_ok=True);client,sftp=self._connect()
        try:
            sftp.get(self._remote(job),str(backup));old_sha=hashlib.sha256(backup.read_bytes()).hexdigest();remote_backup=self._artifacts(job)["backup"]
            try:existing_sha=self._sftp_sha(sftp,remote_backup)
            except FileNotFoundError:existing_sha=""
            except OSError as error:
                if getattr(error,"errno",None)==2:existing_sha=""
                else:raise
            if existing_sha and existing_sha!=old_sha:raise RuntimeError("Backup remoto existente diverge do ZIP atual; retry bloqueado")
            if not existing_sha:self._helper(client,"backup",job,old_sha=old_sha)
        finally:sftp.close();client.close()
        return backup
    def install(self,job,artifact,backup):
        artifacts=self._artifacts(job);temporary=artifacts["upload"];old_sha=hashlib.sha256(Path(backup).read_bytes()).hexdigest();new_sha=hashlib.sha256(Path(artifact).read_bytes()).hexdigest();client,sftp=self._connect()
        try:
            # O helper roda como o usuario dono do repositorio, enquanto o
            # upload SFTP pertence a conta de transporte. 0644 e o contrato do
            # staging canonico: permite a leitura controlada sem conceder
            # escrita ao helper sobre o arquivo recebido.
            sftp.put(str(artifact),temporary);sftp.chmod(temporary,0o644)
            self._helper(client,"prepare",job,new_sha=new_sha)
            self._helper(client,"install",job,old_sha=old_sha,new_sha=new_sha)
        finally:
            try:sftp.remove(temporary)
            except OSError:pass
            sftp.close();client.close()
    def rollback(self,job,backup):
        old_sha=hashlib.sha256(Path(backup).read_bytes()).hexdigest();client,sftp=self._connect()
        try:self._helper(client,"rollback",job,old_sha=old_sha)
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