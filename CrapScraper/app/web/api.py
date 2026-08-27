from __future__ import annotations

from dataclasses import dataclass
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.collection import CollectionService
from app.comparison import ComparisonService
from app.updates import UpdateService
from app.additions import AdditionService
from app.store import StoreService
from app.sync import ManualSyncService, E2EExecutionRecorder
import os


@dataclass
class ApplicationServices:
    collection: CollectionService
    comparison: ComparisonService
    updates: UpdateService
    additions: AdditionService
    store: StoreService
    sync: ManualSyncService

    @classmethod
    def build(cls, settings: Settings, runtime: JsonStore) -> "ApplicationServices":
        updates=UpdateService(settings.data_dir);comparison=ComparisonService(settings.data_dir);additions=AdditionService(settings.data_dir)
        if os.getenv("SCRAPER_SYNC_E2E_FIXTURES","")=="1":updates.executor=E2EExecutionRecorder();additions.executor=E2EExecutionRecorder()
        return cls(CollectionService(settings.data_dir), comparison, updates, additions, StoreService(settings.data_dir,updates), ManualSyncService(comparison,updates,additions))
