from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.integrations.ssh_storage import ControlledWriteSSHStorage, RemoteFileInfo


_LOCKS_GUARD = threading.Lock()
_TARGET_LOCKS: dict[str, threading.Lock] = {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def local_target_lock(path: str) -> Iterator[None]:
    """Process-local lock; it does not coordinate separate processes or hosts."""
    with _LOCKS_GUARD:
        lock = _TARGET_LOCKS.setdefault(path, threading.Lock())
    if not lock.acquire(blocking=False):
        raise RuntimeError("Outro job local ja atua neste arquivo")
    try:
        yield
    finally:
        lock.release()


@dataclass
class RoundTripResult:
    job_id: str
    product_id: int
    path: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    result: str = "running"
    hash_initial: str = ""
    hash_temporary: str = ""
    hash_after_swap: str = ""
    hash_after_rollback: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after_swap: dict[str, Any] = field(default_factory=dict)
    after_rollback: dict[str, Any] = field(default_factory=dict)
    temporary_files: list[str] = field(default_factory=list)
    remaining_files: list[str] = field(default_factory=list)
    divergence: str = ""
    rollback_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def metadata_compatible(expected: RemoteFileInfo, actual: RemoteFileInfo) -> bool:
    return (expected.uid, expected.gid, expected.mode) == (actual.uid, actual.gid, actual.mode)


def write_audit(result: RoundTripResult, audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def run_round_trip(
    storage: ControlledWriteSSHStorage,
    *,
    product_id: int,
    expected_hash: str,
    audit_path: Path,
) -> RoundTripResult:
    result = RoundTripResult(storage.job_id, product_id, storage.target_path)
    result.temporary_files = [storage.temporary_path, storage.backup_path, storage.discard_path]
    original_became_backup = False
    try:
        with local_target_lock(storage.target_path):
            before = storage.validate_file(storage.target_path)
            result.before = before.to_dict()
            result.hash_initial = before.sha256
            if before.sha256 != expected_hash:
                raise RuntimeError("Hash inicial diverge do valor autorizado")
            if storage.exists(storage.backup_path):
                raise FileExistsError("Backup do job ja existe")
            storage.copy_target_to_temporary()
            temporary = storage.stat(storage.temporary_path)
            result.hash_temporary = storage.sha256(storage.temporary_path)
            if result.hash_temporary != result.hash_initial:
                raise RuntimeError("Hash do temporario diverge do original")
            if not metadata_compatible(before, temporary):
                result.divergence = "owner/group/mode do upload temporario divergem do original"
                storage.delete_temporary(storage.temporary_path)
                result.result = "failed_pre_swap"
                return result

            storage.backup()
            original_became_backup = True
            storage.rename(storage.temporary_path, storage.target_path)
            after_swap = storage.validate_file(storage.target_path)
            result.after_swap = after_swap.to_dict()
            result.hash_after_swap = after_swap.sha256
            if result.hash_after_swap != result.hash_initial or not metadata_compatible(before, after_swap):
                raise RuntimeError("Arquivo apos troca diverge do original")

            storage.rename(storage.target_path, storage.discard_path)
            storage.restore()
            original_became_backup = False
            after_rollback = storage.validate_file(storage.target_path)
            result.after_rollback = after_rollback.to_dict()
            result.hash_after_rollback = after_rollback.sha256
            if result.hash_after_rollback != result.hash_initial or not metadata_compatible(before, after_rollback):
                raise RuntimeError("Validacao apos rollback divergiu")
            storage.delete_temporary(storage.discard_path)
            result.rollback_ok = True
            result.result = "rolled_back"
    except Exception as error:
        result.divergence = str(error)
        result.result = "rollback_required" if original_became_backup else "failed"
        if original_became_backup:
            try:
                if storage.exists(storage.target_path):
                    if not storage.exists(storage.discard_path):
                        storage.rename(storage.target_path, storage.discard_path)
                storage.restore()
                original_became_backup = False
                restored = storage.validate_file(storage.target_path)
                result.after_rollback = restored.to_dict()
                result.hash_after_rollback = restored.sha256
                result.rollback_ok = restored.sha256 == result.hash_initial
                result.result = "failed_rolled_back" if result.rollback_ok else "rollback_required"
                if result.rollback_ok and storage.exists(storage.discard_path):
                    storage.delete_temporary(storage.discard_path)
            except Exception as rollback_error:
                result.divergence += f"; rollback falhou: {rollback_error}"
        if not original_became_backup:
            for temporary in (storage.temporary_path, storage.discard_path):
                try:
                    if temporary in storage._created_temporaries and storage.exists(temporary):
                        storage.delete_temporary(temporary)
                except Exception as cleanup_error:
                    result.divergence += f"; limpeza falhou: {cleanup_error}"
    finally:
        for candidate in (storage.temporary_path, storage.backup_path, storage.discard_path):
            try:
                if storage.exists(candidate):
                    result.remaining_files.append(candidate)
            except Exception:
                result.remaining_files.append(candidate + " (estado desconhecido)")
        result.finished_at = utc_now()
        write_audit(result, audit_path)
    return result
