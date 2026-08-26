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

    def context_payload(self) -> dict[str, Any]:
        context = self.engine.context
        return {"ok": True, **registry_payload(), "context": context.to_dict(), "slots": self.repository.slots(), "categories": self.repository.categories(context), "catalog_count": len(self.repository.catalog(context)), "config": self.repository.config(context), "progress": self.repository.progress(context)}

    def set_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = {key: str(payload.get(key, "")) for key in ("site_key", "item_type_key", "account_key", "slot_name")}
        self.engine.set_context(context)
        return self.context_payload()

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
        else: raise ValueError("Ação de slot desconhecida.")
        return self.context_payload()

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = CollectionRequest.from_payload(payload)
        self.engine.set_context(request.context)
        return self.engine.start(request.mode, request.options, resume=request.resume)

    def state(self) -> dict[str, Any]: return {"ok": True, "state": self.engine.snapshot()}
    def control(self, action: str) -> dict[str, Any]: return getattr(self.engine, action)()
