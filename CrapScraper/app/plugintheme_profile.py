"""Persistent PluginTheme profile diagnostics and explicit renewal.

Only metadata about the profile is exposed. Cookie values, storage values and
access tokens never leave this module.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any, Mapping


ACCOUNT_URL = "https://plugintheme.net/pt-BR/account"
SUBSCRIPTION_URL = "https://plugintheme.net/pt-BR/account/subscription"
LOGIN_URL = "https://plugintheme.net/pt-BR/auth/login"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~+/=-]{40,}$")


def _account(account_key: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", str(account_key or "default").lower()).strip("-") or "default"


def profile_path(account_key: str) -> Path:
    from app.collection.legacy_core.browser import get_plugintheme_profile_dir

    return get_plugintheme_profile_dir(_account(account_key)).resolve()


def storage_state_path(account_key: str) -> Path:
    return profile_path(account_key) / "storage_state.json"


def renewal_marker_path(account_key: str) -> Path:
    return profile_path(account_key) / ".manual-renewal-pending"


def renewal_pending(account_key: str) -> bool:
    return renewal_marker_path(account_key).is_file()


def complete_manual_renewal(account_key: str) -> None:
    with suppress(OSError):
        renewal_marker_path(account_key).unlink()


def stored_state(account_key: str) -> dict[str, Any]:
    """Read the private Playwright state internally; callers must never log it."""
    path = storage_state_path(account_key)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def configured(account_key: str) -> bool:
    from app.collection.legacy_core import settings

    return bool(settings.is_account_configured(_account(account_key), "plugintheme"))


def _cookie_database(path: Path) -> Path | None:
    candidates = (
        path / "Default" / "Network" / "Cookies",
        path / "Default" / "Cookies",
        path / "Network" / "Cookies",
        path / "Cookies",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def profile_diagnostic(account_key: str) -> dict[str, Any]:
    """Return safe persistence evidence without exposing cookie names/values."""
    account = _account(account_key)
    path = profile_path(account)
    database = _cookie_database(path)
    cookie_count = 0
    cookie_readable = database is not None
    if database is not None:
        try:
            connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=1)
            try:
                row = connection.execute(
                    "SELECT COUNT(*) FROM cookies WHERE host_key LIKE ? "
                    "AND (value <> '' OR length(encrypted_value) > 0)",
                    ("%plugintheme.net%",),
                ).fetchone()
            finally:
                connection.close()
            cookie_count = int((row or [0])[0] or 0)
        except sqlite3.Error:
            cookie_readable = False
    persisted = stored_state(account)
    persisted_cookies = [
        cookie for cookie in persisted.get("cookies", [])
        if isinstance(cookie, dict)
        and str(cookie.get("domain") or "").lstrip(".").lower().endswith("plugintheme.net")
    ]
    stored_entries = sum(
        len(origin.get("localStorage", []))
        for origin in persisted.get("origins", [])
        if isinstance(origin, dict) and isinstance(origin.get("localStorage"), list)
    )
    storage_candidates = (
        path / "Default" / "Local Storage",
        path / "Default" / "Session Storage",
        path / "Local Storage",
        path / "Session Storage",
    )
    return {
        "account_key": account,
        "configured": configured(account),
        "profile_path": str(path),
        "profile_exists": path.is_dir(),
        "persistence_mode": "persistent_browser_context",
        "cookie_store_exists": database is not None,
        "cookie_store_readable": cookie_readable,
        "cookie_count": max(cookie_count, len(persisted_cookies)),
        "profile_cookie_count": cookie_count,
        "storage_state_cookie_count": len(persisted_cookies),
        "httponly_cookie_count": sum(bool(cookie.get("httpOnly")) for cookie in persisted_cookies),
        "storage_entry_count": stored_entries,
        "storage_state_exists": storage_state_path(account).is_file(),
        "manual_renewal_pending": renewal_pending(account),
        "browser_storage_exists": any(candidate.exists() for candidate in storage_candidates),
    }


def _chrome_executable() -> Path:
    candidates = (
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("Google Chrome não foi encontrado nesta máquina.")


def _profile_process_running(path: Path) -> bool:
    try:
        import psutil
    except ImportError:
        return False
    target = str(path).lower()
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            name = str(process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
            if name in {"chrome", "chrome.exe"} and target in command:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False


def open_manual_session(account_key: str) -> dict[str, Any]:
    """Open the dedicated profile visibly; human verification is never bypassed."""
    account = _account(account_key)
    path = profile_path(account)
    path.mkdir(parents=True, exist_ok=True)
    if _profile_process_running(path):
        renewal_marker_path(account).touch(exist_ok=True)
        return {
            "ok": True,
            "already_open": True,
            "account_key": account,
            "profile_path": str(path),
            "message": "A janela de renovação do PluginTheme já está aberta.",
        }
    process = subprocess.Popen(
        [
            str(_chrome_executable()),
            f"--user-data-dir={path}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--new-window",
            LOGIN_URL,
        ],
        close_fds=True,
    )
    renewal_marker_path(account).touch(exist_ok=True)
    return {
        "ok": True,
        "already_open": False,
        "account_key": account,
        "profile_path": str(path),
        "process_id": process.pid,
        "message": (
            "Chrome aberto com o perfil exclusivo do PluginTheme. Conclua o login, "
            "confirme a área da conta e feche completamente essa janela; depois use Verificar pré-requisitos."
        ),
    }


def find_access_token(value: Any) -> str:
    """Find a bearer/JWT internally. The caller must never log the result."""
    if isinstance(value, Mapping):
        for key in ("access_token", "accessToken", "token", "jwt", "authToken", "auth_token"):
            token = find_access_token(value.get(key))
            if token:
                return token
        for nested in value.values():
            token = find_access_token(nested)
            if token:
                return token
    elif isinstance(value, (list, tuple)):
        for nested in value:
            token = find_access_token(nested)
            if token:
                return token
    elif isinstance(value, str):
        raw = value.strip()
        if raw.startswith(("{", "[")):
            with suppress(ValueError):
                token = find_access_token(json.loads(raw))
                if token:
                    return token
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if len(raw) >= 40 and _TOKEN_PATTERN.fullmatch(raw):
            return raw
    return ""


__all__ = [
    "ACCOUNT_URL", "SUBSCRIPTION_URL", "LOGIN_URL", "complete_manual_renewal", "configured", "find_access_token",
    "open_manual_session", "profile_diagnostic", "profile_path", "renewal_pending",
    "storage_state_path", "stored_state",
]
