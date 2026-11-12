"""Reports are still there after the server process is stopped and started again."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_PY = os.path.join(ROOT, "run.py")

REPORT = {
    "name": "Grace Hopper",
    "station": "Telemetry",
    "wind_knots": 8,
    "temp_c": 21,
    "fuel_pct": 98.6,
    "note": "Downlink dropped for four seconds then recovered.",
}


class ServerProcess(object):
    """Runs ``python3 run.py`` as a real child process on a chosen database."""

    def __init__(self, db_path):
        env = dict(os.environ)
        env.pop("ANTHROPIC_API_KEY", None)
        env["MC_PORT"] = "0"
        env["MC_DB_PATH"] = db_path
        self.process = subprocess.Popen(
            [sys.executable, RUN_PY], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        line = self.process.stdout.readline()
        match = re.search(r"http://[^:]+:(\d+)/", line)
        if not match:
            self.stop()
            raise AssertionError("server did not report its port: %r" % line)
        self.port = int(match.group(1))

    def url(self, path):
        return "http://127.0.0.1:%d%s" % (self.port, path)

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


class TestRestart(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="mission-control-restart-")
        self.db_path = os.path.join(self.tmpdir, "restart.db")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_report_survives_a_full_restart(self):
        first = ServerProcess(self.db_path)
        try:
            request = urllib.request.Request(
                first.url("/api/reports"), data=json.dumps(REPORT).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                self.assertEqual(response.status, 201)
                report_id = json.loads(response.read())["report"]["id"]
        finally:
            first.stop()

        # The first process is gone: its port no longer answers.
        with self.assertRaises(urllib.error.URLError):
            urllib.request.urlopen(first.url("/api/status"), timeout=2)

        second = ServerProcess(self.db_path)
        try:
            with urllib.request.urlopen(second.url("/api/reports/%d" % report_id), timeout=5) as response:
                detail = json.loads(response.read())
            self.assertEqual(detail["report"]["name"], "Grace Hopper")
            self.assertEqual(detail["report"]["note"], REPORT["note"])
            self.assertEqual(detail["report"]["verdict"], "go")
            with urllib.request.urlopen(second.url("/api/reports"), timeout=5) as response:
                listing = json.loads(response.read())
            self.assertEqual([r["id"] for r in listing["reports"]], [report_id])
        finally:
            second.stop()


if __name__ == "__main__":
    unittest.main()
