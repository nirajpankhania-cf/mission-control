import os
import shutil
import tempfile
import unittest

from mission_control.storage import Store

CLEAN = {
    "name": "Ada",
    "station": "Propulsion",
    "wind_knots": 12.0,
    "temp_c": 18.0,
    "fuel_pct": 99.0,
    "note": "Valve 3 opened late.",
}


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="mission-control-")
        self.db_path = os.path.join(self.tmpdir, "store.db")
        self.store = Store(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestReports(StoreTestCase):
    def test_save_and_get_report(self):
        report_id = self.store.save_report(CLEAN)
        report = self.store.get_report(report_id)
        self.assertEqual(report["id"], report_id)
        self.assertEqual(report["name"], "Ada")
        self.assertEqual(report["status"], "filed")
        self.assertIsNone(report["verdict"])
        self.assertEqual(report["violations"], [])
        self.assertFalse(report["needs_review"])

    def test_update_report_stores_json_fields(self):
        report_id = self.store.save_report(CLEAN)
        self.store.update_report(
            report_id, verdict="no_go",
            violations=[{"reading": "fuel_pct", "value": 97.0, "limit": "98 to 100"}],
            needs_review=True, review_reasons=["hidden_instructions"], status="briefed",
        )
        report = self.store.get_report(report_id)
        self.assertEqual(report["verdict"], "no_go")
        self.assertEqual(report["violations"][0]["reading"], "fuel_pct")
        self.assertTrue(report["needs_review"])
        self.assertEqual(report["review_reasons"], ["hidden_instructions"])
        self.assertEqual(report["status"], "briefed")

    def test_update_rejects_unknown_field(self):
        report_id = self.store.save_report(CLEAN)
        with self.assertRaises(ValueError):
            self.store.update_report(report_id, approved=True)

    def test_list_is_newest_first(self):
        first = self.store.save_report(CLEAN)
        second = self.store.save_report(dict(CLEAN, name="Grace"))
        reports = self.store.list_reports()
        self.assertEqual([r["id"] for r in reports], [second, first])
        self.assertIsNone(reports[0]["briefing_status"])
        self.assertEqual(reports[0]["cost_usd"], 0)

    def test_missing_report_is_none(self):
        self.assertIsNone(self.store.get_report(999))
        self.assertIsNone(self.store.report_detail(999))

    def test_reports_survive_a_new_store_on_the_same_file(self):
        report_id = self.store.save_report(CLEAN)
        reopened = Store(self.db_path)
        self.assertEqual(reopened.get_report(report_id)["note"], CLEAN["note"])


class TestTraceAndBriefings(StoreTestCase):
    def test_trace_steps_keep_order_and_detail(self):
        report_id = self.store.save_report(CLEAN)
        self.store.save_trace_step(report_id, {
            "name": "limits", "kind": "code", "status": "ok", "detail": {"verdict": "go"},
        })
        self.store.save_trace_step(report_id, {
            "name": "sort", "kind": "model", "model": "fast", "input_tokens": 10,
            "output_tokens": 5, "cost_usd": 0.0001, "status": "ok", "duration_ms": 12,
        })
        trace = self.store.list_trace(report_id)
        self.assertEqual([s["seq"] for s in trace], [1, 2])
        self.assertEqual(trace[0]["detail"], {"verdict": "go"})
        self.assertEqual(trace[0]["input_tokens"], 0)
        self.assertEqual(trace[1]["model"], "fast")
        self.assertEqual(trace[1]["output_tokens"], 5)

    def test_detail_sums_cost_over_steps(self):
        report_id = self.store.save_report(CLEAN)
        self.store.save_trace_step(report_id, {"name": "a", "kind": "model", "status": "ok", "cost_usd": 0.001})
        self.store.save_trace_step(report_id, {"name": "b", "kind": "model", "status": "ok", "cost_usd": 0.002})
        detail = self.store.report_detail(report_id)
        self.assertAlmostEqual(detail["cost_usd"], 0.003)
        self.assertAlmostEqual(self.store.list_reports()[0]["cost_usd"], 0.003)

    def test_briefing_is_saved_pending(self):
        report_id = self.store.save_report(CLEAN)
        briefing_id = self.store.save_briefing(report_id, "Summary", "Hold", "Full text", [{"round": 1}])
        briefing = self.store.get_briefing(briefing_id)
        self.assertEqual(briefing["status"], "pending")
        self.assertIsNone(briefing["approved_by"])
        self.assertEqual(briefing["rounds"], [{"round": 1}])
        self.assertEqual(self.store.report_detail(report_id)["briefing"]["id"], briefing_id)
        self.assertEqual(self.store.list_reports()[0]["briefing_status"], "pending")


if __name__ == "__main__":
    unittest.main()
