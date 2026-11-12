import unittest
import urllib.error

from tests.test_server import ServerTestCase

GOOD = {
    "name": "Ada Lovelace",
    "station": "Propulsion",
    "wind_knots": 12,
    "temp_c": 18.5,
    "fuel_pct": 99.1,
    "note": "Valve 3 opened 200 ms late on the second cycle.",
}


class TestFileReport(ServerTestCase):
    def test_file_report_returns_201_with_verdict(self):
        status, payload = self.post_json("/api/reports", GOOD)
        self.assertEqual(status, 201)
        report = payload["report"]
        self.assertEqual(report["name"], "Ada Lovelace")
        self.assertEqual(report["verdict"], "go")
        self.assertEqual(report["violations"], [])
        self.assertIn("trace", payload)

    def test_out_of_limit_report_is_accepted_as_no_go(self):
        status, payload = self.post_json("/api/reports", dict(GOOD, fuel_pct=100.4))
        self.assertEqual(status, 201)
        self.assertEqual(payload["report"]["verdict"], "no_go")
        self.assertEqual(payload["report"]["violations"][0]["reading"], "fuel_pct")

    def test_bad_input_is_rejected_with_a_message_per_field(self):
        status, payload = self.post_json("/api/reports", dict(GOOD, wind_knots="breezy", name=""))
        self.assertEqual(status, 400)
        self.assertEqual(payload["errors"], {
            "wind_knots": "Wind must be a number",
            "name": "Name is required",
        })

    def test_non_json_body_is_rejected(self):
        status, payload = self.post_json("/api/reports", None, raw=b"name=Ada&station=x")
        self.assertEqual(status, 400)
        self.assertIn("body", payload["errors"])

    def test_list_and_get_reports(self):
        status, created = self.post_json("/api/reports", dict(GOOD, station="Range Safety"))
        report_id = created["report"]["id"]
        status, listing = self.get_json("/api/reports")
        self.assertEqual(status, 200)
        self.assertEqual(listing["reports"][0]["id"], report_id)
        self.assertEqual(listing["reports"][0]["station"], "Range Safety")
        status, detail = self.get_json("/api/reports/%d" % report_id)
        self.assertEqual(status, 200)
        self.assertEqual(detail["report"]["note"], GOOD["note"])
        self.assertIn("cost_usd", detail)

    def test_unknown_report_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.get_json("/api/reports/999999")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
