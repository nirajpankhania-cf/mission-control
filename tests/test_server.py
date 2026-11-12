import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from mission_control.fake_model import FakeModelClient
from mission_control.server import create_server
from mission_control.storage import Store


class ServerTestCase(unittest.TestCase):
    """Starts the server on a free port and a temporary database."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="mission-control-")
        cls.store = Store(os.path.join(cls.tmpdir, "test.db"))
        cls.client = FakeModelClient()
        cls.server = create_server(host="127.0.0.1", port=0, store=cls.store, client=cls.client, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def get(self, path):
        with urllib.request.urlopen(self.url(path), timeout=5) as response:
            return response.status, response.headers, response.read()

    def get_json(self, path):
        status, headers, body = self.get(path)
        return status, json.loads(body)

    def post_json(self, path, payload, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url(path), data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())


class TestSkeleton(ServerTestCase):
    def test_root_serves_html_page(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Mission Control", body)

    def test_status_endpoint_reports_simulated_mode(self):
        status, payload = self.get_json("/api/status")
        self.assertEqual(status, 200)
        self.assertIn("simulated", payload)

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.get("/no-such-page")
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
