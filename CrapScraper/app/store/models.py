from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class StoreError:
    message: str
    code: str = "store_error"
    operation: str = ""
    product_id: int = 0
    stage: str = ""
    technical_message: str = ""
    http_status: int = 0
    diagnosis: str = ""
    recoverable: bool = True
    timestamp: str = ""
    def to_dict(self) -> dict[str, Any]:
        value=asdict(self);value["timestamp"]=value["timestamp"] or utc_now();return value
