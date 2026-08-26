from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import urlparse, urlsplit
from uuid import uuid4

from app import settings
import app.operational_history_shared_policy as history_shared
import app.operational_simple_flow_policy as simple_flow
import app.operational_simple_flow_recovery_policy as simple_recovery
import app.operations.execution_plan as execution_plan
import app.operations.runtime as runtime
import app.operations.real_executor as real_executor
import app.web as web
from app.integrations.ssh_helper import SSHDeploymentArtifacts, SSHHelperRequest
from app.integrations.ssh_storage import ControlledWriteSSHStorage
from app.integrations.ultrapack_download import UltrapackDownloader
from app.integrations.wordpress import IntegrationError, sanitize_text
from app.integrations.woocommerce import pt_versao, variation_downloads
from app.integrations.woocommerce_version import VersionConfirmationError
from app.operations.models import JobState, OperationalJob, record_execution_outcome, utc_now_iso
from app.operations.preparation import UpdatePreparationService, UpdatePreview
from app.operations.update_logging import UpdateLogger


_INSTALLED = False
_BASE_PREPARE: Callable[..., Any] | None = None
_BASE_BUILD_PLAN: Callable[..., dict[str, Any]] | None = None
_BASE_EXECUTE: Callable[..., dict[str, Any]] | None = None
_BASE_OBSERVED: Callable[..., Any] | None = None
_BASE_HISTORY_ROWS: Callable[..., list[dict[str, Any]]] | None = None
_BASE_SERVER: Any = None
_BASE_RENDER: Callable[..., str] | None = None

_SAFE_RELATIONSHIPS = frozenset({"safe_auto", "manual_confirmed"})
_EXPECTED_OWNER = "plugi2090"
_EXPECTED_GROUP = "nobody"
_EXPECTED_MODE_TEXT = "-rw-rwxr--"
_RETRYABLE_STATES = {
    JobState.APPROVED,
    JobState.PENDING,
    JobState.PREPARED,
    JobState.PLAN_READY,
    JobState.BLOCKED,
    JobState.FAILED,
    JobState.ERROR,
    JobState.INTERRUPTED,
    JobState.ROLLBACK_REQUIRED,
    JobState.ROLLED_BACK,
    JobState.CANCELED,
}
_RECOVERABLE_VALIDATION_KEYS = {
    "version",
    "ultrapack",
    "current_zip",
    "downloaded",
    "new_zip",
    "backup",
    "already_updated",
}
_MISSING_FILE_MARKERS = (
    "arquivo remoto de produção não existe",
    "arquivo remoto de producao nao existe",
    "no such file",
    "does not exist",
    "not found",
    "required artifact is missing",
)
_AUTH_MARKERS = (
    "http 401",
    "http 403",
    "unauthorized",
    "forbidden",
    "nao autentic",
    "não autentic",
    "sessao expirada",
    "sessão expirada",
    "login",
)
_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "update_retry_recovery_v2.js"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version(value: Any) -> tuple[int, ...] | None:
    text = _clean(value).lstrip("vV")
    parts = text.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    parsed = tuple(int(part) for part in parts)
    while len(parsed) > 1 and parsed[-1] == 0:
        parsed = parsed[:-1]
    return parsed


def _compare(left: Any, right: Any) -> int | None:
    a, b = _version(left), _version(right)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    aa = a + (0,) * (width - len(a))
    bb = b + (0,) * (width - len(b))
    return (aa > bb) - (aa < bb)


def _same_version(left: Any, right: Any) -> bool:
    compared = _compare(left, right)
    return compared == 0 if compared is not None else _clean(left) == _clean(right)


def _validation(preview: UpdatePreview, key: str) -> Any | None:
    return next((item for item in preview.validations if _clean(getattr(item, "key", "")) == key), None)


def _validation_detail(preview: UpdatePreview, key: str) -> str:
    item = _validation(preview, key)
    return _clean(getattr(item, "detail", "")) if item is not None else ""


def _set_validation(
    preview: UpdatePreview,
    key: str,
    *,
    ok: bool,
    label: str | None = None,
    detail: str | None = None,
    level: str | None = None,
) -> None:
    item = _validation(preview, key)
    if item is None:
        return
    item.ok = bool(ok)
    if label is not None:
        item.label = label
    if detail is not None:
        item.detail = detail
    if level is not None:
        item.level = level


def _current_missing(preview: UpdatePreview) -> bool:
    current = dict(preview.current_zip or {})
    if current.get("missing") is True:
        return True
    detail = _clean(current.get("error") or _validation_detail(preview, "current_zip")).lower()
    return bool(detail and any(marker in detail for marker in _MISSING_FILE_MARKERS))


def _source_validation_is_snapshot_only(preview: UpdatePreview) -> bool:
    detail = _validation_detail(preview, "ultrapack").lower()
    if not detail:
        return False
    if any(marker in detail for marker in _AUTH_MARKERS):
        return False
    return (
        "fonte anterior" in detail
        or "comparação" in detail
        or "comparacao" in detail
    )


def _hard_failures(preview: UpdatePreview, *, current_missing: bool) -> list[Any]:
    failures: list[Any] = []
    for item in preview.validations:
        if bool(getattr(item, "ok", False)):
            continue
        key = _clean(getattr(item, "key", ""))
        if key not in _RECOVERABLE_VALIDATION_KEYS:
            failures.append(item)
            continue
        if key == "current_zip" and not current_missing:
            failures.append(item)
    return failures


def _artifact_path(artifact: Mapping[str, Any] | None) -> str:
    data = dict(artifact or {})
    for key in ("path", "local_staging_path", "local_path"):
        value = _clean(data.get(key))
        if value:
            return value
    return ""


def _sha256_local(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reuse_or_download(
    service: UpdatePreparationService,
    job: OperationalJob,
    *,
    target_version: str,
    previous_path: str,
    previous_sha: str,
    previous_version: str,
) -> tuple[dict[str, Any], str]:
    candidate = Path(previous_path) if previous_path else None
    if (
        candidate is not None
        and candidate.is_file()
        and previous_sha
        and previous_version
        and _same_version(previous_version, target_version)
    ):
        try:
            artifact = UltrapackDownloader.validate_zip(candidate, source_url="retry-local-reuse")
            if artifact.sha256.lower() == previous_sha.lower():
                service.logger(
                    f"♻ Reaproveitando ZIP local já validado no retry: {candidate.name} · "
                    f"SHA-256 {artifact.sha256[:12]}…"
                )
                return artifact.to_dict(), target_version
            service.logger("⚠ ZIP local do retry ignorado: SHA-256 diverge do artefato persistido")
        except Exception as error:
            service.logger(f"⚠ ZIP local do retry ignorado: {type(error).__name__}: {error}")

    service.logger("📦 Baixando ZIP da versão efetiva para recuperação")
    local, discovered = service.downloader.download(job.ultrapack_url, service.staging_root / job.job_id)
    found_version = _clean(discovered or target_version)
    return local.to_dict(), found_version


def _make_source_usable_again(
    service: UpdatePreparationService,
    job: OperationalJob,
    preview: UpdatePreview,
    *,
    previous_path: str,
    previous_sha: str,
    previous_version: str,
) -> UpdatePreview:
    versions = preview.versions or {}
    site_version = _clean(versions.get("site_version") or job.plugintema_version)
    source_version = _clean(versions.get("effective_source_version") or job.effective_source_version)
    approved = _clean(versions.get("approved_source_version") or job.approved_source_version)
    order = _compare(source_version, site_version)
    missing = _current_missing(preview)

    if order is None:
        return preview

    # Regra operacional final: nunca fazer downgrade. O snapshot da comparação
    # continua auditável, mas uma fonte ao vivo mais nova que o PluginTema é uma
    # atualização válida mesmo quando ficou abaixo do snapshot antigo.
    if order < 0:
        detail = (
            f"Não atualizado para evitar downgrade: a fonte oferece {source_version}, "
            f"mas o PluginTema já está em {site_version}."
        )
        _set_validation(
            preview,
            "ultrapack",
            ok=False,
            label="Fonte anterior ao PluginTema",
            detail=detail,
            level="error",
        )
        job.execution_error = detail
        job.set_state(JobState.BLOCKED, detail)
        preview.state = job.state.value
        service.logger(f"⛔ {detail}")
        return preview

    source_item = _validation(preview, "ultrapack")
    source_ok = bool(getattr(source_item, "ok", False)) if source_item is not None else True
    if not source_ok:
        if not _source_validation_is_snapshot_only(preview):
            return preview
        if job.relationship not in _SAFE_RELATIONSHIPS:
            return preview
        detail = (
            f"Fonte ao vivo {source_version} é {'igual à' if order == 0 else 'mais nova que a'} "
            f"versão instalada {site_version}. O snapshot aprovado {approved or '-'} será preservado "
            "somente para auditoria; a decisão usa o estado real atual."
        )
        _set_validation(preview, "ultrapack", ok=True, detail=detail, level="info")
        service.logger(f"ℹ {detail}")

    # O pt_versao observado agora é a base real do plano. Isso resolve snapshots
    # antigos sem permitir regressão.
    version_item = _validation(preview, "version")
    if version_item is not None and not bool(getattr(version_item, "ok", False)):
        version_item.ok = True
        version_item.level = "info"
        version_item.detail = (
            f"Base revalidada no WooCommerce: {site_version}; comparação anterior: "
            f"{job.plugintema_version or '-'}; alvo vivo: {source_version}."
        )
        job.plugintema_version = site_version

    if order == 0 and not missing:
        # Mesma versão e arquivo presente: não há escrita útil a fazer. Reabilita
        # a conclusão idempotente do already_current_update_policy.
        marker = _validation(preview, "already_updated")
        if marker is None:
            from app.operations.preparation import ValidationItem
            preview.validations.append(ValidationItem(
                "already_updated",
                "Produto já atualizado",
                True,
                f"PluginTema e fonte estão em {site_version}; nenhuma troca é necessária.",
                "info",
            ))
        else:
            marker.ok = True
            marker.level = "info"
            marker.detail = f"PluginTema e fonte estão em {site_version}; nenhuma troca é necessária."
        for key in ("downloaded", "new_zip"):
            _set_validation(
                preview,
                key,
                ok=True,
                label="Download dispensado",
                detail="Versão já é a mesma e o ZIP de produção existe.",
                level="info",
            )
        if all(bool(getattr(item, "ok", False)) for item in preview.validations):
            job.execution_error = ""
            job.prepared_at = _now()
            job.set_state(JobState.PREPARED, "Produto já atual; conclusão idempotente preparada")
            preview.state = job.state.value
        return preview

    # Se o arquivo de produção sumiu, até uma versão igual deve ser baixada para
    # reconstruir o caminho apontado pelas variações. Para fonte mais nova, o
    # fluxo base normalmente já terá baixado; só fazemos download se necessário.
    hard = _hard_failures(preview, current_missing=missing)
    if hard:
        return preview

    artifact = dict(preview.new_zip or {})
    artifact_ok = bool(_artifact_path(artifact) and _clean(artifact.get("sha256")) and int(artifact.get("entries") or 0) > 0)
    if not artifact_ok:
        try:
            artifact, downloaded_version = _reuse_or_download(
                service,
                job,
                target_version=source_version,
                previous_path=previous_path,
                previous_sha=previous_sha,
                previous_version=previous_version,
            )
        except Exception as error:
            detail = f"Falha ao obter ZIP da fonte para nova tentativa: {error}"
            preview.new_zip = {"error": detail}
            _set_validation(preview, "downloaded", ok=False, detail=detail, level="error")
            _set_validation(preview, "new_zip", ok=False, detail=detail, level="error")
            job.execution_error = detail
            job.set_state(JobState.BLOCKED, detail)
            preview.state = job.state.value
            service.logger(f"❌ {detail}")
            return preview

        downloaded_order = _compare(downloaded_version, site_version)
        if downloaded_order is None or downloaded_order < 0:
            detail = (
                f"Não atualizado para evitar downgrade: o ZIP baixado corresponde a "
                f"{downloaded_version or 'versão desconhecida'}, enquanto o PluginTema está em {site_version}."
            )
            preview.new_zip = {"error": detail}
            _set_validation(preview, "downloaded", ok=False, detail=detail, level="error")
            _set_validation(preview, "new_zip", ok=False, detail=detail, level="error")
            job.execution_error = detail
            job.set_state(JobState.BLOCKED, detail)
            preview.state = job.state.value
            service.logger(f"⛔ {detail}")
            return preview

        if downloaded_version and not _same_version(downloaded_version, source_version):
            service.logger(
                f"ℹ A fonte mudou durante a recuperação: {source_version} → {downloaded_version}. "
                "Será utilizada a versão realmente entregue agora."
            )
            source_version = downloaded_version
            preview.versions["effective_source_version"] = source_version
            preview.versions["ultrapack"] = source_version
            preview.versions["ultrapack_found"] = source_version
            job.effective_source_version = source_version

        preview.new_zip = artifact
        _set_validation(
            preview,
            "downloaded",
            ok=True,
            label="Novo ZIP obtido",
            detail=_artifact_path(artifact),
            level="ok",
        )
        _set_validation(
            preview,
            "new_zip",
            ok=bool(_clean(artifact.get("sha256"))),
            label="Novo ZIP válido",
            detail=_clean(artifact.get("sha256")),
            level="ok",
        )

    if missing:
        path = _clean(preview.physical_path)
        preview.current_zip = {
            **dict(preview.current_zip or {}),
            "path": path,
            "resolved_path": path,
            "missing": True,
            "sha256": "",
        }
        _set_validation(
            preview,
            "current_zip",
            ok=True,
            label="ZIP de produção será reconstruído",
            detail=(
                f"O caminho {path} não existe no servidor. A nova tentativa criará o ZIP "
                "nesse mesmo caminho; em caso de falha posterior, o rollback restaura o estado original sem arquivo."
            ),
            level="info",
        )
        _set_validation(
            preview,
            "backup",
            ok=True,
            label="Rollback para estado ausente preparado",
            detail="Não há ZIP antigo para copiar; o estado original é a ausência do arquivo.",
            level="info",
        )
        # Não permita que o wrapper de already-current descarte a reparação física.
        preview.validations = [
            item for item in preview.validations
            if _clean(getattr(item, "key", "")) != "already_updated"
        ]
        notice = (
            "O ZIP apontado pelo WooCommerce está ausente no servidor. O CrapScraper "
            "vai reconstruí-lo usando a versão atual da fonte antes de confirmar pt_versao."
        )
        if notice not in preview.notices:
            preview.notices.append(notice)
        service.logger(f"🛠 {notice}")

    if all(bool(getattr(item, "ok", False)) for item in preview.validations):
        job.execution_error = ""
        job.prepared_at = _now()
        job.current_sha256 = _clean((preview.current_zip or {}).get("sha256"))
        job.new_sha256 = _clean((preview.new_zip or {}).get("sha256"))
        job.local_staging_path = _artifact_path(preview.new_zip)
        job.effective_source_version = _clean(preview.versions.get("effective_source_version")) or source_version
        job.set_state(JobState.PREPARED, "Preview recuperado e preparado para nova tentativa")
        preview.state = job.state.value
        service.logger("✅ Falha recuperada; preview liberado para gerar plano e executar.")

    return preview


def _patched_prepare(self: UpdatePreparationService, job: OperationalJob) -> UpdatePreview:
    if _BASE_PREPARE is None:
        raise RuntimeError("Preparação base indisponível")

    previous_path = _clean(getattr(job, "local_staging_path", ""))
    previous_sha = _clean(getattr(job, "new_sha256", ""))
    previous_version = _clean(getattr(job, "effective_source_version", ""))
    preview = _BASE_PREPARE(self, job)
    return _make_source_usable_again(
        self,
        job,
        preview,
        previous_path=previous_path,
        previous_sha=previous_sha,
        previous_version=previous_version,
    )


def _metadata_strategy(current: Mapping[str, Any]) -> str:
    owner = _clean(current.get("owner"))
    group = _clean(current.get("group"))
    mode = _clean(current.get("mode"))
    if (owner and owner != _EXPECTED_OWNER) or (group and group != _EXPECTED_GROUP):
        return "controlled_metadata_repair"
    if mode and mode not in {_EXPECTED_MODE_TEXT, "0674", "674"}:
        return "controlled_metadata_repair"
    return "helper_transaction"


def _missing_execution_plan(
    job: OperationalJob,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    log = logger or (lambda _message: None)
    log("🧭 Gerando plano de execução")
    if preview.get("ready") is not True:
        raise ValueError("Plano só pode ser criado quando preview.ready=true")

    versions = dict(preview.get("versions") or {})
    site_version = _clean(versions.get("site_version"))
    approved = _clean(versions.get("approved_source_version"))
    effective = _clean(versions.get("effective_source_version"))
    if not site_version or not approved or not effective:
        raise ValueError("Preview recuperado não possui versões completas")
    if not execution_plan.VERSION_RE.fullmatch(effective):
        raise ValueError("effective_source_version inválida")
    if approved != _clean(job.approved_source_version):
        raise ValueError("Snapshot aprovado do job diverge do preview preparado")
    if job.relationship not in execution_plan.SAFE_RELATIONSHIPS:
        raise ValueError("Vínculo do job não é seguro")

    current = dict(preview.get("current_zip") or {})
    remote_path = _clean(preview.get("physical_path") or current.get("path"))
    if not remote_path:
        raise ValueError("Preview preparado não possui caminho do ZIP de produção")
    remote_name = PurePosixPath(remote_path).name
    artifacts = dict(SSHDeploymentArtifacts(remote_name, job.job_id).paths())

    fresh = dict(preview.get("new_zip") or {})
    local_path = execution_plan._prepared_local_path(job, fresh)
    new_sha = _clean(fresh.get("sha256"))
    entries = int(fresh.get("entries") or 0)
    if not new_sha or entries <= 0:
        raise ValueError("Preview recuperado não possui novo ZIP completo")

    downloads = [dict(item) for item in (preview.get("downloads") or [])]
    variations = [int(item) for item in (preview.get("variations") or [])]
    rollback_snapshot = dict(preview.get("rollback_snapshot") or {})
    if not downloads or not variations or not rollback_snapshot.get("pt_versao"):
        raise ValueError("Preview recuperado não possui snapshot WooCommerce completo")

    preconditions = [
        {"key": "woo_product_id", "label": "WooCommerce ID continua o mesmo", "expected": job.woo_product_id},
        {"key": "pt_versao", "label": "pt_versao continua igual ao valor preparado", "expected": site_version},
        {"key": "remote_zip_missing", "label": "ZIP de produção continua ausente", "expected": True},
        {"key": "relationship", "label": "relationship continua seguro", "expected": job.relationship,
         "allowed": sorted(execution_plan.SAFE_RELATIONSHIPS)},
        {"key": "local_zip_exists", "label": "novo ZIP local continua existindo", "expected": True,
         "path": local_path},
        {"key": "local_zip_sha256", "label": "SHA-256 do novo ZIP continua igual", "expected": new_sha},
        {"key": "effective_source_version", "label": "effective_source_version continua válida",
         "expected": effective, "format": "numeric_dotted"},
    ]

    rollback = {
        "original_zip": remote_path,
        "original_missing": True,
        "original_sha256": "",
        "original_pt_versao": site_version,
        "original_variations": rollback_snapshot.get("variations") or [],
        "original_downloads": downloads,
        "backup_path": "",
        "steps": [
            "Se o novo ZIP já tiver sido instalado, removê-lo pelo temporário exclusivo do job.",
            f"Confirmar que {remote_path} voltou ao estado original ausente.",
            f"Restaurar pt_versao para {site_version}, caso tenha sido alterado.",
            "Reler produto e variações e validar o estado restaurado.",
        ],
        "checklist": [
            {"label": "rollback conhece o caminho originalmente ausente", "ok": bool(remote_path)},
            {"label": "rollback possui pt_versao original", "ok": bool(site_version)},
            {"label": "rollback possui estado WooCommerce original",
             "ok": bool(rollback_snapshot.get("variations") and downloads)},
        ],
    }

    plan = {
        "plan_id": str(uuid4()),
        "schema_version": 2,
        "state": "ready_for_homologation",
        "ready": True,
        "execution_enabled": settings.UPDATE_EXECUTION_ENABLED,
        "filesystem_strategy": "recreate_missing",
        "job_id": job.job_id,
        "comparison_item_id": job.comparison_item_id,
        "woo_product_id": job.woo_product_id,
        "product": dict(preview.get("product") or {"name": job.name}),
        "relationship": job.relationship,
        "site_version": site_version,
        "approved_source_version": approved,
        "effective_source_version": effective,
        "origin": {
            "type": "PluginTheme" if "plugintheme.net" in (urlparse(job.ultrapack_url).hostname or "") else "UltraPackV2",
            "version": effective,
            "local_staging_path": local_path,
        },
        "destination": {"type": "PluginTema", "woo_product_id": job.woo_product_id, "remote_path": remote_path},
        "current_zip": {
            "remote_path": remote_path,
            "name": remote_name,
            "missing": True,
            "size": 0,
            "sha256": "",
            "owner": "",
            "group": "",
            "mode": "",
        },
        "new_zip": {
            "local_staging_path": local_path,
            "name": fresh.get("file_name") or PurePosixPath(local_path).name,
            "size": fresh.get("size"),
            "sha256": new_sha,
            "entries": entries,
        },
        "woocommerce": {
            "variation_ids": variations,
            "download_ids": [_clean(item.get("id")) for item in downloads],
            "download_names": [_clean(item.get("name")) for item in downloads],
            "current_file": remote_path,
            "future_file": remote_path,
            "original_downloads": downloads,
        },
        "wordpress": {"pt_versao_current": site_version, "pt_versao_future": effective},
        "backup": {"skipped": True, "reason": "original_missing", "path": "", "expected_original_sha256": ""},
        "remote_staging": {"upload_path": artifacts["upload"], "prepared_path": artifacts["new"]},
        "preconditions": preconditions,
        "planned_steps": [
            "Revalidar WooCommerce e pt_versao.",
            "Confirmar que o ZIP de produção continua ausente.",
            "Revalidar SHA-256 do ZIP local.",
            "Enviar e validar o novo ZIP em staging remoto.",
            "Preparar o .new com owner/group/mode seguros pelo helper restrito.",
            "Instalar o .new no caminho de produção ausente.",
            "Validar SHA-256 do ZIP recriado.",
            "Atualizar pt_versao somente depois da validação física.",
            "Executar validação final e concluir.",
        ],
        "rollback": rollback,
        "status_label": "Plano pronto — ZIP ausente será reconstruído",
        "execution_label": "Execução controlada disponível",
    }
    job.effective_source_version = effective
    job.remote_staging_path = artifacts["upload"]
    job.backup_path = ""
    job.set_state(JobState.PLAN_READY, "Plano de recuperação do ZIP ausente pronto")
    log("🛠 Plano preparado para reconstruir ZIP de produção ausente")
    log("✅ Plano de execução pronto")
    return plan


def _patched_build_plan(
    job: OperationalJob,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if _BASE_BUILD_PLAN is None:
        raise RuntimeError("Gerador de plano base indisponível")

    current = dict(preview.get("current_zip") or {})
    if current.get("missing") is True:
        return _missing_execution_plan(job, preview, logger=logger)

    plan = _BASE_BUILD_PLAN(job, preview, logger=logger)
    if plan.get("terminal") is True:
        return plan

    strategy = _metadata_strategy(plan.get("current_zip") or {})
    plan["filesystem_strategy"] = strategy
    if strategy == "controlled_metadata_repair":
        plan["current_zip"]["metadata_repair"] = True
        plan["status_label"] = "Plano pronto — metadados do ZIP serão corrigidos durante a troca"
        plan.setdefault("planned_steps", []).insert(
            3,
            "Preservar o ZIP atual por rename controlado antes de instalar o .new com metadados seguros.",
        )
        plan.setdefault("rollback", {}).setdefault("steps", []).insert(
            0,
            "Restaurar o ZIP antigo preservado pelo rename controlado, mantendo seu estado original.",
        )
    return plan


class RecoveryWriteSSHStorage(ControlledWriteSSHStorage):
    """Extensão estrita do writer de um job para instalar o .new criado pelo helper."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        file_name = PurePosixPath(self.target_path).name
        self.prepared_path = SSHDeploymentArtifacts(file_name, self.job_id).paths()["new"]

    @classmethod
    def from_env(
        cls,
        *,
        job_id: str,
        target_path: str,
        write_authorized: bool = False,
    ) -> "RecoveryWriteSSHStorage":
        from app.integrations.ssh_storage import SSHStorageConfig
        return cls(
            SSHStorageConfig.from_env(),
            job_id=job_id,
            target_path=target_path,
            write_authorized=write_authorized,
        )

    def _allowed_path(self, path: str) -> str:
        resolved = self._resolved_in_root(path, allow_root=False)
        allowed = {
            self.target_path,
            self.temporary_path,
            self.backup_path,
            self.discard_path,
            self.prepared_path,
        }
        if resolved not in allowed:
            raise IntegrationError("Caminho fora do escopo de recuperação deste job")
        return resolved

    def _rename_recovery(self, source: str, destination: str) -> None:
        source_resolved = self._allowed_path(source)
        destination_resolved = self._allowed_path(destination)
        allowed_pairs = {
            (self.target_path, self.backup_path),
            (self.prepared_path, self.target_path),
            (self.target_path, self.discard_path),
            (self.backup_path, self.target_path),
            (self.discard_path, self.target_path),
        }
        if (source_resolved, destination_resolved) not in allowed_pairs:
            raise IntegrationError("Rename fora da sequência de recuperação permitida")
        if self.exists(destination_resolved):
            raise FileExistsError(f"Destino já existe: {destination_resolved}")
        self._ready().rename(source_resolved, destination_resolved)
        if destination_resolved == self.discard_path:
            self._created_temporaries.add(destination_resolved)
        if source_resolved in self._created_temporaries:
            self._created_temporaries.discard(source_resolved)

    def backup_current(self) -> None:
        if self.exists(self.backup_path):
            raise FileExistsError(f"Backup já existe: {self.backup_path}")
        self._rename_recovery(self.target_path, self.backup_path)

    def install_prepared(self) -> None:
        if not self.exists(self.prepared_path):
            raise FileNotFoundError(f"Staging preparado ausente: {self.prepared_path}")
        self._rename_recovery(self.prepared_path, self.target_path)

    def _remove_discard_if_present(self) -> None:
        if not self.exists(self.discard_path):
            return
        self._created_temporaries.add(self.discard_path)
        self.delete_temporary(self.discard_path)

    def rollback_to_missing(self) -> None:
        self._remove_discard_if_present()
        if self.exists(self.target_path):
            self._rename_recovery(self.target_path, self.discard_path)
            self.delete_temporary(self.discard_path)
        if self.exists(self.target_path):
            raise IntegrationError("Rollback não restaurou o estado originalmente ausente")

    def rollback_to_backup(self, expected_sha256: str) -> None:
        if not self.exists(self.backup_path):
            raise FileNotFoundError(f"Backup ausente: {self.backup_path}")
        if self.sha256(self.backup_path) != expected_sha256:
            raise IntegrationError("Backup de recuperação diverge do SHA original")
        self._remove_discard_if_present()
        if self.exists(self.target_path):
            self._rename_recovery(self.target_path, self.discard_path)
        try:
            self._rename_recovery(self.backup_path, self.target_path)
        except Exception:
            if self.exists(self.discard_path) and not self.exists(self.target_path):
                self._rename_recovery(self.discard_path, self.target_path)
            raise
        self._remove_discard_if_present()
        if self.sha256(self.target_path) != expected_sha256:
            raise IntegrationError("Rollback não restaurou SHA original")


def _observed_recoverable(
    self: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not bool((plan.get("current_zip") or {}).get("missing")):
        if _BASE_OBSERVED is None:
            raise RuntimeError("Observador base indisponível")
        return _BASE_OBSERVED(self, job, plan)

    product_reader = getattr(self.woo, "get_product_fresh", self.woo.get_product)
    variations_reader = getattr(self.woo, "list_variations_fresh", self.woo.list_variations)
    product = product_reader(job.woo_product_id)
    variations = list(variations_reader(job.woo_product_id))
    entries = [
        {"variation_id": int(variation.get("id") or 0), **download}
        for variation in variations
        for download in variation_downloads(variation)
        if variation.get("downloadable")
    ]
    local = Path(_clean((plan.get("new_zip") or {}).get("local_staging_path")))
    remote_path = _clean((plan.get("current_zip") or {}).get("remote_path"))
    try:
        remote_exists = bool(self.storage.exists(remote_path))
    except Exception:
        remote_exists = True
    remote_sha = ""
    if remote_exists:
        try:
            remote_sha = self.storage.sha256(remote_path)
        except Exception:
            remote_sha = ""

    observed = {
        "woo_product_id": int(product.get("id") or 0),
        "pt_versao": pt_versao(product),
        "remote_zip_missing": not remote_exists,
        "remote_zip_sha256": remote_sha,
        "relationship": job.relationship,
        "local_zip_exists": local.is_file(),
        "local_zip_sha256": _sha256_local(local) if local.is_file() else "",
        "effective_source_version": job.effective_source_version,
    }
    expected_ids = sorted(int(value) for value in (plan.get("woocommerce") or {}).get("variation_ids") or [])
    actual_ids = sorted({int(item["variation_id"]) for item in entries})

    def semantic(items: Any) -> list[tuple[int, str, str, str]]:
        return sorted(
            (
                int(item.get("variation_id") or 0),
                _clean(item.get("id")),
                _clean(item.get("name")),
                _clean(item.get("file")),
            )
            for item in items or []
        )

    if (
        actual_ids != expected_ids
        or semantic(entries) != semantic((plan.get("woocommerce") or {}).get("original_downloads") or [])
    ):
        observed["downloads_variations"] = False
    return observed, entries


def _repair_writer(job: OperationalJob, plan: Mapping[str, Any]) -> RecoveryWriteSSHStorage:
    return RecoveryWriteSSHStorage.from_env(
        job_id=job.job_id,
        target_path=_clean((plan.get("current_zip") or {}).get("remote_path")),
        write_authorized=True,
    )


def _execute_repair_strategy(
    self: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    strategy = _clean(plan.get("filesystem_strategy"))
    self.authorize(job, plan, confirmation)
    changed_zip = False
    changed_version = False
    version_plan = None
    writer: RecoveryWriteSSHStorage | None = None
    file_name = PurePosixPath(_clean((plan.get("current_zip") or {}).get("remote_path"))).name
    old_sha = _clean((plan.get("current_zip") or {}).get("sha256"))
    new_sha = _clean((plan.get("new_zip") or {}).get("sha256"))
    job.executing_at = _now()
    job.execution_error = ""
    job.set_state(JobState.EXECUTING)
    self.log(f"🚀 Iniciando execução recuperável: {job.name}")
    self.log(f"🛠 Estratégia de filesystem: {strategy}")

    try:
        observed, _entries = self._observed(job, plan)
        checked = execution_plan.evaluate_preconditions(plan, observed)
        if not checked["ready"] or observed.get("downloads_variations") is False:
            job.set_state(JobState.BLOCKED, checked["message"])
            raise ValueError(checked["message"])
        self.log("✅ Preconditions confirmadas")

        version_plan = self.version_writer.prepare(
            job.woo_product_id,
            plan["site_version"],
            plan["effective_source_version"],
        )
        writer = _repair_writer(job, plan)

        if strategy == "recreate_missing":
            if writer.exists(writer.target_path):
                raise IntegrationError("O ZIP reapareceu depois da preparação; gere o plano novamente")
            self.log("ℹ ZIP original ausente confirmado; não existe backup físico a criar")
            job.last_completed_step = "original_target_missing"
        else:
            self.log("📦 Preservando ZIP atual por rename controlado")
            if writer.exists(writer.backup_path):
                if writer.sha256(writer.backup_path) != old_sha:
                    raise IntegrationError("Backup existente diverge do SHA original; retry bloqueado")
                self.log("♻ Backup existente deste job reutilizado após validação")
                if writer.exists(writer.target_path):
                    writer._remove_discard_if_present()
                    writer._rename_recovery(writer.target_path, writer.discard_path)
            else:
                writer.backup_current()
            if writer.sha256(writer.backup_path) != old_sha:
                raise IntegrationError("SHA-256 do backup controlado divergiu")
            job.last_completed_step = "backup_validated"
            self.log("✅ ZIP anterior preservado e SHA-256 confirmado")
        self.fault("after_backup")

        upload_path = _clean((plan.get("remote_staging") or {}).get("upload_path"))
        self.log("📦 Enviando novo ZIP para staging remoto")
        if self.staging.exists(upload_path):
            if self.staging.sha256(upload_path) != new_sha:
                raise IntegrationError("Staging existente diverge do novo ZIP; retry bloqueado")
            self.log("♻ Staging remoto existente reutilizado após validação")
        else:
            with Path(_clean((plan.get("new_zip") or {}).get("local_staging_path"))).open("rb") as source:
                upload_path = self.staging.upload_staging(source)
        self.staging.chmod_staging_upload(upload_path)
        if self.staging.sha256(upload_path) != new_sha:
            raise IntegrationError("SHA-256 do staging remoto divergiu")
        job.last_completed_step = "staging_upload_validated"
        self.helper.invoke(SSHHelperRequest(
            "prepare",
            file_name,
            job.job_id,
            expected_new_sha256=new_sha,
        ))
        self.log("✅ .new preparado pelo helper com metadados seguros")
        self.fault("after_staging")

        writer.install_prepared()
        changed_zip = True
        job.last_completed_step = "production_zip_installed"
        if self.storage.sha256(_clean((plan.get("current_zip") or {}).get("remote_path"))) != new_sha:
            raise IntegrationError("SHA-256 do ZIP de produção divergiu")
        self.log("✅ ZIP de produção instalado e validado")
        self.fault("after_install")

        self.log(f"🔄 Atualizando pt_versao: {plan['site_version']} → {plan['effective_source_version']}")
        changed_version = True
        try:
            version_evidence = self.version_writer.apply_and_confirm(version_plan)
        except VersionConfirmationError as version_error:
            job.version_write_evidence = dict(version_error.evidence)
            self._log_version_evidence(version_error.evidence)
            raise
        job.version_write_evidence = dict(version_evidence)
        self._log_version_evidence(version_evidence)
        job.last_completed_step = "pt_versao_updated"
        self.log(f"✅ pt_versao confirmado: {plan['effective_source_version']}")
        self.fault("after_pt_versao")

        final, _entries = self._observed(job, plan)
        if (
            final.get("pt_versao") != plan["effective_source_version"]
            or final.get("remote_zip_sha256") != new_sha
            or final.get("downloads_variations") is False
        ):
            raise IntegrationError("Validação final divergiu")

        if writer.exists(writer.discard_path):
            writer._remove_discard_if_present()
        job.completed_at = _now()
        job.set_state(JobState.COMPLETED, "Atualização recuperada e concluída")
        record_execution_outcome(job, dict(plan), "completed")
        self.log("✅ Atualização recuperada e concluída")
        return {
            "ok": True,
            "state": job.state.value,
            "backup_path": _clean((plan.get("backup") or {}).get("path")),
            "helper": {"ok": True, "operation": "controlled-recovery", "strategy": strategy},
            "completed_at": job.completed_at,
        }
    except Exception as error:
        safe_error = UpdateLogger.sanitize(error)
        job.execution_error = safe_error
        self.log(f"❌ Falha na execução recuperável: {safe_error}")
        if changed_zip:
            self.log("↩ Iniciando rollback da estratégia recuperável")
            try:
                if changed_version and version_plan is not None:
                    try:
                        rollback_evidence = self.version_writer.apply_and_confirm(version_plan, rollback=True)
                    except VersionConfirmationError as version_error:
                        job.version_write_evidence = {
                            "apply": dict(job.version_write_evidence),
                            "rollback": dict(version_error.evidence),
                        }
                        self._log_version_evidence(version_error.evidence)
                        raise
                    job.version_write_evidence = {
                        "apply": dict(job.version_write_evidence),
                        "rollback": dict(rollback_evidence),
                    }
                    self._log_version_evidence(rollback_evidence)
                    self.log("✅ pt_versao restaurado e confirmado")

                if writer is None:
                    raise IntegrationError("Writer de recuperação indisponível para rollback")
                if strategy == "recreate_missing":
                    writer.rollback_to_missing()
                    self.log("✅ Estado original sem ZIP restaurado")
                else:
                    writer.rollback_to_backup(old_sha)
                    self.log("✅ ZIP original restaurado pelo backup controlado")
                job.set_state(JobState.ROLLED_BACK, "Rollback automático concluído")
                record_execution_outcome(job, dict(plan), "rolled_back")
                self.log("✅ Rollback concluído")
            except Exception as rollback_error:
                job.set_state(JobState.ROLLBACK_REQUIRED, f"Rollback automático falhou: {rollback_error}")
                self.log(f"❌ Falha no rollback: {rollback_error}")
                record_execution_outcome(job, dict(plan), "rollback_required")
        elif job.state != JobState.BLOCKED:
            job.set_state(JobState.ERROR, f"Falha antes da alteração de produção: {safe_error}")
            record_execution_outcome(job, dict(plan), "failed")
        raise
    finally:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass


def _patched_execute(
    self: real_executor.ControlledUpdateExecutor,
    job: OperationalJob,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    strategy = _clean(plan.get("filesystem_strategy"))
    if strategy in {"recreate_missing", "controlled_metadata_repair"}:
        return _execute_repair_strategy(self, job, plan, confirmation)
    if _BASE_EXECUTE is None:
        raise RuntimeError("Executor base indisponível")
    return _BASE_EXECUTE(self, job, plan, confirmation)


def _combined_logs(job_id: str) -> list[str]:
    key = _clean(job_id)
    if not key:
        return []
    chunks: list[str] = []

    try:
        preview = runtime.get_preview(key)
    except Exception:
        preview = {}
    try:
        plan = runtime.get_plan(key)
    except Exception:
        plan = {}
    try:
        job = runtime.get_job(key)
    except Exception:
        job = None

    for raw in (preview.get("update_logs") or []):
        chunks.append(str(raw))
    for raw in (plan.get("update_logs") or []):
        chunks.append(str(raw))

    if job is not None:
        for history in getattr(job, "execution_history", []) or []:
            if not isinstance(history, Mapping):
                continue
            previous_error = _clean(history.get("error"))
            if previous_error:
                chunks.append(f"[tentativa anterior] {previous_error}")
            for raw in history.get("logs") or []:
                chunks.append(str(raw))
        for raw in getattr(job, "execution_logs", []) or []:
            chunks.append(str(raw))
        for raw in getattr(job, "diagnostics", []) or []:
            if _clean(raw):
                chunks.append(f"[diagnóstico] {_clean(raw)}")
        if _clean(getattr(job, "execution_error", "")):
            chunks.append(f"[erro atual] {_clean(job.execution_error)}")

    try:
        for raw in web._UPDATE_LOGS.to_list(key):
            chunks.append(str(raw))
    except Exception:
        pass

    result: list[str] = []
    seen: set[str] = set()
    for raw in chunks:
        safe = UpdateLogger.sanitize(raw).strip()
        if not safe or safe in seen:
            continue
        seen.add(safe)
        result.append(safe)
    return result[-250:]


def _patched_history_rows() -> list[dict[str, Any]]:
    if _BASE_HISTORY_ROWS is None:
        return []
    rows = _BASE_HISTORY_ROWS()
    for row in rows:
        job_id = _clean(row.get("job_id"))
        logs = _combined_logs(job_id)
        if logs:
            row["logs"] = logs
    return rows


def _archive_retry_attempt(job: OperationalJob) -> None:
    archived = runtime._archive_previous_execution(job)
    if archived:
        return
    if job.execution_error or job.execution_logs:
        job.execution_history.append({
            "result": "retry_requested",
            "error": _clean(job.execution_error),
            "logs": list(job.execution_logs),
            "recorded_at": utc_now_iso(),
        })


def _reset_for_retry(job_id: str, manager: Any) -> OperationalJob:
    key = _clean(job_id)
    if not key:
        raise ValueError("job_id obrigatório")

    with runtime._LOCK:
        job = runtime._JOBS.get(key)
        if job is None:
            raise ValueError("Atualização não encontrada no histórico")
        if job.state == JobState.COMPLETED:
            return job
        if job.state in {JobState.EXECUTING, JobState.QUEUED}:
            raise ValueError("Este produto já está em execução ou em uma fila ativa")
        if job.state not in _RETRYABLE_STATES:
            raise ValueError(f"Estado {job.state.value} não pode ser reprocessado agora")

        previous_error = _clean(job.execution_error)
        _archive_retry_attempt(job)
        runtime._PREVIEWS.pop(key, None)
        runtime._PLANS.pop(key, None)
        job.execution_error = ""
        job.execution_logs = []
        job.version_write_evidence = {}
        job.executing_at = ""
        job.completed_at = ""
        job.last_completed_step = ""
        job.queue_position = 0
        job.queued_at = ""
        job.canceled_at = ""
        job.set_state(
            JobState.APPROVED,
            "Nova tentativa solicitada: preview e plano antigos descartados; staging local preservado apenas para revalidação por SHA e versão.",
        )
        runtime._persist()

    if previous_error and simple_recovery._is_auth_failure(previous_error):
        try:
            primary = web._get_primary_app(manager)
            logger = web._UPDATE_LOGS.for_job(job.job_id)
            simple_recovery._invalidate_source_session(primary, job, logger)
            job.diagnostics.append("Sessão da fonte invalidada antes do retry por falha de autenticação anterior.")
            runtime.persist_job(job)
        except Exception:
            pass
    return job


def _retry_update(job_id: str, manager: Any) -> dict[str, Any]:
    job = _reset_for_retry(job_id, manager)
    if job.state == JobState.COMPLETED:
        return {
            "ok": True,
            "already_completed": True,
            "job_id": job.job_id,
            "message": "Este produto já consta como concluído.",
        }
    result = simple_flow._start_batch("update", [job.job_id], manager)
    return {
        **dict(result or {}),
        "ok": True,
        "job_id": job.job_id,
        "message": "Nova tentativa iniciada com revalidação completa da fonte, ZIP, staging e plano.",
    }


def _script_block() -> str:
    try:
        script = _SCRIPT_PATH.read_text(encoding="utf-8").replace("</script>", "<\\/script>")
    except OSError:
        return ""
    return f"\n<script data-update-retry-recovery-v2>\n{script}\n</script>\n"


def _patched_render_panel_page(*args: Any, **kwargs: Any) -> str:
    base = _BASE_RENDER or web.render_panel_page
    html = base(*args, **kwargs)
    block = _script_block()
    if not block:
        return html
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _server_factory(server_address: Any, handler_class: type, *args: Any, **kwargs: Any) -> Any:
    manager = web._ensure_manager(getattr(handler_class, "app", None)) if False else None

    class UpdateRecoverabilityHandler(handler_class):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/atualizacoes/logs":
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query or "")
                job_id = _clean((query.get("job_id") or [""])[0])
                self._send_json({"ok": True, "job_id": job_id, "logs": _combined_logs(job_id)})
                return
            return super().do_GET()

        def do_POST(self) -> None:
            path = self._request_path()
            if path != "/operacoes/simples/retry-update":
                return super().do_POST()
            try:
                payload = self._read_json_body()
                active_manager = getattr(self.server, "scraper_manager", None)
                if active_manager is None:
                    active_manager = web._ensure_manager(getattr(self.server, "scraper_app", None))
                result = _retry_update(_clean(payload.get("job_id")), active_manager)
                self._send_json(result)
            except ValueError as error:
                self._send_json({"ok": False, "message": str(error)}, code=400)
            except Exception as error:
                self._send_json({"ok": False, "message": sanitize_text(error)}, code=500)

    return _BASE_SERVER(server_address, UpdateRecoverabilityHandler, *args, **kwargs)


def install_update_recoverability_policy() -> None:
    global _INSTALLED, _BASE_PREPARE, _BASE_BUILD_PLAN, _BASE_EXECUTE, _BASE_OBSERVED
    global _BASE_HISTORY_ROWS, _BASE_SERVER, _BASE_RENDER
    if _INSTALLED:
        return

    _BASE_PREPARE = UpdatePreparationService._prepare
    UpdatePreparationService._prepare = _patched_prepare

    _BASE_BUILD_PLAN = execution_plan.build_execution_plan
    execution_plan.build_execution_plan = _patched_build_plan
    # operational_simple_flow_policy imported build_execution_plan by value; keep
    # its fallback path aligned with the final recoverability planner as well.
    simple_flow.build_execution_plan = _patched_build_plan

    _BASE_OBSERVED = real_executor.ControlledUpdateExecutor._observed
    real_executor.ControlledUpdateExecutor._observed = _observed_recoverable

    _BASE_EXECUTE = real_executor.ControlledUpdateExecutor.execute
    real_executor.ControlledUpdateExecutor.execute = _patched_execute

    _BASE_HISTORY_ROWS = history_shared._update_rows
    history_shared._update_rows = _patched_history_rows

    _BASE_RENDER = web.render_panel_page
    web.render_panel_page = _patched_render_panel_page

    _BASE_SERVER = web.PTThreadingHTTPServer
    web.PTThreadingHTTPServer = _server_factory

    _INSTALLED = True


__all__ = [
    "install_update_recoverability_policy",
    "RecoveryWriteSSHStorage",
    "_make_source_usable_again",
    "_missing_execution_plan",
    "_reset_for_retry",
]
