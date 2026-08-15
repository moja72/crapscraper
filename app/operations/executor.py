from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from app import settings
from app.integrations.wordpress import WriteOperationDisabledError
from app.integrations.ssh_storage import ReadOnlySSHStorage
from app.integrations.woocommerce import WooCommerceClient, pt_versao, variation_downloads
from app.operations.models import DryRunPlan, JobState, OperationalJob


EXPECTED_DOWNLOAD_ROOT = PurePosixPath(settings.SSH_DOWNLOAD_ROOT)


class DryRunExecutor:
    def __init__(
        self,
        woo: WooCommerceClient,
        *,
        dry_run: bool = True,
        write_enabled: bool = settings.WORDPRESS_WRITE_ENABLED,
        storage: ReadOnlySSHStorage | None = None,
    ) -> None:
        self.woo = woo
        self.dry_run = bool(dry_run)
        self.write_enabled = bool(write_enabled)
        self.storage = storage

    def _assert_no_write(self) -> None:
        if not self.dry_run or self.write_enabled:
            raise WriteOperationDisabledError(
                "Executor desta fase exige dry_run=True e write_enabled=False"
            )

    def plan_update(self, job: OperationalJob) -> DryRunPlan:
        self._assert_no_write()
        if job.decision != "approve_update" or job.queue_type != "update":
            job.set_state(JobState.BLOCKED, "Decisao/fila nao autoriza atualizacao")
            raise ValueError(job.diagnostics[-1])
        if job.woo_product_id <= 0:
            job.set_state(JobState.BLOCKED, "Produto WooCommerce ausente")
            raise ValueError(job.diagnostics[-1])

        product = self.woo.get_product(job.woo_product_id)
        variations = self.woo.list_variations(job.woo_product_id)
        current = pt_versao(product)
        if job.plugintema_version and current != job.plugintema_version:
            job.set_state(JobState.BLOCKED, "pt_versao divergiu desde a decisao")
            raise ValueError(job.diagnostics[-1])

        entries: list[dict[str, Any]] = []
        relevant_ids: list[int] = []
        for variation in variations:
            downloads = variation_downloads(variation)
            if variation.get("downloadable") and downloads:
                relevant_ids.append(int(variation.get("id") or 0))
                for download in downloads:
                    entries.append({"variation_id": int(variation.get("id") or 0), **download})
        if not entries:
            job.set_state(JobState.BLOCKED, "Nenhum download nas variacoes")
            raise ValueError(job.diagnostics[-1])

        paths = {entry["file"] for entry in entries}
        if len(paths) != 1:
            job.set_state(JobState.BLOCKED, "Variacoes nao compartilham um unico arquivo")
            raise ValueError(job.diagnostics[-1])
        physical_file = next(iter(paths))
        path = PurePosixPath(physical_file)
        if path.parent != EXPECTED_DOWNLOAD_ROOT or path.suffix.lower() != ".zip":
            job.set_state(JobState.BLOCKED, "Caminho ZIP fora do padrao aprovado")
            raise ValueError(job.diagnostics[-1])

        if self.storage is None:
            job.set_state(JobState.BLOCKED, "Armazenamento SSH read-only nao configurado")
            raise ValueError(job.diagnostics[-1])
        try:
            physical = self.storage.validate_file(physical_file)
        except Exception as error:
            job.set_state(JobState.BLOCKED, f"Validacao fisica do ZIP falhou: {error}")
            raise ValueError(job.diagnostics[-1]) from None

        job.set_state(JobState.VALIDATED)
        plan = DryRunPlan(
            job=job,
            product_id=int(product.get("id") or 0),
            variation_ids=sorted(relevant_ids),
            current_version=current,
            target_version=job.ultrapack_version,
            physical_file=physical_file,
            download_entries=entries,
            physical_validation=physical.to_dict(),
            steps=[
                "snapshot WooCommerce read-only",
                "baixar ZIP do Ultrapack localmente (ainda nao implementado)",
                "validar ZIP local e calcular SHA-256",
                "SFTP envia apenas staging .upload (escrita ainda bloqueada)",
                "helper restrito prepare como plugi2090 (execucao ainda bloqueada)",
                "helper restrito install atomico como plugi2090 (execucao ainda bloqueada)",
                "validar filesystem pelo helper/SSH read-only",
                "atualizar pt_versao somente apos validacao (escrita ainda bloqueada)",
                "reler WooCommerce e validar versao, UUIDs, nomes e caminhos",
                "se falhar apos install, executar rollback explicito do helper",
            ],
        )
        job.set_state(JobState.DRY_RUN_READY, "Plano gerado; escrita bloqueada")
        return plan

    def plan_new_product(
        self,
        job: OperationalJob,
        *,
        category_ids: list[int] | None = None,
        image_id: int | None = None,
        download_file: str = "NAO DEFINIDO",
    ) -> DryRunPlan:
        self._assert_no_write()
        if job.decision != "approve_new_product" or job.queue_type != "new_product":
            job.set_state(JobState.BLOCKED, "Decisao/fila nao autoriza cadastro")
            raise ValueError(job.diagnostics[-1])
        slug_name = re.sub(r"[^A-Za-z0-9]+", "", job.name) or "Produto"
        planned_file = (
            str(EXPECTED_DOWNLOAD_ROOT / f"{slug_name}.zip")
            if download_file == "NAO DEFINIDO" else download_file
        )
        parent = {
            "name": job.name,
            "status": "draft",
            "type": "variable",
            "catalog_visibility": "visible",
            "categories": [{"id": item} for item in (category_ids or [])],
            "images": ([{"id": image_id}] if image_id else []),
            "attributes": [{
                "id": 4, "visible": True, "variation": True,
                "options": ["1 Ano", "Vitalicio"],
            }],
            "meta_data": [
                {"key": "pt_versao", "value": job.ultrapack_version},
                {"key": "site_oficial", "value": job.official_url},
                {"key": "_yith_wcmbs_credits", "value": "1"},
            ],
        }
        variations = [
            {
                "status": "draft", "regular_price": "NAO DEFINIDO",
                "virtual": True, "downloadable": True,
                "download_limit": -1, "download_expiry": -1,
                "attributes": [{"id": 4, "option": option}],
                "downloads": [{"name": job.name, "file": planned_file}],
            }
            for option in ("1 Ano", "Vitalicio")
        ]
        job.set_state(JobState.DRY_RUN_READY, "Payload draft gerado; escrita bloqueada")
        return DryRunPlan(
            job=job, product_id=0, variation_ids=[], current_version="",
            target_version=job.ultrapack_version, physical_file=planned_file,
            download_entries=[], steps=["criar pai draft", "criar duas variacoes draft", "validar sem publicar"],
            payload_preview={"product": parent, "variations": variations},
        )

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        raise WriteOperationDisabledError("Execucao remota nao existe nesta fase")
