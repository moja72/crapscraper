from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

import app.addition_custom_fields_policy as field_resolution
import app.addition_full_product_creation_policy as full_creation
import app.new_product_workflow_policy as additions
from app.integrations.woocommerce import metadata_value
from app.operations.real_executor import ControlledUpdateExecutor


_INSTALLED = False
_BASE_EXECUTE: Callable[..., Any] | None = None
_BASE_PUBLISH_COMPLETE: Callable[..., Any] | None = None

_KEYS = ("pt_versao", "desenvolvedor", "site_oficial")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _current_values(product: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: _clean(metadata_value(product, key))
        for key in _KEYS
    }


def _job_value(job: Any, name: str, default: str = "") -> str:
    if isinstance(job, Mapping):
        return _clean(job.get(name, default))
    return _clean(getattr(job, name, default))


def _source_context(
    job: Any,
    *,
    current: Mapping[str, str],
    version: str,
) -> dict[str, Any]:
    official_hint = (
        current.get("site_oficial")
        or _job_value(job, "official_url")
        or _job_value(job, "source_official_url")
        or _job_value(job, "site_official_url")
    )
    source_url = (
        _job_value(job, "source_product_url")
        or _job_value(job, "ultrapack_url")
    )
    developer_hint = (
        current.get("desenvolvedor")
        or _job_value(job, "desenvolvedor")
        or _job_value(job, "developer")
        or _job_value(job, "author")
        or _job_value(job, "vendor")
    )
    return {
        "pt_versao": version,
        "source_version": version,
        "site_oficial": current.get("site_oficial") or "",
        "official_url": official_hint,
        "source_official_url": official_hint,
        "source_product_url": source_url,
        "desenvolvedor": developer_hint,
        "developer": developer_hint,
    }


def _desired_values(
    job: Any,
    *,
    preserved: Mapping[str, str],
    expected_version: str,
) -> dict[str, str]:
    version = _clean(expected_version) or _clean(preserved.get("pt_versao"))
    context = _source_context(job, current=preserved, version=version)

    official = _clean(preserved.get("site_oficial"))
    if not official:
        official = _clean(field_resolution._official_url(context))

    developer = _clean(preserved.get("desenvolvedor"))
    if not developer:
        developer = _clean(field_resolution._developer(context, official))
        developer = _clean(field_resolution._normalize_developer_display(developer))

    return {
        "pt_versao": version,
        "desenvolvedor": developer,
        "site_oficial": official,
    }


def _write_and_confirm(
    woo: Any,
    product_id: int,
    desired: Mapping[str, str],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, str]:
    log = logger or (lambda _message: None)
    reader = getattr(woo, "get_product_fresh", getattr(woo, "get_product", None))
    if not callable(reader):
        raise RuntimeError("Cliente WooCommerce não permite reler o produto para proteger os campos personalizados.")

    current_product = reader(int(product_id))
    current = _current_values(current_product)
    updates: list[dict[str, Any]] = []

    for key in _KEYS:
        wanted = _clean(desired.get(key))
        if not wanted or current.get(key) == wanted:
            continue
        updates.append(field_resolution._meta_payload_item(current_product, key, wanted))

    if updates:
        additions._wc_request(
            woo,
            "PUT",
            f"/wp-json/wc/v3/products/{int(product_id)}",
            {"meta_data": updates},
        )

    fresh = reader(int(product_id))
    confirmed = _current_values(fresh)
    for key in _KEYS:
        wanted = _clean(desired.get(key))
        if wanted and confirmed.get(key) != wanted:
            raise RuntimeError(
                f"WooCommerce não confirmou o campo {key}: esperado {wanted!r}, recebido {confirmed.get(key, '')!r}."
            )

    missing = [key for key in _KEYS if not confirmed.get(key)]
    if missing:
        log("⚠ Campos personalizados ainda sem fonte segura: " + ", ".join(missing))
    else:
        log(
            "✅ Campos personalizados confirmados: "
            f"pt_versao={confirmed['pt_versao']}; "
            f"desenvolvedor={confirmed['desenvolvedor']}; "
            f"site_oficial={confirmed['site_oficial']}"
        )
    return confirmed


def _protected_execute(
    self: ControlledUpdateExecutor,
    job: Any,
    plan: Mapping[str, Any],
    confirmation: str,
) -> dict[str, Any]:
    if _BASE_EXECUTE is None:
        raise RuntimeError("Executor base indisponível")

    reader = getattr(self.woo, "get_product_fresh", self.woo.get_product)
    before_product = reader(int(job.woo_product_id))
    preserved = _current_values(before_product)

    result = _BASE_EXECUTE(self, job, plan, confirmation)

    expected_version = _clean(
        plan.get("effective_source_version")
        or getattr(job, "effective_source_version", "")
        or plan.get("site_version")
    )
    desired = _desired_values(
        job,
        preserved=preserved,
        expected_version=expected_version,
    )
    self.log("🔎 Reconciliando versão, desenvolvedor e site oficial após a atualização")
    _write_and_confirm(
        self.woo,
        int(job.woo_product_id),
        desired,
        logger=self.log,
    )
    return result


def _protected_publish_complete(job_id: str) -> dict[str, Any]:
    if _BASE_PUBLISH_COMPLETE is None:
        raise RuntimeError("Publicação base indisponível")

    job_before = additions._row(job_id)
    product_id_before = int(job_before.get("woo_product_id") or 0)
    woo = additions.web._build_store_woocommerce_client() if product_id_before else None
    preserved: dict[str, str] = {}
    if woo is not None:
        preserved = _current_values(woo.get_product_fresh(product_id_before))

    result = _BASE_PUBLISH_COMPLETE(job_id)
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or product_id_before or 0)
    if not product_id:
        return result

    if woo is None:
        woo = additions.web._build_store_woocommerce_client()
    if not preserved:
        preserved = _current_values(woo.get_product_fresh(product_id))

    expected_version = _clean(job.get("source_version")) or preserved.get("pt_versao", "")
    desired = _desired_values(
        job,
        preserved=preserved,
        expected_version=expected_version,
    )

    one_click = getattr(field_resolution, "one_click", None)
    if one_click is not None:
        try:
            one_click._emit(
                job_id,
                "Reconciliando versão, desenvolvedor e site oficial após a publicação…",
                step="store_fields",
                progress=99,
            )
        except Exception:
            pass

    confirmed = _write_and_confirm(woo, product_id, desired)
    try:
        additions._update(
            job_id,
            site_oficial=confirmed.get("site_oficial", ""),
            desenvolvedor=confirmed.get("desenvolvedor", ""),
            error="",
        )
    except Exception:
        pass
    return result


def install_product_custom_fields_guard_policy() -> None:
    global _INSTALLED, _BASE_EXECUTE, _BASE_PUBLISH_COMPLETE
    if _INSTALLED:
        return

    # Esta policy deve ser instalada depois das demais wrappers do executor para
    # reconciliar o estado realmente final do produto.
    _BASE_EXECUTE = ControlledUpdateExecutor.execute
    ControlledUpdateExecutor.execute = _protected_execute

    # A publicação de um produto novo pode disparar hooks WordPress que limpam
    # metadados não enviados no PUT de status. Reconfirme tudo depois do publish.
    _BASE_PUBLISH_COMPLETE = full_creation._publish_complete
    full_creation._publish_complete = _protected_publish_complete
    _INSTALLED = True
