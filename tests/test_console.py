import json
import os
import unittest

from tests.test_api import GOOD
from tests.test_form import read_static
from tests.test_server import ServerTestCase

INJECTION = "<script>alert('fd')</script><img src=x onerror=alert(1)>"


class TestConsolePage(ServerTestCase):
    def test_console_page_is_served(self):
        status, headers, body = self.get("/console")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        html = body.decode("utf-8")
        self.assertIn("Flight Director", html)
        self.assertIn("/static/console.js", html)
        for element in ("queue", "briefing-text", "trace", "checks", "violations", "approve-form", "simulated-banner"):
            self.assertIn('id="%s"' % element, html)

    def test_status_reports_models_and_simulated_flag(self):
        status, payload = self.get_json("/api/status")
        self.assertTrue(payload["simulated"])
        self.assertIn("fast_model", payload)
        self.assertIn("strong_model", payload)
        self.assertIn("prices_checked_on", payload)

    def test_engineer_text_reaches_the_browser_only_as_json(self):
        status, created = self.post_json("/api/reports", dict(GOOD, name=INJECTION, station=INJECTION, note=INJECTION + " at T-80 min."))
        self.assertEqual(status, 201)
        report_id = created["report"]["id"]
        # Pages are static: no report text is ever interpolated into HTML by the server.
        for page in ("/", "/console"):
            status, headers, body = self.get(page)
            self.assertNotIn(b"<script>alert", body)
            self.assertNotIn(b"onerror", body)
        # The API returns the text JSON-encoded, where < and > cannot start a tag in the page.
        status, headers, body = self.get("/api/reports/%d" % report_id)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["report"]["name"], INJECTION)
        status, headers, body = self.get("/api/reports")
        self.assertIn("application/json", headers["Content-Type"])
        self.assertEqual(json.loads(body)["reports"][0]["station"], INJECTION)


class TestConsoleScript(unittest.TestCase):
    def test_console_script_renders_text_only(self):
        script = read_static("console.js")
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("outerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertNotIn("document.write", script)
        self.assertIn("textContent", script)

    def test_console_script_shows_queue_briefing_cost_and_trace(self):
        script = read_static("console.js")
        for feature in ("review_reasons", "brief_by_minutes", "briefing.text", "cost_usd",
                        "input_tokens", "output_tokens", "/api/briefings/", "simulated-banner", "violations"):
            self.assertIn(feature, script)

    def test_every_trace_step_becomes_one_card(self):
        script = read_static("console.js")
        self.assertIn("payload.trace.forEach(function (step)", script)
        self.assertIn('el("div", "card "', script)


if __name__ == "__main__":
    unittest.main()
