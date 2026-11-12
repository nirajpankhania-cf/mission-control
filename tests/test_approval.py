import os
import re
import unittest

from mission_control.fake_model import FakeModelClient
from mission_control.storage import BriefingNotFound, BriefingNotPending
from tests.test_api import GOOD
from tests.test_server import ServerTestCase
from tests.test_sorting import PipelineTestCase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASS = {"approved": True, "feedback": ""}


class TestApprovalEndpoint(ServerTestCase):
    def file_one(self, **changes):
        status, payload = self.post_json("/api/reports", dict(GOOD, **changes))
        self.assertEqual(status, 201)
        return payload

    def test_briefing_is_pending_right_after_the_pipeline(self):
        payload = self.file_one()
        self.assertEqual(payload["briefing"]["status"], "pending")
        self.assertIsNone(payload["briefing"]["approved_by"])

    def test_a_named_person_can_approve_a_pending_briefing(self):
        briefing_id = self.file_one()["briefing"]["id"]
        status, payload = self.post_json("/api/briefings/%d/approve" % briefing_id, {"approver": "FD Chen"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["briefing"]["status"], "approved")
        self.assertEqual(payload["briefing"]["approved_by"], "FD Chen")
        self.assertIsNotNone(payload["briefing"]["approved_at"])
        status, listing = self.get_json("/api/reports")
        self.assertEqual(listing["reports"][0]["briefing_status"], "approved")

    def test_second_approval_is_a_conflict(self):
        briefing_id = self.file_one()["briefing"]["id"]
        self.post_json("/api/briefings/%d/approve" % briefing_id, {"approver": "FD Chen"})
        status, payload = self.post_json("/api/briefings/%d/approve" % briefing_id, {"approver": "FD Okafor"})
        self.assertEqual(status, 409)
        self.assertIn("already approved", payload["error"])
        status, detail = self.get_json("/api/reports/%d" % self.store.get_briefing(briefing_id)["report_id"])
        self.assertEqual(detail["briefing"]["approved_by"], "FD Chen")

    def test_missing_approver_is_rejected(self):
        briefing_id = self.file_one()["briefing"]["id"]
        for body in ({}, {"approver": ""}, {"approver": "   "}, {"approver": 7}):
            status, payload = self.post_json("/api/briefings/%d/approve" % briefing_id, body)
            self.assertEqual(status, 400, body)
            self.assertEqual(payload["errors"]["approver"], "Approver name is required")
        self.assertEqual(self.store.get_briefing(briefing_id)["status"], "pending")

    def test_unknown_briefing_is_404(self):
        status, payload = self.post_json("/api/briefings/999999/approve", {"approver": "FD Chen"})
        self.assertEqual(status, 404)

    def test_approval_needs_a_post(self):
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.get("/api/briefings/1/approve")
        self.assertEqual(raised.exception.code, 404)


class TestPipelineNeverApproves(PipelineTestCase):
    def test_reviewer_pass_leaves_briefing_pending(self):
        fake = FakeModelClient({"review": PASS})
        detail = self.run_report(fake)
        self.assertTrue(detail["briefing"]["rounds"][0]["approved"])
        self.assertEqual(detail["briefing"]["status"], "pending")
        self.assertIsNone(detail["briefing"]["approved_by"])

    def test_pipeline_and_model_code_never_call_approve(self):
        """The only caller of approve_briefing is the approval endpoint."""
        for name in ("pipeline.py", "drafting.py", "checks.py", "sorting.py", "fake_model.py",
                     "anthropic_client.py", "prompts.py"):
            path = os.path.join(ROOT, "mission_control", name)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            self.assertNotIn("approve_briefing", source, name)
            self.assertNotIn("'approved'", source, name)
        with open(os.path.join(ROOT, "mission_control", "storage.py"), encoding="utf-8") as handle:
            storage = handle.read()
        self.assertEqual(len(re.findall(r"status = 'approved'", storage)), 1)
        self.assertIn("INSERT INTO briefings (report_id, status, summary, recommended_action, text, rounds_json, created_at)\"\n                \" VALUES (?, 'pending'", storage)

    def test_store_update_report_cannot_touch_briefing_status(self):
        detail = self.run_report(FakeModelClient())
        with self.assertRaises(ValueError):
            self.store.update_report(detail["report"]["id"], briefing_status="approved")


class TestStoreApproval(PipelineTestCase):
    def test_approve_then_conflict_then_not_found(self):
        detail = self.run_report(FakeModelClient())
        briefing_id = detail["briefing"]["id"]
        approved = self.store.approve_briefing(briefing_id, "FD Chen")
        self.assertEqual(approved["status"], "approved")
        with self.assertRaises(BriefingNotPending):
            self.store.approve_briefing(briefing_id, "FD Chen")
        with self.assertRaises(BriefingNotFound):
            self.store.approve_briefing(briefing_id + 1000, "FD Chen")
        with self.assertRaises(ValueError):
            self.store.approve_briefing(briefing_id, "")


if __name__ == "__main__":
    unittest.main()
