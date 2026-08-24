from __future__ import annotations

import unittest
from pathlib import Path

import app.list_manager_standardization_policy as policy


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "app" / "static" / "list_manager_standardization.js"


class ListManagerStandardizationTests(unittest.TestCase):
    def test_queue_filename_is_stable(self) -> None:
        self.assertEqual(policy._queue_filename("default"), "default.csv")
        self.assertEqual(policy._queue_filename("Adições Agosto"), "adi-es-agosto.csv")

    def test_render_injects_final_manager_script(self) -> None:
        original = policy._BASE_RENDER
        try:
            policy._BASE_RENDER = lambda: "<html><body>painel</body></html>"
            html = policy._patched_render_panel_page()
        finally:
            policy._BASE_RENDER = original
        self.assertIn("data-list-manager-standardization", html)
        self.assertIn("__csListManagerStandardization", html)

    def test_script_contains_canonical_addition_list_manager(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        required = [
            "Gerenciar Listas de Adições",
            "cs-lm-modal",
            "cs-lm-x",
            "Visualizar",
            "Baixar CSV",
            "Limpar itens",
            "Pesquisar na lista",
            "Itens por página",
            "Mover selecionados da fila",
            "open_addition_lists_modal",
            "/adicoes/fila/listas/detalhe",
            "/adicoes/fila/listas/csv",
        ]
        for value in required:
            self.assertIn(value, script)

    def test_policy_exposes_detail_csv_and_clear_routes(self) -> None:
        source = Path(policy.__file__).read_text(encoding="utf-8")
        self.assertIn('/adicoes/fila/listas/detalhe', source)
        self.assertIn('/adicoes/fila/listas/csv', source)
        self.assertIn('/adicoes/fila/listas/limpar', source)
        self.assertIn("queue_state IN ('completed','canceled')", source)


if __name__ == "__main__":
    unittest.main()
