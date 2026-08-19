from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import app.addition_final_validation_policy as final_validation
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple
import app.addition_two_stage_creation_policy as two_stage
import app.new_product_workflow_policy as additions
from app.integrations.woocommerce import metadata_value
from app.integrations.wordpress import sanitize_text
from app.store_pricing import variation_period


_INSTALLED = False


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _price(value: Any) -> str:
    raw = _norm(value).replace("R$", "").strip()
    if not raw:
        return ""
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return f"{float(raw):.2f}"
    except Exception:
        return raw


def _category_ids(product: Mapping[str, Any]) -> set[int]:
    return {
        int(item.get("id") or 0)
        for item in (product.get("categories") or [])
        if isinstance(item, Mapping) and int(item.get("id") or 0)
    }


def _variation_map(variations: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for variation in variations:
        period = variation_period(variation)
        if period in {"annual", "lifetime"}:
            if period in result:
                raise RuntimeError(f"O WooCommerce retornou mais de uma variação para o período {period}.")
            result[period] = variation
    return result


def _validate_store_product(
    job_id: str,
    *,
    expected_status: str,
    progress: int,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("WooCommerce ID ausente durante a validação do produto completo.")

    woo = additions.web._build_store_woocommerce_client()
    product = woo.get_product_fresh(product_id)
    variations = list(woo.list_variations_fresh(product_id, per_page=100) or [])

    if str(product.get("status") or "") != expected_status:
        raise RuntimeError(
            f"WooCommerce não confirmou o status {expected_status!r} do produto #{product_id}."
        )
    if str(product.get("type") or "").lower() != "variable":
        raise RuntimeError("O produto precisa ser do tipo variable.")

    root_category_id, root_category_name = simple._root_category(woo, simple._kind(job))
    if root_category_id not in _category_ids(product):
        raise RuntimeError(
            f"O produto não confirmou a categoria raiz {root_category_name}."
        )

    version = _norm(job.get("source_version"))
    stored_version = _norm(metadata_value(product, "pt_versao"))
    if not version or stored_version != version:
        raise RuntimeError(
            f"O campo pt_versao não confere: esperado {version or '(vazio)'}, recebido {stored_version or '(vazio)'}."
        )

    if len(variations) != 2:
        raise RuntimeError(
            f"O produto precisa ter exatamente duas variações; WooCommerce retornou {len(variations)}."
        )
    by_period = _variation_map(variations)
    if set(by_period) != {"annual", "lifetime"}:
        raise RuntimeError("As duas variações obrigatórias Anual e Vitalício não foram confirmadas.")

    expected_download = _norm(job.get("remote_file_path"))
    expected_filename = _norm(job.get("remote_file_name"))
    if not expected_download or not expected_filename:
        raise RuntimeError("O ZIP remoto não foi persistido no job antes da validação das variações.")

    for period, label in (("annual", "Anual"), ("lifetime", "Vitalício")):
        variation = by_period[period]
        if not bool(variation.get("downloadable")) or not bool(variation.get("virtual")):
            raise RuntimeError(f"A variação {label} precisa ser virtual e downloadable.")

        expected_regular = _price(job.get(f"{period}_regular"))
        expected_sale = _price(job.get(f"{period}_sale"))
        actual_regular = _price(variation.get("regular_price"))
        actual_sale = _price(variation.get("sale_price"))
        if actual_regular != expected_regular or actual_sale != expected_sale:
            raise RuntimeError(
                f"Os preços da variação {label} não conferem: "
                f"esperado {expected_regular}/{expected_sale or '-'}, "
                f"recebido {actual_regular}/{actual_sale or '-'} ."
            )

        downloads = [item for item in (variation.get("downloads") or []) if isinstance(item, Mapping)]
        if len(downloads) != 1:
            raise RuntimeError(f"A variação {label} precisa ter exatamente um download.")
        download = downloads[0]
        if _norm(download.get("file")) != expected_download:
            raise RuntimeError(f"O download da variação {label} não aponta para o ZIP remoto esperado.")
        if _norm(download.get("name")) != expected_filename:
            raise RuntimeError(f"O nome do download da variação {label} não confere.")

    one_click._emit(
        job_id,
        f"Produto #{product_id} validado: variable, pt_versao={version}, categoria {root_category_name}, "
        "variações Anual/Vitalício, preços e ZIP confirmados.",
        step="store_validation",
        progress=progress,
    )
    return product, variations


def _ensure_download_and_prices(job_id: str, manager: Any) -> dict[str, Any]:
    one_click._emit(
        job_id,
        "Conteúdo visual/textual pronto. Resolvendo os preços atuais de Plugin/Tema antes de criar o produto…",
        step="pricing",
        progress=79,
    )
    job = two_stage._ensure_default_prices(job_id)

    zip_path = Path(_norm(job.get("zip_path"))) if _norm(job.get("zip_path")) else None
    if zip_path is not None and zip_path.exists():
        one_click._emit(
            job_id,
            f"ZIP local já validado ({zip_path.name}); reaproveitando o arquivo preparado.",
            step="zip_ready",
            progress=82,
        )
        return additions._recalculate_state(job_id)

    if manager is None:
        raise RuntimeError("Execução principal não disponível para autenticar e baixar o ZIP do produto.")

    one_click._emit(
        job_id,
        "Baixando o arquivo do produto na fonte autenticada e validando o ZIP antes da loja…",
        step="zip",
        progress=81,
    )
    additions._download_source(job_id, manager)
    job = additions._row(job_id)
    zip_path = Path(_norm(job.get("zip_path")))
    if not zip_path.exists() or int(job.get("zip_size") or 0) <= 0 or not _norm(job.get("zip_sha256")):
        raise RuntimeError("O download terminou, mas o ZIP local não passou na validação final.")
    one_click._emit(
        job_id,
        f"ZIP validado: {zip_path.name} ({int(job.get('zip_size') or 0)} bytes).",
        step="zip_ready",
        progress=84,
    )
    return additions._recalculate_state(job_id)


def _create_complete_draft(job_id: str) -> dict[str, Any]:
    one_click._emit(
        job_id,
        "Enviando o ZIP validado para /downloads/ e criando o produto variável com Anual e Vitalício…",
        step="draft",
        progress=87,
    )
    result = additions._create_or_resume_draft(job_id, "CRIAR RASCUNHO")
    job = dict(result.get("job") or additions._row(job_id))
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("WooCommerce não confirmou o ID do rascunho completo.")

    # _create_or_resume_draft usa a categoria Plugin/Tema, pt_versao e as duas variações.
    # Garanta que a categoria é especificamente a raiz escolhida pelo fluxo atual.
    woo = additions.web._build_store_woocommerce_client()
    root_category_id, _root_name = simple._root_category(woo, simple._kind(job))
    product = woo.get_product_fresh(product_id)
    if root_category_id not in _category_ids(product):
        additions._wc_request(
            woo,
            "PUT",
            f"/wp-json/wc/v3/products/{product_id}",
            {"categories": [{"id": root_category_id}]},
        )

    _validate_store_product(job_id, expected_status="draft", progress=93)
    return additions._row(job_id)


def _publish_complete(job_id: str) -> dict[str, Any]:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if not product_id:
        raise RuntimeError("Nenhum rascunho completo está disponível para publicação.")

    one_click._emit(
        job_id,
        f"Rascunho #{product_id} passou na validação completa. Publicando somente agora…",
        step="publishing",
        progress=96,
    )
    additions._publish(job_id, f"PUBLICAR {product_id}")
    _validate_store_product(job_id, expected_status="publish", progress=99)
    return additions._row(job_id)


def _run_full(job_id: str, manager: Any) -> None:
    with one_click._TASK_LOCK:
        task = one_click._task(job_id)
        task.update(
            running=True,
            done=False,
            error="",
            step="starting",
            progress=1,
            logs=[],
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            finished_at="",
        )

    try:
        job = additions._row(job_id)
        if str(job.get("state") or "") == "completed" and int(job.get("woo_product_id") or 0):
            one_click._emit(
                job_id,
                "Este produto já foi publicado e concluído. Exclua o produto remoto e use Resetar antes de repetir.",
                step="completed",
                progress=100,
            )
        else:
            one_click._emit(
                job_id,
                "Iniciando fluxo completo: descrição + imagem → preços → ZIP → produto variável → validação → publicação.",
                step="starting",
                progress=2,
            )

            # Preserva integralmente o fluxo de IA consolidado pelas policies instaladas antes desta.
            simple._run_two_chats(job_id)

            job = additions._row(job_id)
            description = final_validation._validated_description(_norm(job.get("short_description")))
            if not description:
                raise RuntimeError("A descrição capturada não passou na validação final.")
            final_validation._validate_image_file(job_id, Path(_norm(job.get("image_path"))))

            _ensure_download_and_prices(job_id, manager)
            _create_complete_draft(job_id)
            job = _publish_complete(job_id)

            product_id = int(job.get("woo_product_id") or 0)
            one_click._emit(
                job_id,
                f"Produto WooCommerce #{product_id} concluído: publicado com pt_versao, duas variações, preços e ZIP validados.",
                step="completed",
                progress=100,
            )

        with one_click._TASK_LOCK:
            task = one_click._task(job_id)
            task["running"] = False
            task["done"] = True
            task["error"] = ""
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    except Exception as error:
        message = sanitize_text(error)
        try:
            additions._update(job_id, error=message)
        except Exception:
            pass
        one_click._emit(job_id, f"ERRO: {message}", step="error")
        with one_click._TASK_LOCK:
            task = one_click._task(job_id)
            task["running"] = False
            task["done"] = False
            task["error"] = message
            task["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")


def install_addition_full_product_creation_policy() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    one_click._run = _run_full
    _INSTALLED = True
