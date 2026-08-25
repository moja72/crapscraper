from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

import app.operational_simple_flow_policy as simple_flow
import app.operations.runtime as runtime
import app.staging_reuse_policy as staging_reuse
import app.web as web
from app.integrations.plugintheme_download import SourceDownloader


_INSTALLED = False
_BASE_PREPARE_UPDATE: Callable[..., Any] | None = None
_BASE_EXECUTE_UPDATE_ONE: Callable[..., Any] | None = None
_BASE_CANDIDATE_PATHS: Callable[..., list[Path]] | None = None

_AUTH_FAILURE_MARKERS = (
    "http 401",
    "http 403",
    "unauthorized",
    "forbidden",
    "botao real de download nao encontrado",
    "botão real de download não encontrado",
    "sessao expirada",
    "sessão expirada",
    "sessao invalida",
    "sessão inválida",
    "nao autentic",
    "não autentic",
    "login",
)

_TRANSIENT_LOCAL_MARKERS = (
    "[errno 2]",
    "no such file",
    "arquivo ou diretório inexistente",
    "arquivo ou diretorio inexistente",
)

_METADATA_MARKERS = {
    "wrong owner for": (
        "O ZIP atual do servidor está com proprietário fora do padrão seguro. "
        "Ajuste o arquivo para owner=plugi2090, group=nobody e mode=0674 e execute novamente."
    ),
    "wrong group for": (
        "O ZIP atual do servidor está com grupo fora do padrão seguro. "
        "Ajuste o arquivo para owner=plugi2090, group=nobody e mode=0674 e execute novamente."
    ),
    "wrong mode for": (
        "O ZIP atual do servidor está com permissões fora do padrão seguro. "
        "Ajuste o arquivo para owner=plugi2090, group=nobody e mode=0674 e execute novamente."
    ),
}


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _validation_reason(preview: Mapping[str, Any] | None) -> str:
    data = dict(preview or {})
    validations = data.get("validations")
    if not isinstance(validations, list):
        return _normalize(data.get("message") or data.get("error"))

    rows = [dict(item) for item in validations if isinstance(item, Mapping)]
    priority = (
        "ultrapack",
        "source",
        "downloaded",
        "new_zip",
        "current_zip",
        "downloads",
        "version",
        "relationship",
        "product",
        "backup",
    )

    def blocked(item: Mapping[str, Any]) -> bool:
        if str(item.get("level") or "").strip().lower() == "info":
            return False
        return item.get("ok") is False

    for key in priority:
        for item in rows:
            if str(item.get("key") or "").strip().lower() != key:
                continue
            if not blocked(item):
                continue
            detail = _normalize(item.get("detail") or item.get("message"))
            if detail:
                return detail

    for item in rows:
        if blocked(item):
            detail = _normalize(item.get("detail") or item.get("message"))
            if detail:
                return detail

    return _normalize(data.get("message") or data.get("error"))


def _job_block_reason(job: Any) -> str:
    try:
        reason = _validation_reason(runtime.get_preview(str(getattr(job, "job_id", "") or "")))
    except Exception:
        reason = ""
    if reason:
        return reason
    return _normalize(getattr(job, "execution_error", ""))


def _is_auth_failure(message: Any) -> bool:
    lowered = _normalize(message).lower()
    return any(marker in lowered for marker in _AUTH_FAILURE_MARKERS)


def _is_transient_local_failure(message: Any) -> bool:
    lowered = _normalize(message).lower()
    return any(marker in lowered for marker in _TRANSIENT_LOCAL_MARKERS)


def _close_session(session: Any) -> None:
    close = getattr(session, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def _invalidate_source_session(primary: Any, job: Any, logger: Any) -> None:
    source_url = _normalize(getattr(job, "ultrapack_url", ""))
    attr = (
        "plugintheme_http_session"
        if SourceDownloader.is_plugintheme(source_url)
        else "ultrapack_http_session"
    )
    current = getattr(primary, attr, None)
    _close_session(current)
    try:
        setattr(primary, attr, None)
    except Exception:
        pass
    logger.log(
        "♻ A sessão HTTP da fonte foi descartada após falha de autenticação; "
        "o CrapScraper fará uma nova autenticação antes da segunda tentativa."
    )


def _friendly_block_message(reason: Any) -> str:
    detail = _normalize(reason)
    if not detail:
        return "A preparação foi bloqueada por uma validação técnica. Abra os detalhes do produto."
    return f"Preparação bloqueada: {detail}"


def _friendly_execution_message(error: Any) -> str:
    detail = _normalize(error)
    lowered = detail.lower()
    for marker, message in _METADATA_MARKERS.items():
        if marker in lowered:
            return f"{message} Nenhuma alteração foi aplicada ao produto. Detalhe: {detail}"
    return detail


def _patched_prepare_update(job: Any, manager: Any, logger: Any):
    if _BASE_PREPARE_UPDATE is None:
        raise RuntimeError("Fluxo simplificado base indisponível")

    try:
        return _BASE_PREPARE_UPDATE(job, manager, logger)
    except Exception as first_error:
        first_reason = _job_block_reason(job) or _normalize(first_error)
        recover_auth = _is_auth_failure(first_reason)
        recover_local = _is_transient_local_failure(first_reason)

        if not (recover_auth or recover_local):
            raise RuntimeError(_friendly_block_message(first_reason)) from None

        if recover_auth:
            primary = web._get_primary_app(manager)
            _invalidate_source_session(primary, job, logger)
        else:
            logger.log(
                "♻ Artefato local transitório desapareceu durante a preparação; "
                "repetindo a preparação uma única vez."
            )

        try:
            result = _BASE_PREPARE_UPDATE(job, manager, logger)
        except Exception as second_error:
            second_reason = _job_block_reason(job) or _normalize(second_error)
            raise RuntimeError(_friendly_block_message(second_reason)) from None

        logger.log("✅ Preparação recuperada automaticamente na segunda tentativa.")
        return result


def _patched_execute_update_one(job_id: str, manager: Any):
    if _BASE_EXECUTE_UPDATE_ONE is None:
        raise RuntimeError("Executor simplificado base indisponível")
    try:
        return _BASE_EXECUTE_UPDATE_ONE(job_id, manager)
    except Exception as error:
        message = _friendly_execution_message(error)
        if message != _normalize(error):
            raise RuntimeError(message) from None
        raise


def _patched_candidate_paths(staging_dir: str | Path, persisted_path: str) -> list[Path]:
    """Ignora arquivos que sumiram entre glob/stat durante lotes sequenciais."""
    root = Path(staging_dir)
    candidates: list[tuple[float, Path]] = []

    persisted = Path(persisted_path) if persisted_path else None
    if persisted is not None:
        try:
            if persisted.is_file():
                candidates.append((persisted.stat().st_mtime, persisted))
        except OSError:
            pass

    try:
        discovered = list(root.glob("*.zip")) if root.exists() else []
    except OSError:
        discovered = []

    known = {path for _mtime, path in candidates}
    for candidate in discovered:
        if candidate in known:
            continue
        try:
            if not candidate.is_file():
                continue
            candidates.append((candidate.stat().st_mtime, candidate))
            known.add(candidate)
        except OSError:
            # Um cleanup concorrente pode remover um ZIP entre glob() e stat().
            # Esse arquivo já não é reutilizável e deve simplesmente ser ignorado.
            continue

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [path for _mtime, path in candidates]


def install_operational_simple_flow_recovery_policy() -> None:
    global _INSTALLED, _BASE_PREPARE_UPDATE, _BASE_EXECUTE_UPDATE_ONE, _BASE_CANDIDATE_PATHS
    if _INSTALLED:
        return

    _BASE_PREPARE_UPDATE = simple_flow._prepare_update
    simple_flow._prepare_update = _patched_prepare_update

    _BASE_EXECUTE_UPDATE_ONE = simple_flow._execute_update_one
    simple_flow._execute_update_one = _patched_execute_update_one

    _BASE_CANDIDATE_PATHS = staging_reuse._candidate_paths
    staging_reuse._candidate_paths = _patched_candidate_paths

    _INSTALLED = True
