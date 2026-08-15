from __future__ import annotations

import re
from datetime import datetime
from threading import RLock
from typing import Any

_SECRET = re.compile(r"(?i)(password|senha|consumer[_ -]?(?:key|secret)|authorization|cookie)\s*[:=]\s*[^\s,;]+")


class UpdateLogger:
    def __init__(self) -> None:
        self.entries: list[str] = []
        self._lock = RLock()

    def clear(self) -> None:
        with self._lock: self.entries.clear()

    def log(self, message: Any) -> None:
        safe = self.sanitize(message)
        with self._lock:
            self.entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] {safe}")

    @staticmethod
    def sanitize(message: Any) -> str:
        return _SECRET.sub(lambda m: m.group(1) + "=[redacted]", str(message or ""))

    def to_list(self) -> list[str]:
        with self._lock: return list(self.entries)


class UpdateLogRegistry:
    """Mantém logs isolados por job; nunca limpa outro job em andamento."""
    def __init__(self) -> None:
        self._logs: dict[str, UpdateLogger] = {}
        self._lock = RLock()

    def for_job(self, job_id: Any) -> UpdateLogger:
        key = str(job_id or "").strip()
        if not key:
            raise ValueError("job_id obrigatório para logs")
        with self._lock:
            return self._logs.setdefault(key, UpdateLogger())

    def to_list(self, job_id: Any) -> list[str]:
        return self.for_job(job_id).to_list()
