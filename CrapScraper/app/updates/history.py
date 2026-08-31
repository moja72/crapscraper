from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.store.wordpress import WordPressManualQueueClient
from app.updates.repository import UpdateRepository


LOGGER = logging.getLogger("crapscraper.updates.history")


class UpdateHistory:
    """Leitura compatível do histórico interno de tentativas."""

    def __init__(self, repository: UpdateRepository) -> None:
        self.repository = repository

    def for_job(self, job_id: str) -> list[dict[str, Any]]:
        return self.repository.history(job_id)


class UpdateHistorySynchronizer:
    """Replica o outbox canônico no WordPress e confirma a persistência por leitura."""

    def __init__(self, repository: UpdateRepository, client: WordPressManualQueueClient | None = None) -> None:
        self.repository = repository
        self.client = client or WordPressManualQueueClient()

    @staticmethod
    def payload(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": str(event["operation_id"]),
            "job_id": str(event["job_id"]),
            "woo_product_id": int(event["woo_product_id"]),
            "source": str(event["source"]),
            "previous_version": str(event["previous_version"]),
            "new_version": str(event["new_version"]),
            "status": "completed",
            "completed_at": str(event["completed_at"]),
        }

    @staticmethod
    def _timestamp(value: Any) -> str:
        text = str(value or "").strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return text
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")

    @classmethod
    def _matches(cls, expected: dict[str, Any], observed: dict[str, Any]) -> bool:
        event = observed.get("event") if isinstance(observed.get("event"), dict) else observed
        return (
            str(event.get("operation_id") or event.get("request_id") or "") == expected["operation_id"]
            and int(event.get("woo_product_id") or event.get("product_id") or 0) == expected["woo_product_id"]
            and str(event.get("source") or "") == expected["source"]
            and str(event.get("previous_version") or "") == expected["previous_version"]
            and str(event.get("new_version") or "") == expected["new_version"]
            and str(event.get("status") or "") == "completed"
            and cls._timestamp(event.get("completed_at")) == cls._timestamp(expected["completed_at"])
        )

    def sync_event(self, operation_id: str) -> dict[str, Any]:
        event = self.repository.history_event(operation_id)
        if not event:
            raise KeyError(operation_id)
        if event["sync_status"] == "confirmed":
            return {"ok": True, "confirmed": True, "operation_id": operation_id, "already_confirmed": True}
        if not self.client.configured:
            return {"ok": False, "confirmed": False, "operation_id": operation_id, "status": "not_configured"}
        expected = self.payload(event)
        try:
            response = self.client.send_history(expected)
            confirmation = self.client.confirm_history(operation_id)
            if not self._matches(expected, confirmation):
                raise RuntimeError("HTTP aceito, mas a leitura posterior não confirmou o evento persistido.")
            self.repository.mark_history_sync(operation_id, confirmed=True)
            LOGGER.info(
                "Histórico WordPress confirmado: operation_id=%s woo_product_id=%s source=%s",
                operation_id,
                expected["woo_product_id"],
                expected["source"],
            )
            return {"ok": True, "confirmed": True, "operation_id": operation_id, "response": response}
        except Exception as error:
            message=f"{type(error).__name__}: {error}"
            self.repository.mark_history_sync(operation_id, confirmed=False, error=message)
            LOGGER.warning("Histórico WordPress não confirmado: operation_id=%s erro=%s", operation_id, type(error).__name__)
            return {"ok": False, "confirmed": False, "operation_id": operation_id, "status": "error", "message": str(error)}

    def sync_pending(self, limit: int = 20) -> list[dict[str, Any]]:
        return [self.sync_event(event["operation_id"]) for event in self.repository.pending_history_events(limit)]
