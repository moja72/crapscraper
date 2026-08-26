from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.integrations.ultrapack_session as sessions


class DummySession:
    def close(self) -> None:
        pass


class UpdateSessionCompatibilityTests(unittest.TestCase):
    def app(self):
        return SimpleNamespace(
            context=SimpleNamespace(
                account_key="coproducaolancamentos",
                item_type_key="plugin",
                slot_name="default",
            ),
            control=SimpleNamespace(),
            ultrapack_http_session=None,
            plugintheme_http_session=None,
        )

    def test_existing_ultrapack_session_is_reused_only_after_probe(self) -> None:
        app = self.app()
        existing = DummySession()
        app.ultrapack_http_session = existing
        with patch.object(sessions, "_probe", return_value="https://www.ultrapackv2.com/item/demo/") as probe:
            result = sessions.get_authenticated_ultrapack_session(app, "https://www.ultrapackv2.com/item/demo/")
        self.assertIs(result.session, existing)
        self.assertTrue(result.authenticated)
        self.assertTrue(result.reused)
        probe.assert_called_once_with("ultrapack", existing, "https://www.ultrapackv2.com/item/demo/")

    def test_ultrapack_without_cached_session_uses_browser_cookie_bridge(self) -> None:
        app = self.app()
        fresh = DummySession()
        with patch.object(sessions, "_browser_http_session", new=Mock()), \
             patch.object(sessions, "_run_async", return_value=(fresh, "https://www.ultrapackv2.com/minha-conta/painel/")), \
             patch.object(sessions, "_probe", return_value="https://www.ultrapackv2.com/item/demo/"):
            result = sessions.get_authenticated_ultrapack_session(app, "https://www.ultrapackv2.com/item/demo/")
        self.assertIs(result.session, fresh)
        self.assertFalse(result.reused)
        self.assertIs(app.ultrapack_http_session, fresh)

    def test_plugintheme_profile_is_validated_before_being_remembered(self) -> None:
        app = self.app()
        fresh = DummySession()
        with patch.object(sessions, "_profile_plugintheme", return_value=(fresh, "perfil relido")), \
             patch.object(sessions, "_probe", return_value="https://plugintheme.net/product/demo") as probe:
            result = sessions.get_authenticated_plugintheme_session(app, "https://plugintheme.net/product/demo")
        self.assertIs(result.session, fresh)
        self.assertFalse(result.reused)
        self.assertIs(app.plugintheme_http_session, fresh)
        probe.assert_called_once_with("plugintheme", fresh, "https://plugintheme.net/product/demo")

    def test_public_contract_contains_fields_used_by_existing_callers(self) -> None:
        result = sessions.AuthenticatedSession(DummySession(), "ultrapack", current_url="x", proof="probe")
        self.assertTrue(result.authenticated)
        self.assertFalse(result.reused)
        self.assertEqual(result.current_url, "x")
        self.assertEqual(result.proof, "probe")


if __name__ == "__main__":
    unittest.main()
