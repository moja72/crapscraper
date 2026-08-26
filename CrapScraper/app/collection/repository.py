from __future__ import annotations

from typing import Any


class CollectionRepository:
    @property
    def storage(self):
        from app.collection.legacy_core import storage
        return storage

    def slots(self) -> list[dict[str, Any]]: return self.storage.build_slots_public_list()
    def create_slot(self, name: str) -> str: return self.storage.create_slot(name)
    def select_slot(self, name: str) -> str: return self.storage.set_active_slot(name)
    def default_slot(self, name: str) -> str: return self.storage.set_default_slot(name)
    def delete_slot(self, name: str) -> tuple[bool, str]: return self.storage.delete_slot(name)
    def clear_slot(self, name: str) -> tuple[bool, str]: return self.storage.clear_slot_contents(name)
    def categories(self, context: Any) -> list[dict[str, Any]]: return self.storage.load_available_categories(context)
    def catalog(self, context: Any) -> list[dict[str, Any]]: return self.storage.load_catalog_items(context)
    def config(self, context: Any) -> dict[str, Any]: return self.storage.load_context_config(context)
    def progress(self, context: Any) -> dict[str, Any]: return self.storage.load_progress_data(context)
