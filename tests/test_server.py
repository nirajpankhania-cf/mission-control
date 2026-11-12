import threading
import unittest
import urllib.error
import urllib.request
import json

from mission_control.server import create_server


class ServerTestCase(unittest.TestCase):
    """Starts the server on a free port in a background thread."""

    @classmethod
    def setUpClass(cls):
        cls.server = create_server(host="127.0.0.1", port=0, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=5) as response:
            return response.status, response.headers, response.read()


class TestSkeleton(ServerTestCase):
    def test_root_serves_html_page(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Mission Control", body)

    def test_status_endpoint_reports_simulated_mode(self):
        status, headers, body = self.get("/api/status")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("simulated", payload)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.get("/no-such-page")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
