from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ListManagerVisualPolishTests(unittest.TestCase):
    def test_polish_script_matches_update_modal_width_and_actions(self):
        script = (ROOT / "app" / "static" / "list_manager_visual_polish.js").read_text(encoding="utf-8")
        self.assertIn("width:min(1480px,calc(100vw - 48px))!important", script)
        self.assertIn("padding:62px 18px 18px!important", script)
        self.assertIn("border-radius:50%!important", script)
        self.assertIn("⬇️ Baixar", script)
        self.assertIn("⬇️ Baixar CSV", script)
        self.assertIn('querySelectorAll(".cs-lm-move")', script)
        self.assertIn('classList.add("btn-success")', script)

    def test_policy_is_installed_after_standardization(self):
        policy = (ROOT / "app" / "process_modal_stability_policy.py").read_text(encoding="utf-8")
        standard = policy.index("install_list_manager_standardization_policy()")
        polish = policy.index("install_list_manager_visual_polish_policy()")
        self.assertLess(standard, polish)


if __name__ == "__main__":
    unittest.main()
