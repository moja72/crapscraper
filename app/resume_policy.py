from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.app import ScraperApp, normalize_run_payload

_INSTALLED = False
_ORIGINAL_START = ScraperApp.start
_ORIGINAL_LOAD_INITIAL_SUMMARY = ScraperApp.load_initial_summary


def _is_primary_mode(value: str | None) -> bool:
    return str(value or "primary").strip().lower() == "primary"


def _patched_load_initial_summary(self: ScraperApp) -> dict[str, Any]:
    _ORIGINAL_LOAD_INITIAL_SUMMARY(self)
    continue_info = self.get_continue_info()
    can_continue = bool(continue_info.get("can_continue"))

    if can_continue and not self.is_running():
        queue_index = int(continue_info.get("queue_index") or 0)
        queue_total = int(continue_info.get("queue_total") or 0)
        self.state.update(
            status="Interrompido",
            summary=(
                f"Continuação disponível: {queue_index}/{queue_total} itens da fila já processados. "
                "A retomada reutiliza a fila salva e não refaz a descoberta do catálogo."
            ),
            current_phase="Aguardando retomada",
            primary_button_label="⏯ Retomar do ponto salvo",
            can_continue=True,
            resume_queue_index=queue_index,
            resume_queue_total=queue_total,
        )
    else:
        data = self.state.get_data()
        if not can_continue and str(data.get("primary_button_label") or "").startswith("▶️ Retomar"):
            self.state.update(primary_button_label="▶️ Iniciar nova coleta")

    return self.snapshot()


def _patched_start(
    self: ScraperApp,
    *,
    run_mode: str | None = None,
    run_options: Mapping[str, Any] | Any | None = None,
    run_payload: Mapping[str, Any] | None = None,
    resume: bool = False,
    clear_logs: bool = True,
) -> dict[str, Any]:
    payload = normalize_run_payload(run_payload)

    # O botão principal historicamente chama /start mesmo quando a UI o rotula
    # como "Retomar". Quando existe uma fila persistida utilizável, convertemos
    # somente esse start primário em continuação real. Outros modos continuam
    # começando normalmente.
    if (
        not resume
        and not bool(payload.get("resume"))
        and _is_primary_mode(run_mode)
        and self.can_continue()
    ):
        continue_info = self.get_continue_info()
        payload["resume"] = True
        return _ORIGINAL_START(
            self,
            run_mode=str(continue_info.get("run_mode") or "full_sync"),
            run_options=run_options,
            run_payload=payload,
            resume=True,
            clear_logs=clear_logs,
        )

    return _ORIGINAL_START(
        self,
        run_mode=run_mode,
        run_options=run_options,
        run_payload=payload,
        resume=resume,
        clear_logs=clear_logs,
    )


def install_resume_policy() -> None:
    """Instala a política uma única vez em todas as instâncias ScraperApp."""
    global _INSTALLED
    if _INSTALLED:
        return
    ScraperApp.load_initial_summary = _patched_load_initial_summary
    ScraperApp.start = _patched_start
    _INSTALLED = True
