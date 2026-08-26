from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateRecoverabilityContractTests(unittest.TestCase):
    def test_new_python_policies_parse(self) -> None:
        for relative in (
            "app/update_recoverability_policy.py",
            "app/update_metadata_preflight_policy.py",
            "app/update_recovery_finalizer_policy.py",
            "app/server_manager_binding_policy.py",
            "app/accordion_cleanup_policy.py",
            "app/process_modal_stability_policy.py",
            "app/startup_runtime_gate_policy.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            ast.parse(source, filename=relative)

    def test_retry_discards_old_preview_and_plan(self) -> None:
        source = (ROOT / "app/update_recoverability_policy.py").read_text(encoding="utf-8")
        self.assertIn("runtime._PREVIEWS.pop(key, None)", source)
        self.assertIn("runtime._PLANS.pop(key, None)", source)
        self.assertIn("JobState.APPROVED", source)
        self.assertIn("/operacoes/simples/retry-update", source)

    def test_no_downgrade_rule_is_explicit(self) -> None:
        source = (ROOT / "app/update_recoverability_policy.py").read_text(encoding="utf-8")
        self.assertIn("Não atualizado para evitar downgrade", source)
        self.assertIn("source_version", source)
        self.assertIn("site_version", source)
        self.assertIn("if order < 0:", source)

    def test_missing_production_zip_has_recovery_plan(self) -> None:
        source = (ROOT / "app/update_recoverability_policy.py").read_text(encoding="utf-8")
        for token in (
            '"filesystem_strategy": "recreate_missing"',
            '"remote_zip_missing"',
            '"original_missing": True',
            "rollback_to_missing",
            "install_prepared",
        ):
            self.assertIn(token, source)

    def test_metadata_repair_has_preflight_and_final_safety_net(self) -> None:
        preflight = (ROOT / "app/update_metadata_preflight_policy.py").read_text(encoding="utf-8")
        finalizer = (ROOT / "app/update_recovery_finalizer_policy.py").read_text(encoding="utf-8")
        process = (ROOT / "app/process_modal_stability_policy.py").read_text(encoding="utf-8")
        self.assertIn('"controlled_metadata_repair"', preflight)
        self.assertIn('SSHHelperRequest("inspect", file_name)', preflight)
        self.assertIn("_restore_preserved_zip", finalizer)
        self.assertIn("writer.backup_path", finalizer)
        self.assertIn("writer.target_path", finalizer)
        self.assertLess(
            process.index("install_update_recoverability_policy()"),
            process.index("install_update_metadata_preflight_policy()"),
        )
        self.assertLess(
            process.index("install_update_metadata_preflight_policy()"),
            process.index("install_update_recovery_finalizer_policy()"),
        )
        self.assertLess(
            process.index("install_update_recovery_finalizer_policy()"),
            process.index("install_server_manager_binding_policy()"),
        )

    def test_retry_is_blocked_until_runtime_restore_finishes(self) -> None:
        source = (ROOT / "app/startup_runtime_gate_policy.py").read_text(encoding="utf-8")
        self.assertIn('"/operacoes/simples/retry-update"', source)
        self.assertIn("_BLOCKED_POST_EXACT", source)
        self.assertIn("not is_runtime_ready()", source)

    def test_retry_ui_uses_new_route_and_stable_technical_log_toggle(self) -> None:
        source = (ROOT / "app/static/update_retry_recovery_v2.js").read_text(encoding="utf-8")
        self.assertIn("/operacoes/simples/retry-update", source)
        self.assertIn("Não atualizado:", source)
        self.assertIn('window.addEventListener("click"', source)
        self.assertIn("event.stopImmediatePropagation()", source)
        self.assertIn("TECHNICAL_STATE_KEY", source)

    def test_global_update_mutation_observer_is_replaced(self) -> None:
        source = (ROOT / "app/accordion_cleanup_policy.py").read_text(encoding="utf-8")
        self.assertIn("_GLOBAL_UPDATE_OBSERVER", source)
        self.assertIn("_EVENT_DRIVEN_UPDATE_REFRESH", source)
        self.assertIn("script.replace(_GLOBAL_UPDATE_OBSERVER, _EVENT_DRIVEN_UPDATE_REFRESH)", source)

    def test_history_log_limit_is_expanded(self) -> None:
        source = (ROOT / "app/panel_layout_standardization_policy.py").read_text(encoding="utf-8")
        self.assertIn('script.replace("logs.slice(-10)", "logs.slice(-100)")', source)
        recoverability = (ROOT / "app/update_recoverability_policy.py").read_text(encoding="utf-8")
        self.assertIn("return result[-250:]", recoverability)


if __name__ == "__main__":
    unittest.main()
