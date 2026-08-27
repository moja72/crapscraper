from __future__ import annotations

import threading
from typing import Any


class CollectionEngine:
    """Adaptador fino para o manager multi-run maduro, sem policies ou patches."""

    def __init__(self) -> None:
        from app.collection.legacy_core.app import ScraperRunManager
        self._lock = threading.RLock()
        self.manager = ScraperRunManager()
        self._app = self.manager.create_run(auto_load_summary=True)

    @property
    def context(self): return self._app.context
    def context_for(self, run_id: str | None = None): return self._run(run_id).context

    def _run(self, run_id: str | None = None): return self.manager.get_run(run_id)

    def set_context(self, context: dict[str, str], run_id: str | None = None) -> dict[str, Any]:
        with self._lock: return self._run(run_id).set_context(context)

    def snapshot(self, run_id: str | None = None) -> dict[str, Any]: return self._run(run_id).snapshot()
    def runs(self) -> list[dict[str, Any]]: return self.manager.list_runs_public()
    def create_run(self, context: dict[str, str]) -> dict[str, Any]:
        app=self.manager.create_run(context,auto_load_summary=True);return {"ok":True,"run_id":app.run_id,"runs":self.runs(),"state":app.snapshot()}
    def remove_run(self, run_id: str) -> dict[str, Any]: return self.manager.remove_run(run_id)

    def start(self, mode: str, options: dict[str, Any], *, resume: bool = False, run_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if resume:
                return self.manager.continue_run(run_id,run_mode=mode,run_options=options)
            return self.manager.start_run(run_id,run_mode=mode,run_options=options)

    def pause(self, run_id: str | None = None) -> dict[str, Any]: return self._run(run_id).pause()
    def resume(self, run_id: str | None = None) -> dict[str, Any]: return self._run(run_id).resume()
    def stop(self, run_id: str | None = None) -> dict[str, Any]: return self._run(run_id).stop()
    def queue_rules(self) -> list[dict[str, Any]]: return self.manager.get_queue_rules()
    def save_queue_rules(self, rules: list[dict[str, Any]]) -> dict[str, Any]: return self.manager.save_queue_rules(rules)
    def save_options(self, options: dict[str, Any], run_id: str | None = None) -> dict[str, Any]: return self._run(run_id).save_run_options(options)
    def rename_slot(self, old_name: str, new_name: str) -> dict[str, Any]: return self._app.rename_slot(old_name,new_name)
    def remove_context(self, payload: dict[str, Any]) -> dict[str, Any]: return self._app.remove_slot_context(payload.get("slot_name"),payload.get("site_key"),payload.get("item_type_key"),payload.get("account_key"))
    def remove_zero_contexts(self, slot_name: str | None = None) -> dict[str, Any]: return self._app.remove_zero_item_contexts(slot_name)
