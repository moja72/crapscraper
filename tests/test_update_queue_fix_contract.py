from __future__ import annotations

from pathlib import Path


def test_update_queue_fix_keeps_lifecycle_contract():
    script = (Path(__file__).resolve().parents[1] / "app" / "static" / "update_queue_fix.js").read_text(encoding="utf-8")
    assert 'job?.state === "plan_ready"' in script
    assert '"/atualizacoes/fila/adicionar"' in script
    assert "PREPARATION_STATES" in script
    assert "COMPLETED_STATES" in script
