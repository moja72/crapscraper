from __future__ import annotations

from pathlib import Path


def test_store_prices_ui_contains_accordion_and_plan_section() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "static"
        / "store_pack_variation_table.js"
    ).read_text(encoding="utf-8")

    assert "store_prices_accordion" in script
    assert "Preços da loja" in script
    assert "Preços de Plugins e Temas" in script
    assert "Preços de pacotes" in script
    assert "Preços dos planos" in script
    assert "store_plan_prices" in script
    assert "pricing_group" in script
    assert "Salvar preços" in script
    assert "#tab_btn_loja" in script
