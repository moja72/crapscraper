"""Origem única das mensagens de erro do fluxo Atualizar."""
from __future__ import annotations

from typing import Any, Mapping


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _value(obj: Any, key: str, default: Any = "") -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _diagnostics(job: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in _value(job, "diagnostics", []) or []:
        text = _clean(raw)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result[-12:]


def _download_diagnostic(preview: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(preview or {})
    fresh = dict(data.get("new_zip") or {})
    diagnostic = fresh.get("download_diagnostic") or fresh.get("diagnostic") or {}
    return dict(diagnostic) if isinstance(diagnostic, Mapping) else {}


def _category(message: str, diagnostic: Mapping[str, Any]) -> tuple[str, bool]:
    text = (message + " " + _clean(diagnostic.get("probable_cause"))).lower()
    if any(term in text for term in ("sessão", "sessao", "autentic", "login", "401", "403")):
        return "authentication", True
    if "cloudflare" in text:
        return "cloudflare", True
    if any(term in text for term in ("html", "magic bytes", "não corresponde a um zip", "nao corresponde a um zip")):
        return "download_invalid", False
    if any(term in text for term in ("download", "zip", "arquivo")):
        return "download", False
    if "downgrade" in text or "fonte anterior" in text:
        return "downgrade", False
    if any(term in text for term in ("owner", "group", "mode", "metadad")):
        return "filesystem_metadata", False
    if any(term in text for term in ("rollback", "backup", "staging", "sha-256", "sha256")):
        return "filesystem", False
    return "validation", False


def normalize_update_error(
    job: Any,
    preview: Mapping[str, Any] | None = None,
    plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    preview_data = dict(preview or {})
    plan_data = dict(plan or {})
    diagnostics = _diagnostics(job)
    current_error = _clean(_value(job, "execution_error"))
    if not current_error:
        current_error = diagnostics[-1] if diagnostics else ""

    download_diag = _download_diagnostic(preview_data)
    message = current_error
    if download_diag and not message:
        cause = _clean(download_diag.get("probable_cause"))
        message = "Não foi possível obter um ZIP válido" + (f": {cause}" if cause else "")

    state = _value(job, "state", "")
    status = _clean(getattr(state, "value", state))
    versions = dict(preview_data.get("versions") or {})
    expected = _clean(
        versions.get("approved_source_version")
        or _value(job, "approved_source_version")
        or _value(job, "ultrapack_version")
    )
    detected = _clean(
        versions.get("effective_source_version")
        or _value(job, "effective_source_version")
        or expected
    )
    stage = _clean(_value(job, "last_completed_step"))
    if not stage:
        if status in {"validating", "downloading", "staging", "installing", "updating_wordpress", "validating_wordpress"}:
            stage = status
        elif message:
            stage = "preparation" if not plan_data else "execution"

    category, global_block = _category(message, download_diag)
    technical_parts: list[str] = []
    if download_diag:
        for label, key in (
            ("URL solicitada", "requested_url"),
            ("URL final", "final_url"),
            ("Status HTTP", "status"),
            ("Content-Type", "content_type"),
            ("Diagnóstico provável", "probable_cause"),
        ):
            value = _clean(download_diag.get(key))
            if value:
                technical_parts.append(f"{label}: {value}")
    technical_detail = " | ".join(technical_parts)

    history = list(_value(job, "execution_history", []) or [])
    attempt = max(1, int(_value(job, "attempts", 0) or 0), len(history) + (1 if message else 0))
    occurred_at = _clean(
        _value(job, "completed_at")
        or _value(job, "updated_at")
        or _value(job, "executing_at")
        or _value(job, "prepared_at")
    )

    return {
        "message": message,
        "current_error": current_error,
        "diagnostics": diagnostics,
        "stage": stage,
        "product": _clean(_value(job, "name")),
        "woo_product_id": int(_value(job, "woo_product_id", 0) or 0),
        "source": _clean(_value(job, "source_name")) or ("PluginTheme" if "plugintheme.net" in _clean(_value(job, "ultrapack_url")) else "UltraPackV2"),
        "expected_version": expected,
        "detected_version": detected,
        "attempt": attempt,
        "technical_detail": technical_detail,
        "download": download_diag,
        "occurred_at": occurred_at,
        "status": status,
        "category": category,
        "global_block": global_block,
        "has_error": bool(message),
    }
