from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app import settings


_FILE_LOCK = threading.RLock()
_STATUS_LOCK = threading.RLock()
_RUNTIME_READY = threading.Event()
_STATUS: dict[str, Any] = {
    "stage": "not_started",
    "ready": False,
    "error": "",
    "started_at": "",
    "finished_at": "",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _runtime_path(path: str | Path | None = None) -> Path:
    return Path(path or settings.UPDATE_RUNTIME_PATH)


def _deferred_path(path: str | Path | None = None) -> Path:
    target = _runtime_path(path)
    return target.with_suffix(target.suffix + ".boot-deferred")


def defer_runtime_file_for_imports(path: str | Path | None = None) -> dict[str, Any]:
    """Hide the persisted update runtime while modules are imported.

    ``app.operations.runtime`` historically calls ``restore()`` at import time.
    With a large persisted history that makes ``python main.py`` wait minutes
    before the HTTP socket exists. Moving the file atomically out of the expected
    path makes that legacy import-time restore a no-op. The file is put back before
    the panel starts serving requests and is then recovered in a daemon thread.
    """
    target = _runtime_path(path)
    deferred = _deferred_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with _FILE_LOCK:
        # Crash recovery: if a previous boot stopped after the atomic rename, the
        # deferred file is still authoritative. Keep it deferred for this import.
        if deferred.exists() and not target.exists():
            return {
                "deferred": True,
                "path": str(target),
                "deferred_path": str(deferred),
                "recovered_stale_boot": True,
            }

        # Both files should never normally coexist. Preserve the current runtime
        # as authoritative and move the stale deferred copy aside instead of
        # deleting user data.
        if deferred.exists() and target.exists():
            stale = deferred.with_suffix(deferred.suffix + f".stale-{int(time.time())}")
            deferred.replace(stale)

        if not target.exists():
            return {
                "deferred": False,
                "path": str(target),
                "deferred_path": str(deferred),
                "missing": True,
            }

        target.replace(deferred)
        return {
            "deferred": True,
            "path": str(target),
            "deferred_path": str(deferred),
            "recovered_stale_boot": False,
        }


def restore_deferred_runtime_file(path: str | Path | None = None) -> dict[str, Any]:
    """Restore the atomically deferred runtime file without silently overwriting data."""
    target = _runtime_path(path)
    deferred = _deferred_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with _FILE_LOCK:
        if not deferred.exists():
            return {
                "restored": False,
                "path": str(target),
                "deferred_path": str(deferred),
                "already_present": target.exists(),
            }

        if target.exists():
            conflict = target.with_suffix(target.suffix + f".boot-conflict-{int(time.time())}")
            target.replace(conflict)
        deferred.replace(target)
        return {
            "restored": True,
            "path": str(target),
            "deferred_path": str(deferred),
        }


def mark_runtime_loading() -> None:
    with _STATUS_LOCK:
        _STATUS.update(
            stage="loading",
            ready=False,
            error="",
            started_at=_now_iso(),
            finished_at="",
        )
        _RUNTIME_READY.clear()


def mark_runtime_ready() -> None:
    with _STATUS_LOCK:
        _STATUS.update(stage="ready", ready=True, error="", finished_at=_now_iso())
        _RUNTIME_READY.set()


def mark_runtime_error(error: BaseException | str) -> None:
    message = str(error or "Falha desconhecida ao restaurar o histórico operacional.").strip()
    with _STATUS_LOCK:
        _STATUS.update(stage="error", ready=False, error=message, finished_at=_now_iso())
        _RUNTIME_READY.clear()


def runtime_restore_status() -> dict[str, Any]:
    with _STATUS_LOCK:
        return dict(_STATUS)


def is_runtime_ready() -> bool:
    return _RUNTIME_READY.is_set()


def wait_runtime_ready(timeout: float | None = None) -> bool:
    return _RUNTIME_READY.wait(timeout=timeout)


def start_runtime_recovery_background(
    *,
    delay_seconds: float = 0.75,
    on_ready: Callable[[], Any] | None = None,
    on_error: Callable[[BaseException], Any] | None = None,
) -> threading.Thread:
    """Repair/recover/restore update state after the panel had a chance to bind.

    The expensive work intentionally remains exactly the same safety pipeline used
    before; only its position in the boot sequence changes. Update writes are gated
    by ``startup_runtime_gate_policy`` until this thread marks the runtime ready.
    """
    restore_deferred_runtime_file()
    mark_runtime_loading()

    def run() -> None:
        if delay_seconds > 0:
            threading.Event().wait(float(delay_seconds))
        try:
            from app.operations.runtime_repair import repair_update_runtime
            from app.operations.transient_recovery import recover_interrupted_preparations
            import app.operations.runtime as update_runtime

            repair_update_runtime()
            recover_interrupted_preparations()
            update_runtime.restore()
            mark_runtime_ready()
            if callable(on_ready):
                on_ready()
        except BaseException as error:  # keep update writes blocked on any restore failure
            mark_runtime_error(error)
            if callable(on_error):
                on_error(error)

    thread = threading.Thread(
        target=run,
        name="update-runtime-bootstrap",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = [
    "defer_runtime_file_for_imports",
    "restore_deferred_runtime_file",
    "start_runtime_recovery_background",
    "runtime_restore_status",
    "is_runtime_ready",
    "wait_runtime_ready",
]
