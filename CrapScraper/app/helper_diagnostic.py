from __future__ import annotations

from typing import Any


_INSTALLED = False
_REQUIRED_MISSING_TARGET_OPERATIONS = ("install-missing", "rollback-missing")


def is_legacy_helper_capabilities_failure(message: Any) -> bool:
    text = str(message or "").strip().lower()
    if "capabilities" not in text:
        return False
    if "invalid choice" not in text and '"operation": "parse"' not in text:
        return False
    return all(operation in text for operation in ("inspect", "prepare", "backup", "install", "rollback", "cleanup"))


def normalize_helper_check(result: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(result or {})
    if value.get("ok") or not is_legacy_helper_capabilities_failure(value.get("message")):
        return value
    return {
        **value,
        "ok": False,
        "helper_version": 1,
        "required_helper_version": 2,
        "missing_operations": list(_REQUIRED_MISSING_TARGET_OPERATIONS),
        "message": (
            "Helper remoto do CrapScraper v1 detectado. Atualize "
            "/usr/local/sbin/crapscraper-zip-helper para a versão 2 do repositório. "
            "Até o helper v2 ser implantado, as atualizações permanecem bloqueadas por segurança."
        ),
    }


def install_helper_diagnostic() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from app.updates.adapters import SFTPInstaller

    if getattr(SFTPInstaller, "_helper_diagnostic_installed", False):
        _INSTALLED = True
        return

    original_check = SFTPInstaller.check

    def check(self: Any) -> dict[str, Any]:
        return normalize_helper_check(original_check(self))

    SFTPInstaller.check = check
    SFTPInstaller._helper_diagnostic_installed = True
    _INSTALLED = True


__all__ = [
    "install_helper_diagnostic",
    "is_legacy_helper_capabilities_failure",
    "normalize_helper_check",
]
