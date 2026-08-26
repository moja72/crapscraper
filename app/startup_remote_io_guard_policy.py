from __future__ import annotations

import threading
from typing import Any, Callable

import app.addition_download_contract_policy as download_contract


_INSTALLED = False
_BASE_REPAIR: Callable[..., dict[str, Any]] | None = None
_LOCK = threading.RLock()
_REPAIR_THREAD: threading.Thread | None = None
_LAST_RESULT: dict[str, Any] = {
    "scheduled": False,
    "running": False,
    "completed": False,
    "error": "",
}


def _snapshot() -> dict[str, Any]:
    with _LOCK:
        return dict(_LAST_RESULT)


def _run_repair_after_startup(delay_seconds: float) -> None:
    global _REPAIR_THREAD
    if delay_seconds > 0:
        threading.Event().wait(float(delay_seconds))

    with _LOCK:
        _LAST_RESULT.update(scheduled=True, running=True, completed=False, error="")

    try:
        if _BASE_REPAIR is None:
            raise RuntimeError("Retrocorreção base de downloads indisponível.")
        result = dict(_BASE_REPAIR() or {})
        with _LOCK:
            _LAST_RESULT.clear()
            _LAST_RESULT.update(
                scheduled=True,
                running=False,
                completed=True,
                error="",
                **result,
            )
    except Exception as error:
        with _LOCK:
            _LAST_RESULT.update(
                scheduled=True,
                running=False,
                completed=True,
                error=f"{type(error).__name__}: {error}",
            )
    finally:
        with _LOCK:
            _REPAIR_THREAD = None


def _deferred_repair_existing_additions(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Never perform WooCommerce/SSH I/O on the policy-install call stack.

    The original function iterates every previously created addition and performs
    fresh WooCommerce requests plus SSH validation. It used to be called while
    `python main.py` was still installing policies, before the HTTP server bound
    port 8765. One slow WooCommerce response therefore made the whole application
    look frozen for minutes.

    Preserve the retro-repair behavior, but execute it once in a daemon thread
    after startup. Repeated sync calls while it is pending/running simply reuse
    the same background task.
    """
    global _REPAIR_THREAD
    del args, kwargs

    with _LOCK:
        if _REPAIR_THREAD is not None and _REPAIR_THREAD.is_alive():
            return _snapshot()

        # If the automatic repair already completed successfully in this process,
        # there is no reason to scan every WooCommerce product again on every UI
        # refresh/sync.
        if _LAST_RESULT.get("completed") and not _LAST_RESULT.get("error"):
            return _snapshot()

        _LAST_RESULT.update(
            scheduled=True,
            running=False,
            completed=False,
            error="",
        )
        _REPAIR_THREAD = threading.Thread(
            target=_run_repair_after_startup,
            args=(8.0,),
            daemon=True,
            name="addition-download-contract-repair",
        )
        _REPAIR_THREAD.start()
        return _snapshot()


def install_startup_remote_io_guard_policy() -> None:
    global _INSTALLED, _BASE_REPAIR
    if _INSTALLED:
        return

    _BASE_REPAIR = download_contract._repair_existing_additions
    download_contract._repair_existing_additions = _deferred_repair_existing_additions
    _INSTALLED = True


__all__ = [
    "install_startup_remote_io_guard_policy",
    "_deferred_repair_existing_additions",
]
