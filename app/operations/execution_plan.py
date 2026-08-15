"""Plano persistível e estritamente read-only para uma futura atualização."""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable, Mapping
import re
from uuid import uuid4
from urllib.parse import urlparse

from app import settings
from app.integrations.ssh_helper import SSHDeploymentArtifacts
from app.operations.models import JobState, OperationalJob


SAFE_RELATIONSHIPS = frozenset({"safe_auto", "manual_confirmed"})
VERSION_RE = re.compile(r"\A[0-9]+(?:\.[0-9]+)*\Z")

FUTURE_STEPS = [
    "Revalidar WooCommerce e pt_versao.",
    "Revalidar SHA-256 do ZIP remoto.",
    "Revalidar SHA-256 do ZIP local.",
    "Criar backup do ZIP atual.",
    "Enviar novo ZIP para staging remoto.",
    "Validar arquivo remoto enviado.",
    "Substituir ZIP de produção de forma atômica.",
    "Validar SHA-256 do ZIP em produção.",
    "Atualizar pt_versao para effective_source_version.",
    "Validar produto e variações WooCommerce.",
    "Executar smoke-check final.",
    "Marcar job como concluído.",
]


def _require(value: Any, label: str) -> Any:
    if value in (None, "", [], {}):
        raise ValueError(f"Preview preparado não possui {label}")
    return value


def build_execution_plan(
    job: OperationalJob,
    preview: Mapping[str, Any],
    *,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Transforma somente dados preparados em plano; não recebe clientes de escrita."""
    log = logger or (lambda _message: None)
    log("🧭 Gerando plano de execução")
    if preview.get("ready") is not True:
        raise ValueError("Plano só pode ser criado quando preview.ready=true")

    log("🔎 Registrando estado atual")
    versions = dict(preview.get("versions") or {})
    site_version = str(_require(versions.get("site_version"), "site_version"))
    approved = str(_require(versions.get("approved_source_version"), "approved_source_version"))
    effective = str(_require(versions.get("effective_source_version"), "effective_source_version"))
    if not VERSION_RE.fullmatch(effective):
        raise ValueError("effective_source_version inválida")
    if approved != job.approved_source_version:
        raise ValueError("Snapshot aprovado do job diverge do preview preparado")
    if job.relationship not in SAFE_RELATIONSHIPS:
        raise ValueError("Vínculo do job não é seguro")

    log("📦 Registrando ZIP atual")
    current = dict(preview.get("current_zip") or {})
    remote_path = str(_require(preview.get("physical_path") or current.get("path"), "caminho do ZIP atual"))
    remote_name = PurePosixPath(remote_path).name
    current_sha = str(_require(current.get("sha256"), "SHA-256 do ZIP atual"))
    artifacts = dict(SSHDeploymentArtifacts(remote_name, job.job_id).paths())

    log("📥 Registrando ZIP preparado")
    fresh = dict(preview.get("new_zip") or {})
    local_path = str(_require(fresh.get("path"), "caminho local do novo ZIP"))
    new_sha = str(_require(fresh.get("sha256"), "SHA-256 do novo ZIP"))
    entries = int(fresh.get("entries") or 0)
    if entries <= 0:
        raise ValueError("Preview preparado não possui quantidade de entries do novo ZIP")

    downloads = [dict(item) for item in (preview.get("downloads") or [])]
    variations = [int(item) for item in (preview.get("variations") or [])]
    rollback_snapshot = dict(preview.get("rollback_snapshot") or {})
    _require(downloads, "downloads WooCommerce originais")
    _require(variations, "variation IDs")
    _require(rollback_snapshot.get("pt_versao"), "pt_versao original do rollback")

    log("🛡 Gerando preconditions")
    preconditions = [
        {"key": "woo_product_id", "label": "WooCommerce ID continua o mesmo", "expected": job.woo_product_id},
        {"key": "pt_versao", "label": "pt_versao continua igual ao valor preparado", "expected": site_version},
        {"key": "remote_zip_sha256", "label": "SHA-256 do ZIP remoto continua igual", "expected": current_sha},
        {"key": "relationship", "label": "relationship continua seguro", "expected": job.relationship,
         "allowed": sorted(SAFE_RELATIONSHIPS)},
        {"key": "local_zip_exists", "label": "novo ZIP local continua existindo", "expected": True,
         "path": local_path},
        {"key": "local_zip_sha256", "label": "SHA-256 do novo ZIP continua igual", "expected": new_sha},
        {"key": "effective_source_version", "label": "effective_source_version continua válida",
         "expected": effective, "format": "numeric_dotted"},
    ]

    log("↩ Gerando plano de rollback")
    rollback = {
        "original_zip": remote_path,
        "original_sha256": current_sha,
        "original_pt_versao": site_version,
        "original_variations": rollback_snapshot.get("variations") or [],
        "original_downloads": downloads,
        "backup_path": artifacts["backup"],
        "steps": [
            "Restaurar o ZIP original a partir do backup planejado.",
            f"Validar o ZIP restaurado pelo SHA-256 {current_sha}.",
            f"Restaurar pt_versao para {site_version}.",
            "Restaurar referências, IDs e nomes de downloads WooCommerce originais, caso alterados.",
            "Reler produto e variações e validar o estado restaurado.",
        ],
        "checklist": [
            {"label": "rollback possui ZIP original", "ok": bool(remote_path)},
            {"label": "rollback possui hash original", "ok": bool(current_sha)},
            {"label": "rollback possui pt_versao original", "ok": bool(site_version)},
            {"label": "rollback possui estado WooCommerce original",
             "ok": bool(rollback_snapshot.get("variations") and downloads)},
        ],
    }

    plan = {
        "plan_id": str(uuid4()),
        "schema_version": 1,
        "state": "ready_for_homologation",
        "ready": True,
        "execution_enabled": settings.UPDATE_EXECUTION_ENABLED,
        "job_id": job.job_id,
        "comparison_item_id": job.comparison_item_id,
        "woo_product_id": job.woo_product_id,
        "product": dict(preview.get("product") or {"name": job.name}),
        "relationship": job.relationship,
        "site_version": site_version,
        "approved_source_version": approved,
        "effective_source_version": effective,
        "origin": {
            "type": "PluginTheme" if "plugintheme.net" in (urlparse(job.ultrapack_url).hostname or "") else "UltraPackV2",
            "version": effective, "local_staging_path": local_path,
        },
        "destination": {"type": "PluginTema", "woo_product_id": job.woo_product_id,
                        "remote_path": remote_path},
        "current_zip": {
            "remote_path": remote_path, "name": remote_name,
            "size": current.get("size"), "sha256": current_sha,
            "owner": current.get("owner", ""), "group": current.get("group", ""),
            "mode": current.get("mode", ""),
        },
        "new_zip": {
            "local_staging_path": local_path,
            "name": fresh.get("file_name") or PurePosixPath(local_path).name,
            "size": fresh.get("size"), "sha256": new_sha, "entries": entries,
        },
        "woocommerce": {
            "variation_ids": variations,
            "download_ids": [str(item.get("id") or "") for item in downloads],
            "download_names": [str(item.get("name") or "") for item in downloads],
            "current_file": remote_path,
            "future_file": remote_path,
            "original_downloads": downloads,
        },
        "wordpress": {"pt_versao_current": site_version, "pt_versao_future": effective},
        "backup": {"path": artifacts["backup"], "name": PurePosixPath(artifacts["backup"]).name,
                   "expected_original_sha256": current_sha},
        "remote_staging": {"upload_path": artifacts["upload"], "prepared_path": artifacts["new"]},
        "preconditions": preconditions,
        "planned_steps": list(FUTURE_STEPS),
        "rollback": rollback,
        "status_label": "Plano pronto para homologação",
        "execution_label": "Execução real ainda bloqueada para homologação",
    }
    job.effective_source_version = effective
    job.remote_staging_path = artifacts["upload"]
    job.backup_path = artifacts["backup"]
    job.set_state(JobState.PLAN_READY, "Plano de execução pronto")
    log("✅ Plano de execução pronto")
    return plan


def evaluate_preconditions(plan: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    """Compara futuras leituras com o snapshot, sem executar qualquer correção."""
    checks = []
    for item in plan.get("preconditions", []) or []:
        key = str(item.get("key") or "")
        actual = observed.get(key)
        ok = actual == item.get("expected")
        if key == "relationship":
            ok = ok and actual in SAFE_RELATIONSHIPS
        elif key == "effective_source_version":
            ok = ok and bool(VERSION_RE.fullmatch(str(actual or "")))
        checks.append({"key": key, "label": item.get("label", key), "ok": ok,
                       "expected": item.get("expected"), "actual": actual})
    ready = bool(checks) and all(item["ok"] for item in checks)
    return {
        "ready": ready,
        "state": "ready" if ready else "blocked",
        "message": "Preconditions válidas" if ready else "BLOCKED — preparação ficou desatualizada",
        "checks": checks,
    }
