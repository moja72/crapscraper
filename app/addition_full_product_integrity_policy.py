from __future__ import annotations

from typing import Any, Mapping

import app.addition_final_validation_policy as final_validation
import app.addition_full_product_creation_policy as full
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions


_INSTALLED = False
_ORIGINAL_VALIDATE = None


def _image_ids(product: Mapping[str, Any]) -> set[int]:
    return {
        int(item.get("id") or 0)
        for item in (product.get("images") or [])
        if isinstance(item, Mapping) and int(item.get("id") or 0)
    }


def _strict_validate_store_product(
    job_id: str,
    *,
    expected_status: str,
    progress: int,
):
    product, variations = _ORIGINAL_VALIDATE(
        job_id,
        expected_status=expected_status,
        progress=progress,
    )
    job = additions._row(job_id)
    woo = additions.web._build_store_woocommerce_client()

    root_category_id, root_category_name = simple._root_category(woo, simple._kind(job))
    categories = full._category_ids(product)
    if categories != {root_category_id}:
        raise RuntimeError(
            f"O produto precisa ficar somente na categoria raiz {root_category_name}; "
            f"categorias recebidas: {sorted(categories)}."
        )

    description = final_validation._validated_description(
        str(product.get("short_description") or "")
    )
    if not description:
        raise RuntimeError("O WooCommerce não confirmou a breve descrição validada.")

    media_id = int(job.get("media_id") or 0)
    if not media_id:
        raise RuntimeError("A imagem do Chat 2 não recebeu um media_id válido no WordPress.")
    if media_id not in _image_ids(product):
        raise RuntimeError("O WooCommerce não confirmou a imagem principal gerada pelo Chat 2.")

    return product, variations


def install_addition_full_product_integrity_policy() -> None:
    global _INSTALLED, _ORIGINAL_VALIDATE
    if _INSTALLED:
        return
    _ORIGINAL_VALIDATE = full._validate_store_product
    full._validate_store_product = _strict_validate_store_product
    _INSTALLED = True
