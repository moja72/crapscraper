from __future__ import annotations

GROUP_BY_STATE = {
    "prepared": ("ready",),
    "running": ("running",),
    "success": ("success",),
    "error": ("error",),
}

CARD_LABELS = (
    ("total", "Total"),
    ("prepared", "Preparados"),
    ("running", "Em andamento"),
    ("success", "Concluídos"),
    ("error", "Erros"),
)


def group_for_state(state: str) -> str:
    for group, states in GROUP_BY_STATE.items():
        if state in states:
            return group
    raise ValueError(f"Estado público inválido: {state}")
