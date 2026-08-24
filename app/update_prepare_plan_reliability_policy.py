from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import app.operations.runtime as runtime
import app.update_operational_ui_policy as update_ui
import app.web as web
from app.operations.execution_plan import build_execution_plan
from app.operations.models import JobState


_INSTALLED = False
_BASE_WEB_SAVE_PREVIEW: Callable[..., dict[str, Any]] | None = None
_BASE_MATERIALIZE: Callable[..., list[dict[str, Any]]] | None = None

# Campos descobertos/revalidados ao vivo que podem sobreviver a uma
# rematerialização. approved_source_version NÃO entra aqui: ele é o snapshot
# auditável da comparação aprovada e deve voltar do catálogo/decisão original.
_LIVE_SOURCE_FIELDS = (
    "ultrapack_url",
    "ultrapack_version",
    "effective_source_version",
    "official_url",
    "source_name",
    "relationship",
)
_ADVANCED_STATES = {
    JobState.PREPARED,
    JobState.PLAN_READY,
    JobState.QUEUED,
}


def _version(value: Any) -> tuple[int, ...] | None:
    text = str(value or "").strip()
    parts = text.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def _compare_versions(left: Any, right: Any) -> int | None:
    a, b = _version(left), _version(right)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    aa = a + (0,) * (width - len(a))
    bb = b + (0,) * (width - len(b))
    return (aa > bb) - (aa < bb)


def _version_ge(left: Any, right: Any) -> bool:
    compared = _compare_versions(left, right)
    if compared is None:
        return False
    return compared >= 0


def _best_old_version(snapshot: Mapping[str, Any]) -> str:
    effective = str(snapshot.get("effective_source_version") or "").strip()
    approved = str(snapshot.get("approved_source_version") or "").strip()
    if _version_ge(effective, approved):
        return effective
    return approved


def _snapshot_source_state() -> dict[str, dict[str, Any]]:
    with runtime._LOCK:
        result: dict[str, dict[str, Any]] = {}
        for job in runtime._JOBS.values():
            result[job.comparison_item_id] = {
                "state": job.state,
                "approved_source_version": getattr(job, "approved_source_version", ""),
                **{field: getattr(job, field, "") for field in _LIVE_SOURCE_FIELDS},
            }
        return result


def _materialize_preserving_live_source(
    comparison_rows: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Preserva fonte ao vivo sem reescrever o snapshot aprovado da comparação.

    O PREPARAR pode descobrir 2.36.0 enquanto a decisão persistida ainda contém
    2.35.2. A URL e a versão efetiva ao vivo podem sobreviver à rematerialização,
    mas approved_source_version deve continuar 2.35.2 para manter o plano e a
    auditoria coerentes.
    """
    if _BASE_MATERIALIZE is None:
        raise RuntimeError("Materialização base indisponível")

    previous = _snapshot_source_state()
    _BASE_MATERIALIZE(comparison_rows)
    changed = False

    with runtime._LOCK:
        for job in runtime._JOBS.values():
            old = previous.get(job.comparison_item_id)
            if not old:
                continue

            old_best = _best_old_version(old)
            new_approved = str(getattr(job, "approved_source_version", "") or "").strip()
            old_state = old.get("state")
            should_preserve = bool(
                old_best
                and _version_ge(old_best, new_approved)
                and (
                    old_state in _ADVANCED_STATES
                    or _version(old_best) != _version(new_approved)
                )
            )
            if not should_preserve:
                continue

            for field in _LIVE_SOURCE_FIELDS:
                value = old.get(field)
                if value not in (None, "") and getattr(job, field, "") != value:
                    setattr(job, field, value)
                    changed = True

        if changed:
            runtime._persist()

        return [
            runtime.job_public(job)
            for job in runtime._JOBS.values()
            if job.queue_type == "update"
        ]


def _reconcile_approved_snapshot(
    job: Any,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Reconcilia somente drift seguro do snapshot aprovado antes do plano.

    O erro real observado no AffiliateWP foi:
    ``Snapshot aprovado do job diverge do preview preparado``. Isso pode ocorrer
    quando uma política antiga gravou a versão ao vivo (2.36.0) em
    approved_source_version enquanto o preview preservou corretamente a versão
    aprovada na comparação (2.35.2), ou no sentido inverso após rematerialização.

    A reconciliação só é permitida quando:
    - o preview já está integralmente pronto;
    - o ZIP novo foi validado;
    - a versão efetiva do job é a mesma do preview;
    - os dois snapshots divergentes são versões válidas e não superam a versão
      efetiva realmente validada na fonte.

    Nessa situação escolhemos o snapshot mais antigo, que é o registro auditável
    mais conservador. A versão que será instalada continua sendo a efetiva.
    """
    normalized = dict(preview)
    versions = dict(normalized.get("versions") or {})
    preview_approved = str(versions.get("approved_source_version") or "").strip()
    job_approved = str(getattr(job, "approved_source_version", "") or "").strip()
    effective = str(versions.get("effective_source_version") or "").strip()
    job_effective = str(getattr(job, "effective_source_version", "") or "").strip()

    if preview_approved == job_approved:
        return normalized, False
    if normalized.get("ready") is not True:
        return normalized, False
    if not str((normalized.get("new_zip") or {}).get("sha256") or "").strip():
        return normalized, False
    if not preview_approved or not job_approved or not effective:
        return normalized, False
    if job_effective and _compare_versions(job_effective, effective) != 0:
        return normalized, False

    preview_vs_effective = _compare_versions(preview_approved, effective)
    job_vs_effective = _compare_versions(job_approved, effective)
    approved_compare = _compare_versions(preview_approved, job_approved)
    if (
        preview_vs_effective is None
        or job_vs_effective is None
        or approved_compare is None
        or preview_vs_effective > 0
        or job_vs_effective > 0
    ):
        return normalized, False

    canonical = preview_approved if approved_compare <= 0 else job_approved
    changed = False

    if job_approved != canonical:
        job.approved_source_version = canonical
        changed = True

    if preview_approved != canonical:
        versions["approved_source_version"] = canonical
        if "ultrapack_approved" in versions:
            versions["ultrapack_approved"] = canonical
        normalized["versions"] = versions
        changed = True

    if changed and callable(logger):
        logger(
            "ℹ Snapshot aprovado reconciliado com segurança: "
            f"job={job_approved}, preview={preview_approved}, auditável={canonical}, "
            f"versão efetiva={effective}."
        )
    return normalized, changed


def _build_and_save_plan(job_id: str, preview: Mapping[str, Any]) -> dict[str, Any] | None:
    if preview.get("ready") is not True:
        return None

    job = runtime.get_job(job_id)
    if job.state in {JobState.EXECUTING, JobState.COMPLETED}:
        return runtime.get_plan(job_id) if job_id in runtime._PLANS else None

    logger = web._UPDATE_LOGS.for_job(job_id)
    normalized_preview, reconciled = _reconcile_approved_snapshot(
        job, preview, logger=logger.log
    )
    if reconciled:
        # Mantém runtime, preview e job coerentes antes de chamar o validador
        # estrito do plano. save_preview também invalida qualquer plano stale.
        runtime.save_preview(job_id, normalized_preview)
        runtime.persist_job(job)

    plan = build_execution_plan(job, normalized_preview, logger=logger.log)
    plan["update_logs"] = logger.to_list()
    runtime.save_plan(job_id, plan)
    runtime.persist_job(job)
    return plan


def _save_preview_and_plan(job_id: str, preview: Mapping[str, Any]) -> dict[str, Any]:
    """PREPARAR passa a terminar já com plano pronto quando o preview é válido."""
    if _BASE_WEB_SAVE_PREVIEW is None:
        raise RuntimeError("Persistência de preview indisponível")

    saved = _BASE_WEB_SAVE_PREVIEW(job_id, preview)
    if saved.get("ready") is not True:
        return saved

    try:
        _build_and_save_plan(job_id, saved)
    except Exception as error:
        job = runtime.get_job(job_id)
        job.execution_error = f"Falha ao gerar plano automaticamente: {type(error).__name__}: {error}"
        job.set_state(JobState.BLOCKED, "Preview válido, mas a geração do plano falhou")
        runtime.persist_job(job)
        web._UPDATE_LOGS.for_job(job_id).log(job.execution_error)
        raise
    return saved


def _repair_ready_previews() -> int:
    """Recupera jobs antigos que ficaram Aprovado/Bloqueado com preview válido."""
    repaired = 0
    with runtime._LOCK:
        candidates = [
            job.job_id
            for job in runtime._JOBS.values()
            if job.state in {JobState.APPROVED, JobState.PREPARED, JobState.BLOCKED}
            and (runtime._PREVIEWS.get(job.job_id) or {}).get("ready") is True
        ]

    for job_id in candidates:
        preview = runtime.get_preview(job_id)
        local_path = str((preview.get("new_zip") or {}).get("path") or "").strip()
        if not local_path or not Path(local_path).is_file():
            continue
        try:
            _build_and_save_plan(job_id, preview)
            repaired += 1
        except Exception:
            continue
    return repaired


def install_update_prepare_plan_reliability_policy() -> None:
    global _INSTALLED, _BASE_WEB_SAVE_PREVIEW, _BASE_MATERIALIZE
    if _INSTALLED:
        return

    _BASE_WEB_SAVE_PREVIEW = web.save_preview
    web.save_preview = _save_preview_and_plan

    _BASE_MATERIALIZE = runtime.materialize
    runtime.materialize = _materialize_preserving_live_source

    # update_operational_ui_policy foi instalada antes e guardou uma referência
    # à materialização antiga. Troque também essa referência para fechar a corrida.
    if getattr(update_ui, "_BASE_MATERIALIZE", None) is not None:
        update_ui._BASE_MATERIALIZE = _materialize_preserving_live_source

    # Também recupera o estado Bloqueado produzido pela versão anterior da policy
    # quando o único erro era a divergência do snapshot aprovado.
    _repair_ready_previews()
    _INSTALLED = True
