from __future__ import annotations

from dataclasses import dataclass
from app.configuration import Settings
from app.core.persistence import JsonStore
from app.domains import DomainService


@dataclass
class ApplicationServices:
    domains: DomainService

    @classmethod
    def build(cls, settings: Settings, runtime: JsonStore) -> "ApplicationServices":
        return cls(DomainService(settings.data_dir, runtime))
