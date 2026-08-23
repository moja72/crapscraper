from __future__ import annotations

from typing import Any, Mapping

import app.addition_download_contract_v2_policy as contract_v2
import app.addition_full_product_creation_policy as full_creation
import app.addition_retry_recovery_policy as retry
import app.new_product_workflow_policy as additions


_INSTALLED = False


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _rest_download_identity(variations: list[Mapping[str, Any]]) -> tuple[str, str]:
    names: set[str] = set()
    files: set[str] = set()
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        downloads = [item for item in variation.get("downloads", []) or [] if isinstance(item, Mapping)]
        if len(downloads) != 1:
            continue
        name = _clean(downloads[0].get("name"))
        file_path = _clean(downloads[0].get("file"))
        if name:
            names.add(name)
        if file_path:
            files.add(file_path)
    if len(names) == 1 and len(files) == 1:
        return next(iter(names)), next(iter(files))
    return "", ""


def _validate_store_product_bridge(
    job_id: str,
    *,
    expected_status: str,
    progress: int,
):
    """Validate the product without forcing REST to echo the local download path.

    The legacy complete-product validator also checks downloads against the job.
    For the generic validation pass we temporarily project the representation
    currently returned by REST.  The exact PluginTema contract is then written
    and verified directly from WordPress postmeta by contract v2.
    """
    job = additions._row(job_id)
    woo = additions.web._build_store_woocommerce_client()
    rest_variations = list(woo.list_variations_fresh(int(job.get("woo_product_id") or 0), per_page=100) or [])
    rest_name, rest_file = _rest_download_identity(rest_variations)

    saved_name = _clean(job.get("remote_file_name"))
    saved_file = _clean(job.get("remote_file_path"))
    projected = bool(rest_name and rest_file)
    if projected:
        additions._update(job_id, remote_file_name=rest_name, remote_file_path=rest_file)

    try:
        product, variations = retry._validate_store_product_recovering(
            job_id,
            expected_status=expected_status,
            progress=progress,
        )
    finally:
        if projected:
            additions._update(job_id, remote_file_name=saved_name, remote_file_path=saved_file)

    contract_v2._apply_download_contract_v2(job_id, woo=woo)
    return product, variations


def install_addition_download_validation_bridge_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    full_creation._validate_store_product = _validate_store_product_bridge
    _INSTALLED = True
