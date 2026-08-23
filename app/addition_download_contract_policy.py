from __future__ import annotations

import html as html_lib
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit

from app import settings
import app.addition_full_product_creation_policy as full_creation
import app.addition_one_click_policy as one_click
import app.addition_operational_ui_policy as operational
import app.new_product_workflow_policy as additions
from app.store_pricing import variation_period


_INSTALLED = False
_BASE_CREATE_OR_RESUME: Callable[..., dict[str, Any]] | None = None
_BASE_VALIDATE_STORE_PRODUCT: Callable[..., Any] | None = None
_BASE_SYNC_APPROVED: Callable[..., dict[str, Any]] | None = None

_DEFAULT_DOWNLOAD_ROOT = "/home/plugintema.com/downloads"
_ANNUAL_DOWNLOAD_EXPIRY_DAYS = 365


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _download_name(job: Mapping[str, Any]) -> str:
    """Nome humano exibido no WooCommerce; o HTML do admin escapará & como &amp;."""
    return html_lib.unescape(
        _clean(job.get("title") or job.get("source_name") or "Produto WordPress")
    )


def _basename(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        path = unquote(parsed.path or raw)
    except Exception:
        path = raw
    return PurePosixPath(path.replace("\\", "/")).name


def _download_filename(job: Mapping[str, Any], variations: list[Mapping[str, Any]] | None = None) -> str:
    candidates = (
        job.get("zip_name"),
        Path(_clean(job.get("zip_path"))).name if _clean(job.get("zip_path")) else "",
        _basename(job.get("remote_file_path")),
    )
    for candidate in candidates:
        name = _clean(candidate)
        if name.lower().endswith(".zip"):
            return name

    for variation in variations or []:
        for download in variation.get("downloads", []) or []:
            if not isinstance(download, Mapping):
                continue
            name = _basename(download.get("file"))
            if name.lower().endswith(".zip"):
                return name
    return ""


def _download_root() -> str:
    root = _clean(getattr(settings, "SSH_DOWNLOAD_ROOT", "")) or _DEFAULT_DOWNLOAD_ROOT
    return str(PurePosixPath(root))


def _download_file_path(job: Mapping[str, Any], variations: list[Mapping[str, Any]] | None = None) -> str:
    filename = _download_filename(job, variations)
    if not filename:
        return ""
    return str(PurePosixPath(_download_root()) / filename)


def _variation_download(variation: Mapping[str, Any]) -> Mapping[str, Any] | None:
    downloads = [item for item in (variation.get("downloads") or []) if isinstance(item, Mapping)]
    return downloads[0] if len(downloads) == 1 else None


def _variation_matches_contract(
    variation: Mapping[str, Any],
    *,
    title: str,
    file_path: str,
) -> bool:
    period = variation_period(variation)
    if period not in {"annual", "lifetime"}:
        return False
    download = _variation_download(variation)
    if download is None:
        return False
    remote_name = html_lib.unescape(_clean(download.get("name")))
    remote_file = _clean(download.get("file"))
    if remote_name != title or remote_file != file_path:
        return False
    if period == "annual" and _safe_int(variation.get("download_expiry"), -1) != _ANNUAL_DOWNLOAD_EXPIRY_DAYS:
        return False
    return True


def _variation_payload(period: str, title: str, file_path: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "downloadable": True,
        "virtual": True,
        "downloads": [{"name": title, "file": file_path}],
    }
    if period == "annual":
        payload["download_expiry"] = _ANNUAL_DOWNLOAD_EXPIRY_DAYS
    return payload


def _apply_download_contract(
    job_id: str,
    *,
    woo: Any | None = None,
    emit: bool = True,
) -> dict[str, Any]:
    job = additions._row(job_id)
    product_id = _safe_int(job.get("woo_product_id"))
    if product_id <= 0:
        return {"ok": True, "changed": False, "repaired_variations": 0, "job_id": job_id}

    client = woo or additions.web._build_store_woocommerce_client()
    variations = list(client.list_variations_fresh(product_id, per_page=100) or [])
    title = _download_name(job)
    file_path = _download_file_path(job, variations)
    if not title:
        raise RuntimeError("O produto não possui nome válido para o arquivo baixável.")
    if not file_path:
        raise RuntimeError("Não foi possível determinar o nome do ZIP para montar o caminho interno de download.")

    repaired = 0
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        period = variation_period(variation)
        variation_id = _safe_int(variation.get("id"))
        if period not in {"annual", "lifetime"} or variation_id <= 0:
            continue
        if _variation_matches_contract(variation, title=title, file_path=file_path):
            continue
        additions._wc_request(
            client,
            "PUT",
            f"/wp-json/wc/v3/products/{product_id}/variations/{variation_id}",
            _variation_payload(period, title, file_path),
        )
        repaired += 1

    fresh_variations = list(client.list_variations_fresh(product_id, per_page=100) or [])
    by_period = {
        variation_period(variation): variation
        for variation in fresh_variations
        if isinstance(variation, Mapping) and variation_period(variation) in {"annual", "lifetime"}
    }
    if set(by_period) == {"annual", "lifetime"}:
        for period, variation in by_period.items():
            if not _variation_matches_contract(variation, title=title, file_path=file_path):
                label = "1 Ano" if period == "annual" else "Vitalício"
                raise RuntimeError(f"O WooCommerce não confirmou o contrato de download da variação {label}.")

    additions._update(
        job_id,
        remote_file_name=title,
        remote_file_path=file_path,
        error="",
    )
    if repaired and emit:
        one_click._emit(
            job_id,
            (
                f"Downloads corrigidos no WooCommerce #{product_id}: nome do arquivo = produto, "
                f"caminho interno {file_path} e validade de 365 dias na licença 1 Ano."
            ),
            step="store_validation",
            progress=94,
        )
    return {
        "ok": True,
        "changed": bool(repaired),
        "repaired_variations": repaired,
        "job_id": job_id,
        "product_id": product_id,
        "download_name": title,
        "download_file": file_path,
    }


def _create_or_resume_with_download_contract(job_id: str, confirmation: str) -> dict[str, Any]:
    if _BASE_CREATE_OR_RESUME is None:
        raise RuntimeError("Criador de produto base indisponível.")
    result = dict(_BASE_CREATE_OR_RESUME(job_id, confirmation) or {})
    _apply_download_contract(job_id)
    result["job"] = additions._public_job(additions._row(job_id))
    return result


def _validate_store_product_with_download_contract(
    job_id: str,
    *,
    expected_status: str,
    progress: int,
):
    if _BASE_VALIDATE_STORE_PRODUCT is None:
        raise RuntimeError("Validador WooCommerce base indisponível.")
    product, variations = _BASE_VALIDATE_STORE_PRODUCT(
        job_id,
        expected_status=expected_status,
        progress=progress,
    )
    job = additions._row(job_id)
    title = _download_name(job)
    file_path = _download_file_path(job, list(variations or []))
    by_period = {
        variation_period(variation): variation
        for variation in variations or []
        if isinstance(variation, Mapping) and variation_period(variation) in {"annual", "lifetime"}
    }
    if set(by_period) != {"annual", "lifetime"}:
        raise RuntimeError("Não foi possível validar as duas variações de download do produto.")
    for period, variation in by_period.items():
        if not _variation_matches_contract(variation, title=title, file_path=file_path):
            label = "1 Ano" if period == "annual" else "Vitalício"
            raise RuntimeError(
                f"A variação {label} não confirmou nome, caminho interno ou validade do download esperados."
            )
    return product, variations


def _repair_existing_additions() -> dict[str, Any]:
    with additions._db() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT job_id, woo_product_id FROM addition_jobs "
                "WHERE woo_product_id > 0 ORDER BY updated_at ASC"
            ).fetchall()
        ]
    if not rows:
        return {"checked": 0, "repaired_products": 0, "repaired_variations": 0, "errors": []}

    try:
        woo = additions.web._build_store_woocommerce_client()
    except Exception as error:
        return {
            "checked": 0,
            "repaired_products": 0,
            "repaired_variations": 0,
            "errors": [f"WooCommerce indisponível: {_clean(error)}"],
        }

    repaired_products = 0
    repaired_variations = 0
    errors: list[str] = []
    for row in rows:
        job_id = _clean(row.get("job_id"))
        if not job_id:
            continue
        try:
            result = _apply_download_contract(job_id, woo=woo, emit=True)
            count = _safe_int(result.get("repaired_variations"))
            repaired_variations += count
            repaired_products += 1 if count else 0
        except Exception as error:
            errors.append(f"{job_id}: {_clean(error)}")

    return {
        "checked": len(rows),
        "repaired_products": repaired_products,
        "repaired_variations": repaired_variations,
        "errors": errors[:20],
    }


def _sync_approved_with_download_repair() -> dict[str, Any]:
    if _BASE_SYNC_APPROVED is None:
        raise RuntimeError("Sincronização operacional base indisponível.")
    result = dict(_BASE_SYNC_APPROVED() or {})
    repair = _repair_existing_additions()
    result["download_contract_repair"] = repair
    if repair.get("repaired_products"):
        base_message = _clean(result.get("message"))
        result["message"] = (
            f"{base_message} Contrato de download corrigido retroativamente em "
            f"{repair['repaired_products']} produto(s) / {repair['repaired_variations']} variação(ões)."
        ).strip()
    return result


def install_addition_download_contract_policy() -> None:
    global _INSTALLED, _BASE_CREATE_OR_RESUME, _BASE_VALIDATE_STORE_PRODUCT, _BASE_SYNC_APPROVED
    if _INSTALLED:
        return

    # Instalar depois do contrato Licença e antes da UI operacional permite que
    # o sync inicial do painel corrija também os produtos adicionados anteriormente.
    _BASE_CREATE_OR_RESUME = additions._create_or_resume_draft
    additions._create_or_resume_draft = _create_or_resume_with_download_contract

    _BASE_VALIDATE_STORE_PRODUCT = full_creation._validate_store_product
    full_creation._validate_store_product = _validate_store_product_with_download_contract

    _BASE_SYNC_APPROVED = operational._sync_approved_operational
    operational._sync_approved_operational = _sync_approved_with_download_repair

    _INSTALLED = True
