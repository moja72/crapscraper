from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PublicState(str, Enum):
    READY = "ready"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class UpdateError:
    message: str
    technical_message: str = ""
    code: str = "update_error"
    stage: str = ""
    source: str = ""
    requested_url: str = ""
    final_url: str = ""
    http_status: int | None = None
    content_type: str = ""
    diagnosis: str = ""
    attempt_id: str = ""
    job_id: str = ""
    timestamp: str = field(default_factory=utc_now)
    recoverable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UpdateJob:
    job_id: str
    comparison_item_id: str
    woo_product_id: int
    product_name: str
    current_version: str
    source_version: str
    source_kind: str
    source_name: str
    source_url: str
    source_product_id: str = ""
    public_state: str = PublicState.READY
    stage: str = "prepared"
    queue_name: str = "updates"
    queue_position: int = 0
    attempts: int = 0
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    started_at: str = ""
    finished_at: str = ""
    error: dict[str, Any] | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["state"] = value.pop("public_state")
        return value
