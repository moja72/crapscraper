from __future__ import annotations

from dataclasses import dataclass
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.collection import CollectionService
from app.comparison import ComparisonService
from app.updates import UpdateService
from app.additions import AdditionService
from app.store import StoreService


@dataclass
class ApplicationServices:
    collection: CollectionService
    comparison: ComparisonService
    updates: UpdateService
    additions: AdditionService
    store: StoreService

    @classmethod
    def build(cls, settings: Settings, runtime: JsonStore) -> "ApplicationServices":
        updates=UpdateService(settings.data_dir)
        return cls(CollectionService(settings.data_dir), ComparisonService(settings.data_dir), updates, AdditionService(settings.data_dir), StoreService(settings.data_dir,updates))
