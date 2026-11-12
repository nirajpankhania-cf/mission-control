import os
import re
import unittest

from mission_control.validation import FIELDS, all_messages
from tests.test_api import GOOD
from tests.test_server import ServerTestCase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_static(name):
    with open(os.path.join(ROOT, "static", name), encoding="utf-8") as handle:
        return handle.read()


class TestReportForm(ServerTestCase):
    def test_form_page_has_an_input_for_every_field(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")
        for field in FIELDS:
            self.assertIsNotNone(
                re.search(r'name="%s"' % field, html), "form is missing input %s" % field
            )
        self.assertIn('id="report-form"', html)
        self.assertIn("/static/app.js", html)

    def test_static_assets_are_served(self):
        status, headers, body = self.get("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        status, headers, body = self.get("/static/style.css")
        self.assertIn("text/css", headers["Content-Type"])

    def test_bad_post_returns_the_message_the_form_shows(self):
        status, payload = self.post_json("/api/reports", dict(GOOD, fuel_pct="full"))
        self.assertEqual(status, 400)
        self.assertEqual(payload["errors"], {"fuel_pct": "Fuel must be a number"})


class TestClientMessagesMirrorServer(unittest.TestCase):
    def test_form_script_builds_every_server_message(self):
        """The JS builds messages from the same labels, limits and templates."""
        script = read_static("app.js")
        for label, limit in (("Name", 100), ("Station", 100), ("Note", 4000)):
            self.assertIn('label: "%s", max: %d' % (label, limit), script)
        self.assertIn('label: "Wind", low: 0, high: 500, unit: "knots"', script)
        self.assertIn('label: "Temperature", low: -150, high: 150, unit: "C"', script)
        self.assertIn('label: "Fuel", low: 0, high: 150, unit: "percent"', script)
        self.assertIn('label + " is required"', script)
        self.assertIn('label + " must be " + limit + " characters or fewer"', script)
        self.assertIn('label + " must be a number"', script)
        self.assertIn('label + " must be between " + low + " and " + high + " " + unit', script)
        self.assertEqual(len(all_messages()), 15)

    def test_form_script_never_uses_inner_html(self):
        self.assertNotIn("innerHTML", read_static("app.js"))

    def test_form_page_posts_every_field_by_name(self):
        html = read_static("index.html")
        for field in FIELDS:
            self.assertIn('name="%s"' % field, html)


if __name__ == "__main__":
    unittest.main()
