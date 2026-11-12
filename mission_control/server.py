"""HTTP server for Mission Control.

Standard library only: ``http.server`` with a threading server so the
Flight Director console stays responsive while a report is processed.
"""
import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mission_control import config
from mission_control.anthropic_client import AnthropicClient
from mission_control.fake_model import FakeModelClient
from mission_control.pipeline import file_report
from mission_control.storage import BriefingNotFound, BriefingNotPending, Store
from mission_control.validation import validate_report

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
MAX_BODY_BYTES = 1024 * 1024

REPORT_ID_PATTERN = re.compile(r"^/api/reports/(\d+)$")
APPROVE_PATTERN = re.compile(r"^/api/briefings/(\d+)/approve$")


class MissionControlHandler(BaseHTTPRequestHandler):
    """Routes requests to the pages, static files and the JSON API."""

    server_version = "MissionControl/0.1"

    # ----- helpers -------------------------------------------------------
    def _send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def send_page(self, filename):
        self.send_static(filename)

    def send_static(self, relative_path):
        safe = os.path.normpath(relative_path).lstrip(os.sep)
        full = os.path.join(STATIC_DIR, safe)
        if not full.startswith(STATIC_DIR + os.sep) or not os.path.isfile(full):
            self.send_json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        with open(full, "rb") as handle:
            self._send_bytes(200, handle.read(), content_type)

    def read_json_body(self):
        """Return the parsed JSON body, or None after sending a 400."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self.send_json(400, {"errors": {"body": "Request body must be JSON"}})
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.send_json(400, {"errors": {"body": "Request body must be JSON"}})
            return None

    def log_message(self, fmt, *args):
        if getattr(self.server, "quiet", False):
            return
        BaseHTTPRequestHandler.log_message(self, fmt, *args)

    # ----- routing -------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_page("index.html")
        elif path == "/console":
            self.send_page("console.html")
        elif path == "/api/status":
            self.send_json(200, self.server.status())
        elif path == "/api/reports":
            self.send_json(200, {"reports": self.server.store.list_reports()})
        elif REPORT_ID_PATTERN.match(path):
            report_id = int(REPORT_ID_PATTERN.match(path).group(1))
            detail = self.server.store.report_detail(report_id)
            if detail is None:
                self.send_json(404, {"error": "report %d not found" % report_id})
            else:
                self.send_json(200, detail)
        elif path.startswith("/static/"):
            self.send_static(path[len("/static/"):])
        else:
            self.send_json(404, {"error": "not found"})

    do_HEAD = do_GET

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/reports":
            self.file_report()
        elif APPROVE_PATTERN.match(path):
            self.approve_briefing(int(APPROVE_PATTERN.match(path).group(1)))
        else:
            self.send_json(404, {"error": "not found"})

    # ----- actions -------------------------------------------------------
    def file_report(self):
        payload = self.read_json_body()
        if payload is None:
            return
        clean, errors = validate_report(payload)
        if errors:
            self.send_json(400, {"errors": errors})
            return
        report_id = self.server.file_report(clean)
        self.send_json(201, self.server.store.report_detail(report_id))

    def approve_briefing(self, briefing_id):
        """A person approves a pending briefing. Nothing else can."""
        payload = self.read_json_body()
        if payload is None:
            return
        approver = payload.get("approver") if isinstance(payload, dict) else None
        if not isinstance(approver, str) or not approver.strip():
            self.send_json(400, {"errors": {"approver": "Approver name is required"}})
            return
        if len(approver.strip()) > 100:
            self.send_json(400, {"errors": {"approver": "Approver name must be 100 characters or fewer"}})
            return
        try:
            briefing = self.server.store.approve_briefing(briefing_id, approver.strip())
        except BriefingNotFound:
            self.send_json(404, {"error": "briefing %d not found" % briefing_id})
            return
        except BriefingNotPending as conflict:
            self.send_json(409, {"error": "briefing %d is already %s" % (briefing_id, conflict)})
            return
        self.send_json(200, {"briefing": briefing})


class MissionControlServer(ThreadingHTTPServer):
    """Threading server that carries the shared application objects."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, client, quiet=False):
        ThreadingHTTPServer.__init__(self, address, MissionControlHandler)
        self.store = store
        self.client = client
        self.quiet = quiet

    def status(self):
        return {
            "app": "mission-control",
            "simulated": self.client.name == "fake",
            "fast_model": config.fast_model(),
            "strong_model": config.strong_model(),
            "prices_checked_on": config.PRICES_CHECKED_ON,
        }

    def file_report(self, clean):
        """Save the raw report and run the pipeline; returns the report id."""
        return file_report(self.store, self.client, clean)


def choose_client():
    """The real client when ANTHROPIC_API_KEY is set, otherwise the fake."""
    key = config.api_key()
    if key:
        return AnthropicClient(key)
    return FakeModelClient()


def create_server(host="127.0.0.1", port=8000, store=None, client=None, db_path=None, quiet=False):
    """Build the server without starting it. Port 0 picks a free port.

    Tests always pass an explicit fake client; only run.py lets the
    environment choose.
    """
    if store is None:
        store = Store(db_path or "mission_control.db")
    if client is None:
        client = choose_client()
    return MissionControlServer((host, port), store=store, client=client, quiet=quiet)
