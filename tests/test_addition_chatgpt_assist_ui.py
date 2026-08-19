from __future__ import annotations

from pathlib import Path


def test_addition_chatgpt_assist_ui_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "app" / "static" / "addition_chatgpt_assist.js").read_text(encoding="utf-8")
    policy = (root / "app" / "addition_chatgpt_assist_policy.py").read_text(encoding="utf-8")
    server = (root / "app" / "addition_server_integration_fix.py").read_text(encoding="utf-8")

    assert "Abrir no ChatGPT" in script
    assert "Importar texto copiado" in script
    assert "Importar imagem baixada" in script
    assert "Configurar conversa ChatGPT" in script
    assert "/adicoes/chatgpt/abrir" in script
    assert "/adicoes/chatgpt/importar-texto" in script
    assert "/adicoes/chatgpt/importar-imagem" in script
    assert "data-addition-chatgpt-assist" in policy
    assert "/adicoes/chatgpt/config" in server
    assert "chatgpt_assist.open_for_job" in server
