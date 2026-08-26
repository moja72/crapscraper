from __future__ import annotations

from dataclasses import dataclass
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.collection import CollectionService
from app.domains import DomainService


@dataclass
class ApplicationServices:
    collection: CollectionService
    domains: DomainService

    @classmethod
    def build(cls, settings: Settings, runtime: JsonStore) -> "ApplicationServices":
        return cls(CollectionService(settings.data_dir), DomainService(settings.data_dir, runtime))
