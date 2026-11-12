"""HTTP server for Mission Control.

Standard library only: ``http.server`` with a threading server so the
Flight Director console stays responsive while a report is processed.
"""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

PLACEHOLDER_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Mission Control</title></head>
<body>
<h1>Mission Control</h1>
<p>The engineer report form and Flight Director console are on their way.</p>
</body>
</html>
"""


class MissionControlHandler(BaseHTTPRequestHandler):
    """Routes requests to the page, static files and the JSON API."""

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
        elif path.startswith("/static/"):
            self.send_static(path[len("/static/"):])
        else:
            self.send_json(404, {"error": "not found"})

    do_HEAD = do_GET


class MissionControlServer(ThreadingHTTPServer):
    """Threading server that carries the shared application objects."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, quiet=False):
        ThreadingHTTPServer.__init__(self, address, MissionControlHandler)
        self.quiet = quiet

    def status(self):
        return {"app": "mission-control", "simulated": True}


def create_server(host="127.0.0.1", port=8000, quiet=False):
    """Build the server without starting it. Port 0 picks a free port."""
    return MissionControlServer((host, port), quiet=quiet)
