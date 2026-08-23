from __future__ import annotations

import base64
import html as html_lib
import json
import os
import shlex
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit

from app import settings
import app.addition_full_product_creation_policy as full_creation
import app.addition_one_click_policy as one_click
import app.addition_operational_ui_policy as operational
import app.new_product_workflow_policy as additions
from app.integrations.ssh_storage import ReadOnlySSHStorage
from app.integrations.wordpress import sanitize_text
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


def _wordpress_root() -> str:
    configured = _clean(os.getenv("SCRAPER_WP_ROOT", ""))
    if configured:
        return str(PurePosixPath(configured))
    return str(PurePosixPath(_download_root()).parent / "public_html")


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
    expected_expiry = _ANNUAL_DOWNLOAD_EXPIRY_DAYS if period == "annual" else -1
    return _safe_int(variation.get("download_expiry"), -1) == expected_expiry


def _variation_payload(period: str, title: str, file_path: str) -> dict[str, Any]:
    """Contrato lógico. Não é enviado pela REST porque downloads.file é validado como URL."""
    payload: dict[str, Any] = {
        "downloadable": True,
        "virtual": True,
        "downloads": [{"name": title, "file": file_path}],
    }
    if period == "annual":
        payload["download_expiry"] = _ANNUAL_DOWNLOAD_EXPIRY_DAYS
    return payload


def _remote_php_payload(title: str, file_path: str, targets: list[dict[str, Any]]) -> str:
    raw = json.dumps(
        {"title": title, "file": file_path, "targets": targets},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _remote_php_program(encoded_payload: str) -> str:
    return (
        "$cfg=json_decode(base64_decode('" + encoded_payload + "'),true);"
        "if(!is_array($cfg)){throw new Exception('payload invalido');}"
        "if(!function_exists('wc_get_product')){throw new Exception('WooCommerce indisponivel');}"
        "$out=array();"
        "foreach(($cfg['targets']??array()) as $row){"
        "$id=(int)($row['id']??0);$period=(string)($row['period']??'');"
        "$product=wc_get_product($id);"
        "if(!$product||!is_a($product,'WC_Product_Variation')){throw new Exception('variacao nao encontrada: '.$id);}"
        "$downloads=$product->get_downloads('edit');"
        "if(empty($downloads)){throw new Exception('variacao sem download: '.$id);}"
        "$updated=array();"
        "foreach($downloads as $key=>$download){"
        "if(!$download instanceof WC_Product_Download){continue;}"
        "$download->set_name((string)$cfg['title']);"
        "$download->set_file((string)$cfg['file']);"
        "$updated[$key]=$download;"
        "}"
        "if(empty($updated)){throw new Exception('download invalido: '.$id);}"
        "$product->set_downloadable(true);$product->set_virtual(true);"
        "$product->set_downloads($updated);"
        "$product->set_download_expiry($period==='annual'?365:-1);"
        "$product->save();"
        "$out[]=array('id'=>$id,'period'=>$period);"
        "}"
        "echo json_encode(array('ok'=>true,'variations'=>$out),JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);"
    )


def _exec_remote(client: Any, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    status = int(stdout.channel.recv_exit_status())
    return status, out, err


def _apply_server_side(
    title: str,
    file_path: str,
    targets: list[dict[str, Any]],
    *,
    ssh: ReadOnlySSHStorage | None = None,
) -> None:
    if not targets:
        return
    encoded = _remote_php_payload(title, file_path, targets)
    program = _remote_php_program(encoded)
    root = _wordpress_root()
    wp_command = (
        "wp --path=" + shlex.quote(root) + " --allow-root eval " + shlex.quote(program)
    )
    php_program = "require_once " + repr(str(PurePosixPath(root) / "wp-load.php")) + ";" + program
    php_command = "php -r " + shlex.quote(php_program)

    owned = ssh is None
    reader = ssh or ReadOnlySSHStorage.from_env()
    try:
        if owned:
            reader.connect()
        client = getattr(reader, "_client", None)
        if client is None:
            raise RuntimeError("Conexão SSH não disponível para corrigir as variações.")

        attempts: list[str] = []
        for label, command in (("wp-cli", wp_command), ("php-cli", php_command)):
            try:
                status, out, err = _exec_remote(client, command)
            except Exception as error:
                attempts.append(f"{label}: {sanitize_text(error)}")
                continue
            if status == 0:
                try:
                    result = json.loads(out.strip() or "{}")
                except Exception:
                    result = {}
                if isinstance(result, Mapping) and result.get("ok") is True:
                    return
                attempts.append(f"{label}: resposta inválida {out.strip()[:300]}")
                continue
            detail = _clean(err) or _clean(out) or f"exit {status}"
            attempts.append(f"{label}: {detail[:400]}")

        raise RuntimeError(
            "Não foi possível atualizar o caminho interno das variações no servidor. "
            + " | ".join(attempts[-2:])
        )
    finally:
        if owned:
            try:
                reader.close()
            except Exception:
                pass


def _apply_download_contract(
    job_id: str,
    *,
    woo: Any | None = None,
    emit: bool = True,
    ssh: ReadOnlySSHStorage | None = None,
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

    targets: list[dict[str, Any]] = []
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        period = variation_period(variation)
        variation_id = _safe_int(variation.get("id"))
        if period not in {"annual", "lifetime"} or variation_id <= 0:
            continue
        if not _variation_matches_contract(variation, title=title, file_path=file_path):
            targets.append({"id": variation_id, "period": period})

    if targets:
        # O endpoint REST do WooCommerce documenta downloads.file como URL e pode
        # rejeitar um caminho absoluto com HTTP 400. O ajuste final é feito pelo
        # próprio WooCommerce no servidor, via WC_Product_Variation, preservando o
        # caminho local exatamente como o admin aceita.
        _apply_server_side(title, file_path, targets, ssh=ssh)

    fresh_variations = list(client.list_variations_fresh(product_id, per_page=100) or [])
    by_period = {
        variation_period(variation): variation
        for variation in fresh_variations
        if isinstance(variation, Mapping) and variation_period(variation) in {"annual", "lifetime"}
    }
    if set(by_period) != {"annual", "lifetime"}:
        raise RuntimeError("O WooCommerce não confirmou as duas variações 1 Ano/Vitalício após a correção.")
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
    repaired = len(targets)
    if repaired and emit:
        one_click._emit(
            job_id,
            (
                f"Downloads corrigidos no WooCommerce #{product_id}: nome = {title}; "
                f"caminho interno {file_path}; 1 Ano = 365 dias; Vitalício = sem expiração."
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

    ssh: ReadOnlySSHStorage | None = None
    try:
        ssh = ReadOnlySSHStorage.from_env()
        ssh.connect()
    except Exception as error:
        return {
            "checked": len(rows),
            "repaired_products": 0,
            "repaired_variations": 0,
            "errors": [f"SSH indisponível para retrocorreção: {sanitize_text(error)}"],
        }

    repaired_products = 0
    repaired_variations = 0
    errors: list[str] = []
    try:
        for row in rows:
            job_id = _clean(row.get("job_id"))
            if not job_id:
                continue
            try:
                result = _apply_download_contract(job_id, woo=woo, emit=True, ssh=ssh)
                count = _safe_int(result.get("repaired_variations"))
                repaired_variations += count
                repaired_products += 1 if count else 0
            except Exception as error:
                errors.append(f"{job_id}: {sanitize_text(error)}")
    finally:
        try:
            ssh.close()
        except Exception:
            pass

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
    base_message = _clean(result.get("message"))
    if repair.get("repaired_products"):
        base_message = (
            f"{base_message} Contrato de download corrigido retroativamente em "
            f"{repair['repaired_products']} produto(s) / {repair['repaired_variations']} variação(ões)."
        ).strip()
    if repair.get("errors"):
        base_message = (
            f"{base_message} Retrocorreção verificou {repair.get('checked', 0)} produto(s) e "
            f"teve {len(repair['errors'])} falha(s); consulte o log técnico."
        ).strip()
    result["message"] = base_message
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
