from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from app.integrations.ssh_helper import SSHHelperRequest
from app.integrations.wordpress import IntegrationError
from app.operations.models import JobState
from app.operations.preparation import UpdatePreparationService
from app.operations.real_executor import ControlledUpdateExecutor

_INSTALLED = False
_BASE_PREPARE: Callable[..., Any] | None = None
_BASE_EXECUTE: Callable[..., Any] | None = None
_PRODUCTION_STEPS = frozenset({"production_zip_installed", "pt_versao_updated"})


def _patched_prepare(self: UpdatePreparationService, job: Any) -> Any:
    """Faz a preparação ler WooCommerce sem cache, como o executor já faz.

    O executor revalida produto e variações por URLs únicas. Se a preparação usa
    leituras potencialmente cacheadas, um plano pode nascer obsoleto e ser
    bloqueado imediatamente na execução. Este wrapper mantém toda a preparação
    atual, trocando somente os dois leitores quando as variantes fresh existem.
    """
    if _BASE_PREPARE is None:
        raise RuntimeError("prepare base indisponível")

    woo = self.woo
    original_product = getattr(woo, "get_product", None)
    original_variations = getattr(woo, "list_variations", None)
    fresh_product = getattr(woo, "get_product_fresh", None)
    fresh_variations = getattr(woo, "list_variations_fresh", None)

    replaced_product = callable(original_product) and callable(fresh_product)
    replaced_variations = callable(original_variations) and callable(fresh_variations)

    if replaced_product:
        woo.get_product = fresh_product
    if replaced_variations:
        woo.list_variations = fresh_variations

    try:
        if replaced_product or replaced_variations:
            self.logger("🔄 Revalidando WooCommerce sem cache antes de preparar o plano")
        return _BASE_PREPARE(self, job)
    finally:
        if replaced_product:
            woo.get_product = original_product
        if replaced_variations:
            woo.list_variations = original_variations


def _cleanup_retry_temporaries(
    self: ControlledUpdateExecutor,
    job: Any,
    plan: Mapping[str, Any],
) -> None:
    """Remove somente temporários exatos deste job antes de uma nova tentativa.

    Nunca toca em produção nem no backup. Se a execução já alcançou produção,
    a recuperação continua seguindo as regras de rollback existentes.
    """
    if job.state == JobState.ROLLBACK_REQUIRED:
        return
    if str(getattr(job, "last_completed_step", "") or "") in _PRODUCTION_STEPS:
        return

    current_zip = dict(plan.get("current_zip") or {})
    new_zip = dict(plan.get("new_zip") or {})
    remote_staging = dict(plan.get("remote_staging") or {})
    remote_path = str(current_zip.get("remote_path") or "")
    file_name = PurePosixPath(remote_path).name if remote_path else ""
    expected_new_sha = str(new_zip.get("sha256") or "").lower()
    upload_path = str(remote_staging.get("upload_path") or "")
    prepared_path = str(remote_staging.get("prepared_path") or "")

    if not file_name or not expected_new_sha:
        return

    if upload_path and self.staging.exists(upload_path):
        observed_upload_sha = str(self.staging.sha256(upload_path) or "").lower()
        if observed_upload_sha != expected_new_sha:
            self.log(
                "♻ Staging .upload residual pertence a este job, mas possui SHA diferente; "
                "removendo temporário antes do novo envio"
            )
            self.helper.invoke(SSHHelperRequest(
                "cleanup", file_name, job.job_id, artifact="upload"
            ))
            if self.staging.exists(upload_path):
                raise IntegrationError("Cleanup do staging .upload não foi confirmado")
            self.log("✅ Staging .upload residual removido com segurança")

    # O helper cria .new a partir de .upload. Esse arquivo nunca é produção e
    # precisa ser recriado em cada retry para não colidir com O_EXCL do helper.
    if prepared_path and self.storage.exists(prepared_path):
        self.log("♻ Removendo staging .new residual deste job antes de recriá-lo")
        self.helper.invoke(SSHHelperRequest(
            "cleanup", file_name, job.job_id, artifact="new"
        ))
        if self.storage.exists(prepared_path):
            raise IntegrationError("Cleanup do staging .new não foi confirmado")
        self.log("✅ Staging .new residual removido com segurança")


def _patched_execute(
    self: ControlledUpdateExecutor,
    job: Any,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    if _BASE_EXECUTE is None:
        raise RuntimeError("execute base indisponível")

    # Autoriza antes de qualquer cleanup remoto. O executor base autoriza de
    # novo, mantendo a defesa original e compatibilidade com outras políticas.
    self.authorize(job, plan, confirmation)
    _cleanup_retry_temporaries(self, job, plan)
    return _BASE_EXECUTE(self, job, plan, confirmation)


def install_update_retry_safety_policy() -> None:
    global _INSTALLED, _BASE_PREPARE, _BASE_EXECUTE
    if _INSTALLED:
        return

    # Instalada depois das políticas anteriores para envolver o comportamento
    # efetivo em uso, sem remover staging reuse nem already-current.
    _BASE_PREPARE = UpdatePreparationService._prepare
    UpdatePreparationService._prepare = _patched_prepare

    _BASE_EXECUTE = ControlledUpdateExecutor.execute
    ControlledUpdateExecutor.execute = _patched_execute
    _INSTALLED = True
