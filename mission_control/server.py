"""HTTP server for Mission Control.

Standard library only: ``http.server`` with a threading server so the
Flight Director console stays responsive while a report is processed.
"""
import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mission_control.limits import check_limits
from mission_control.storage import Store
from mission_control.validation import validate_report

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
MAX_BODY_BYTES = 1024 * 1024

PLACEHOLDER_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Mission Control</title></head>
<body>
<h1>Mission Control</h1>
<p>The engineer report form and Flight Director console are on their way.</p>
</body>
</html>
"""

REPORT_ID_PATTERN = re.compile(r"^/api/reports/(\d+)$")


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

    def send_html(self, html):
        self._send_bytes(200, html.encode("utf-8"), "text/html; charset=utf-8")

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
            self.send_html(PLACEHOLDER_PAGE)
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


class MissionControlServer(ThreadingHTTPServer):
    """Threading server that carries the shared application objects."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, quiet=False):
        ThreadingHTTPServer.__init__(self, address, MissionControlHandler)
        self.store = store
        self.quiet = quiet

    def status(self):
        return {"app": "mission-control", "simulated": True}

    def file_report(self, clean):
        """Save the raw report first, then set the verdict from the readings in code."""
        report_id = self.store.save_report(clean)
        result = check_limits(clean["wind_knots"], clean["temp_c"], clean["fuel_pct"])
        self.store.update_report(report_id, verdict=result.verdict, violations=result.violations)
        return report_id


def create_server(host="127.0.0.1", port=8000, store=None, db_path=None, quiet=False):
    """Build the server without starting it. Port 0 picks a free port."""
    if store is None:
        store = Store(db_path or "mission_control.db")
    return MissionControlServer((host, port), store=store, quiet=quiet)
