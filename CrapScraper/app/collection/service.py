from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.collection.adapters import registry_payload
from app.collection.engine import CollectionEngine
from app.collection.models import CollectionRequest
from app.collection.repository import CollectionRepository


class CollectionService:
    def __init__(self, data_dir: Path, *, engine: CollectionEngine | None = None, repository: CollectionRepository | None = None):
        os.environ["SCRAPER_DATA_DIR"] = str(data_dir)
        self.repository = repository or CollectionRepository()
        self.engine = engine or CollectionEngine()

    def context_payload(self, payload: dict[str,Any]|None=None) -> dict[str, Any]:
        run_id=str((payload or {}).get("run_id") or "") or None
        context = self.engine.context_for(run_id) if hasattr(self.engine,"context_for") else self.engine.context
        runs=self.engine.runs() if hasattr(self.engine,"runs") else [];rules=self.engine.queue_rules() if hasattr(self.engine,"queue_rules") else []
        return {"ok": True, **registry_payload(), "context": context.to_dict(), "slots": self.repository.slots(), "contexts":self.repository.contexts(context.slot_name) if hasattr(self.repository,"contexts") else [], "categories": self.repository.categories(context), "catalog_count": len(self.repository.catalog(context)), "config": self.repository.config(context), "progress": self.repository.progress(context),"runs":runs,"queue_rules":rules}

    def set_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = {key: str(payload.get(key, "")) for key in ("site_key", "item_type_key", "account_key", "slot_name")}
        if hasattr(self.engine,"runs"):self.engine.set_context(context,str(payload.get("run_id") or "") or None)
        else:self.engine.set_context(context)
        return self.context_payload({"run_id":payload.get("run_id")})

    def slot_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if action == "create": self.repository.create_slot(name)
        elif action == "select": self.repository.select_slot(name); self.engine.set_context({**self.engine.context.to_dict(), "slot_name": name})
        elif action == "default": self.repository.default_slot(name)
        elif action == "clear":
            ok, message = self.repository.clear_slot(name)
            if not ok: raise ValueError(message)
        elif action == "delete":
            ok, message = self.repository.delete_slot(name)
            if not ok: raise ValueError(message)
        elif action == "rename":
            result=self.engine.rename_slot(name,str(payload.get("new_name") or ""))
            if not result.get("ok"):raise ValueError(str(result.get("message") or "Falha ao renomear slot"))
        elif action == "remove-context":
            result=self.engine.remove_context(payload)
            if not result.get("ok"):raise ValueError(str(result.get("message") or "Falha ao remover contexto"))
        elif action == "remove-zero-contexts":
            result=self.engine.remove_zero_contexts(name or None)
            if not result.get("ok"):raise ValueError(str(result.get("message") or "Falha ao remover contextos"))
        else: raise ValueError("Ação de slot desconhecida.")
        return self.context_payload()

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = CollectionRequest.from_payload(payload)
        if hasattr(self.engine,"runs"):
            run_id=str(payload.get("run_id") or "") or None;self.engine.set_context(request.context,run_id);return self.engine.start(request.mode,request.options,resume=request.resume,run_id=run_id)
        self.engine.set_context(request.context)
        return self.engine.start(request.mode,request.options,resume=request.resume)

    def state(self, payload: dict[str,Any]|None=None) -> dict[str, Any]:
        multi=hasattr(self.engine,"runs");state=self.engine.snapshot(str((payload or {}).get("run_id") or "") or None) if multi else self.engine.snapshot();return {"ok":True,"state":state,"runs":self.engine.runs() if multi else []}
    def logs_full(self, payload: dict[str,Any]|None=None) -> dict[str, Any]:
        run_id=str((payload or {}).get("run_id") or "") or None
        return {"ok":True,"run_id":run_id or "","logs":self.engine.full_logs(run_id)}
    def catalogs(self) -> dict[str, Any]: return {"ok":True,**self.repository.catalog_management()}
    def catalog_file(self, payload: dict[str,Any]|None=None) -> dict[str, Any]:
        payload=payload or {};context={key:str(payload.get(key) or "") for key in ("slot_name","site_key","item_type_key","account_key")};kind=str(payload.get("kind") or "")
        return {"ok":True,"kind":kind,"context":context,"content":self.repository.context_file(context,kind)}
    def control(self, action: str, payload: dict[str,Any]|None=None) -> dict[str, Any]:
        method=getattr(self.engine,action);return method(str((payload or {}).get("run_id") or "") or None) if hasattr(self.engine,"runs") else method()
    def create_run(self,payload):
        context={key:str(payload.get(key,"")) for key in ("site_key","item_type_key","account_key","slot_name")};return self.engine.create_run(context)
    def remove_run(self,payload):return self.engine.remove_run(str(payload.get("run_id") or ""))
    def save_queue(self,payload):return self.engine.save_queue_rules(list(payload.get("rules") or []))
    def save_config(self,payload):
        saved=self.engine.save_options(dict(payload.get("options") or {}),str(payload.get("run_id") or "") or None);return {"ok":True,"config":saved}
