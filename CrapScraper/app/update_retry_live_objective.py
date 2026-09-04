from __future__ import annotations

from typing import Any

from app.updates.adapters import normalize_version, product_version

_INSTALLED = False


def _refresh_retry_objective(service: Any, job_id: str) -> dict[str, Any] | None:
    job = service.repository.get(job_id)
    if str(job.get("state") or "") != "error":
        return None
    try:
        reader = getattr(service.executor.woo, "get_product_fresh", None) or service.executor.woo.get_product
        product = reader(int(job["woo_product_id"]))
        current = normalize_version(product_version(product))
        source = service.executor.sources.get(str(job.get("source_kind") or ""))
        probe = getattr(source, "validate_access", None)
        details = probe(job) if callable(probe) else None
        live = normalize_version((details or {}).get("version") or source.confirm_version(job))
        if not current or not live:
            return None
        refreshed = service.repository.refresh_objective(
            job_id,
            current_version=current,
            source_version=live,
        )
        service.repository.append_log(
            job_id,
            None,
            f"Retry revalidou objetivo em tempo real: WooCommerce {current}; fonte aprovada {live}.",
        )
        return refreshed
    except Exception:
        # A política normal de retry continua responsável por apresentar a falha
        # real de autenticação, origem ou WooCommerce. Esta etapa é apenas uma
        # reconciliação preventiva contra snapshots de versão envelhecidos.
        return None


def install_update_retry_live_objective() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from app.updates.service import UpdateService

    if getattr(UpdateService, "_crapscraper_live_retry_objective", False):
        _INSTALLED = True
        return
    original_retry = UpdateService.retry

    def retry(self: Any, job_id: str) -> dict[str, Any]:
        _refresh_retry_objective(self, job_id)
        return original_retry(self, job_id)

    UpdateService.retry = retry
    UpdateService._crapscraper_live_retry_objective = True
    _INSTALLED = True


__all__ = ["install_update_retry_live_objective", "_refresh_retry_objective"]
