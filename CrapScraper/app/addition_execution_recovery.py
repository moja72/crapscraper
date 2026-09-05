from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

import requests

_INSTALLED = False

_FIXED_ERROR_MARKERS = (
    "openai_api_key não configurada",
    "openai_api_key nao configurada",
    "autenticação do ultrapackv2 não configurada",
    "autenticacao do ultrapackv2 nao configurada",
    "403 client error: forbidden for url:",
    "desenvolvedor não confirmado por fonte confiável",
    "desenvolvedor nao confirmado por fonte confiavel",
    "destino de download não configurado",
    "destino de download nao configurado",
    "configuração ssh incompleta",
    "configuracao ssh incompleta",
    "imagem inválida: sem permissão para enviar esse tipo de arquivo",
    "imagem invalida: sem permissao para enviar esse tipo de arquivo",
    "um termo com o nome fornecido já existe com este ascendente",
    "um termo com o nome fornecido ja existe com este ascendente",
)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:190]


def _configure_addition_download_destination() -> None:
    """Make Adicionar use the same canonical destination as Atualizar.

    The update SFTP adapter already accepts SCRAPER_SSH_USERNAME and defaults the
    production directory to /home/plugintema.com/downloads. ArtifactPublisher
    historically required SCRAPER_SSH_USER *and* SCRAPER_SSH_DOWNLOAD_ROOT,
    causing Adicionar to fail although Ambiente correctly reported storage as
    validated. Normalize the aliases/defaults once at startup so both flows use
    one destination contract.
    """
    username = (os.getenv("SCRAPER_SSH_USERNAME") or os.getenv("SCRAPER_SSH_USER") or "").strip()
    if username:
        os.environ.setdefault("SCRAPER_SSH_USER", username)
        os.environ.setdefault("SCRAPER_SSH_USERNAME", username)

    if os.getenv("SCRAPER_SSH_HOST", "").strip():
        os.environ.setdefault("SCRAPER_SSH_DOWNLOAD_ROOT", "/home/plugintema.com/downloads")

    if not os.getenv("SCRAPER_DOWNLOAD_PUBLIC_BASE_URL", "").strip():
        site = (os.getenv("SCRAPER_WP_BASE_URL") or os.getenv("SCRAPER_WOOCOMMERCE_URL") or "").strip().rstrip("/")
        if "/wp-json/" in site:
            site = site.split("/wp-json/", 1)[0].rstrip("/")
        if site:
            os.environ["SCRAPER_DOWNLOAD_PUBLIC_BASE_URL"] = site + "/downloads"


def _patch_research() -> None:
    from app.additions.source import ProductResearchService

    if getattr(ProductResearchService, "_crapscraper_optional_developer", False):
        return
    original = ProductResearchService.resolve

    def resolve(self: Any, job: dict[str, Any]) -> dict[str, str]:
        result = dict(original(self, job))
        if not str(result.get("developer") or "").strip():
            result["developer"] = str(job.get("developer") or "").strip() or "Não identificado"
        return result

    ProductResearchService.resolve = resolve
    ProductResearchService._crapscraper_optional_developer = True


def _patch_store_reconcile() -> None:
    from app.additions.wordpress import AdditionStoreGateway

    if getattr(AdditionStoreGateway, "_crapscraper_safe_reconcile", False):
        return

    def reconcile(self: Any, job: dict[str, Any]) -> int:
        current = int(job.get("woo_product_id") or 0)
        if current:
            return current
        slug = _slug(str(job.get("product_name") or ""))
        if not slug:
            return 0
        try:
            products = self._wc("GET", "/products", params={"slug": slug, "per_page": 100})
        except requests.HTTPError as error:
            response = getattr(error, "response", None)
            if response is not None and int(getattr(response, "status_code", 0) or 0) == 403:
                return 0
            raise
        for product in products or []:
            meta = product.get("meta_data", []) or []
            if any(
                str(item.get("key")) == "crapscraper_addition_job"
                and str(item.get("value")) == str(job.get("job_id") or "")
                for item in meta
            ):
                return int(product.get("id") or 0)
        return 0

    AdditionStoreGateway.reconcile = reconcile
    AdditionStoreGateway._crapscraper_safe_reconcile = True


def _reset_obsolete_errors(repository: Any) -> int:
    changed = 0
    with repository.connection() as db:
        rows = db.execute(
            "SELECT job_id,current_error FROM addition_jobs WHERE public_state='error'"
        ).fetchall()
        for row in rows:
            raw = str(row["current_error"] or "")
            try:
                decoded = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                decoded = raw
            text = json.dumps(decoded, ensure_ascii=False).lower() if not isinstance(decoded, str) else decoded.lower()
            if not any(marker in text for marker in _FIXED_ERROR_MARKERS):
                continue
            db.execute(
                "UPDATE addition_jobs SET public_state='ready',stage='prepared',current_error=NULL,finished_at='' WHERE job_id=?",
                (row["job_id"],),
            )
            changed += 1
    return changed


def _patch_service_startup() -> None:
    from app.additions.service import AdditionService

    if getattr(AdditionService, "_crapscraper_fixed_error_reset", False):
        return
    original = AdditionService.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        _reset_obsolete_errors(self.repository)

    AdditionService.__init__ = init
    AdditionService._crapscraper_fixed_error_reset = True


def install_addition_execution_recovery() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _configure_addition_download_destination()
    _patch_research()
    _patch_store_reconcile()
    _patch_service_startup()
    _INSTALLED = True


__all__ = [
    "install_addition_execution_recovery",
    "_slug",
    "_reset_obsolete_errors",
    "_configure_addition_download_destination",
]
