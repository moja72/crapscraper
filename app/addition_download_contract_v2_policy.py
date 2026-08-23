from __future__ import annotations

import base64
import html as html_lib
import json
import shlex
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

import app.addition_download_contract_policy as contract
import app.addition_full_product_creation_policy as full_creation
import app.addition_one_click_policy as one_click
import app.addition_retry_recovery_policy as retry
import app.new_product_workflow_policy as additions
from app.integrations.ssh_storage import ReadOnlySSHStorage
from app.integrations.wordpress import sanitize_text
from app.store_pricing import variation_period


_INSTALLED = False
_BASE_VALIDATE_STORE_PRODUCT: Callable[..., Any] | None = None
_ANNUAL_EXPIRY = 365


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _existing_download_filename(variations: list[Mapping[str, Any]]) -> str:
    """Prefer the filename already used by WooCommerce for retroactive repairs."""
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        for download in variation.get("downloads", []) or []:
            if not isinstance(download, Mapping):
                continue
            name = contract._basename(download.get("file"))
            if name.lower().endswith(".zip"):
                return name
    return ""


def _target_file_path(job: Mapping[str, Any], variations: list[Mapping[str, Any]]) -> str:
    filename = _existing_download_filename(variations) or contract._download_filename(job, variations)
    if not filename:
        return ""
    return str(PurePosixPath(contract._download_root()) / filename)


def _encode_payload(
    *,
    product_id: int,
    title: str,
    file_path: str,
    targets: list[dict[str, Any]],
) -> str:
    payload = {
        "product_id": int(product_id),
        "title": title,
        "file": file_path,
        "targets": targets,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _postmeta_program(encoded_payload: str) -> str:
    """Write the exact WooCommerce variation metadata used by the admin UI.

    WooCommerce REST treats downloads.file as a URL.  The PluginTema catalog,
    however, intentionally stores a local absolute path.  Writing through
    WC_Product_Download or the REST API may normalize/reject that path.  The
    authoritative value is therefore persisted directly in _downloadable_files
    on the WordPress host and verified from the same metadata afterwards.
    """
    return (
        "$cfg=json_decode(base64_decode('" + encoded_payload + "'),true);"
        "if(!is_array($cfg)){throw new Exception('payload invalido');}"
        "$title=(string)($cfg['title']??'');$file=(string)($cfg['file']??'');"
        "$product_id=(int)($cfg['product_id']??0);$out=array();"
        "foreach(($cfg['targets']??array()) as $target){"
        "$id=(int)($target['id']??0);$period=(string)($target['period']??'');"
        "if($id<=0){throw new Exception('id de variacao invalido');}"
        "$files=get_post_meta($id,'_downloadable_files',true);"
        "if(!is_array($files)){$files=array();}"
        "$first_key='';$first=array();"
        "foreach($files as $key=>$row){$first_key=(string)$key;$first=is_array($row)?$row:array();break;}"
        "if($first_key===''){$first_key=md5($file);}"
        "$expiry=$period==='annual'?'365':'-1';"
        "$same=count($files)===1"
        " && (string)($first['name']??'')===$title"
        " && (string)($first['file']??'')===$file"
        " && (string)get_post_meta($id,'_download_expiry',true)===$expiry"
        " && (string)get_post_meta($id,'_downloadable',true)==='yes'"
        " && (string)get_post_meta($id,'_virtual',true)==='yes';"
        "if(!$same){"
        "$new=array($first_key=>array('name'=>$title,'file'=>$file));"
        "update_post_meta($id,'_downloadable_files',$new);"
        "update_post_meta($id,'_downloadable','yes');"
        "update_post_meta($id,'_virtual','yes');"
        "update_post_meta($id,'_download_expiry',$expiry);"
        "clean_post_cache($id);"
        "}"
        "$verify=get_post_meta($id,'_downloadable_files',true);"
        "$verify=is_array($verify)?$verify:array();$vfirst=array();"
        "foreach($verify as $vrow){$vfirst=is_array($vrow)?$vrow:array();break;}"
        "$out[]=array('id'=>$id,'period'=>$period,'changed'=>!$same,"
        "'name'=>(string)($vfirst['name']??''),'file'=>(string)($vfirst['file']??''),"
        "'expiry'=>(string)get_post_meta($id,'_download_expiry',true),"
        "'downloadable'=>(string)get_post_meta($id,'_downloadable',true),"
        "'virtual'=>(string)get_post_meta($id,'_virtual',true));"
        "}"
        "if(function_exists('wc_delete_product_transients')&&$product_id>0){wc_delete_product_transients($product_id);}"
        "echo json_encode(array('ok'=>true,'variations'=>$out),JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);"
    )


def _json_from_stdout(raw: str) -> Mapping[str, Any]:
    text = str(raw or "").strip()
    candidates = [text] + [line.strip() for line in reversed(text.splitlines()) if line.strip().startswith("{")]
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except Exception:
            continue
        if isinstance(value, Mapping):
            return value
    return {}


def _exec_remote(client: Any, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return int(stdout.channel.recv_exit_status()), out, err


def _apply_postmeta_server(
    *,
    product_id: int,
    title: str,
    file_path: str,
    targets: list[dict[str, Any]],
    ssh: ReadOnlySSHStorage | None = None,
) -> Mapping[str, Any]:
    encoded = _encode_payload(
        product_id=product_id,
        title=title,
        file_path=file_path,
        targets=targets,
    )
    program = _postmeta_program(encoded)
    root = contract._wordpress_root()
    wp_command = "wp --path=" + shlex.quote(root) + " --allow-root eval " + shlex.quote(program)
    php_program = "require_once " + repr(str(PurePosixPath(root) / "wp-load.php")) + ";" + program
    php_command = "php -r " + shlex.quote(php_program)

    owned = ssh is None
    reader = ssh or ReadOnlySSHStorage.from_env()
    try:
        if owned:
            reader.connect()
        client = getattr(reader, "_client", None)
        if client is None:
            raise RuntimeError("Conexão SSH não disponível para corrigir os arquivos baixáveis.")

        attempts: list[str] = []
        for label, command in (("wp-cli", wp_command), ("php-cli", php_command)):
            try:
                status, out, err = _exec_remote(client, command)
            except Exception as error:
                attempts.append(f"{label}: {sanitize_text(error)}")
                continue
            result = _json_from_stdout(out)
            if status == 0 and result.get("ok") is True:
                return result
            detail = _clean(err) or _clean(out) or f"exit {status}"
            attempts.append(f"{label}: {detail[:500]}")

        raise RuntimeError(
            "Não foi possível gravar o contrato de download diretamente no WordPress. "
            + " | ".join(attempts[-2:])
        )
    finally:
        if owned:
            try:
                reader.close()
            except Exception:
                pass


def _server_row_matches(row: Mapping[str, Any], *, title: str, file_path: str) -> bool:
    period = _clean(row.get("period"))
    if period not in {"annual", "lifetime"}:
        return False
    expected_expiry = _ANNUAL_EXPIRY if period == "annual" else -1
    return (
        html_lib.unescape(_clean(row.get("name"))) == title
        and _clean(row.get("file")) == file_path
        and _safe_int(row.get("expiry"), -999) == expected_expiry
        and _clean(row.get("downloadable")) == "yes"
        and _clean(row.get("virtual")) == "yes"
    )


def _apply_download_contract_v2(
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
    title = contract._download_name(job)
    file_path = _target_file_path(job, variations)
    if not title:
        raise RuntimeError("O produto não possui nome válido para o arquivo baixável.")
    if not file_path:
        raise RuntimeError("Não foi possível determinar o ZIP remoto do produto.")

    by_period: dict[str, Mapping[str, Any]] = {}
    for variation in variations:
        if not isinstance(variation, Mapping):
            continue
        period = variation_period(variation)
        variation_id = _safe_int(variation.get("id"))
        if period in {"annual", "lifetime"} and variation_id > 0:
            by_period[period] = variation
    if set(by_period) != {"annual", "lifetime"}:
        raise RuntimeError("Não foi possível identificar as variações 1 Ano e Vitalício do produto.")

    targets = [
        {"id": _safe_int(by_period[period].get("id")), "period": period}
        for period in ("annual", "lifetime")
    ]
    result = _apply_postmeta_server(
        product_id=product_id,
        title=title,
        file_path=file_path,
        targets=targets,
        ssh=ssh,
    )
    rows = [row for row in result.get("variations", []) or [] if isinstance(row, Mapping)]
    verified = {str(row.get("period") or ""): row for row in rows}
    if set(verified) != {"annual", "lifetime"}:
        raise RuntimeError("O servidor não devolveu a confirmação das duas variações após a gravação.")
    for period in ("annual", "lifetime"):
        if not _server_row_matches(verified[period], title=title, file_path=file_path):
            label = "1 Ano" if period == "annual" else "Vitalício"
            raise RuntimeError(
                f"O WordPress não confirmou nome, caminho interno e validade da variação {label}."
            )

    repaired = sum(1 for row in rows if bool(row.get("changed")))
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
                f"Contrato de download corrigido diretamente no WordPress #{product_id}: "
                f"nome humano, caminho interno {file_path}, 365 dias em 1 Ano e Vitalício sem expiração."
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


def _validate_store_product_v2(
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
    _apply_download_contract_v2(job_id)
    return product, variations


def _repair_existing_additions_v2() -> dict[str, Any]:
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
        ssh = ReadOnlySSHStorage.from_env()
        ssh.connect()
    except Exception as error:
        return {
            "checked": 0,
            "repaired_products": 0,
            "repaired_variations": 0,
            "errors": [f"WooCommerce/SSH indisponível: {_clean(error)}"],
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
                result = _apply_download_contract_v2(job_id, woo=woo, emit=True, ssh=ssh)
                count = _safe_int(result.get("repaired_variations"))
                repaired_variations += count
                repaired_products += 1 if count else 0
            except Exception as error:
                errors.append(f"{job_id}: {_clean(error)}")
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


def install_addition_download_contract_v2_policy() -> None:
    global _INSTALLED, _BASE_VALIDATE_STORE_PRODUCT
    if _INSTALLED:
        return

    # The old contract correctly established the desired values, but validated
    # the local path through REST.  Keep its creation/sync wrappers and replace
    # only the authoritative implementation they resolve at runtime.
    contract._apply_download_contract = _apply_download_contract_v2
    contract._repair_existing_additions = _repair_existing_additions_v2

    # Retry was installed after the original contract and therefore captured
    # that wrapper as its base. Point retry back at the true store validator so
    # its short-description recovery remains available without re-entering the
    # obsolete REST download validation.
    original_base = contract._BASE_VALIDATE_STORE_PRODUCT
    if original_base is None:
        raise RuntimeError("Validador WooCommerce original não foi capturado pelo contrato de download.")
    retry._BASE_VALIDATE_STORE_PRODUCT = original_base
    _BASE_VALIDATE_STORE_PRODUCT = retry._validate_store_product_recovering
    full_creation._validate_store_product = _validate_store_product_v2

    _INSTALLED = True
