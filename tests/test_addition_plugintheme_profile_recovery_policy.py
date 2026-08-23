from __future__ import annotations

import unittest

import app.addition_plugintheme_profile_recovery_policy as policy


class AdditionPluginThemeProfileRecoveryPolicyTests(unittest.TestCase):
    def test_finds_nested_access_token(self):
        token = "x" * 80
        payload = {"session": {"current": {"access_token": token}}}
        self.assertEqual(policy._find_access_token(payload), token)

    def test_finds_access_token_inside_json_string(self):
        token = "y" * 80
        payload = '{"session":{"access_token":"' + token + '"}}'
        self.assertEqual(policy._find_access_token(payload), token)

    def test_short_values_are_not_mistaken_for_tokens(self):
        self.assertEqual(policy._find_access_token({"token": "abc"}), "")


if __name__ == "__main__":
    unittest.main()
