from __future__ import annotations

import os
import unittest
import subprocess
import sys
from unittest.mock import MagicMock, patch

import main
from app import settings
from app.configuration import (
    ENVIRONMENT_VARIABLES, WINDOWS_USER_ENVIRONMENT_KEYS, prerequisite_status,
    parse_update_execution_allowed_product_ids,
)


class NormalConfigurationTests(unittest.TestCase):
    def test_plugintheme_inherits_same_account_ultrapack_credentials(self) -> None:
        env = {
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL": "same@example.test",
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD": "same-password",
        }
        with patch.dict(os.environ, env, clear=True):
            credentials = settings.resolve_account_credentials(
                "coproducaolancamentos", "plugintheme"
            )
        self.assertEqual(credentials["login_email"], env[next(iter(env))])
        self.assertEqual(credentials["login_password"], env[list(env)[1]])
        self.assertEqual(credentials["credential_source"], "ultrapackv2")

    def test_central_inventory_has_unique_scraper_names(self) -> None:
        names = [item.name for item in ENVIRONMENT_VARIABLES]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(name.startswith("SCRAPER_") for name in names))
        self.assertEqual(tuple(names), WINDOWS_USER_ENVIRONMENT_KEYS)

    def test_normal_environment_includes_ultrapack_credentials(self) -> None:
        self.assertIn("SCRAPER_UPDATE_EXECUTION_ENABLED", main.WINDOWS_USER_ENVIRONMENT_KEYS)
        self.assertIn("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", main.WINDOWS_USER_ENVIRONMENT_KEYS)
        self.assertIn(
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL",
            main.WINDOWS_USER_ENVIRONMENT_KEYS,
        )
        self.assertIn(
            "SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD",
            main.WINDOWS_USER_ENVIRONMENT_KEYS,
        )

    def test_windows_user_environment_is_loaded_without_overriding_process(self) -> None:
        registry = {
            key: f"configured-{index}"
            for index, key in enumerate(main.WINDOWS_USER_ENVIRONMENT_KEYS)
        }
        fake_winreg = MagicMock()
        fake_winreg.HKEY_CURRENT_USER = object()
        fake_winreg.OpenKey.return_value.__enter__.return_value = object()
        fake_winreg.QueryValueEx.side_effect = lambda _handle, key: (registry[key], 1)

        with patch.object(main.sys, "platform", "win32"), patch.dict(os.environ, {}, clear=True), patch.dict(
            "sys.modules", {"winreg": fake_winreg}
        ):
            presence = main.load_windows_user_environment()
            self.assertTrue(all(presence.values()))
            self.assertEqual(os.environ["SCRAPER_WP_BASE_URL"], registry["SCRAPER_WP_BASE_URL"])
            self.assertEqual(
                os.environ["SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL"],
                registry["SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_EMAIL"],
            )
            self.assertEqual(
                os.environ["SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD"],
                registry["SCRAPER_ULTRAPACKV2_COPRODUCAOLANCAMENTOS_PASSWORD"],
            )
            self.assertEqual(set(os.environ), set(WINDOWS_USER_ENVIRONMENT_KEYS))

        fake_winreg.QueryValueEx.reset_mock()
        with patch.object(main.sys, "platform", "win32"), patch.dict(
            os.environ, {"SCRAPER_WP_BASE_URL": "process-value"}, clear=True
        ), patch.dict("sys.modules", {"winreg": fake_winreg}):
            main.load_windows_user_environment()
            self.assertEqual(os.environ["SCRAPER_WP_BASE_URL"], "process-value")

    def test_safety_locks_remain_disabled(self) -> None:
        self.assertIs(settings.WORDPRESS_WRITE_ENABLED, False)
        self.assertIs(settings.SSH_STORAGE_WRITE_ENABLED, False)
        self.assertIs(settings.SSH_HELPER_EXECUTION_ENABLED, False)

    def test_presence_diagnostic_never_returns_values(self) -> None:
        secret = "secret-that-must-not-appear"
        with patch.dict(os.environ, {"SCRAPER_WC_CONSUMER_SECRET": secret}, clear=True):
            result = prerequisite_status()
        rendered = str(result)
        self.assertNotIn(secret, rendered)
        self.assertIn("PRESENTE", rendered)
        self.assertIn("AUSENTE", rendered)

    def test_execution_flag_changes_only_in_a_new_process(self) -> None:
        command = [sys.executable, "-c", "import main; from app import settings; print(settings.UPDATE_EXECUTION_ENABLED)"]
        for value, expected in (("false", "False"), ("true", "True")):
            environment = dict(os.environ)
            environment["SCRAPER_UPDATE_EXECUTION_ENABLED"] = value
            result = subprocess.run(command, cwd=str(settings.PROJECT_ROOT), env=environment,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), expected)

    def test_execution_presence_is_distinct_from_enabled(self) -> None:
        with patch.dict(os.environ, {"SCRAPER_UPDATE_EXECUTION_ENABLED": "false"}, clear=True):
            result = prerequisite_status()["update_execution"]
        self.assertTrue(result["configured"])
        self.assertFalse(result["enabled"])
        self.assertEqual(result["status"], "BLOQUEADA")

    def test_execution_allowed_product_ids_parser_is_closed_and_strict(self) -> None:
        self.assertEqual(parse_update_execution_allowed_product_ids(None), frozenset({94567}))
        self.assertEqual(parse_update_execution_allowed_product_ids("94567,90109"),
                         frozenset({94567, 90109}))
        self.assertEqual(parse_update_execution_allowed_product_ids(" 94567, 90109 "),
                         frozenset({94567, 90109}))
        self.assertEqual(parse_update_execution_allowed_product_ids(""), frozenset())
        self.assertEqual(parse_update_execution_allowed_product_ids("*,all,90109x,-1,0"), frozenset())
        self.assertEqual(parse_update_execution_allowed_product_ids("94567,invalid,90109"),
                         frozenset({94567, 90109}))

    def test_whitelist_is_loaded_only_by_a_new_process(self) -> None:
        command = [sys.executable, "-c", "from app import settings; print(','.join(map(str, sorted(settings.UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS))))"]
        cases = ((None, "94567"), ("94567,90109", "90109,94567"), ("", ""), ("*", ""))
        for value, expected in cases:
            environment = dict(os.environ)
            if value is None:
                environment.pop("SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS", None)
            else:
                environment["SCRAPER_UPDATE_EXECUTION_ALLOWED_PRODUCT_IDS"] = value
            result = subprocess.run(command, cwd=str(settings.PROJECT_ROOT), env=environment,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
