from __future__ import annotations

import threading
import traceback
import uuid
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any

from app.collection.legacy_core import settings
from app.collection.legacy_core.engine import execute_flow
from app.collection.legacy_core.models import (
    RunOptions,
    ScraperContext,
    build_context,
    build_context_public_dict,
    build_run_options,
    build_runtime_context_dict,
    get_default_run_options,
    is_context_configured,
)
from app.collection.legacy_core.storage import (
    append_runtime_log_line,
    build_default_runtime_state,
    build_slots_public_list,
    build_state_payload,
    clean_queue_items,
    clear_slot_contents,
    create_slot,
    delete_slot,
    format_log_line,
    get_active_slot_name,
    get_default_slot_name,
    get_resume_info,
    get_slot_dir,
    load_available_categories,
    load_catalog_items,
    load_context_config,
    load_existing_products_dict,
    load_full_logs_text,
    load_progress_data,
    load_run_queue_rules,
    normalize_logs_list,
    rename_slot,
    remove_slot_context,
    normalize_state_data,
    now_iso,
    save_context_config,
    save_full_logs_text,
    save_run_queue_rules,
    save_status_text,
    set_active_slot,
    set_default_slot,
)

try:
    from app.core.exceptions import (
        ContinueNotAvailableError,
        InvalidRunModeError,
        StopScraper,
        WorkerAlreadyRunningError,
        WorkerNotRunningError,
        build_error_payload,
    )
except Exception:  # pragma: no cover
    from app.collection.legacy_core.engine import StopScraper

    class InvalidRunModeError(RuntimeError):
        pass

    class WorkerAlreadyRunningError(RuntimeError):
        pass

    class WorkerNotRunningError(RuntimeError):
        pass

    class ContinueNotAvailableError(RuntimeError):
        pass

    class AccountInUseError(RuntimeError):
        pass

    class RunNotFoundError(RuntimeError):
        pass

    def build_error_payload(error: Exception, *, fallback_message: str = "Erro interno.", fallback_code: str = "internal_error") -> dict[str, Any]:
        return {
            "ok": False,
            "error": fallback_code,
            "message": str(error) or fallback_message,
            "details": {},
        }


try:
    AccountInUseError
except NameError:  # pragma: no cover
    class AccountInUseError(RuntimeError):
        pass

try:
    RunNotFoundError
except NameError:  # pragma: no cover
    class RunNotFoundError(RuntimeError):
        pass


# ============================================================
# HELPERS BÁSICOS
# ============================================================


def _normalize_spaces(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).split()).strip()


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "sim"}:
        return True
    if text in {"0", "false", "no", "n", "off", "nao", "não"}:
        return False
    return default


def _get_default_run_mode() -> str:
    return str(getattr(settings, "RUN_MODE_FULL", "full_sync") or "full_sync").strip().lower()


def _get_run_mode_primary() -> str:
    return str(getattr(settings, "RUN_MODE_PRIMARY", "primary") or "primary").strip().lower()


def _get_allowed_run_modes() -> set[str]:
    values = getattr(
        settings,
        "RUN_MODES",
        {
            "full_sync",
            "categories_only",
            "links_only",
            "existing_review",
            "primary",
        },
    )
    try:
        return {str(value).strip().lower() for value in values if str(value).strip()}
    except Exception:
        return {
            "full_sync",
            "categories_only",
            "links_only",
            "existing_review",
            "primary",
        }


def _get_run_modes_with_detail() -> set[str]:
    values = getattr(
        settings,
        "RUN_MODES_WITH_DETAIL",
        {
            _get_default_run_mode(),
            str(getattr(settings, "RUN_MODE_EXISTING_REVIEW", "existing_review") or "existing_review"),
        },
    )
    try:
        return {str(value).strip().lower() for value in values if str(value).strip()}
    except Exception:
        return {
            _get_default_run_mode(),
            "existing_review",
        }


def _get_run_mode_labels() -> dict[str, str]:
    raw = getattr(settings, "RUN_MODE_LABELS", None)
    if isinstance(raw, Mapping):
        return {
            str(key).strip().lower(): str(value)
            for key, value in dict(raw).items()
        }

    return {
        "full_sync": "Iniciar",
        "categories_only": "Atualizar categorias",
        "links_only": "Detectar links",
        "existing_review": "Revisar existentes",
        "primary": "Iniciar",
    }


def normalize_run_mode(value: str | None) -> str:
    run_mode = str(value or "").strip().lower()
    if run_mode in _get_allowed_run_modes():
        return run_mode
    return _get_default_run_mode()


def ensure_run_mode(value: str | None) -> str:
    run_mode = str(value or "").strip().lower()

    if not run_mode:
        return _get_default_run_mode()

    if run_mode not in _get_allowed_run_modes():
        raise InvalidRunModeError(f"Modo de execução inválido: {value!r}")

    return run_mode


def get_run_mode_label(value: str | None) -> str:
    run_mode = normalize_run_mode(value)
    return _get_run_mode_labels().get(run_mode, run_mode)


def normalize_run_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _context_to_public_dict(context: Any) -> dict[str, Any] | None:
    if context is None:
        return None

    if isinstance(context, Mapping):
        return dict(context)

    to_dict = getattr(context, "to_dict", None)
    if callable(to_dict):
        try:
            value = to_dict()
            if isinstance(value, Mapping):
                return dict(value)
        except Exception:
            return None

    result: dict[str, Any] = {}
    for field_name in ("site_key", "item_type_key", "account_key", "slot_name"):
        if hasattr(context, field_name):
            result[field_name] = getattr(context, field_name)

    return result or None


def _map_progress_status_to_label(value: Any) -> str:
    normalized = str(value or "").strip().lower()

    mapping = {
        "": "Parado",
        "parado": "Parado",
        "ready": "Pronto",
        "pronto": "Pronto",
        "rodando": "Rodando",
        "running": "Rodando",
        "em_andamento": "Rodando",
        "in_progress": "Rodando",
        "pausado": "Pausado",
        "paused": "Pausado",
        "interrompido": "Interrompido",
        "stopped": "Interrompido",
        "concluido": "Concluído",
        "completed": "Concluído",
        "erro": "Erro",
        "error": "Erro",
    }

    return mapping.get(normalized, str(value or "Parado"))


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _normalize_run_id(value: str | None) -> str:
    text = _normalize_spaces(value)
    return text or _new_run_id()


def _build_account_lock_key(context: ScraperContext | Mapping[str, Any] | None) -> str:
    resolved = build_context(context)
    return f"{resolved.site_key}:{resolved.account_key}"


def _build_run_public_summary(app: Any) -> dict[str, Any]:
    if app is None:
        return {}

    def _as_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _ensure_trailing_slash_local(value: Any) -> str:
        text = _normalize_spaces(value)
        if not text:
            return ""
        return text if text.endswith("/") else f"{text}/"

    context_public = {}
    with_context = getattr(app, "get_current_context_public", None)
    if callable(with_context):
        try:
            context_public = dict(with_context())
        except Exception:
            context_public = {}

    state_payload = {}
    snapshot = getattr(app, "snapshot", None)
    if callable(snapshot):
        try:
            payload = snapshot(max_logs=0)
            if isinstance(payload, Mapping):
                state_payload = dict(payload.get("data", payload))
        except Exception:
            state_payload = {}

    saved_count = max(0, _as_int(state_payload.get("saved_count", 0), 0))
    timer_seconds = max(0, _as_int(state_payload.get("timer_seconds", 0), 0))
    scope_mode = _normalize_spaces(state_payload.get("scope_mode", "all")).lower()

    selected_categories_raw = state_payload.get("selected_categories", [])
    if not isinstance(selected_categories_raw, list):
        selected_categories_raw = []

    selected_categories = {
        _ensure_trailing_slash_local(item)
        for item in selected_categories_raw
        if _ensure_trailing_slash_local(item)
    }

    total_expected = 0
    available_categories = state_payload.get("available_categories", [])
    if isinstance(available_categories, list):
        for category in available_categories:
            if not isinstance(category, Mapping):
                continue

            category_url = _ensure_trailing_slash_local(
                category.get("url", category.get("categoria_url", ""))
            )

            if scope_mode == "selected" and selected_categories:
                if category_url not in selected_categories:
                    continue

            total_expected += max(
                0,
                _as_int(
                    category.get(
                        "total",
                        category.get("total_esperado", category.get("expected_total", 0)),
                    ),
                    0,
                ),
            )

    if total_expected <= 0:
        total_expected = max(0, _as_int(state_payload.get("total_expected", 0), 0))

    status_text = _normalize_spaces(state_payload.get("status", "Parado")) or "Parado"
    status_lower = status_text.lower()

    if total_expected <= 0 and saved_count > 0 and (
        "conclu" in status_lower or "completed" in status_lower
    ):
        total_expected = saved_count

    if total_expected > 0:
        progress_percent = int(round((saved_count / total_expected) * 100))
        progress_percent = max(0, min(100, progress_percent))
    elif "conclu" in status_lower or "completed" in status_lower:
        progress_percent = 100
    else:
        progress_percent = 0

    return {
        "run_id": _normalize_spaces(getattr(app, "run_id", "")),
        "account_lock_key": _normalize_spaces(getattr(app, "get_account_lock_key", lambda: "")()),
        "context": context_public,
        "status": status_text,
        "summary": state_payload.get("summary", ""),
        "running": bool(state_payload.get("running", False)),
        "paused": bool(state_payload.get("paused", False)),
        "updated_at": state_payload.get("updated_at", ""),
        "saved_count": saved_count,
        "total_expected": total_expected,
        "progress_percent": progress_percent,
        "timer_seconds": timer_seconds,
    }


# ============================================================
# ESTADO EM MEMÓRIA
# ============================================================


class RuntimeState:
    def __init__(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        initial_data: Mapping[str, Any] | None = None,
        initial_logs: Iterable[Any] | str | None = None,
        max_logs_in_memory: int | None = None,
        snapshot_logs_limit: int | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._max_logs_in_memory = max(1, int(max_logs_in_memory or getattr(settings, "STATE_MAX_LOGS_IN_MEMORY", 5000)))
        self._snapshot_logs_limit = max(1, int(snapshot_logs_limit or getattr(settings, "STATE_SNAPSHOT_LOGS_LIMIT", 600)))

        self._context = build_context(context)
        base_data = build_default_runtime_state(self._context)

        if isinstance(initial_data, Mapping):
            base_data.update(dict(initial_data))

        self._data = normalize_state_data(base_data, self._context)
        self._logs = normalize_logs_list(initial_logs, max_items=self._max_logs_in_memory)

    def _touch_updated_at_unlocked(self) -> None:
        self._data["updated_at"] = now_iso()

    def set_context(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        rebase_data: bool = True,
    ) -> dict[str, Any] | None:
        resolved = build_context(context)

        with self._lock:
            self._context = resolved

            if rebase_data:
                self._data = normalize_state_data(self._data, self._context)
                self._touch_updated_at_unlocked()

            return _context_to_public_dict(self._context)

    def get_context(self) -> dict[str, Any] | None:
        with self._lock:
            return _context_to_public_dict(self._context)

    def update(self, data: Mapping[str, Any] | None = None, /, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if isinstance(data, Mapping):
            payload.update(dict(data))
        if kwargs:
            payload.update(kwargs)

        with self._lock:
            self._data.update(payload)
            self._touch_updated_at_unlocked()
            self._data = normalize_state_data(self._data, self._context)
            return dict(self._data)

    def replace(self, data: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            base = build_default_runtime_state(self._context)
            if isinstance(data, Mapping):
                base.update(dict(data))
            self._data = normalize_state_data(base, self._context)
            self._touch_updated_at_unlocked()
            return dict(self._data)

    def reset(self, *, preserve_logs: bool = True) -> dict[str, Any]:
        with self._lock:
            self._data = build_default_runtime_state(self._context)
            self._touch_updated_at_unlocked()

            if not preserve_logs:
                self._logs = []

            self._data = normalize_state_data(self._data, self._context)
            return dict(self._data)

    def get_data(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def append_log(
        self,
        text: Any,
        *,
        persist_runtime: bool = False,
        timestamp: str | None = None,
        already_formatted: bool = True,
    ) -> str:
        line = str(text or "").rstrip()
        if not already_formatted:
            line = format_log_line(line, timestamp=timestamp)

        with self._lock:
            self._logs.append(line)
            if len(self._logs) > self._max_logs_in_memory:
                self._logs = self._logs[-self._max_logs_in_memory:]
            self._touch_updated_at_unlocked()

        if persist_runtime:
            try:
                append_runtime_log_line(
                    line,
                    self._context,
                    timestamp=timestamp if not already_formatted else None,
                )
            except Exception:
                pass

        return line

    def extend_logs(
        self,
        logs: Iterable[Any] | str | None,
        *,
        persist_runtime: bool = False,
    ) -> list[str]:
        new_logs = normalize_logs_list(logs)
        appended: list[str] = []

        for item in new_logs:
            appended.append(
                self.append_log(
                    item,
                    persist_runtime=persist_runtime,
                    already_formatted=True,
                )
            )

        return appended

    def set_logs(self, logs: Iterable[Any] | str | None) -> list[str]:
        normalized = normalize_logs_list(logs, max_items=self._max_logs_in_memory)
        with self._lock:
            self._logs = normalized
            self._touch_updated_at_unlocked()
            return list(self._logs)

    def clear_logs(self) -> None:
        with self._lock:
            self._logs = []
            self._touch_updated_at_unlocked()

    def get_logs(self, *, max_items: int | None = None) -> list[str]:
        with self._lock:
            if max_items is None:
                return list(self._logs)
            return list(self._logs[-max(0, int(max_items)):])

    def full_logs_text(self) -> str:
        with self._lock:
            return "\n".join(self._logs)

    def snapshot(self, *, max_logs: int | None = None) -> dict[str, Any]:
        with self._lock:
            return build_state_payload(
                data=self._data,
                logs=self._logs,
                context=self._context,
                max_logs=self._snapshot_logs_limit if max_logs is None else max_logs,
            )

    def to_public_dict(self, *, max_logs: int | None = None) -> dict[str, Any]:
        return self.snapshot(max_logs=max_logs)

    def persist_status(self) -> None:
        try:
            save_status_text(self, self._context)
        except Exception:
            pass

    def persist_full_logs(self, *, also_save_status: bool = True) -> None:
        try:
            save_full_logs_text(
                self,
                self._context,
                also_save_status=also_save_status,
            )
        except Exception:
            pass

    def persist_all(self) -> None:
        self.persist_full_logs(also_save_status=True)


class SharedState(RuntimeState):
    pass


# ============================================================
# CONTROLE DE EXECUÇÃO
# ============================================================


class PassiveControl:
    def reset(self, **_: Any) -> "PassiveControl":
        return self

    def pause(self, **_: Any) -> bool:
        return False

    def resume(self, **_: Any) -> bool:
        return False

    def stop(self, **_: Any) -> bool:
        return False

    def is_paused(self) -> bool:
        return False

    def should_stop(self) -> bool:
        return False

    def is_running(self) -> bool:
        return False

    def cleanup_finished_worker(self) -> bool:
        return False

    def get_current_run_mode(self) -> str:
        return _get_default_run_mode()

    def get_current_run_payload(self) -> dict[str, Any]:
        return {}

    def get_current_context(self) -> dict[str, Any] | None:
        return None

    def snapshot(self) -> dict[str, Any]:
        run_mode = self.get_current_run_mode()
        return {
            "current_run_mode": run_mode,
            "current_run_mode_label": get_run_mode_label(run_mode),
            "current_run_payload": {},
            "current_context": None,
            "paused": False,
            "stop_requested": False,
            "running": False,
            "worker_name": "",
            "worker_ident": None,
            "worker_alive": False,
        }


class ControlState:
    def __init__(
        self,
        *,
        run_mode: str | None = None,
        run_payload: Mapping[str, Any] | None = None,
        context: ScraperContext | Mapping[str, Any] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.current_run_mode = normalize_run_mode(run_mode)
        self.current_run_payload = normalize_run_payload(run_payload)
        self.current_context = build_context(context) if context is not None else None

    def reset(
        self,
        *,
        clear_run_payload: bool = False,
        clear_context: bool = False,
        clear_worker_if_finished: bool = True,
    ) -> "ControlState":
        with self._lock:
            self.pause_event.clear()
            self.stop_event.clear()

            if clear_run_payload:
                self.current_run_payload = {}

            if clear_context:
                self.current_context = None

            if clear_worker_if_finished:
                self.cleanup_finished_worker()

        return self

    def set_run_mode(self, run_mode: str | None) -> str:
        normalized = ensure_run_mode(run_mode)
        with self._lock:
            self.current_run_mode = normalized
        return normalized

    def get_current_run_mode(self) -> str:
        with self._lock:
            return self.current_run_mode

    def set_run_payload(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        normalized = normalize_run_payload(payload)
        with self._lock:
            self.current_run_payload = normalized
            return dict(self.current_run_payload)

    def update_run_payload(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        normalized = normalize_run_payload(payload)
        with self._lock:
            self.current_run_payload.update(normalized)
            return dict(self.current_run_payload)

    def clear_run_payload(self) -> None:
        with self._lock:
            self.current_run_payload = {}

    def get_current_run_payload(self) -> dict[str, Any]:
        with self._lock:
            return dict(self.current_run_payload)

    def set_context(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
    ) -> ScraperContext | None:
        resolved = build_context(context) if context is not None else None
        with self._lock:
            self.current_context = resolved
        return resolved

    def clear_context(self) -> None:
        with self._lock:
            self.current_context = None

    def get_current_context(self) -> dict[str, Any] | None:
        with self._lock:
            return _context_to_public_dict(self.current_context)

    def prepare_run(
        self,
        *,
        run_mode: str | None = None,
        run_payload: Mapping[str, Any] | None = None,
        context: ScraperContext | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self.reset(clear_worker_if_finished=True)

            if run_mode is not None:
                self.current_run_mode = ensure_run_mode(run_mode)

            if run_payload is not None:
                self.current_run_payload = normalize_run_payload(run_payload)

            if context is not None:
                self.current_context = build_context(context)

            return self.snapshot()

    def pause(self, *, require_running: bool = False) -> bool:
        if require_running:
            self.require_running()
        with self._lock:
            self.pause_event.set()
        return True

    def resume(self, *, require_running: bool = False) -> bool:
        if require_running:
            self.require_running()
        with self._lock:
            self.pause_event.clear()
        return True

    def stop(self, *, require_running: bool = False) -> bool:
        if require_running:
            self.require_running()
        with self._lock:
            self.stop_event.set()
            self.pause_event.clear()
        return True

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def get_worker_thread(self) -> threading.Thread | None:
        with self._lock:
            return self.worker_thread

    def cleanup_finished_worker(self) -> bool:
        with self._lock:
            if self.worker_thread is None:
                return False

            if self.worker_thread.is_alive():
                return False

            self.worker_thread = None
            return True

    def is_running(self) -> bool:
        self.cleanup_finished_worker()
        with self._lock:
            return self.worker_thread is not None and self.worker_thread.is_alive()

    def require_running(self) -> None:
        if not self.is_running():
            raise WorkerNotRunningError("Não há processo rodando.")

    def require_not_running(self) -> None:
        if self.is_running():
            raise WorkerAlreadyRunningError("O processo já está rodando.")

    def attach_worker_thread(
        self,
        thread: threading.Thread,
        *,
        allow_replace: bool = False,
    ) -> threading.Thread:
        if not isinstance(thread, threading.Thread):
            raise TypeError("thread precisa ser uma instância de threading.Thread.")

        with self._lock:
            self.cleanup_finished_worker()

            if (
                not allow_replace
                and self.worker_thread is not None
                and self.worker_thread.is_alive()
            ):
                raise WorkerAlreadyRunningError("O processo já está rodando.")

            self.worker_thread = thread
            return thread

    def detach_worker_thread(
        self,
        thread: threading.Thread | None = None,
    ) -> None:
        with self._lock:
            if thread is None:
                self.worker_thread = None
                return

            if self.worker_thread is thread:
                self.worker_thread = None

    def start_worker_thread(
        self,
        target: Callable[..., Any],
        *,
        name: str = "scraper-worker",
        daemon: bool = True,
        args: tuple[Any, ...] = (),
        kwargs: Mapping[str, Any] | None = None,
    ) -> threading.Thread:
        self.require_not_running()

        thread = threading.Thread(
            target=target,
            name=name,
            daemon=daemon,
            args=args,
            kwargs=dict(kwargs or {}),
        )
        self.attach_worker_thread(thread)
        thread.start()
        return thread

    def wait_for_worker(self, timeout: float | None = None) -> bool:
        thread = self.get_worker_thread()
        if thread is None:
            return True

        thread.join(timeout=timeout)
        self.cleanup_finished_worker()
        return not self.is_running()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            worker_thread = self.worker_thread
            worker_alive = bool(worker_thread and worker_thread.is_alive())

            return {
                "current_run_mode": self.current_run_mode,
                "current_run_mode_label": get_run_mode_label(self.current_run_mode),
                "current_run_payload": dict(self.current_run_payload),
                "current_context": _context_to_public_dict(self.current_context),
                "paused": self.pause_event.is_set(),
                "stop_requested": self.stop_event.is_set(),
                "running": worker_alive,
                "worker_name": worker_thread.name if worker_thread else "",
                "worker_ident": worker_thread.ident if worker_thread else None,
                "worker_alive": worker_alive,
            }


# ============================================================
# APP PRINCIPAL
# ============================================================


class ScraperApp:
    def __init__(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        site_key: str | None = None,
        item_type_key: str | None = None,
        account_key: str | None = None,
        slot_name: str | None = None,
        auto_load_summary: bool = True,
        run_id: str | None = None,
        manager: Any | None = None,
    ) -> None:
        self.context = build_context(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        self.run_id = _normalize_run_id(run_id)
        self.manager = manager
        self._account_lock_owned = False
        self.control = ControlState(context=self.context)
        self.state = RuntimeState(context=self.context)
        self.server: Any = None

        self.refresh_slots_state()
        self._sync_manager_metadata()

        if auto_load_summary:
            self.load_initial_summary()

    # ========================================================
    # CONTEXTO
    # ========================================================

    def _set_context_internal(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        site_key: str | None = None,
        item_type_key: str | None = None,
        account_key: str | None = None,
        slot_name: str | None = None,
        rebase_state: bool = True,
    ) -> ScraperContext:
        resolved = build_context(
            context or self.context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
        )
        self.context = resolved
        self.control.set_context(resolved)
        self.state.set_context(resolved, rebase_data=rebase_state)
        self._sync_manager_metadata()
        return resolved

    def set_context(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        site_key: str | None = None,
        item_type_key: str | None = None,
        account_key: str | None = None,
        slot_name: str | None = None,
        load_summary: bool = True,
    ) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível trocar o contexto com o processo rodando.")

        resolved = self._set_context_internal(
            context,
            site_key=site_key,
            item_type_key=item_type_key,
            account_key=account_key,
            slot_name=slot_name,
            rebase_state=True,
        )
        self.refresh_slots_state()

        if load_summary:
            self.load_initial_summary()

        return resolved.to_public_dict()

    def get_current_context(self) -> ScraperContext:
        return self.context

    def get_current_context_public(self) -> dict[str, Any]:
        return build_context_public_dict(self.context)

    def get_runtime_context_dict(self) -> dict[str, Any]:
        return build_runtime_context_dict(self.context)

    def is_current_context_configured(self) -> bool:
        return is_context_configured(self.context)

    def get_current_slot(self) -> str:
        return str(self.context.slot_name)

    def get_account_lock_key(self) -> str:
        return _build_account_lock_key(self.context)

    def _find_first_context_in_slot(self, slot_name: str | None) -> dict[str, str] | None:
        slot_dir = get_slot_dir(slot_name)

        if not slot_dir.exists() or not slot_dir.is_dir():
            return None

        for site_dir in sorted(slot_dir.iterdir(), key=lambda path: path.name.lower()):
            if not site_dir.is_dir():
                continue

            for item_type_dir in sorted(site_dir.iterdir(), key=lambda path: path.name.lower()):
                if not item_type_dir.is_dir():
                    continue

                for account_dir in sorted(item_type_dir.iterdir(), key=lambda path: path.name.lower()):
                    if not account_dir.is_dir():
                        continue

                    return {
                        "site_key": site_dir.name,
                        "item_type_key": item_type_dir.name,
                        "account_key": account_dir.name,
                        "slot_name": settings.normalize_slot_name(slot_name),
                    }

        return None

    def set_manager(self, manager: Any | None, *, run_id: str | None = None) -> None:
        self.manager = manager
        if run_id is not None:
            self.run_id = _normalize_run_id(run_id)
        self._sync_manager_metadata()

    def set_account_lock_owned(self, owned: bool) -> None:
        self._account_lock_owned = bool(owned)
        self._sync_manager_metadata()

    def _sync_manager_metadata(self) -> dict[str, Any]:
        return self.state.update(
            run_id=self.run_id,
            account_lock_key=self.get_account_lock_key(),
            account_lock_owned=self._account_lock_owned,
        )

    def _release_manager_account_lock(self) -> None:
        manager = self.manager
        releaser = getattr(manager, "release_account_lock", None)
        if callable(releaser):
            try:
                releaser(self.run_id)
            except Exception:
                pass
        self._account_lock_owned = False
        self._sync_manager_metadata()

    # ========================================================
    # SNAPSHOT / LOGS
    # ========================================================

    def snapshot(self, *, max_logs: int | None = None) -> dict[str, Any]:
        return self.state.snapshot(max_logs=max_logs)

    def build_public_state_payload(self, *, max_logs: int | None = None) -> dict[str, Any]:
        return self.snapshot(max_logs=max_logs)

    def log(self, message: Any) -> str:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {str(message)}"
        print(line)
        self.state.append_log(line, persist_runtime=True, already_formatted=True)
        return line

    def log_exception(self, prefix: str, error: Exception) -> str:
        err = "".join(traceback.format_exception_only(type(error), error)).strip()
        tb = traceback.format_exc().strip()

        self.log(f"{prefix}: {err}")

        if tb:
            for line in tb.splitlines():
                self.log(line)

        return err

    def refresh_slots_state(self) -> dict[str, Any]:
        current_slot = settings.normalize_slot_name(self.context.slot_name or get_active_slot_name())
        default_slot = get_default_slot_name()

        data = self.state.update(
            current_slot=current_slot,
            default_slot=default_slot,
            slot_name=current_slot,
            slots=build_slots_public_list(),
        )
        return data

    def _sync_state_with_control(self) -> dict[str, Any]:
        control_snapshot = self.control.snapshot()
        return self.state.update(
            run_id=self.run_id,
            account_lock_key=self.get_account_lock_key(),
            account_lock_owned=self._account_lock_owned,
            run_mode=control_snapshot.get("current_run_mode", self.state.get_data().get("run_mode", _get_default_run_mode())),
            run_mode_label=control_snapshot.get("current_run_mode_label", get_run_mode_label(_get_default_run_mode())),
            paused=control_snapshot.get("paused", False),
            stop_requested=control_snapshot.get("stop_requested", False),
            running=control_snapshot.get("running", False),
            worker_name=control_snapshot.get("worker_name", ""),
            worker_ident=control_snapshot.get("worker_ident"),
            worker_alive=control_snapshot.get("worker_alive", False),
            current_run_payload=control_snapshot.get("current_run_payload", {}),
        )

    # ========================================================
    # CONFIG / OPTIONS / SUMMARY
    # ========================================================

    def get_run_options(self) -> RunOptions:
        return build_run_options(load_context_config(self.context))

    def get_run_options_public(self) -> dict[str, Any]:
        return self.get_run_options().to_dict()

    def save_run_options(
        self,
        run_options: Mapping[str, Any] | RunOptions | None,
    ) -> dict[str, Any]:
        normalized = build_run_options(run_options).to_dict()
        saved = save_context_config(normalized, self.context)
        self.state.update(
            verify_mode=saved.get("verify_mode", normalized.get("verify_mode", settings.DEFAULT_VERIFY_MODE)),
            scope_mode=saved.get("scope_mode", normalized.get("scope_mode", "all")),
            scope_start=saved.get("scope_start", normalized.get("scope_start", 1)),
            scope_end=saved.get("scope_end", normalized.get("scope_end", 0)),
            scope_match_text=saved.get("scope_match_text", normalized.get("scope_match_text", "")),
            save_every_items=saved.get("save_every_items", normalized.get("save_every_items", getattr(settings, "DEFAULT_SAVE_EVERY_ITEMS", 10))),
            save_every_minutes=saved.get("save_every_minutes", normalized.get("save_every_minutes", getattr(settings, "DEFAULT_SAVE_EVERY_MINUTES", 10))),
            selected_categories=saved.get("selected_categories", normalized.get("selected_categories", [])),
        )
        return saved

    def get_continue_info(self) -> dict[str, Any]:
        progress = load_progress_data(self.context)
        meta = progress.get("meta", {}) if isinstance(progress, Mapping) else {}
        if not isinstance(meta, Mapping):
            meta = {}

        return get_resume_info(
            meta,
            allowed_run_modes_with_detail=_get_run_modes_with_detail(),
            run_mode_labels=_get_run_mode_labels(),
        )

    def can_continue(self) -> bool:
        return bool(self.get_continue_info().get("can_continue", False))

    def load_initial_summary(self) -> dict[str, Any]:
        config = load_context_config(self.context)
        progress = load_progress_data(self.context)
        meta = progress.get("meta", {}) if isinstance(progress, Mapping) else {}
        if not isinstance(meta, Mapping):
            meta = {}

        full_logs_text = load_full_logs_text(self.context)
        available_categories = load_available_categories(self.context)
        saved_count = len(load_existing_products_dict(self.context))
        continue_info = self.get_continue_info()

        status_text = _map_progress_status_to_label(meta.get("status", "Parado"))
        run_mode = normalize_run_mode(meta.get("run_mode", _get_default_run_mode()))
        if run_mode == _get_run_mode_primary():
            run_mode = _get_default_run_mode()

        data = build_default_runtime_state(self.context)
        data.update(config)
        data.update(
            site_key=self.context.site_key,
            item_type_key=self.context.item_type_key,
            account_key=self.context.account_key,
            slot_name=self.context.slot_name,
            context_prefix=self.context.context_prefix,
            current_slot=self.context.slot_name,
            default_slot=get_default_slot_name(),
            slots=build_slots_public_list(),
            available_categories=available_categories,
            selected_categories=config.get("selected_categories", []),
            saved_count=int(progress.get("total_salvos", saved_count) if isinstance(progress, Mapping) else saved_count),
            pending_count=0,
            status=status_text,
            summary=f"Itens já salvos: {int(progress.get('total_salvos', saved_count) if isinstance(progress, Mapping) else saved_count)}",
            current_phase=_normalize_spaces(meta.get("current_phase", "")) or "-",
            current_category=_normalize_spaces(meta.get("ultima_categoria", meta.get("current_category", ""))) or "-",
            current_item=_normalize_spaces(meta.get("ultimo_item_nome", meta.get("current_item", ""))) or "-",
            run_mode=run_mode,
            run_mode_label=get_run_mode_label(run_mode),
            resume_run_mode=continue_info.get("run_mode") or run_mode,
            resume_run_mode_label=continue_info.get("run_mode_label") or get_run_mode_label(run_mode),
            can_continue=continue_info.get("can_continue", False),
            resume_queue_index=continue_info.get("queue_index", 0),
            resume_queue_total=continue_info.get("queue_total", 0),
            reused_categories=meta.get("categorias_reutilizadas", meta.get("reused_categories", 0)),
            refetched_categories=meta.get("categorias_refeitas", meta.get("refetched_categories", 0)),
            queue_detected_count=meta.get("queue_detected_count", 0),
            new_links_detected=meta.get("new_links_detected", 0),
            existing_links_detected=meta.get("existing_links_detected", 0),
            new_items_added=meta.get("itens_novos_adicionados", 0),
            items_updated=meta.get("itens_atualizados", 0),
            items_unchanged=meta.get("itens_sem_mudanca", 0),
            run_started_at=_normalize_spaces(meta.get("run_started_at", "")),
            run_finished_at=_normalize_spaces(meta.get("run_finished_at", "")),
            timer_seconds=meta.get("timer_seconds", 0),
            timer_text=_normalize_spaces(meta.get("timer_text", "")) or "0:00:00",
            primary_button_label="▶️ Retomar" if int(progress.get("total_salvos", saved_count) if isinstance(progress, Mapping) else saved_count) > 0 else "▶️ Iniciar",
            running=False,
            paused=False,
            stop_requested=False,
            worker_name="",
            worker_ident=None,
            worker_alive=False,
            current_run_payload={},
            run_id=self.run_id,
            account_lock_key=self.get_account_lock_key(),
            account_lock_owned=self._account_lock_owned,
        )

        self.state.replace(data)
        self.state.set_logs(full_logs_text)
        self._sync_state_with_control()
        return self.snapshot()

    # ========================================================
    # RUN / WORKER
    # ========================================================

    def get_current_run_mode(self) -> str:
        return self.control.get_current_run_mode()

    def is_running(self) -> bool:
        return self.control.is_running()

    def is_paused(self) -> bool:
        return self.control.is_paused()

    def start(
        self,
        *,
        run_mode: str | None = None,
        run_options: Mapping[str, Any] | RunOptions | None = None,
        run_payload: Mapping[str, Any] | None = None,
        resume: bool = False,
        clear_logs: bool = True,
    ) -> dict[str, Any]:
        self.control.require_not_running()

        normalized_run_mode = ensure_run_mode(run_mode or _get_default_run_mode())
        normalized_run_options = build_run_options(run_options or self.get_run_options())
        normalized_run_payload = normalize_run_payload(run_payload)

        if resume:
            normalized_run_payload["resume"] = True

        if normalized_run_payload.get("resume") and not self.can_continue():
            raise ContinueNotAvailableError("Não há continuação utilizável salva.")

        self.save_run_options(normalized_run_options)

        if clear_logs:
            self.state.clear_logs()

        self.control.prepare_run(
            run_mode=normalized_run_mode,
            run_payload=normalized_run_payload,
            context=self.context,
        )

        self.state.update(
            status="Iniciando",
            summary="Preparando execução",
            running=True,
            paused=False,
            stop_requested=False,
            current_phase="Inicializando",
            current_category="-",
            current_item="-",
            run_mode=normalized_run_mode,
            run_mode_label=get_run_mode_label(normalized_run_mode),
            verify_mode=normalized_run_options.verify_mode,
            scope_mode=normalized_run_options.scope_mode,
            scope_start=normalized_run_options.scope_start,
            scope_end=normalized_run_options.scope_end,
            scope_match_text=normalized_run_options.scope_match_text,
            save_every_items=normalized_run_options.save_every_items,
            save_every_minutes=normalized_run_options.save_every_minutes,
            selected_categories=list(normalized_run_options.selected_categories),
            run_started_at=now_iso(),
            run_finished_at="",
            timer_seconds=0,
            timer_text="0:00:00",
            can_continue=False,
            resume_queue_index=0,
            resume_queue_total=0,
            current_run_payload=normalized_run_payload,
        )
        self.refresh_slots_state()
        self._sync_state_with_control()

        self.log(
            f"🚀 Iniciando fluxo: {get_run_mode_label(normalized_run_mode)} | "
            f"site={self.context.site_key} | tipo={self.context.item_type_key} | "
            f"conta={self.context.account_key} | slot={self.context.slot_name}"
        )

        thread = self.control.start_worker_thread(
            target=self._worker_entrypoint,
            name="scraper-worker",
            daemon=True,
            kwargs={
                "run_mode": normalized_run_mode,
                "run_options": normalized_run_options,
                "run_payload": normalized_run_payload,
                "context": self.context,
            },
        )
        self._sync_state_with_control()

        return {
            "ok": True,
            "message": "Processo iniciado.",
            "worker_name": thread.name,
            "state": self.snapshot(),
        }

    def continue_run(
        self,
        *,
        run_mode: str | None = None,
        run_options: Mapping[str, Any] | RunOptions | None = None,
        run_payload: Mapping[str, Any] | None = None,
        clear_logs: bool = True,
    ) -> dict[str, Any]:
        payload = dict(normalize_run_payload(run_payload))
        payload["resume"] = True
        return self.start(
            run_mode=run_mode or self.get_continue_info().get("run_mode") or _get_default_run_mode(),
            run_options=run_options,
            run_payload=payload,
            resume=True,
            clear_logs=clear_logs,
        )

    def _worker_entrypoint(
        self,
        *,
        run_mode: str,
        run_options: RunOptions | Mapping[str, Any],
        run_payload: Mapping[str, Any] | None,
        context: ScraperContext,
    ) -> None:
        current_thread = threading.current_thread()
        completed_successfully = False

        try:
            self._sync_state_with_control()
            execute_flow(
                self,
                run_options,
                run_mode,
                run_payload,
                context=context,
            )

            self.state.update(
                summary="Execução finalizada.",
            )
            completed_successfully = True

        except StopScraper:
            self.log("⏹ Execução interrompida.")
            self.state.update(
                status="Interrompido",
                summary="Execução interrompida pelo usuário.",
            )

        except Exception as error:
            self.log_exception("❌ Erro no worker", error)
            self.state.update(
                status="Erro",
                summary=str(error) or "Erro durante a execução.",
            )

        finally:
            self.control.detach_worker_thread(current_thread)
            self.control.reset(clear_run_payload=False, clear_context=False, clear_worker_if_finished=False)

            self.state.update(
                running=False,
                paused=False,
                stop_requested=False,
                worker_name="",
                worker_ident=None,
                worker_alive=False,
                run_finished_at=now_iso(),
            )

            continue_info = self.get_continue_info()
            self.state.update(
                can_continue=continue_info.get("can_continue", False),
                resume_run_mode=continue_info.get("run_mode") or self.state.get_data().get("run_mode", _get_default_run_mode()),
                resume_run_mode_label=continue_info.get("run_mode_label") or get_run_mode_label(self.state.get_data().get("run_mode", _get_default_run_mode())),
                resume_queue_index=continue_info.get("queue_index", 0),
                resume_queue_total=continue_info.get("queue_total", 0),
            )

            self.refresh_slots_state()
            self._release_manager_account_lock()

            if completed_successfully:
                trigger_queue = getattr(self.manager, "trigger_queue_for_context", None)
                if callable(trigger_queue):
                    try:
                        queue_result = trigger_queue(context, source_run_id=self.run_id)
                    except Exception as queue_error:
                        self.log_exception("❌ Erro ao acionar fila", queue_error)
                    else:
                        for item in queue_result.get("started", []) or []:
                            target = dict(item.get("target", {}) or {})
                            self.log(
                                "⏭ Fila acionada: "
                                f"{target.get('slot_name', '-')} | "
                                f"{target.get('site_key', '-')} | "
                                f"{target.get('item_type_key', '-')} | "
                                f"{target.get('account_key', '-')}"
                            )

                        for item in queue_result.get("skipped", []) or []:
                            self.log(f"⚠ Fila ignorada: {item.get('message', 'Regra não iniciada.')}")

            self.state.persist_all()

    def pause(self) -> dict[str, Any]:
        self.control.pause(require_running=True)
        self.state.update(
            paused=True,
            status="Pausado",
            summary="Execução pausada.",
        )
        self._sync_state_with_control()
        self.log("⏸ Pausa solicitada.")
        return {"ok": True, "message": "Execução pausada.", "state": self.snapshot()}

    def resume(self) -> dict[str, Any]:
        self.control.resume(require_running=True)
        self.state.update(
            paused=False,
            status="Rodando",
            summary="Execução retomada.",
        )
        self._sync_state_with_control()
        self.log("▶️ Retomada solicitada.")
        return {"ok": True, "message": "Execução retomada.", "state": self.snapshot()}

    def stop(self) -> dict[str, Any]:
        self.control.stop(require_running=True)
        self.state.update(
            stop_requested=True,
            paused=False,
            status="Parando",
            summary="Parada solicitada.",
        )
        self._sync_state_with_control()
        self.log("🛑 Parada solicitada.")
        return {"ok": True, "message": "Parada solicitada.", "state": self.snapshot()}

    def wait(self, timeout: float | None = None) -> bool:
        finished = self.control.wait_for_worker(timeout=timeout)
        self._sync_state_with_control()
        return finished

    # ========================================================
    # SLOT
    # ========================================================

    def switch_slot(self, slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível trocar o slot com o processo rodando.")

        new_slot = set_active_slot(slot_name)
        self._set_context_internal(slot_name=new_slot, rebase_state=True)
        self.load_initial_summary()
        self.log(f"📂 Slot ativo alterado para: {new_slot}")
        return {"ok": True, "slot_name": new_slot, "state": self.snapshot()}

    def create_and_switch_slot(self, slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível criar/trocar slot com o processo rodando.")

        new_slot = create_slot(slot_name)
        self._set_context_internal(slot_name=new_slot, rebase_state=True)
        self.load_initial_summary()
        self.log(f"🆕 Slot criado e ativado: {new_slot}")
        return {"ok": True, "slot_name": new_slot, "state": self.snapshot()}

    def rename_slot(self, old_slot_name: str | None, new_slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível renomear slot com o processo rodando.")

        normalized_old_slot_name = settings.normalize_slot_name(old_slot_name)
        success, message, renamed_slot_name = rename_slot(
            normalized_old_slot_name,
            new_slot_name,
        )

        active_slot = get_active_slot_name()
        self._set_context_internal(slot_name=active_slot, rebase_state=True)
        self.load_initial_summary()

        if success:
            self.log(f"✏️ {message}")
            return {
                "ok": True,
                "message": message,
                "slot_name": renamed_slot_name,
                "state": self.snapshot(),
            }

        return {
            "ok": False,
            "message": message,
            "slot_name": renamed_slot_name,
            "state": self.snapshot(),
        }

    def remove_slot_context(
        self,
        slot_name: str | None,
        site_key: str | None,
        item_type_key: str | None,
        account_key: str | None,
    ) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível remover contexto com o processo rodando.")

        normalized_slot_name = settings.normalize_slot_name(slot_name)
        normalized_site_key = str(site_key or "").strip()
        normalized_item_type_key = str(item_type_key or "").strip()
        normalized_account_key = str(account_key or "").strip()

        current_matches = (
            settings.normalize_slot_name(getattr(self.context, "slot_name", "")) == normalized_slot_name
            and getattr(self.context, "site_key", "") == normalized_site_key
            and getattr(self.context, "item_type_key", "") == normalized_item_type_key
            and getattr(self.context, "account_key", "") == normalized_account_key
        )

        success, message = remove_slot_context(
            normalized_slot_name,
            normalized_site_key,
            normalized_item_type_key,
            normalized_account_key,
        )

        if not success:
            self.refresh_slots_state()
            return {"ok": False, "message": message, "state": self.snapshot()}

        fallback_context = None
        if current_matches:
            fallback_context = self._find_first_context_in_slot(normalized_slot_name)

            if fallback_context:
                self._set_context_internal(fallback_context, rebase_state=True)
                self.state.replace(build_default_runtime_state(self.context))
                self.state.clear_logs()
                self.refresh_slots_state()
                self._release_manager_account_lock()
                self.state.persist_all()
                self.load_initial_summary()
            else:
                self.refresh_slots_state()
                self.state.replace(build_default_runtime_state(self.context))
                self.state.clear_logs()
                self.state.update(
                    site_key=self.context.site_key,
                    item_type_key=self.context.item_type_key,
                    account_key=self.context.account_key,
                    slot_name=self.context.slot_name,
                    current_slot=normalized_slot_name,
                    default_slot=get_default_slot_name(),
                    slots=build_slots_public_list(),
                    available_categories=[],
                    selected_categories=[],
                    saved_count=0,
                    pending_count=0,
                    status="Pronto",
                    summary="Contexto removido.",
                    current_phase="-",
                    current_category="-",
                    current_item="-",
                    can_continue=False,
                    resume_queue_index=0,
                    resume_queue_total=0,
                    running=False,
                    paused=False,
                    stop_requested=False,
                )
                self._release_manager_account_lock()
                # Não persista a identidade removida: persist_all recriaria
                # sua árvore no disco e o contexto reapareceria no restart.
        else:
            self.refresh_slots_state()
            self.load_initial_summary()

        if not current_matches or fallback_context:
            self.log(f"🧩 {message}")
        return {"ok": True, "message": message, "state": self.snapshot()}

    def remove_zero_item_contexts(self, slot_name: str | None = None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Nao e possivel remover contextos com o processo rodando.")

        known_slots = {str(item.get("name", "")) for item in build_slots_public_list()}
        requested = str(slot_name or "").strip()
        candidates = [requested] if requested else sorted(known_slots)
        removed: list[dict[str, str]] = []
        errors: list[str] = []

        for candidate in candidates:
            if candidate not in known_slots or settings.normalize_slot_name(candidate) != candidate:
                errors.append(f'Catalogo invalido: "{candidate}".')
                continue
            slot_dir = get_slot_dir(candidate)
            if not slot_dir.is_dir():
                continue
            identities = [
                (site.name, item_type.name, account.name)
                for site in slot_dir.iterdir() if site.is_dir()
                for item_type in site.iterdir() if item_type.is_dir()
                for account in item_type.iterdir() if account.is_dir()
            ]
            for site_key, item_type_key, account_key in identities:
                items = load_catalog_items(
                    site_key=site_key, item_type_key=item_type_key,
                    account_key=account_key, slot_name=candidate,
                )
                if items:
                    continue
                result = self.remove_slot_context(candidate, site_key, item_type_key, account_key)
                if result.get("ok"):
                    removed.append({"slot_name": candidate, "site_key": site_key, "item_type_key": item_type_key, "account_key": account_key})
                else:
                    errors.append(str(result.get("message") or "Falha ao remover contexto."))

        message = f"{len(removed)} contexto(s) zerado(s) removido(s)."
        if errors:
            message += " Falhas: " + " | ".join(errors)
        self.log(f"Contextos zerados: {message}")
        return {"ok": bool(removed) or not errors, "message": message, "removed": removed, "errors": errors, "state": self.snapshot()}

    def define_default_slot(self, slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível alterar o slot default com o processo rodando.")

        updated_slot = set_default_slot(slot_name)
        self.refresh_slots_state()
        self.log(f"⭐ Slot default alterado para: {updated_slot}")
        return {"ok": True, "slot_name": updated_slot, "state": self.snapshot()}

    def remove_slot(self, slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível apagar slot com o processo rodando.")

        normalized_slot_name = settings.normalize_slot_name(slot_name)
        current_slot = settings.normalize_slot_name(
            getattr(self.context, "slot_name", "") or get_active_slot_name()
        )

        if normalized_slot_name == current_slot:
            fallback_slot = get_default_slot_name()
            self._set_context_internal(slot_name=fallback_slot, rebase_state=True)
            self.state.replace(build_default_runtime_state(self.context))
            self.state.clear_logs()
            self.refresh_slots_state()
            self._release_manager_account_lock()
            self.state.persist_all()

        success, message = delete_slot(normalized_slot_name)

        active_slot = get_active_slot_name()
        self._set_context_internal(slot_name=active_slot, rebase_state=True)
        self.load_initial_summary()

        if success:
            self.log(f"🗑 {message}")
            return {"ok": True, "message": message, "state": self.snapshot()}

        return {"ok": False, "message": message, "state": self.snapshot()}

    def clear_slot(self, slot_name: str | None) -> dict[str, Any]:
        if self.is_running():
            raise WorkerAlreadyRunningError("Não é possível limpar slot com o processo rodando.")

        normalized_slot_name = settings.normalize_slot_name(slot_name)
        success, message = clear_slot_contents(normalized_slot_name)

        active_slot = get_active_slot_name()

        if normalized_slot_name == active_slot:
            self._set_context_internal(slot_name=active_slot, rebase_state=True)
            self.state.replace(build_default_runtime_state(self.context))
            self.state.clear_logs()
            self.refresh_slots_state()
            self._release_manager_account_lock()
            self.state.persist_all()
        else:
            self.refresh_slots_state()

        if success:
            return {"ok": True, "message": message, "state": self.snapshot()}

        return {"ok": False, "message": message, "state": self.snapshot()}

    # ========================================================
    # HELPERS PÚBLICOS PARA WEB
    # ========================================================

    def get_boot_payload(self) -> dict[str, Any]:
        self.refresh_slots_state()
        return {
            "ok": True,
            "run_id": self.run_id,
            "account_lock_key": self.get_account_lock_key(),
            "account_lock_owned": self._account_lock_owned,
            "settings": settings.build_structural_public_settings(),
            "context": self.get_current_context_public(),
            "runtime_context": self.get_runtime_context_dict(),
            "configured": self.is_current_context_configured(),
            "run_options": self.get_run_options_public(),
            "continue_info": self.get_continue_info(),
            "state": self.snapshot(),
        }

    def safe_action(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = fn(*args, **kwargs)
            if isinstance(result, Mapping):
                payload = dict(result)
                payload.setdefault("ok", True)
                return payload
            return {"ok": True, "result": result}
        except Exception as error:
            return build_error_payload(error)


# ============================================================
# MULTI-RUN MANAGER
# ============================================================


class ScraperRunManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, ScraperApp] = {}
        self._account_locks: dict[str, str] = {}
        self._primary_run_id: str = ""

    def _ensure_primary_run_id(self, run_id: str) -> None:
        if not self._primary_run_id:
            self._primary_run_id = run_id

    def create_run(
        self,
        context: ScraperContext | Mapping[str, Any] | None = None,
        *,
        run_id: str | None = None,
        site_key: str | None = None,
        item_type_key: str | None = None,
        account_key: str | None = None,
        slot_name: str | None = None,
        auto_load_summary: bool = True,
    ) -> ScraperApp:
        resolved_run_id = _normalize_run_id(run_id)

        with self._lock:
            if resolved_run_id in self._runs:
                raise WorkerAlreadyRunningError(f"A execução '{resolved_run_id}' já existe.")

            app = ScraperApp(
                context,
                site_key=site_key,
                item_type_key=item_type_key,
                account_key=account_key,
                slot_name=slot_name,
                auto_load_summary=auto_load_summary,
                run_id=resolved_run_id,
                manager=self,
            )
            self._runs[resolved_run_id] = app
            self._ensure_primary_run_id(resolved_run_id)
            return app

    def list_run_ids(self) -> list[str]:
        with self._lock:
            return list(self._runs.keys())

    def list_runs_public(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_build_run_public_summary(app) for app in self._runs.values()]

    def has_run(self, run_id: str | None) -> bool:
        resolved_run_id = _normalize_spaces(run_id)
        with self._lock:
            return resolved_run_id in self._runs

    def get_run(self, run_id: str | None = None) -> ScraperApp:
        resolved_run_id = _normalize_spaces(run_id) or self._primary_run_id
        with self._lock:
            app = self._runs.get(resolved_run_id)
            if app is None:
                raise RunNotFoundError(f"Execução não encontrada: {resolved_run_id or '-'}")
            return app

    def get_or_create_primary_run(self) -> ScraperApp:
        with self._lock:
            if self._primary_run_id and self._primary_run_id in self._runs:
                return self._runs[self._primary_run_id]

        return self.create_run()

    def get_queue_rules(self) -> list[dict[str, Any]]:
        return load_run_queue_rules()

    def save_queue_rules(self, rules: Any) -> dict[str, Any]:
        saved = save_run_queue_rules(rules)
        return {
            "ok": True,
            "message": "Fila salva.",
            "queue_rules": saved,
        }

    def _find_reusable_run_for_context(
        self,
        context: ScraperContext | Mapping[str, Any] | None,
    ) -> ScraperApp | None:
        resolved = build_context(context)

        with self._lock:
            for app in self._runs.values():
                app_context = app.get_current_context()
                if (
                    app_context.site_key == resolved.site_key
                    and app_context.item_type_key == resolved.item_type_key
                    and app_context.account_key == resolved.account_key
                    and app_context.slot_name == resolved.slot_name
                ):
                    return app

        return None

    def trigger_queue_for_context(
        self,
        context: ScraperContext | Mapping[str, Any] | None,
        *,
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_source = build_context(context)
        rules = load_run_queue_rules()

        def context_key(value: ScraperContext | Mapping[str, Any] | None) -> tuple[str, str, str, str]:
            resolved = build_context(value)
            return (
                resolved.site_key,
                resolved.item_type_key,
                resolved.account_key,
                resolved.slot_name,
            )

        resolved_source_key = context_key(resolved_source)

        started: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for rule in rules:
            if not bool(rule.get("enabled", True)):
                continue

            source = build_context(rule.get("source"))
            # A regra persiste somente a identidade. O dicionário completo
            # também possui campos derivados, que não devem impedir o match.
            if context_key(source) != resolved_source_key:
                continue

            target = build_context(rule.get("target"))
            existing_app = self._find_reusable_run_for_context(target)

            if existing_app is not None and existing_app.is_running():
                skipped.append(
                    {
                        "target": target.to_dict(),
                        "message": "Já existe uma execução rodando para o destino da fila.",
                    }
                )
                continue

            target_app = existing_app or self.create_run(target, auto_load_summary=True)

            try:
                result = self.start_run(
                    target_app.run_id,
                    run_mode=_get_run_mode_primary(),
                    run_options=load_context_config(target),
                    run_payload={
                        "triggered_by_queue": True,
                        "queue_source_run_id": _normalize_spaces(source_run_id),
                    },
                    clear_logs=True,
                )
                started.append(
                    {
                        "run_id": target_app.run_id,
                        "target": target.to_dict(),
                        "message": str(result.get("message", "Processo iniciado.")),
                    }
                )
            except Exception as error:
                skipped.append(
                    {
                        "target": target.to_dict(),
                        "message": str(error) or "Falha ao iniciar item da fila.",
                    }
                )

        return {
            "started": started,
            "skipped": skipped,
        }

    def remove_run(self, run_id: str | None) -> dict[str, Any]:
        resolved_run_id = _normalize_spaces(run_id)
        if not resolved_run_id:
            raise RunNotFoundError("Execução não encontrada.")

        with self._lock:
            if resolved_run_id == self._primary_run_id:
                raise RuntimeError("A execução principal não pode ser removida.")

            app = self._runs.get(resolved_run_id)
            if app is None:
                raise RunNotFoundError(f"Execução não encontrada: {resolved_run_id}")

        if app.is_running():
            raise WorkerAlreadyRunningError("Não é possível remover uma execução com processo rodando.")

        self.release_account_lock(resolved_run_id)

        with self._lock:
            self._runs.pop(resolved_run_id, None)
            runs = [_build_run_public_summary(item) for item in self._runs.values()]
            primary_run_id = self._primary_run_id

        with suppress(Exception):
            app.set_manager(None)

        return {
            "ok": True,
            "message": f'Execução "{resolved_run_id}" removida.',
            "run_id": resolved_run_id,
            "primary_run_id": primary_run_id,
            "runs": runs,
        }

    def _acquire_account_lock(self, app: ScraperApp) -> str:
        lock_key = app.get_account_lock_key()

        with self._lock:
            owner_run_id = self._account_locks.get(lock_key, "")
            if owner_run_id and owner_run_id != app.run_id:
                owner_app = self._runs.get(owner_run_id)
                owner_context = owner_app.get_current_context_public() if owner_app is not None else {}
                owner_label = _normalize_spaces(owner_context.get("account_key", owner_run_id)) or owner_run_id
                raise AccountInUseError(
                    f"A conta '{owner_label}' já está em uso em outra execução."
                )

            self._account_locks[lock_key] = app.run_id

        app.set_account_lock_owned(True)
        return lock_key

    def release_account_lock(self, run_id: str | None) -> bool:
        resolved_run_id = _normalize_spaces(run_id)
        if not resolved_run_id:
            return False

        with self._lock:
            removed = False
            stale_keys = [key for key, owner in self._account_locks.items() if owner == resolved_run_id]
            for key in stale_keys:
                self._account_locks.pop(key, None)
                removed = True

            app = self._runs.get(resolved_run_id)

        if app is not None:
            app.set_account_lock_owned(False)

        return removed

    def start_run(
        self,
        run_id: str | None = None,
        *,
        run_mode: str | None = None,
        run_options: Mapping[str, Any] | RunOptions | None = None,
        run_payload: Mapping[str, Any] | None = None,
        resume: bool = False,
        clear_logs: bool = True,
    ) -> dict[str, Any]:
        app = self.get_run(run_id)
        self._acquire_account_lock(app)

        try:
            result = app.start(
                run_mode=run_mode,
                run_options=run_options,
                run_payload=run_payload,
                resume=resume,
                clear_logs=clear_logs,
            )
        except Exception:
            self.release_account_lock(app.run_id)
            raise

        if isinstance(result, Mapping):
            payload = dict(result)
            payload.setdefault("run_id", app.run_id)
            return payload

        return {"ok": True, "run_id": app.run_id, "result": result}

    def continue_run(
        self,
        run_id: str | None = None,
        *,
        run_mode: str | None = None,
        run_options: Mapping[str, Any] | RunOptions | None = None,
        run_payload: Mapping[str, Any] | None = None,
        clear_logs: bool = True,
    ) -> dict[str, Any]:
        return self.start_run(
            run_id,
            run_mode=run_mode,
            run_options=run_options,
            run_payload=run_payload,
            resume=True,
            clear_logs=clear_logs,
        )

    def safe_action(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            result = fn(*args, **kwargs)
            if isinstance(result, Mapping):
                payload = dict(result)
                payload.setdefault("ok", True)
                return payload
            return {"ok": True, "result": result}
        except Exception as error:
            return build_error_payload(error)


# ============================================================
# HELPERS DE COMPATIBILIDADE
# ============================================================


def build_runtime_state(
    context: ScraperContext | Mapping[str, Any] | None = None,
    *,
    initial_data: Mapping[str, Any] | None = None,
    initial_logs: Iterable[Any] | str | None = None,
) -> RuntimeState:
    return RuntimeState(
        context,
        initial_data=initial_data,
        initial_logs=initial_logs,
    )


def build_state_public_payload(source: Any, *, max_logs: int | None = None) -> dict[str, Any]:
    if hasattr(source, "snapshot") and callable(source.snapshot):
        try:
            payload = source.snapshot(max_logs=max_logs)
            if isinstance(payload, Mapping):
                return dict(payload)
        except Exception:
            pass

    if isinstance(source, Mapping):
        data = source.get("data", source)
        logs = source.get("logs", [])
        context = source.get("context")
        return build_state_payload(data=data, logs=logs, context=context, max_logs=max_logs)

    return build_state_payload(data={}, logs=[], context=None, max_logs=max_logs)


# ============================================================
# ALIASES PT-BR
# ============================================================

EstadoRuntime = RuntimeState
EstadoCompartilhado = SharedState
ControlePassivo = PassiveControl
EstadoControle = ControlState
GerenciadorExecucoesScraper = ScraperRunManager

construir_estado_runtime = build_runtime_state
montar_payload_publico_estado = build_state_public_payload


__all__ = [
    "RuntimeState",
    "SharedState",
    "PassiveControl",
    "ControlState",
    "ScraperApp",
    "ScraperRunManager",
    "AccountInUseError",
    "RunNotFoundError",
    "build_runtime_state",
    "build_state_public_payload",
    "normalize_run_mode",
    "ensure_run_mode",
    "get_run_mode_label",
    "normalize_run_payload",
    "EstadoRuntime",
    "EstadoCompartilhado",
    "ControlePassivo",
    "EstadoControle",
    "GerenciadorExecucoesScraper",
    "construir_estado_runtime",
    "montar_payload_publico_estado",
]
