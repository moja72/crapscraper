from __future__ import annotations

import threading
from typing import Any

from app.catalogs.managed import ManagedCatalogService


class CatalogService(ManagedCatalogService):
    """Garante a finalização da identidade mesmo quando a geração termina muito rápido."""

    def generate_plugintema(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        response = super().generate_plugintema(payload)
        source_worker = self._worker
        if source_worker and source_worker is not self._finalizer_source:
            self._finalizer_source = source_worker
            self._finalizer = threading.Thread(
                target=self._finalize_generation,
                args=(source_worker, payload),
                name="plugintema-catalog-finalizer",
                daemon=True,
            )
            self._finalizer.start()
        return response
