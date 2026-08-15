from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from app import settings
from app.integrations.ssh_helper import RestrictedSSHHelperClient, SSHHelperRequest
from app.integrations.wordpress import IntegrationError, WriteOperationDisabledError
from app.integrations.woocommerce import pt_versao, variation_downloads
from app.operations.execution_plan import SAFE_RELATIONSHIPS, VERSION_RE, evaluate_preconditions
from app.operations.models import JobState, OperationalJob, record_execution_outcome
from app.operations.update_logging import UpdateLogger
from app.integrations.woocommerce_version import VersionConfirmationError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def authorize_update_execution(job: OperationalJob, plan: Mapping[str, Any], confirmation: str,
                               *, enabled: bool, allowed_product_ids: frozenset[int]) -> None:
    """Autorização puramente local; não cria conexão ou cliente write-capable."""
    if not enabled:
        raise WriteOperationDisabledError("Execução real bloqueada para homologação")
    if allowed_product_ids and job.woo_product_id not in allowed_product_ids:
        raise PermissionError(
            f"Produto WooCommerce #{job.woo_product_id} não está autorizado para execução real."
        )
    if confirmation != f"EXECUTAR {job.woo_product_id}":
        raise PermissionError("Confirmação individual incorreta")
    if plan.get("job_id") != job.job_id or int(plan.get("woo_product_id") or 0) != job.woo_product_id:
        raise PermissionError("Plano não pertence ao job informado")
    if not plan.get("plan_id") or plan.get("ready") is not True:
        raise ValueError("Plano válido e pronto é obrigatório")
    if job.relationship not in SAFE_RELATIONSHIPS:
        raise ValueError("Relacionamento inseguro")


class ControlledUpdateExecutor:
    """Executor transacional de um unico job, com dependencias injetaveis."""

    def __init__(self, woo: Any, storage: Any, staging: Any, helper: RestrictedSSHHelperClient,
                 version_writer: Any, *, enabled: bool = settings.UPDATE_EXECUTION_ENABLED,
                 allowed_product_ids: frozenset[int] = settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS,
                 logger: Callable[[str], None] | None = None,
                 fault: Callable[[str], None] | None = None) -> None:
        self.woo, self.storage, self.staging = woo, storage, staging
        self.helper, self.version_writer = helper, version_writer
        self.enabled, self.allowed_product_ids = bool(enabled), frozenset(allowed_product_ids)
        self.log = logger or (lambda _message: None)
        self.fault = fault or (lambda _stage: None)

    def authorize(self, job: OperationalJob, plan: Mapping[str, Any], confirmation: str) -> None:
        authorize_update_execution(job, plan, confirmation, enabled=self.enabled,
                                   allowed_product_ids=self.allowed_product_ids)

    def _log_version_evidence(self, evidence: Mapping[str, Any]) -> None:
        self.log(f"ℹ WooCommerce PUT HTTP {evidence.get('http_status', 'desconhecido')}")
        put_value = evidence.get("put_pt_versao")
        self.log(f"ℹ PUT retornou pt_versao: {put_value if put_value is not None else 'ausente'}")
        self.log(f"ℹ meta id PUT: {evidence.get('put_meta_id') if evidence.get('put_meta_id') is not None else 'ausente'}")
        self.log("🔎 Confirmando pt_versao via GET")
        if "get_pt_versao" in evidence:
            self.log(f"🔎 GET retornou pt_versao: {evidence.get('get_pt_versao')}")
            self.log(f"ℹ meta id GET: {evidence.get('get_meta_id')}")

    def _observed(self, job: OperationalJob, plan: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        product_reader = getattr(self.woo, "get_product_fresh", self.woo.get_product)
        variations_reader = getattr(self.woo, "list_variations_fresh", self.woo.list_variations)
        product = product_reader(job.woo_product_id)
        variations = list(variations_reader(job.woo_product_id))
        entries = [{"variation_id": int(v.get("id") or 0), **d}
                   for v in variations for d in variation_downloads(v)
                   if v.get("downloadable")]
        local = Path(str(plan["new_zip"]["local_staging_path"]))
        observed = {
            "woo_product_id": int(product.get("id") or 0),
            "pt_versao": pt_versao(product),
            "remote_zip_sha256": self.storage.sha256(plan["current_zip"]["remote_path"]),
            "relationship": job.relationship,
            "local_zip_exists": local.is_file(),
            "local_zip_sha256": _sha256(local) if local.is_file() else "",
            "effective_source_version": job.effective_source_version,
        }
        expected_ids = sorted(int(v) for v in plan["woocommerce"]["variation_ids"])
        actual_ids = sorted({int(item["variation_id"]) for item in entries})
        def semantic(items: Any) -> list[tuple[int, str, str, str]]:
            return sorted((int(item.get("variation_id") or 0), str(item.get("id") or ""),
                           str(item.get("name") or ""), str(item.get("file") or ""))
                          for item in items)
        if (actual_ids != expected_ids or
                semantic(entries) != semantic(plan["woocommerce"]["original_downloads"])):
            observed["downloads_variations"] = False
        return observed, entries

    def execute(self, job: OperationalJob, plan: Mapping[str, Any], confirmation: str) -> dict[str, Any]:
        self.authorize(job, plan, confirmation)
        changed_zip = changed_version = False
        version_plan = None
        file_name = PurePosixPath(plan["current_zip"]["remote_path"]).name
        old_sha, new_sha = plan["current_zip"]["sha256"], plan["new_zip"]["sha256"]
        job.executing_at = _now()
        job.execution_error = ""
        job.set_state(JobState.EXECUTING)
        self.log(f"🚀 Iniciando execução: {job.name}")
        try:
            self.log(f"🔎 Revalidando WooCommerce #{job.woo_product_id}")
            observed, _entries = self._observed(job, plan)
            checked = evaluate_preconditions(plan, observed)
            if not checked["ready"] or observed.get("downloads_variations") is False:
                job.set_state(JobState.BLOCKED, checked["message"])
                raise ValueError(checked["message"])
            self.log(" Preconditions confirmadas")
            version_plan = self.version_writer.prepare(
                job.woo_product_id, plan["site_version"], plan["effective_source_version"]
            )

            self.log("📦 Criando backup do ZIP atual")
            backup_path = plan["backup"]["path"]
            if self.storage.exists(backup_path):
                if self.storage.sha256(backup_path) != old_sha:
                    raise IntegrationError("Backup existente diverge do SHA original; retry bloqueado")
                self.log("ℹ Backup existente deste job reutilizado após validação")
            else:
                self.helper.invoke(SSHHelperRequest(
                    "backup", file_name, job.job_id, expected_sha256=old_sha
                ))
            if self.storage.sha256(backup_path) != old_sha:
                raise IntegrationError("SHA-256 do backup divergiu")
            self.log(" Backup criado")
            self.log(" SHA-256 do backup confirmado")
            job.last_completed_step = "backup_validated"
            self.fault("after_backup")

            self.log("📦 Enviando novo ZIP para staging remoto")
            upload_path = plan["remote_staging"]["upload_path"]
            if self.staging.exists(upload_path):
                if self.staging.sha256(upload_path) != new_sha:
                    raise IntegrationError("Staging existente diverge do novo ZIP; retry bloqueado")
                self.log("ℹ Staging existente deste job reutilizado após validação")
            else:
                with Path(plan["new_zip"]["local_staging_path"]).open("rb") as source:
                    upload_path = self.staging.upload_staging(source)
            self.staging.chmod_staging_upload(upload_path)
            if self.staging.sha256(upload_path) != new_sha:
                raise IntegrationError("SHA-256 do staging remoto divergiu")
            job.last_completed_step = "staging_upload_validated"
            self.helper.invoke(SSHHelperRequest("prepare", file_name, job.job_id,
                                               expected_new_sha256=new_sha))
            self.log(" Staging remoto validado")
            self.fault("after_staging")

            result = self.helper.invoke(SSHHelperRequest(
                "install", file_name, job.job_id, expected_old_sha256=old_sha,
                expected_new_sha256=new_sha,
            ))
            changed_zip = True
            job.last_completed_step = "production_zip_installed"
            if self.storage.sha256(plan["current_zip"]["remote_path"]) != new_sha:
                raise IntegrationError("SHA-256 do ZIP de produção divergiu")
            self.log(" ZIP de produção validado")
            self.fault("after_install")

            self.log(f"🔄 Atualizando pt_versao: {plan['site_version']} → {plan['effective_source_version']}")
            # A escrita pode ter ocorrido mesmo se a confirmação remota falhar.
            # A partir daqui o rollback sempre tenta restaurar o valor original.
            changed_version = True
            try:
                version_evidence = self.version_writer.apply_and_confirm(version_plan)
            except VersionConfirmationError as version_error:
                job.version_write_evidence = dict(version_error.evidence)
                self._log_version_evidence(version_error.evidence)
                raise
            job.version_write_evidence = dict(version_evidence)
            self._log_version_evidence(version_evidence)
            self.log(f" pt_versao confirmado: {plan['effective_source_version']}")
            job.last_completed_step = "pt_versao_updated"
            self.fault("after_pt_versao")

            self.log("🔎 Revalidando WooCommerce")
            final, _entries = self._observed(job, plan)
            if (final["pt_versao"] != plan["effective_source_version"] or
                    final["remote_zip_sha256"] != new_sha or
                    final.get("downloads_variations") is False):
                raise IntegrationError("Validação final divergiu")
            job.completed_at = _now()
            job.set_state(JobState.COMPLETED, "Atualização individual concluída")
            record_execution_outcome(job, dict(plan), "completed")
            self.log(" Atualização concluída")
            return {"ok": True, "state": job.state.value, "backup_path": plan["backup"]["path"],
                    "helper": dict(result), "completed_at": job.completed_at}
        except Exception as error:
            safe_error = UpdateLogger.sanitize(error)
            job.execution_error = safe_error
            self.log(f" Falha na execução: {safe_error}")
            if changed_zip:
                self.log(" Falha após início da alteração")
                self.log(" Iniciando rollback")
                try:
                    if changed_version and version_plan is not None:
                        try:
                            rollback_evidence = self.version_writer.apply_and_confirm(version_plan, rollback=True)
                        except VersionConfirmationError as version_error:
                            job.version_write_evidence = {"apply": dict(job.version_write_evidence),
                                                          "rollback": dict(version_error.evidence)}
                            self._log_version_evidence(version_error.evidence)
                            raise
                        job.version_write_evidence = {"apply": dict(job.version_write_evidence),
                                                      "rollback": dict(rollback_evidence)}
                        self._log_version_evidence(rollback_evidence)
                        self.log(" pt_versao restaurado e confirmado")
                    self.helper.invoke(SSHHelperRequest(
                        "rollback", file_name, job.job_id, expected_sha256=old_sha
                    ))
                    if self.storage.sha256(plan["current_zip"]["remote_path"]) != old_sha:
                        raise IntegrationError("Rollback não restaurou SHA original")
                    self.log(" ZIP original restaurado")
                    job.set_state(JobState.ROLLED_BACK, "Rollback automático concluído")
                    record_execution_outcome(job, dict(plan), "rolled_back")
                    self.log(" Rollback concluído")
                except Exception as rollback_error:
                    job.set_state(JobState.ROLLBACK_REQUIRED, f"Rollback automático falhou: {rollback_error}")
                    self.log(f" Falha no rollback: {rollback_error}")
                    record_execution_outcome(job, dict(plan), "rollback_required")
            elif job.state != JobState.BLOCKED:
                job.set_state(JobState.ERROR, f"Falha antes da alteração de produção: {safe_error}")
                self.log("ℹ Falha ocorreu antes da troca do ZIP de produção; rollback não necessário.")
                record_execution_outcome(job, dict(plan), "failed")
            raise
