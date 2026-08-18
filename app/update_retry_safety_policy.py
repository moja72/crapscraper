from __future__ import annotations

import shlex
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from app.integrations.ssh_helper import SSHHelperRequest
from app.integrations.wordpress import IntegrationError, sanitize_text
from app.operations.models import JobState
from app.operations.preparation import UpdatePreparationService
from app.operations.real_executor import ControlledUpdateExecutor

_INSTALLED = False
_BASE_PREPARE: Callable[..., Any] | None = None
_BASE_EXECUTE: Callable[..., Any] | None = None
_PRODUCTION_STEPS = frozenset({"production_zip_installed", "pt_versao_updated"})
_SHA256_TIMEOUT_SECONDS = 90


def _remote_sha256(storage: Any, path: str) -> str:
    """Calcula o hash no servidor sem transferir o ZIP inteiro por SFTP.

    O caminho primeiro passa pela mesma validação de confinamento do storage. O
    comando executado é somente leitura e recebe o caminho já resolvido e
    protegido por shlex. Isso evita que a preparação pareça travada enquanto um
    tema grande é baixado apenas para calcular o SHA localmente.
    """
    resolved = storage._resolved_in_root(path, allow_root=False)
    client = getattr(storage, "_client", None)
    if client is None:
        raise IntegrationError("Conexão SSH indisponível para calcular SHA-256 remoto")

    command = "sha256sum -- " + shlex.quote(resolved)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=_SHA256_TIMEOUT_SECONDS)
        raw = stdout.read().decode("utf-8", "replace").strip()
        raw_error = stderr.read().decode("utf-8", "replace").strip()
        channel = getattr(stdout, "channel", None)
        status = channel.recv_exit_status() if channel is not None else 0
    except Exception as error:
        safe = sanitize_text(error, storage.config.username, storage.config.password)
        raise IntegrationError(f"Falha ao calcular SHA-256 remoto: {safe}") from None

    if status != 0:
        detail = sanitize_text(raw_error, storage.config.username, storage.config.password)
        raise IntegrationError(
            f"sha256sum remoto falhou: {detail}" if detail else
            f"sha256sum remoto retornou status {status}"
        )

    digest = raw.split()[0].lower() if raw else ""
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise IntegrationError("Servidor retornou SHA-256 remoto inválido")
    return digest


def _patch_fast_sha(storage: Any, *, logger: Callable[[str], None] | None = None) -> tuple[Any, bool]:
    """Troca o SHA SFTP pelo SHA executado no host apenas nesta conexão."""
    original = getattr(storage, "sha256", None)
    if not callable(original) or getattr(storage, "_client", None) is None:
        return original, False

    def fast_sha(path: str, *, chunk_size: int = 1024 * 1024) -> str:
        del chunk_size  # compatibilidade com a assinatura original
        if logger is not None:
            name = PurePosixPath(str(path)).name
            logger(f"🔎 Calculando SHA-256 remoto no servidor: {name}")
        digest = _remote_sha256(storage, path)
        if logger is not None:
            logger(f"✅ SHA-256 remoto confirmado: {digest[:12]}…")
        return digest

    storage.sha256 = fast_sha
    return original, True


def _restore_sha(storage: Any, original: Any, replaced: bool) -> None:
    if replaced and callable(original):
        storage.sha256 = original


def _patched_prepare(self: UpdatePreparationService, job: Any) -> Any:
    """Prepara com WooCommerce fresh e hashing remoto eficiente."""
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

    original_sha, replaced_sha = _patch_fast_sha(self.storage, logger=self.logger)
    try:
        if replaced_product or replaced_variations:
            self.logger("🔄 Revalidando WooCommerce sem cache antes de preparar o plano")
        return _BASE_PREPARE(self, job)
    finally:
        _restore_sha(self.storage, original_sha, replaced_sha)
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

    # O executor consulta hashes várias vezes. Faça essas leituras no próprio
    # servidor para que retry e validações não transfiram ZIPs inteiros por SFTP.
    storage_sha, storage_replaced = _patch_fast_sha(self.storage)
    staging_sha, staging_replaced = _patch_fast_sha(self.staging)
    try:
        # Autoriza antes de qualquer cleanup remoto. O executor base autoriza de
        # novo, mantendo a defesa original e compatibilidade com outras políticas.
        self.authorize(job, plan, confirmation)
        _cleanup_retry_temporaries(self, job, plan)
        return _BASE_EXECUTE(self, job, plan, confirmation)
    finally:
        _restore_sha(self.staging, staging_sha, staging_replaced)
        _restore_sha(self.storage, storage_sha, storage_replaced)


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
