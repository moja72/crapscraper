from __future__ import annotations

import html as html_lib
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import app.addition_final_validation_policy as final_validation
import app.addition_full_product_creation_policy as full_creation
import app.addition_one_click_policy as one_click
import app.addition_simple_creation_policy as simple
import app.new_product_workflow_policy as additions
import app.web as web


_INSTALLED = False
_BASE_VALIDATE_DESCRIPTION: Callable[[str], str] | None = None
_BASE_VALIDATE_STORE_PRODUCT: Callable[..., Any] | None = None
_BASE_DOWNLOAD_SOURCE: Callable[..., dict[str, Any]] | None = None
_BASE_OPEN_MANUAL_SESSION: Callable[..., dict[str, Any]] | None = None

_SESSION_MARKERS = (
    "sessão plugintheme não confirmada",
    "sessao plugintheme nao confirmada",
    "sessão do plugintheme expirada",
    "sessao do plugintheme expirada",
    "sessão plugintheme",
    "sessao plugintheme",
    "plugintheme session",
)
_CREDIT_MARKERS = (
    "crédito",
    "credito",
    "créditos",
    "creditos",
    "credit",
    "credits",
    "saldo insuficiente",
)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _plain_remote_description(value: Any) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<\s*br\s*/?\s*>", " ", text, flags=re.I)
    text = re.sub(r"</\s*p\s*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean(text.replace("\xa0", " "))


def _validated_description_html_tolerant(text: str) -> str:
    """Aceita a mesma descrição depois que WordPress/WooCommerce adiciona HTML de apresentação."""
    if _BASE_VALIDATE_DESCRIPTION is None:
        return ""
    raw = str(text or "")
    validated = _BASE_VALIDATE_DESCRIPTION(raw)
    if validated:
        return validated
    plain = _plain_remote_description(raw)
    if plain and plain != _clean(raw):
        return _BASE_VALIDATE_DESCRIPTION(plain)
    return ""


def _repair_remote_product_content(job_id: str, expected_status: str) -> bool:
    job = additions._row(job_id)
    product_id = int(job.get("woo_product_id") or 0)
    if product_id <= 0:
        return False

    local_description = _validated_description_html_tolerant(
        str(job.get("short_description") or job.get("description") or "")
    )
    if not local_description:
        return False

    woo = additions.web._build_store_woocommerce_client()
    root_category_id, root_category_name = simple._root_category(woo, simple._kind(job))
    payload: dict[str, Any] = {
        "name": str(job.get("title") or job.get("source_name") or "Novo produto").strip(),
        "description": str(job.get("description") or local_description),
        "short_description": str(job.get("short_description") or local_description),
        "categories": [{"id": root_category_id}],
    }
    if expected_status in {"draft", "publish"}:
        payload["status"] = expected_status
    media_id = int(job.get("media_id") or 0)
    if media_id:
        payload["images"] = [{"id": media_id}]

    additions._wc_request(
        woo,
        "PUT",
        f"/wp-json/wc/v3/products/{product_id}",
        payload,
    )
    one_click._emit(
        job_id,
        (
            f"Retry reparou o produto WooCommerce #{product_id}: breve descrição, conteúdo, "
            f"categoria {root_category_name} e imagem foram reaplicados antes de validar novamente."
        ),
        step="store_validation",
        progress=93 if expected_status == "draft" else 99,
    )
    return True


def _validate_store_product_recovering(
    job_id: str,
    *,
    expected_status: str,
    progress: int,
):
    if _BASE_VALIDATE_STORE_PRODUCT is None:
        raise RuntimeError("Validador WooCommerce base indisponível.")
    try:
        return _BASE_VALIDATE_STORE_PRODUCT(
            job_id,
            expected_status=expected_status,
            progress=progress,
        )
    except Exception as first_error:
        message = _clean(first_error).lower()
        if (
            "breve descrição validada" not in message
            and "descrição validada" not in message
            and "descricao validada" not in message
        ):
            raise
        if not _repair_remote_product_content(job_id, expected_status):
            raise
        return _BASE_VALIDATE_STORE_PRODUCT(
            job_id,
            expected_status=expected_status,
            progress=progress,
        )


def _is_plugintheme_session_error(error: BaseException) -> bool:
    text = str(error or "").strip().lower()
    return any(marker in text for marker in _SESSION_MARKERS)


def _is_credit_error(error: BaseException) -> bool:
    text = str(error or "").strip().lower()
    return any(marker in text for marker in _CREDIT_MARKERS)


def _unwrap_http_session(value: Any) -> Any | None:
    if value is None:
        return None
    nested = getattr(value, "session", None)
    if nested is not None and nested is not value and callable(getattr(nested, "get", None)):
        return nested
    return value if callable(getattr(value, "get", None)) else None


def _session_candidates(primary: Any) -> list[Any]:
    if primary is None:
        return []
    names = (
        "plugintheme_http_session",
        "_plugintheme_http_session",
        "plugintheme_session",
        "_plugintheme_session",
        "http_session",
        "_http_session",
    )
    result: list[Any] = []
    seen: set[int] = set()
    for name in names:
        try:
            session = _unwrap_http_session(getattr(primary, name, None))
        except Exception:
            session = None
        if session is None or id(session) in seen:
            continue
        seen.add(id(session))
        result.append(session)
    return result


def _clear_plugintheme_session_cache(primary: Any) -> None:
    if primary is not None:
        for name in (
            "plugintheme_http_session",
            "_plugintheme_http_session",
            "plugintheme_session",
            "_plugintheme_session",
        ):
            try:
                if hasattr(primary, name):
                    setattr(primary, name, None)
            except Exception:
                pass

    try:
        import app.integrations.ultrapack_session as session_module
    except Exception:
        return
    for name, value in list(vars(session_module).items()):
        lowered = name.lower()
        if "cache" not in lowered:
            continue
        if "session" not in lowered and "plugintheme" not in lowered:
            continue
        if isinstance(value, dict):
            try:
                value.clear()
            except Exception:
                pass


def _persist_download(job_id: str, artifact: Any, detected_version: Any) -> dict[str, Any]:
    job = additions._row(job_id)
    expected = _clean(job.get("source_version"))
    detected = _clean(detected_version)
    if expected and detected and expected != detected:
        raise ValueError(
            f"A versão da fonte mudou de {expected} para {detected}. Revise a comparação antes de cadastrar."
        )
    additions._update(
        job_id,
        zip_path=artifact.path,
        zip_name=artifact.file_name,
        zip_sha256=artifact.sha256,
        zip_size=int(artifact.size),
        source_version=detected or expected,
        error="",
    )
    return additions._recalculate_state(job_id)


def _direct_plugintheme_download(job_id: str, session: Any) -> dict[str, Any]:
    from app.integrations.plugintheme_download import PluginThemeDownloader

    job = additions._row(job_id)
    source_url = _clean(job.get("source_product_url"))
    staging_dir = additions._STAGING_ROOT / additions._safe_job_id(job_id)
    staging_dir.mkdir(parents=True, exist_ok=True)
    downloader = PluginThemeDownloader(session)
    artifact, detected_version = downloader.download(source_url, staging_dir)
    one_click._emit(
        job_id,
        "Sessão HTTP já aberta passou na validação real da API PluginTheme; ZIP recuperado sem repetir conteúdo/imagem.",
        step="zip",
        progress=83,
    )
    return _persist_download(job_id, artifact, detected_version)


def _download_source_recovering(job_id: str, manager: Any) -> dict[str, Any]:
    if _BASE_DOWNLOAD_SOURCE is None:
        raise RuntimeError("Downloader base indisponível.")

    job = additions._row(job_id)
    source_url = _clean(job.get("source_product_url"))
    if "plugintheme.net" not in source_url.lower():
        return _BASE_DOWNLOAD_SOURCE(job_id, manager)

    primary = web._get_primary_app(manager) if manager is not None else None
    preserved_sessions = _session_candidates(primary)
    try:
        return _BASE_DOWNLOAD_SOURCE(job_id, manager)
    except Exception as first_error:
        if _is_credit_error(first_error):
            raise
        if not _is_plugintheme_session_error(first_error):
            raise

        one_click._emit(
            job_id,
            "A sessão PluginTheme em cache foi recusada. Invalidando o cache e relendo a sessão renovada antes de desistir.",
            step="zip",
            progress=81,
        )
        _clear_plugintheme_session_cache(primary)
        time.sleep(0.5)

        try:
            return _BASE_DOWNLOAD_SOURCE(job_id, manager)
        except Exception as second_error:
            if _is_credit_error(second_error):
                raise
            if not _is_plugintheme_session_error(second_error):
                raise

            # Alguns builds locais antigos recusam a sessão pelo sinalizador `authenticated`
            # mesmo quando o requests.Session já tem cookies válidos. A API real do produto
            # é a autoridade final: check-access + download precisam aceitar a sessão.
            direct_errors: list[BaseException] = []
            for session in preserved_sessions + _session_candidates(primary):
                try:
                    return _direct_plugintheme_download(job_id, session)
                except Exception as direct_error:
                    direct_errors.append(direct_error)

            for direct_error in direct_errors:
                if _is_credit_error(direct_error):
                    raise direct_error

            raise RuntimeError(
                "Sessão PluginTheme ainda não foi confirmada após recarregar o cache. "
                "Clique em Renovar sessão PluginTheme, conclua o login na janela exclusiva, "
                "feche essa janela do Chrome por completo e então clique em Tentar novamente. "
                "O retry agora reaproveita descrição/imagem e retoma diretamente do ZIP."
            ) from second_error


def _open_manual_session_recovering(primary: Any) -> dict[str, Any]:
    if _BASE_OPEN_MANUAL_SESSION is None:
        return {"message": "Abra a sessão PluginTheme e conclua o login."}
    _clear_plugintheme_session_cache(primary)
    result = dict(_BASE_OPEN_MANUAL_SESSION(primary) or {})
    result["message"] = (
        _clean(result.get("message"))
        or "Chrome aberto. Faça login no PluginTheme e feche completamente essa janela ao concluir."
    )
    return result


def install_addition_retry_recovery_policy() -> None:
    global _INSTALLED
    global _BASE_VALIDATE_DESCRIPTION, _BASE_VALIDATE_STORE_PRODUCT, _BASE_DOWNLOAD_SOURCE
    global _BASE_OPEN_MANUAL_SESSION
    if _INSTALLED:
        return

    _BASE_VALIDATE_DESCRIPTION = final_validation._validated_description
    final_validation._validated_description = _validated_description_html_tolerant

    _BASE_VALIDATE_STORE_PRODUCT = full_creation._validate_store_product
    full_creation._validate_store_product = _validate_store_product_recovering

    _BASE_DOWNLOAD_SOURCE = additions._download_source
    additions._download_source = _download_source_recovering

    try:
        import app.integrations.plugintheme_manual_session as manual_session

        _BASE_OPEN_MANUAL_SESSION = manual_session.open_manual_plugintheme_session
        manual_session.open_manual_plugintheme_session = _open_manual_session_recovering
    except Exception:
        _BASE_OPEN_MANUAL_SESSION = None

    _INSTALLED = True
