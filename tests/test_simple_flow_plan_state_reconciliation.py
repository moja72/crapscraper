from __future__ import annotations

import unittest
from types import SimpleNamespace

import app.operational_simple_flow_policy as simple_flow
from app.operations.models import JobState


class SimpleFlowPlanStateReconciliationTests(unittest.TestCase):
    def test_valid_ready_plan_reconciles_prepared_job_to_plan_ready(self) -> None:
        job = SimpleNamespace(
            job_id="job-safe", woo_product_id=89461, state=JobState.PREPARED,
            set_state=lambda state, message="": setattr(job, "state", state),
        )
        preview = {"ready": True}
        plan = {"ready": True, "job_id": job.job_id, "woo_product_id": job.woo_product_id}

        changed = simple_flow._reconcile_ready_plan_state(job, preview, plan)

        self.assertTrue(changed)
        self.assertEqual(job.state, JobState.PLAN_READY)


if __name__ == "__main__":
    unittest.main()
