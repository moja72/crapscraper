from __future__ import annotations

from pathlib import Path


def test_addition_ui_has_manual_chatgpt_and_draft_publish_stages() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = (root / "app" / "addition_workflow_policy.py").read_text(encoding="utf-8")
    script = (root / "app" / "static" / "addition_workflow.js").read_text(encoding="utf-8")

    assert "Adicionar novos produtos" in policy
    assert "Fila de adição" in policy
    assert "Histórico de adições" in policy
    assert "/adicoes/jobs" in policy
    assert "/adicoes/preparar" in policy
    assert "/adicoes/conteudo" in policy
    assert "/adicoes/rascunho" in policy
    assert "/adicoes/publicar" in policy

    assert "Copiar prompt para ChatGPT" in script
    assert "Abrir conversa" in script
    assert "Adicionar conteúdo" in script
    assert "CRIAR RASCUNHO" in script
    assert "PUBLICAR" in script
    assert "image/jpeg,image/png,image/webp" in script


def test_addition_workflow_is_installed_from_main() -> None:
    root = Path(__file__).resolve().parents[1]
    main = (root / "main.py").read_text(encoding="utf-8")
    assert "install_addition_workflow_policy" in main
    assert "install_addition_workflow_policy()" in main
