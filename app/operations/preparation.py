"""Preparação read-only do primeiro fluxo real de atualização."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
import re

from app import settings
from app.integrations.ssh_helper import HELPER_PATH
from app.integrations.woocommerce import pt_versao, variation_downloads
from app.operations.models import JobState, OperationalJob, normalize_operational_job
from app.operations.rollback import build_snapshot


@dataclass
class ValidationItem:
    key: str
    label: str
    ok: bool
    detail: str = ""
    level: str = "ok"


@dataclass
class UpdatePreview:
    job_id: str
    state: str
    product: dict[str, Any]
    versions: dict[str, str]
    current_zip: dict[str, Any]
    new_zip: dict[str, Any]
    variations: list[int]
    downloads: list[dict[str, Any]]
    physical_path: str
    rollback_snapshot: dict[str, Any]
    validations: list[ValidationItem] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    execution_enabled: bool = False
    execution_label: str = "Execução real ainda bloqueada para homologação"

    @property
    def ready(self) -> bool:
        return bool(self.validations) and all(item.ok for item in self.validations)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ready"] = self.ready
        return result


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    return asdict(snapshot)


def _numeric_version(value: str) -> tuple[int, ...] | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", text):
        return None
    return tuple(int(part) for part in text.split("."))


def _compare_source_version(found: str, approved: str) -> int | None:
    left, right = _numeric_version(found), _numeric_version(approved)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    return (padded_left > padded_right) - (padded_left < padded_right)


class UpdatePreparationService:
    def __init__(self, woo: Any, storage: Any, downloader: Any, *, staging_root: str | Path,
                 helper_probe: Callable[[], bool] | None = None,
                 session_provider: Callable[[OperationalJob], Any] | None = None,
                 logger: Callable[[str], None] | None = None,
                 wordpress_write_enabled: bool = settings.WORDPRESS_WRITE_ENABLED,
                 helper_execution_enabled: bool = settings.SSH_HELPER_EXECUTION_ENABLED) -> None:
        self.woo, self.storage, self.downloader = woo, storage, downloader
        self.staging_root = Path(staging_root)
        self.helper_probe = helper_probe or (lambda: False)
        self.session_provider = session_provider
        self.logger = logger or (lambda _message: None)
        self.wordpress_write_enabled = bool(wordpress_write_enabled)
        self.helper_execution_enabled = bool(helper_execution_enabled)

    def prepare(self, job: OperationalJob) -> UpdatePreview:
        normalize_operational_job(job)
        try:
            return self._prepare(job)
        except Exception as error:
            job.set_state(JobState.APPROVED, "Falha na preparação; job liberado para nova tentativa")
            self.logger(f" Falha na preparação: {error}")
            raise

    def _prepare(self, job: OperationalJob) -> UpdatePreview:
        if job.decision != "approve_update" or job.queue_type != "update":
            raise ValueError("Job nao aprovado para atualizacao")
        job.execution_error = ""
        job.set_state(JobState.VALIDATING)
        self.logger(f"🚀 Preparando atualização: {job.name}")
        self.logger(f"🔎 Consultando WooCommerce #{job.woo_product_id}")
        product = self.woo.get_product(job.woo_product_id)
        variations = list(self.woo.list_variations(job.woo_product_id))
        current_version = pt_versao(product)
        validations: list[ValidationItem] = [
            ValidationItem("product", "Produto validado", int(product.get("id") or 0) == job.woo_product_id,
                           f"WooCommerce #{product.get('id', '')}"),
            ValidationItem("relationship", "Vínculo validado", bool(job.ultrapack_url) and bool(job.relationship),
                           job.relationship or "Vínculo ausente"),
            ValidationItem("version", "pt_versao validado", current_version == job.plugintema_version,
                           f"esperado {job.plugintema_version}; atual {current_version}"),
        ]
        self.logger(" Produto validado" if validations[0].ok else " Produto divergente")
        downloads: list[dict[str, Any]] = []
        variation_ids: list[int] = []
        for variation in variations:
            entries = variation_downloads(variation)
            if variation.get("downloadable") and entries:
                variation_id = int(variation.get("id") or 0)
                variation_ids.append(variation_id)
                downloads.extend({"variation_id": variation_id, **item} for item in entries)
        paths = {item["file"] for item in downloads}
        valid_downloads = bool(downloads) and len(paths) == 1
        path = next(iter(paths), "")
        valid_path = (PurePosixPath(path).parent == PurePosixPath(settings.SSH_DOWNLOAD_ROOT)
                      and PurePosixPath(path).suffix.lower() == ".zip") if path else False
        validations.append(ValidationItem("downloads", "Downloads validados", valid_downloads and valid_path,
                                          f"{len(downloads)} entrada(s), {len(paths)} caminho(s)"))
        self.logger(" Downloads validados" if validations[-1].ok else " Downloads divergentes")
        physical: dict[str, Any] = {}
        try:
            physical = self.storage.validate_file(path).to_dict() if valid_path else {}
            physical_ok = bool(physical.get("sha256"))
        except FileNotFoundError:
            physical_ok = False
            physical = {
                "error": (
                    "Falha ao validar ZIP atual: arquivo remoto de produção não existe: "
                    f"{path or '[caminho ausente]'}"
                )
            }
        except Exception as error:
            physical_ok = False
            physical = {"error": str(error)}
        validations.append(ValidationItem("current_zip", "ZIP atual validado", physical_ok,
                                          physical.get("error", physical.get("sha256", ""))))
        self.logger("📦 ZIP atual validado" if physical_ok else " ZIP atual inválido")

        ultrapack_ok = False
        approved_source_version = getattr(job, "approved_source_version", "") or job.ultrapack_version
        effective_source_version = approved_source_version
        source_advanced = False
        source_error = ""
        try:
            self.logger("🔐 Verificando sessão da fonte")
            if self.session_provider is not None:
                self.downloader.session = self.session_provider(job)
                self.logger(" Sessão autenticada")
                self.logger("🔎 Consultando produto na fonte")
                source_url, discovered = self.downloader.inspect_product(job.ultrapack_url)
                trace = list(getattr(self.downloader, "request_trace", None) or [])
                if trace:
                    last = trace[-1]
                    self.logger(
                        "ℹ Página autenticada HTTP "
                        f"{last.get('status')}: {last.get('final_url')} · "
                        f"cookies={len(last.get('cookie_scope') or [])} · "
                        f"redirects={max(0, len(last.get('redirects') or []) - 1)}"
                    )
                effective_source_version = discovered or ""
                self.logger(f"🔎 Versão registrada na comparação: {approved_source_version}")
                self.logger(f"🔎 Versão atual encontrada na fonte: {effective_source_version}")
                version_order = _compare_source_version(effective_source_version, approved_source_version)
                safe_relationship = job.relationship in {"safe_auto", "manual_confirmed"}
                # A URL aprovada do job identifica a fonte. ``inspect_product``
                # pode confirmar a versão sem devolver outra URL; o artefato de
                # download é validado separadamente logo abaixo.
                source_identity_ok = bool(source_url or job.ultrapack_url)
                ultrapack_ok = source_identity_ok and version_order in {0, 1} and safe_relationship
                source_advanced = version_order == 1 and ultrapack_ok
                if source_advanced:
                    self.logger(
                        f"ℹ Fonte avançou desde a comparação; utilizando {effective_source_version}"
                    )
            else:
                ultrapack_ok = True
            job.effective_source_version = effective_source_version
            self.logger(" Produto da fonte validado" if ultrapack_ok else " Versão da fonte divergente")
        except Exception as error:
            source_error = str(error)
            self.logger(f" Falha na fonte: {error}")
        version_order = _compare_source_version(effective_source_version, approved_source_version)
        if source_error:
            source_detail = source_error
        elif version_order == 1 and ultrapack_ok:
            source_detail = (
                f"Fonte avançou desde a comparação: {approved_source_version} → "
                f"{effective_source_version}"
            )
        elif version_order is None:
            source_detail = (f"versão inválida/incomparável; comparação {approved_source_version}; "
                             f"encontrada {effective_source_version}")
        elif version_order < 0:
            source_detail = (f"fonte anterior à comparação; comparação {approved_source_version}; "
                             f"encontrada {effective_source_version}")
        else:
            source_detail = (f"comparação {approved_source_version}; "
                             f"encontrada {effective_source_version}")
        validations.append(ValidationItem("ultrapack", "Produto da fonte validado", ultrapack_ok,
                                          source_detail, "info" if source_advanced else
                                          ("ok" if ultrapack_ok else "error")))

        site_vs_source = _compare_source_version(current_version, effective_source_version)
        already_updated = bool(ultrapack_ok and site_vs_source in {0, 1})
        already_updated_message = ""
        if already_updated:
            relation = "igual à" if site_vs_source == 0 else "superior à"
            already_updated_message = (
                f"Produto já atualizado no PluginTema: versão atual {current_version} é {relation} "
                f"versão disponível na fonte {effective_source_version}. Nenhuma ação necessária."
            )
            version_validation = next((item for item in validations if item.key == "version"), None)
            if version_validation is not None:
                version_validation.ok = True
                version_validation.level = "info"
                version_validation.detail = (
                    f"Comparação registrava {job.plugintema_version}; WooCommerce já está em {current_version}."
                )
            validations.append(ValidationItem(
                "already_updated", "Produto já atualizado", False,
                already_updated_message, "info",
            ))
            self.logger(f"ℹ {already_updated_message}")

        artifact: dict[str, Any] = {}
        try:
            if not ultrapack_ok:
                raise RuntimeError("Download bloqueado pela validacao da versao fonte ou do vinculo")
            if already_updated:
                raise RuntimeError(already_updated_message)
            self.logger("📦 Baixando ZIP para staging local")
            job.set_state(JobState.DOWNLOADING)
            local, discovered_version = self.downloader.download(
                job.ultrapack_url, self.staging_root / job.job_id
            )
            trace = list(getattr(self.downloader, "request_trace", None) or [])
            if trace:
                last = trace[-1]
                self.logger(
                    "ℹ Download final HTTP "
                    f"{last.get('status')}: {last.get('final_url')} · "
                    f"Content-Type={last.get('content_type') or '-'} · "
                    f"Content-Disposition={'sim' if last.get('content_disposition') else 'não'}"
                )
            artifact = local.to_dict()
            downloaded_version = discovered_version or effective_source_version
            if _compare_source_version(downloaded_version, effective_source_version) != 0:
                raise RuntimeError(
                    "Versão do ZIP baixado não corresponde à versão efetiva: "
                    f"esperada {effective_source_version}; recebida {downloaded_version}"
                )
            download_ok = True
            self.logger(" SHA-256 calculado; ZIP válido")
        except Exception as error:
            download_ok = False
            artifact = {"error": str(error)}
        validations.extend([
            ValidationItem("downloaded", "Novo ZIP baixado", download_ok, artifact.get("error", artifact.get("path", ""))),
            ValidationItem("new_zip", "Novo ZIP válido", download_ok and bool(artifact.get("sha256")),
                           artifact.get("sha256", artifact.get("error", ""))),
        ])
        snapshot = build_snapshot(product, variations,
                                  captured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        snapshot = type(snapshot)(**{**asdict(snapshot), "variations": snapshot.variations,
                                     "file_hash": physical.get("sha256") or None})
        validations.append(ValidationItem("backup", "Backup disponível", bool(snapshot.pt_versao_meta_id and snapshot.file_hash),
                                          "Snapshot WooCommerce + hash físico"))
        validations.append(ValidationItem("helper", "Helper disponível", True, "Não executado nesta etapa"))
        execution_available = bool(settings.UPDATE_EXECUTION_ENABLED)
        validations.append(ValidationItem(
            "execution", "Execução controlada disponível" if execution_available
            else "Atualização ainda não executada", True,
            "Pronta para confirmação individual" if execution_available
            else "Habilite SCRAPER_UPDATE_EXECUTION_ENABLED e autorize o produto",
            "ok" if execution_available else "info",
        ))
        preview_ready = all(item.ok for item in validations)
        first_failure = next((item.detail for item in validations if not item.ok and item.detail), "")
        job.set_state(
            JobState.PREPARED if preview_ready else JobState.BLOCKED,
            "Preview preparado" if preview_ready else f"Preparação bloqueada: {first_failure}",
        )
        if job.state == JobState.PREPARED:
            job.execution_error = ""
            job.prepared_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            job.current_sha256 = str(physical.get("sha256") or "")
            job.new_sha256 = str(artifact.get("sha256") or "")
            job.local_staging_path = str(artifact.get("path") or "")
        else:
            job.execution_error = first_failure or "Preparação bloqueada. Abra os detalhes para revisar as validações."
        self.logger("🛑 Preparação concluída. Nenhuma atualização executada.")
        return UpdatePreview(
            job_id=job.job_id, state=job.state.value,
            product={"id": int(product.get("id") or 0), "name": str(product.get("name") or job.name)},
            versions={
                "site_version": current_version,
                "approved_source_version": approved_source_version,
                "effective_source_version": effective_source_version,
                # Aliases temporários para consumidores anteriores do preview.
                "plugintema": current_version,
                "ultrapack": effective_source_version,
                "ultrapack_approved": approved_source_version,
                "ultrapack_found": effective_source_version,
            },
            current_zip=physical, new_zip=artifact, variations=sorted(variation_ids),
            downloads=downloads, physical_path=path, rollback_snapshot=_snapshot_dict(snapshot),
            validations=validations,
            notices=([
                "A fonte foi atualizada desde a comparação. "
                "Será utilizada a versão mais recente disponível."
            ] if source_advanced else []),
            execution_enabled=(self.wordpress_write_enabled and self.helper_execution_enabled),
        )

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        from app.integrations.wordpress import WriteOperationDisabledError
        raise WriteOperationDisabledError("Execução real ainda bloqueada para homologação")
