from __future__ import annotations

from dataclasses import dataclass
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.collection import CollectionService
from app.comparison import ComparisonService
from app.domains import DomainService
from app.updates import UpdateService
from app.additions import AdditionService


@dataclass
class ApplicationServices:
    collection: CollectionService
    comparison: ComparisonService
    updates: UpdateService
    additions: AdditionService
    domains: DomainService

    @classmethod
    def build(cls, settings: Settings, runtime: JsonStore) -> "ApplicationServices":
        return cls(CollectionService(settings.data_dir), ComparisonService(settings.data_dir), UpdateService(settings.data_dir), AdditionService(settings.data_dir), DomainService(settings.data_dir, runtime))
