from pathlib import Path


def test_process_history_and_credit_labels_exist():
    script = Path("app/static/process_history_credits.js").read_text(encoding="utf-8")
    assert "UltraPackV2:" in script
    assert "PluginTheme:" in script
    assert "Processos concluídos" in script
    assert "Início:" in script
    assert "Fim:" in script
    assert "crapscraper.process.history.v1" in script
    assert "/processos/creditos" in script
    assert "/loja/produtos/campos-ausentes" in script
    assert "/adicoes/automatico/status" in script
    assert "/loja/wordpress-manual/status" in script
    assert '"/comparacao/", "comparison"' in script
    assert '"/atualizacoes/", "update"' in script
    assert '"/adicoes/", "addition"' in script
    assert '"/loja/", "store"' in script


def test_recent_transient_cards_are_hidden_in_favor_of_history():
    script = Path("app/static/process_history_credits.js").read_text(encoding="utf-8")
    assert ".cs-process-modal-body>.cs-process-card.is-recent{display:none!important}" in script
    assert "cs_process_history_section" in script
