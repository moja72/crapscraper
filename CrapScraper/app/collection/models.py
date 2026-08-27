from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectionRequest:
    context: dict[str, str]
    mode: str
    options: dict[str, Any]
    resume: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CollectionRequest":
        return cls(
            context={key: str(payload.get(key, "")) for key in ("site_key", "item_type_key", "account_key", "slot_name")},
            mode=str(payload.get("mode") or "full_sync"),
            options=dict(payload.get("options") or {}),
            resume=bool(payload.get("resume")),
        )
