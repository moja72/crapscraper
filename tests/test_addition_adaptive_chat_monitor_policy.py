from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

import app.addition_adaptive_chat_monitor_policy as policy


class _FakePage:
    def bring_to_front(self) -> None:
        return None

    def wait_for_timeout(self, _ms: int) -> None:
        return None


class AdditionAdaptiveChatMonitorPolicyTests(unittest.TestCase):
    def test_limits_are_extended_but_polling_remains_fast(self) -> None:
        self.assertEqual(policy._DESCRIPTION_TIMEOUT_SECONDS, 300)
        self.assertEqual(policy._IMAGE_TIMEOUT_SECONDS, 600)
        self.assertEqual(policy._IMAGE_RECOVERY_SECONDS, 300)
        self.assertLessEqual(policy._DESCRIPTION_STATUS_SECONDS, 10)
        self.assertLessEqual(policy._IMAGE_STATUS_SECONDS, 15)
        self.assertLess(policy._LOOP_SLEEP_SECONDS, 1.0)

    def test_duration_label_is_human_readable(self) -> None:
        self.assertEqual(policy._duration_label(45), "45s")
        self.assertEqual(policy._duration_label(300), "5m")
        self.assertEqual(policy._duration_label(615), "10m 15s")

    def test_full_image_bytes_can_be_captured_while_ui_is_busy(self) -> None:
        raw = b"image-bytes" * 3000
        data_url = "data:image/png;base64,AAAA"
        candidate = {"src": "blob:https://chatgpt.com/generated", "width": 1024, "height": 1024}
        with patch.object(policy.binding, "_assistant_image_candidates", return_value=[candidate]), \
             patch.object(policy.simple, "_assistant_busy", return_value=True), \
             patch.object(policy.capture, "_extract_image_data_url", return_value=data_url), \
             patch.object(policy.capture, "_decode_data_url", return_value=raw):
            result = policy._adaptive_image_data_url(_FakePage(), set(), "")
        self.assertEqual(result, data_url)

    def test_reference_image_is_never_accepted(self) -> None:
        raw = b"reference" * 4000
        sha = hashlib.sha256(raw).hexdigest()
        candidate = {"src": "blob:https://chatgpt.com/reference", "width": 1024, "height": 1024}
        with patch.object(policy.binding, "_assistant_image_candidates", return_value=[candidate]), \
             patch.object(policy.simple, "_assistant_busy", return_value=True), \
             patch.object(policy.capture, "_extract_image_data_url", return_value="data:image/png;base64,AAAA"), \
             patch.object(policy.capture, "_decode_data_url", return_value=raw):
            result = policy._adaptive_image_data_url(_FakePage(), set(), sha)
        self.assertEqual(result, "")

    def test_recovery_deadline_extends_without_exceeding_hard_limit(self) -> None:
        with patch.object(policy.time, "time", return_value=1000.0):
            self.assertEqual(policy._extend_image_deadline(1100.0, 1400.0), 1300.0)
            self.assertEqual(policy._extend_image_deadline(1350.0, 1400.0), 1350.0)
            self.assertEqual(policy._extend_image_deadline(1390.0, 1400.0), 1390.0)


if __name__ == "__main__":
    unittest.main()
