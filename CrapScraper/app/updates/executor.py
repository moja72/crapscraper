from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.configuration import parse_update_execution_allowed_product_ids
from app.updates.adapters import Installer, VersionPersistenceError, WooCommerceConnectivityError, WooCommerceGateway, WooCommerceRequestError, WooGateway, build_installer, normalize_version, product_version, version_metadata
from app.updates.logging import safe_message, safe_text
from app.updates.history import UpdateHistorySynchronizer
from app.updates.models import UpdateError
from app.updates.repository import UpdateRepository
from app.updates.sources import SourceFailure, SourceRegistry


def env_enabled(name: str) -> bool: return os.getenv(name,"").strip().lower() in {"1","true","yes","on"}

def version_key(value: str) -> tuple[int,...]:
    import re
    parts=[int(part) for part in re.findall(r"\d+", str(value or ""))]
    while len(parts)>1 and parts[-1]==0: parts.pop()
    return tuple(parts) or (0,)


class UpdateExecutor:
    """Único caminho de execução, usado tanto por jobs individuais quanto por lotes/retries."""
    def __init__(self, repository: UpdateRepository, *, sources: SourceRegistry|None=None, woo: WooGateway|None=None,
                 installer: Installer|None=None, staging_root: Path|None=None, enabled: bool|None=None,
                 allowed_product_ids: frozenset[int]|None=None, history: UpdateHistorySynchronizer|None=None):
        self.repository=repository;self.sources=sources or SourceRegistry();self.woo=woo or WooCommerceGateway();self.installer=installer or build_installer()
        self.history=history or UpdateHistorySynchronizer(repository)
        self.staging_root=staging_root or repository.path.parent/"update_staging"
        self.enabled=env_enabled("SCRAPER_UPDATE_EXECUTION_ENABLED") if enabled is None else enabled
        self.allowed_product_ids=parse_update_execution_allowed_product_ids(os.getenv("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS")) if allowed_product_ids is None else allowed_product_ids

    def _authorize(self, job: dict[str,Any]) -> None:
        if not self.enabled: raise PermissionError("Execução real desabilitada por SCRAPER_UPDATE_EXECUTION_ENABLED")
        if self.allowed_product_ids and int(job["woo_product_id"]) not in self.allowed_product_ids: raise PermissionError(f"Produto WooCommerce #{job['woo_product_id']} não autorizado")

    def execute(self, job_id: str) -> dict[str,Any]:
        job=self.repository.get(job_id)
        if job["state"]=="running": raise ValueError("Job já está em execução")
        attempt=self.repository.begin_attempt(job_id);attempt_id=attempt["attempt_id"]
        attempt_dir=self.staging_root/job_id/attempt_id;attempt_dir.mkdir(parents=True,exist_ok=True)
        backup=None;backup_sha="";original_version="";original_metadata:dict[str,Any]={};critical=False;woocommerce_changed=False;artifact_sha="";stage="validating";version_evidence:dict[str,Any]={};rollback_evidence:dict[str,Any]={}
        def progress(next_stage: str, message: str) -> None:
            nonlocal stage;stage=next_stage;self.repository.progress(job_id,attempt_id,next_stage,message)
        def record_version_evidence(label: str, evidence: dict[str,Any]) -> None:
            if not evidence:return
            before=evidence.get("before") or {};put=evidence.get("put") or {};gets=evidence.get("gets") or []
            previous=evidence.get("previous_pt_versao",before.get("value"));requested=evidence.get("requested_pt_versao") or evidence.get("expected_pt_versao")
            if previous is not None:progress(stage,f"pt_versao antes: {previous if previous!='' else '(ausente)'}.")
            if requested is not None:progress(stage,f"pt_versao solicitado: {requested}.")
            if evidence.get("method")=="PUT":
                progress(stage,f"WooCommerce PUT endpoint={evidence.get('endpoint')}; HTTP={evidence.get('http_status')}; payload={json.dumps(evidence.get('payload'),ensure_ascii=False,sort_keys=True)}.")
                progress(stage,f"PUT retornou produto={put.get('product_id')}; pt_versao={put.get('value') if put.get('status')=='single' else put.get('status')}; entradas={put.get('count')}; meta_id={put.get('meta_id')}.")
            for item in gets:
                progress(stage,f"GET #{item.get('number')} retornou produto={item.get('product_id')}; pt_versao={item.get('observed_pt_versao')}; entradas={item.get('count')}; meta_id={item.get('meta_id')}; cache_busted={item.get('cache_busted')}.")
            progress(stage,f"Diagnóstico pt_versao ({label}): {json.dumps(evidence,ensure_ascii=False,sort_keys=True)}")
        def confirm_version(expected: str) -> dict[str,Any]:
            checker=getattr(self.woo,"confirm_version",None)
            if callable(checker):return dict(checker(int(job["woo_product_id"]),expected) or {})
            reader=getattr(self.woo,"get_product_fresh",None) or self.woo.get_product
            product=reader(int(job["woo_product_id"]));metadata=version_metadata(product);observed=metadata.get("value") if metadata["status"]=="single" else metadata["status"]
            evidence={"method":"GET","endpoint":f"/products/{int(job['woo_product_id'])}","product_id":int(job["woo_product_id"]),"requested_pt_versao":expected,"expected_pt_versao":expected,"observed_pt_versao":observed,"gets":[{"number":1,"product_id":product.get("id"),"observed_pt_versao":observed,"cache_busted":callable(getattr(self.woo,"get_product_fresh",None)),**metadata}],"confirmation_status":"confirmed" if metadata["status"]=="single" and normalize_version(metadata["value"])==normalize_version(expected) else "diverged"}
            if evidence["confirmation_status"]!="confirmed":raise VersionPersistenceError(f"Validação final do pt_versao divergiu. Esperado: {normalize_version(expected)}. Encontrado: {observed}.",evidence)
            return evidence
        try:
            progress("validating",f"Validando {job['product_name']} (Woo #{job['woo_product_id']}).")
            if int(job["woo_product_id"])<=0 or not job["source_url"] or not job["source_version"]: raise ValueError("Job incompleto: produto, URL e versão são obrigatórios")
            self._authorize(job)
            check_storage=getattr(self.installer,"check",None)
            if callable(check_storage):
                storage_check=check_storage()
                if not storage_check.get("ok"):raise RuntimeError("Armazenamento de destino indisponível: "+str(storage_check.get("message") or "não configurado"))
            reader=getattr(self.woo,"get_product_fresh",None) or self.woo.get_product
            product=reader(int(job["woo_product_id"]));original_metadata=version_metadata(product)
            if original_metadata["status"]=="duplicate":
                evidence={"method":"GET","endpoint":f"/products/{int(job['woo_product_id'])}","product_id":int(job["woo_product_id"]),"requested_pt_versao":normalize_version(job["source_version"]),"before":original_metadata,"confirmation_status":"duplicate_before_execution"}
                raise VersionPersistenceError("pt_versao duplicado; execução bloqueada para não validar o registro incorreto",evidence)
            original_version=product_version(product);target_version=normalize_version(job["source_version"])
            if original_version==target_version or version_key(original_version)>version_key(target_version):
                message=f"Destino já está na versão {original_version}; aprovação {target_version} não será aplicada para evitar downgrade." if version_key(original_version)>version_key(target_version) else f"Destino já está na versão {original_version}; nenhuma escrita necessária."
                progress("already_current",message)
                self.repository.finish(job_id,attempt_id,success=True,stage="already_current")
                return {"ok":True,"job_id":job_id,"already_current":True}
            prepare_job=getattr(self.woo,"prepare_job",None)
            if prepare_job: prepare_job(job)
            if job.get("woocommerce_version_scope"):
                progress("validating","Escopo pt_versao: escrita somente no produto pai; variações inspecionadas e preservadas: "+json.dumps(job["woocommerce_version_scope"],ensure_ascii=False,sort_keys=True))
            source=self.sources.get(job["source_kind"])
            if source.kind!=job["source_kind"]: raise RuntimeError("A fonte resolvida diverge da fonte imutável aprovada")
            progress("authenticating",f"Validando autenticação do {source.display_name}.")
            access_probe=getattr(source,"validate_access",None)
            if callable(access_probe):
                access=access_probe(job) or {}
                confirmed=str(access.get("version") or source.confirm_version(job))
            else:
                source.validate_authentication();confirmed=source.confirm_version(job)
            if confirmed!=job["source_version"]: raise ValueError(f"Versão da fonte divergiu da aprovação: {confirmed} != {job['source_version']}")
            progress("downloading",f"Baixando versão {confirmed} exclusivamente do {source.display_name}.")
            artifact=source.download(job,attempt_dir/"artifact.zip");artifact_sha=artifact.sha256
            if not artifact.path.is_file() or artifact.path.stat().st_size <= 0:
                raise RuntimeError("Artefato de atualização ausente ou vazio")
            if not zipfile.is_zipfile(artifact.path):
                raise RuntimeError("Artefato de atualização não é um ZIP válido")
            try:
                from app.credits import refresh_credits_after_download
                refresh_credits_after_download(source.kind)
            except ImportError:
                pass
            progress("staging",f"Download concluído e ZIP validado: {artifact.path.name} ({artifact.size} bytes, SHA-256 {artifact.sha256[:12]}…).")
            backup=self.installer.backup(job,attempt_dir)
            if isinstance(backup,(str,Path)) and Path(backup).is_file():backup_sha=hashlib.sha256(Path(backup).read_bytes()).hexdigest()
            if not backup_sha:raise RuntimeError("Backup não forneceu SHA-256 verificável")
            progress("backing_up",f"Arquivo atual preservado em backup: {getattr(backup,'name','backup')} (SHA-256 {backup_sha[:12]}…).")
            critical=True;progress("installing",f"Substituindo o arquivo de destino por {artifact.path.name}.");self.installer.install(job,artifact.path,backup)
            if not self.installer.validate(job,artifact.sha256): raise RuntimeError("Validação SHA-256 do destino falhou")
            progress("verifying_artifact","Substituição física confirmada pelo SHA-256 do destino.")
            progress("updating_woocommerce",f"Atualizando pt_versao para {confirmed}.");woocommerce_changed=True
            try:
                write=dict(self.woo.set_version(int(job["woo_product_id"]),confirmed) or {})
                version_evidence={"write":write};record_version_evidence("PUT",write)
                confirmation=confirm_version(confirmed);version_evidence["confirmation"]=confirmation;record_version_evidence("confirmação",confirmation)
            except VersionPersistenceError as version_error:
                if version_error.evidence:
                    version_evidence.setdefault("failure",dict(version_error.evidence));record_version_evidence("divergência",dict(version_error.evidence))
                combined={"write":version_evidence.get("write",{}),"confirmation":version_evidence.get("confirmation",{}),"failure":version_evidence.get("failure",{})}
                raise VersionPersistenceError(str(version_error),combined) from version_error
            if not self.installer.validate(job,artifact.sha256):raise RuntimeError("Validação final do SHA-256 do destino falhou")
            progress("completed","Atualização concluída e validada.")
            self.repository.finish(job_id,attempt_id,success=True,stage="completed",sha256=artifact_sha,history_event={
                "operation_id":attempt_id,"woo_product_id":int(job["woo_product_id"]),"source":source.display_name,
                "previous_version":original_version,"new_version":confirmed,
            })
            sync=self.history.sync_event(attempt_id)
            if sync.get("confirmed"):
                self.repository.append_log(job_id,attempt_id,f"Histórico WordPress confirmado: Woo #{job['woo_product_id']}; operation_id={attempt_id}.")
            elif sync.get("status")=="not_configured":
                self.repository.append_log(job_id,attempt_id,f"Histórico WordPress pendente: integração não configurada; operation_id={attempt_id}.")
            else:
                self.repository.append_log(job_id,attempt_id,f"Histórico WordPress não confirmado; nova sincronização poderá reutilizar operation_id={attempt_id}.")
            return {"ok":True,"job_id":job_id,"attempt_id":attempt_id,"sha256":artifact_sha,"history_confirmed":bool(sync.get("confirmed"))}
        except Exception as exc:
            if isinstance(exc,SourceFailure): error=exc.error
            elif isinstance(exc,VersionPersistenceError):
                observed=(exc.evidence.get("failure") or exc.evidence).get("observed_pt_versao")
                details={"stage":stage,"product":job.get("product_name"),"woo_product_id":job.get("woo_product_id"),"source":job.get("source_name",job.get("source_kind","")),"attempt_id":attempt_id,"previous_pt_versao":original_version,"requested_pt_versao":normalize_version(job.get("source_version")),"observed_pt_versao":observed,"version_evidence":exc.evidence}
                error=UpdateError(message=str(exc),technical_message=json.dumps(details,ensure_ascii=False,sort_keys=True),code="woocommerce_version_diverged",stage=stage,source="WooCommerce",diagnosis="A escrita ou uma das leituras frescas não confirmou exatamente o pt_versao solicitado.",recoverable=True,details=details)
            elif isinstance(exc,WooCommerceRequestError):
                layer="WooCommerce/WordPress" if exc.content_type.lower().startswith("application/json") else "servidor/proxy anterior ao WooCommerce"
                error=UpdateError(message=str(exc),technical_message=f"HTTP {exc.status}; método={exc.method}; endpoint={exc.endpoint}; código_rest={exc.code or 'não informado'}; content_type={exc.content_type or 'não informado'}; server={exc.server or 'não informado'}; redirects={exc.redirects or []}; URL_final={exc.final_url or 'não informado'}",code="woocommerce_http_error",stage=stage,source="WooCommerce",http_status=exc.status,final_url=exc.final_url,content_type=exc.content_type,diagnosis=f"Resposta 4xx/5xx gerada por {layer}; a aplicação não recebeu JSON REST válido.",recoverable=exc.status in {408,409,429,500,502,503,504})
            elif isinstance(exc,WooCommerceConnectivityError):
                details={"stage":stage,"host":exc.host,"error_type":exc.error_type,"attempts":exc.attempts,"method":exc.method,"endpoint":exc.endpoint,"original_exception":exc.original_exception}
                error=UpdateError(message="Falha de conexão com WooCommerce.",technical_message=json.dumps(details,ensure_ascii=False,sort_keys=True),code=exc.error_type,stage=stage,source="WooCommerce",diagnosis=exc.diagnosis,recoverable=True,details=details)
            else: error=UpdateError(message=safe_message(exc),technical_message=safe_text(repr(exc),limit=2000),code="execution_failed",stage=stage,source=job.get("source_name",job.get("source_kind","")),recoverable=not isinstance(exc,(PermissionError,ValueError)))
            error.job_id=job_id;error.attempt_id=attempt_id
            if critical and backup is not None:
                progress("rolling_back","Falha após alteração crítica; iniciando rollback validado.")
                rollback_errors=[]
                if woocommerce_changed:
                    try:
                        if original_metadata.get("status")!="single":raise RuntimeError("Rollback de pt_versao ausente exige remoção de metadata, não suportada pelo gateway")
                        rollback_write=dict(self.woo.set_version(int(job["woo_product_id"]),original_version) or {});rollback_evidence["write"]=rollback_write;record_version_evidence("rollback PUT",rollback_write)
                    except Exception as rollback_error:rollback_errors.append("escrita pt_versao: "+safe_message(rollback_error))
                try:self.installer.rollback(job,backup)
                except Exception as rollback_error:rollback_errors.append("restauração ZIP: "+safe_message(rollback_error))
                try:
                    rollback_evidence["zip"]={"expected_sha256":backup_sha,"confirmed":bool(self.installer.validate(job,backup_sha))}
                    if not rollback_evidence["zip"]["confirmed"]:raise RuntimeError("SHA-256 restaurado divergiu do original")
                except Exception as rollback_error:rollback_errors.append("validação ZIP: "+safe_message(rollback_error))
                if original_metadata.get("status")=="single":
                    try:
                        rollback_confirmation=confirm_version(original_version);rollback_evidence["confirmation"]=rollback_confirmation;record_version_evidence("rollback confirmação",rollback_confirmation)
                    except Exception as rollback_error:rollback_errors.append("validação pt_versao: "+safe_message(rollback_error))
                if rollback_errors:
                    error.diagnosis=(error.diagnosis+" Rollback incompleto: "+"; ".join(rollback_errors)).strip();error.recoverable=False;stage="rollback_required"
                else:progress("rolled_back",f"Rollback validado: ZIP SHA-256 {backup_sha[:12]}… e pt_versao {original_version} restaurados.")
                if hasattr(error,"details"):error.details["rollback"]=rollback_evidence
            self.repository.finish(job_id,attempt_id,success=False,stage=stage,error=error.to_dict(),sha256=artifact_sha)
            return {"ok":False,"job_id":job_id,"attempt_id":attempt_id,"error":error.to_dict()}
        finally:
            # Somente temporários desta tentativa; backups/histórico continuam persistidos.
            artifact=attempt_dir/"artifact.zip"
            artifact.unlink(missing_ok=True)
