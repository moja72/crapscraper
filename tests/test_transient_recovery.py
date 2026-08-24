from __future__ import annotations

import unittest

from app.operations.transient_recovery import recover_payload


class TransientRecoveryTests(unittest.TestCase):
    def test_recovery_clears_error_and_stale_plan_but_preserves_staging(self):
        payload = {
            "jobs": [{
                "job_id": "update_affiliatewp",
                "woo_product_id": 89674,
                "name": "AffiliateWP WordPress Plugin",
                "state": "downloading",
                "execution_error": "erro antigo",
                "local_staging_path": "data/staging/updates/affiliatewp.zip",
                "new_sha256": "a" * 64,
                "queue_position": 4,
                "diagnostics": [],
                "execution_history": [],
            }],
            "previews": {
                "update_affiliatewp": {"ready": False, "old": True},
                "other": {"ready": True},
            },
            "plans": {
                "update_affiliatewp": {"ready": False, "old": True},
                "other": {"ready": True},
            },
        }

        repaired, changes = recover_payload(payload)
        job = repaired["jobs"][0]

        self.assertEqual(job["state"], "approved")
        self.assertEqual(job["execution_error"], "")
        self.assertEqual(job["queue_position"], 0)
        self.assertEqual(job["local_staging_path"], "data/staging/updates/affiliatewp.zip")
        self.assertEqual(job["new_sha256"], "a" * 64)
        self.assertNotIn("update_affiliatewp", repaired["previews"])
        self.assertNotIn("update_affiliatewp", repaired["plans"])
        self.assertIn("other", repaired["previews"])
        self.assertIn("other", repaired["plans"])
        self.assertEqual(len(changes), 1)
        self.assertEqual(job["execution_history"][-1]["result"], "preparation_interrupted")

    def test_non_transient_job_is_untouched(self):
        payload = {
            "jobs": [{
                "job_id": "ready",
                "state": "plan_ready",
                "execution_error": "",
            }],
            "previews": {"ready": {"ready": True}},
            "plans": {"ready": {"ready": True}},
        }
        repaired, changes = recover_payload(payload)
        self.assertEqual(changes, [])
        self.assertEqual(repaired, payload)


if __name__ == "__main__":
    unittest.main()
