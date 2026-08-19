from __future__ import annotations

import unittest

import app.addition_wait_budget_policy as policy


class AdditionWaitBudgetPolicyTests(unittest.TestCase):
    def test_description_timeout_is_capped_at_two_minutes(self) -> None:
        self.assertEqual(policy._bounded_description_timeout(300), 120)
        self.assertEqual(policy._bounded_description_timeout(120), 120)

    def test_image_timeout_is_capped_at_four_minutes(self) -> None:
        self.assertEqual(policy._bounded_image_timeout(480), 240)
        self.assertEqual(policy._bounded_image_timeout(240), 240)

    def test_timeouts_keep_smaller_explicit_values(self) -> None:
        self.assertEqual(policy._bounded_description_timeout(45), 45)
        self.assertEqual(policy._bounded_image_timeout(90), 90)


if __name__ == "__main__":
    unittest.main()
