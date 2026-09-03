from __future__ import annotations

from typing import Any

from app.comparison import decisions
from app.updates.adapters import normalize_version, product_version
from app.updates.logging import safe_message
from app.updates.manual_discovery import discover_safe_update
from app.updates.service import UpdateExecutionBlocked, UpdateService


_ORIGINAL_EXECUTION = UpdateService._execution
_ORIGINAL_EXECUTE = UpdateService.execute
_ORIGINAL_RETRY = UpdateService.retry
_AUTO_VALIDATION_BLOCKERS = {
    "woocommerce_not_validated",
    "storage_not_validated",
    "source_not_validated",
}


def _approval_signature(rows: list[dict[str, Any]]) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(
        (
            str(row.get("comparison_item_id") or ""),
            str(row.get("updated_at") or ""),
            str(row.get("source_version") or ""),
            str(row.get("site_version") or ""),
            str(row.get("source_product_url") or ""),
        )
        for row in rows
    ))


def _materialize(self: UpdateService) -> dict[str, Any]:
    approvals = decisions.list_approved_updates()
    signature = _approval_signature(approvals)
    if signature == getattr(self, "_crapscraper_materialized_signature", None):
        return {"ok": True, "created": 0, "total": self.repository.count(), "cached": True}
    with self.lock:
        result = self.repository.materialize(approvals)
        self._crapscraper_materialized_signature = signature
    return {"ok": True, **result, "cached": False}


def _version_key(self: UpdateService, value: Any) -> tuple[int, ...]:
    return self._version_key(value)


def _execution(self: UpdateService, job: dict[str, Any]) -> dict[str, Any]:
    """Mantém o botão executável quando falta apenas o preflight ainda não rodado.

    Falhas reais (credencial inválida, storage indisponível, gate, job inválido etc.)
    continuam bloqueando. A validação efetiva é feita imediatamente antes da execução.
    """
    result = dict(_ORIGINAL_EXECUTION(self, job))
    blockers = list(result.get("blockers") or [])
    if blockers and all(str(item.get("code") or "") in _AUTO_VALIDATION_BLOCKERS for item in blockers):
        return {
            **result,
            "allowed": True,
            "preflight_required": True,
            "warnings": blockers,
            "blockers": [],
        }
    return result


def _needs_environment_check(self: UpdateService, kinds: set[str]) -> bool:
    validation = self.environment_validation or {}
    if not validation.get("woocommerce") or not validation.get("storage"):
        return True
    sources = validation.get("sources") or {}
    return any(kind and kind not in sources for kind in kinds)


def _ensure_environment(self: UpdateService, kinds: set[str]) -> None:
    """Executa Verificar pré-requisitos automaticamente uma vez quando necessário."""
    if _needs_environment_check(self, kinds):
        self.verify_environment()


def _refresh_live_target(self: UpdateService, job_id: str) -> dict[str, Any]:
    """Promove a versão live da origem quando ela é mais nova que a versão do catálogo.

    A origem aprovada permanece imutável. Somente o objetivo de versão é elevado.
    Isso também cobre o caso em que o destino já alcançou a versão do catálogo, mas a
    origem publicou uma versão mais nova depois da coleta/comparação.
    """
    job = self.repository.get(job_id)
    source = self.executor.sources.get(str(job.get("source_kind") or ""))
    probe = getattr(source, "validate_access", None)
    details = probe(job) if callable(probe) else None
    live = normalize_version((details or {}).get("version") or source.confirm_version(job))
    catalog = normalize_version(job.get("source_version"))
    if not live:
        return job
    if _version_key(self, live) > _version_key(self, catalog):
        refreshed = self.repository.refresh_objective(
            job_id,
            current_version=normalize_version(job.get("current_version")),
            source_version=live,
        )
        self.repository.append_log(
            job_id,
            "",
            f"Versão live da origem {live} é superior à versão catalogada {catalog or '—'}; objetivo promovido automaticamente para {live}.",
        )
        return refreshed
    return job


def _execute(self: UpdateService, job_id: str) -> dict[str, Any]:
    job = self.repository.get(job_id)
    kind = str(job.get("source_kind") or "")
    _ensure_environment(self, {kind})
    _refresh_live_target(self, job_id)
    return _ORIGINAL_EXECUTE(self, job_id)


def _retry(self: UpdateService, job_id: str) -> dict[str, Any]:
    job = self.repository.get(job_id)
    kind = str(job.get("source_kind") or "")
    _ensure_environment(self, {kind})
    _refresh_live_target(self, job_id)
    return _ORIGINAL_RETRY(self, job_id)


def _resolve_manual_request(self: UpdateService, product_id: int) -> dict[str, Any]:
    """Resolve MU-plugin usando aprovações e vínculos exatos dos catálogos atuais."""
    product_id = int(product_id)
    self.materialize()

    reader = getattr(self.executor.woo, "get_product_fresh", None) or self.executor.woo.get_product
    product = reader(product_id)
    current = normalize_version(product_version(product))

    discovery = discover_safe_update(product, current)
    approval = discovery.get("approval") if isinstance(discovery, dict) else None
    if isinstance(approval, dict):
        self.repository.materialize([approval])

    listing = self.repository.list(query=str(product_id), page=1, page_size=100, sort_by="date", sort_order="desc")
    candidates = [item for item in listing["items"] if int(item.get("woo_product_id") or 0) == product_id]
    if not candidates:
        return {
            "ok": True,
            "state": str(discovery.get("state") or "no_match"),
            "message": str(discovery.get("message") or "Produto sem correspondência segura para atualização."),
            "discovery": discovery,
        }

    live: list[tuple[tuple[int, ...], dict[str, Any], str]] = []
    failures: list[str] = []
    for candidate in candidates:
        try:
            source = self.executor.sources.get(str(candidate.get("source_kind") or ""))
            probe = getattr(source, "validate_access", None)
            details = probe(candidate) if callable(probe) else None
            found = normalize_version((details or {}).get("version") or source.confirm_version(candidate))
            if not found:
                raise ValueError("a fonte não retornou versão")
            live.append((_version_key(self, found), candidate, found))
        except Exception as error:
            failures.append(f"{candidate.get('source_name') or candidate.get('source_kind')}: {safe_message(error)}")

    if not live:
        raise RuntimeError("Não foi possível consultar a versão atual da fonte correspondente. " + "; ".join(failures))

    _key, selected, target = max(live, key=lambda item: item[0])
    refreshed = self.repository.refresh_objective(
        str(selected["job_id"]), current_version=current, source_version=target,
    )
    state = "update_available" if _version_key(self, target) > _version_key(self, current) else "already_updated"
    return {
        "ok": True,
        "state": state,
        "stage": "checked",
        "message": (
            f"Atualização encontrada: {current} → {target}."
            if state == "update_available"
            else f"Produto já estava atualizado para a versão {current}."
        ),
        "current_version": current,
        "target_version": target,
        "item": self._with_execution(refreshed),
        "checked_sources": len(live),
        "source_errors": failures,
        "catalog_discovery": discovery,
    }


def _prepared_ids(self: UpdateService) -> list[str]:
    first = self.repository.list(group="prepared", page=1, page_size=100, sort_by="date", sort_order="asc")
    rows = list(first["items"])
    for page in range(2, int(first.get("pages") or 1) + 1):
        rows.extend(self.repository.list(group="prepared", page=page, page_size=100, sort_by="date", sort_order="asc")["items"])
    return [str(item["job_id"]) for item in rows]


def _batch_start(self: UpdateService, job_ids: list[str] | None = None) -> dict[str, Any]:
    """Valida preflight, promove versões live e executa somente os itens elegíveis."""
    requested = list(dict.fromkeys(str(item) for item in (job_ids or _prepared_ids(self)) if str(item)))
    if not requested:
        raise ValueError("Nenhum job preparado foi selecionado para execução.")

    existing: list[dict[str, Any]] = []
    missing: list[str] = []
    for job_id in requested:
        try:
            existing.append(self.repository.get(job_id))
        except KeyError:
            missing.append(job_id)

    _ensure_environment(self, {str(job.get("source_kind") or "") for job in existing})
    self._require_execution_environment()

    eligible: list[str] = []
    skipped: list[dict[str, Any]] = []
    blockers_for_error: list[dict[str, str]] = []
    for job_id in requested:
        try:
            job = self.repository.get(job_id)
        except KeyError:
            item = {"code": "job_not_found", "message": f"Job {job_id} não existe mais na fila."}
            skipped.append({"job_id": job_id, "product_name": "", "blockers": [item]})
            blockers_for_error.append(item)
            continue

        try:
            job = _refresh_live_target(self, job_id)
        except Exception as error:
            item = {"code": "source_live_probe_failed", "message": f"Não foi possível confirmar a versão live da origem: {safe_message(error)}"}
            skipped.append({"job_id": job_id, "product_name": str(job.get("product_name") or ""), "blockers": [item]})
            blockers_for_error.append(item)
            continue

        execution = self._execution(job)
        if execution.get("allowed"):
            eligible.append(job_id)
            continue
        blockers = list(execution.get("blockers") or [])
        skipped.append({"job_id": job_id, "product_name": str(job.get("product_name") or ""), "blockers": blockers})
        blockers_for_error.extend(blockers)

    if not eligible:
        unique: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for blocker in blockers_for_error:
            key = (str(blocker.get("code") or ""), str(blocker.get("message") or ""))
            if key not in seen:
                seen.add(key)
                unique.append(blocker)
        raise UpdateExecutionBlocked(unique or [{"code": "no_eligible_jobs", "message": "Nenhum item selecionado está elegível para execução."}])

    batch = self.batch.start(eligible)
    return {
        "ok": True,
        "batch": batch,
        "selected_count": len(requested),
        "queued_count": len(eligible),
        "skipped_count": len(skipped),
        "skipped": skipped,
    }


def install_update_performance_runtime() -> None:
    if getattr(UpdateService, "_crapscraper_performance_runtime_installed", False):
        return
    UpdateService.materialize = _materialize
    UpdateService._execution = _execution
    UpdateService.execute = _execute
    UpdateService.retry = _retry
    UpdateService.resolve_manual_request = _resolve_manual_request
    UpdateService.batch_start = _batch_start
    UpdateService._crapscraper_performance_runtime_installed = True


install_update_performance_runtime()

__all__ = [
    "install_update_performance_runtime",
    "_ensure_environment",
    "_refresh_live_target",
]
