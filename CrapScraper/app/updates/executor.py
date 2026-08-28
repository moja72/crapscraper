from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.configuration import parse_update_execution_allowed_product_ids
from app.updates.adapters import Installer, WooCommerceGateway, WooCommerceRequestError, WooGateway, build_installer, product_version
from app.updates.logging import safe_message
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
                 allowed_product_ids: frozenset[int]|None=None):
        self.repository=repository;self.sources=sources or SourceRegistry();self.woo=woo or WooCommerceGateway();self.installer=installer or build_installer()
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
        backup=None;original_version="";critical=False;woocommerce_changed=False;artifact_sha="";stage="validating"
        def progress(next_stage: str, message: str) -> None:
            nonlocal stage;stage=next_stage;self.repository.progress(job_id,attempt_id,next_stage,message)
        try:
            progress("validating",f"Validando {job['product_name']} (Woo #{job['woo_product_id']}).")
            if int(job["woo_product_id"])<=0 or not job["source_url"] or not job["source_version"]: raise ValueError("Job incompleto: produto, URL e versão são obrigatórios")
            self._authorize(job)
            check_storage=getattr(self.installer,"check",None)
            if callable(check_storage):
                storage_check=check_storage()
                if not storage_check.get("ok"):raise RuntimeError("Armazenamento de destino indisponível: "+str(storage_check.get("message") or "não configurado"))
            product=self.woo.get_product(int(job["woo_product_id"]));original_version=product_version(product)
            target_version=str(job["source_version"] or "")
            if original_version==target_version or version_key(original_version)>version_key(target_version):
                message=f"Destino já está na versão {original_version}; aprovação {target_version} não será aplicada para evitar downgrade." if version_key(original_version)>version_key(target_version) else f"Destino já está na versão {original_version}; nenhuma escrita necessária."
                progress("already_current",message)
                self.repository.finish(job_id,attempt_id,success=True,stage="already_current")
                return {"ok":True,"job_id":job_id,"already_current":True}
            prepare_job=getattr(self.woo,"prepare_job",None)
            if prepare_job: prepare_job(job)
            source=self.sources.get(job["source_kind"])
            if source.kind!=job["source_kind"]: raise RuntimeError("A fonte resolvida diverge da fonte imutável aprovada")
            progress("authenticating",f"Validando autenticação do {source.display_name}.");source.validate_authentication()
            confirmed=source.confirm_version(job)
            if confirmed!=job["source_version"]: raise ValueError(f"Versão da fonte divergiu da aprovação: {confirmed} != {job['source_version']}")
            progress("downloading",f"Baixando versão {confirmed} exclusivamente do {source.display_name}.")
            artifact=source.download(job,attempt_dir/"artifact.zip");artifact_sha=artifact.sha256
            try:
                from app.credits import invalidate_credit_cache
                invalidate_credit_cache(source.kind)
            except ImportError:
                pass
            if not artifact.path.is_file() or artifact.path.stat().st_size <= 0:
                raise RuntimeError("Artefato de atualização ausente ou vazio")
            if not zipfile.is_zipfile(artifact.path):
                raise RuntimeError("Artefato de atualização não é um ZIP válido")
            progress("staging",f"Download concluído e ZIP validado: {artifact.path.name} ({artifact.size} bytes, SHA-256 {artifact.sha256[:12]}…).")
            backup=self.installer.backup(job,attempt_dir);progress("backing_up",f"Arquivo atual preservado em backup: {getattr(backup,'name','backup')}.")
            critical=True;progress("installing",f"Substituindo o arquivo de destino por {artifact.path.name}.");self.installer.install(job,artifact.path,backup)
            if not self.installer.validate(job,artifact.sha256): raise RuntimeError("Validação SHA-256 do destino falhou")
            progress("verifying_artifact","Substituição física confirmada pelo SHA-256 do destino.")
            progress("updating_woocommerce",f"Atualizando pt_versao para {confirmed}.");self.woo.set_version(int(job["woo_product_id"]),confirmed);woocommerce_changed=True
            final=self.woo.get_product(int(job["woo_product_id"]));
            if product_version(final)!=confirmed: raise RuntimeError("Validação final do pt_versao divergiu")
            progress("completed","Atualização concluída e validada.");self.repository.finish(job_id,attempt_id,success=True,stage="completed",sha256=artifact_sha)
            return {"ok":True,"job_id":job_id,"attempt_id":attempt_id,"sha256":artifact_sha}
        except Exception as exc:
            if isinstance(exc,SourceFailure): error=exc.error
            elif isinstance(exc,WooCommerceRequestError):
                layer="WooCommerce/WordPress" if exc.content_type.lower().startswith("application/json") else "servidor/proxy anterior ao WooCommerce"
                error=UpdateError(message=str(exc),technical_message=f"HTTP {exc.status}; método={exc.method}; endpoint={exc.endpoint}; código_rest={exc.code or 'não informado'}; content_type={exc.content_type or 'não informado'}; server={exc.server or 'não informado'}; redirects={exc.redirects or []}; URL_final={exc.final_url or 'não informado'}",code="woocommerce_http_error",stage=stage,source="WooCommerce",http_status=exc.status,final_url=exc.final_url,content_type=exc.content_type,diagnosis=f"Resposta 4xx/5xx gerada por {layer}; a aplicação não recebeu JSON REST válido.",recoverable=exc.status in {408,409,429,500,502,503,504})
            else: error=UpdateError(message=safe_message(exc),technical_message=repr(exc),code="execution_failed",stage=stage,source=job.get("source_name",job.get("source_kind","")),recoverable=not isinstance(exc,(PermissionError,ValueError)))
            error.job_id=job_id;error.attempt_id=attempt_id
            if critical and backup is not None:
                try:
                    progress("rolling_back","Falha após alteração crítica; iniciando rollback.")
                    if woocommerce_changed and original_version: self.woo.set_version(int(job["woo_product_id"]),original_version)
                    self.installer.rollback(job,backup);progress("rolled_back","Rollback concluído.")
                except Exception as rollback_error:
                    error.diagnosis=(error.diagnosis+" "+f"Rollback falhou: {safe_message(rollback_error)}").strip();error.recoverable=False;stage="rollback_required"
            self.repository.finish(job_id,attempt_id,success=False,stage=stage,error=error.to_dict(),sha256=artifact_sha)
            return {"ok":False,"job_id":job_id,"attempt_id":attempt_id,"error":error.to_dict()}
        finally:
            # Somente temporários desta tentativa; backups/histórico continuam persistidos.
            artifact=attempt_dir/"artifact.zip"
            artifact.unlink(missing_ok=True)
