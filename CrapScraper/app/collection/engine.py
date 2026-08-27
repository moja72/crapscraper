from __future__ import annotations

import threading
from typing import Any


class CollectionEngine:
    """Dono único do ScraperApp maduro, sem instalar policies ou patches."""

    def __init__(self) -> None:
        from app.collection.legacy_core.app import ScraperApp
        self._lock = threading.RLock()
        self._app = ScraperApp(auto_load_summary=True)

    @property
    def context(self): return self._app.context

    def set_context(self, context: dict[str, str]) -> dict[str, Any]:
        with self._lock: return self._app.set_context(context)

    def snapshot(self) -> dict[str, Any]: return self._app.snapshot()

    def start(self, mode: str, options: dict[str, Any], *, resume: bool = False) -> dict[str, Any]:
        with self._lock:
            if resume:
                return self._app.continue_run(run_mode=mode, run_options=options)
            return self._app.start(run_mode=mode, run_options=options)

    def pause(self) -> dict[str, Any]: return self._app.pause()
    def resume(self) -> dict[str, Any]: return self._app.resume()
    def stop(self) -> dict[str, Any]: return self._app.stop()
