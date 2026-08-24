from __future__ import annotations

import unittest

import app.addition_plugintheme_entitlement_recovery_policy as policy


class PluginThemeEntitlementRecoveryPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_find = policy._BASE_FIND_ACCESS_TOKEN
        self.old_access = policy._BASE_ACCESS_ALLOWED
        policy._BASE_FIND_ACCESS_TOKEN = lambda value: ""
        policy._BASE_ACCESS_ALLOWED = lambda payload: False

    def tearDown(self) -> None:
        policy._BASE_FIND_ACCESS_TOKEN = self.old_find
        policy._BASE_ACCESS_ALLOWED = self.old_access

    def test_accepts_plain_jwt_from_storage(self) -> None:
        token = "eyJhbGciOiJIUzI1NiJ9." + ("a" * 48) + "." + ("b" * 48)
        self.assertEqual(policy._find_access_token_robust(token), token)
        self.assertEqual(policy._find_access_token_robust("Bearer " + token), token)

    def test_accepts_explicit_bundle_purchase_entitlement(self) -> None:
        self.assertTrue(policy._access_allowed_robust({"data": {"hasPurchased": True}}))
        self.assertTrue(policy._access_allowed_robust({"bundle": {"entitled": "true"}}))
        self.assertTrue(policy._access_allowed_robust({"access": True}))

    def test_does_not_accept_unrelated_truthy_payload(self) -> None:
        self.assertFalse(policy._access_allowed_robust({"success": True}))
        self.assertFalse(policy._access_allowed_robust({"data": {"purchased": False}}))
        self.assertFalse(policy._access_allowed_robust({"access": "denied"}))


if __name__ == "__main__":
    unittest.main()
