"""A full report runs through the HTTP app with no API key and no network.

``socket.connect`` is patched to refuse anything that is not loopback, so a
model call that tried to reach the internet would fail the test.
"""
import os
import socket
import unittest

from mission_control.fake_model import FakeModelClient
from tests.test_api import GOOD
from tests.test_checks import HIDDEN_NOTE
from tests.test_server import ServerTestCase

LOOPBACK = ("127.0.0.1", "::1", "localhost")


class NonLocalConnectionAttempted(AssertionError):
    pass


def _is_loopback(address):
    if not isinstance(address, tuple) or not address:
        return False
    host = address[0]
    if host in LOOPBACK:
        return True
    return host.startswith("127.")


class OfflineGuard(object):
    """Blocks non-loopback socket connections while active."""

    def __init__(self):
        self.attempts = []

    def __enter__(self):
        guard = self
        self.original_connect = socket.socket.connect
        self.original_connect_ex = socket.socket.connect_ex
        self.original_create_connection = socket.create_connection

        def guarded_connect(sock, address, *args, **kwargs):
            if not _is_loopback(address):
                guard.attempts.append(address)
                raise NonLocalConnectionAttempted("non-local connection to %r" % (address,))
            return guard.original_connect(sock, address, *args, **kwargs)

        def guarded_connect_ex(sock, address, *args, **kwargs):
            if not _is_loopback(address):
                guard.attempts.append(address)
                raise NonLocalConnectionAttempted("non-local connection to %r" % (address,))
            return guard.original_connect_ex(sock, address, *args, **kwargs)

        def guarded_create_connection(address, *args, **kwargs):
            if not _is_loopback(address):
                guard.attempts.append(address)
                raise NonLocalConnectionAttempted("non-local connection to %r" % (address,))
            return guard.original_create_connection(address, *args, **kwargs)

        socket.socket.connect = guarded_connect
        socket.socket.connect_ex = guarded_connect_ex
        socket.create_connection = guarded_create_connection
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self.original_connect
        socket.socket.connect_ex = self.original_connect_ex
        socket.create_connection = self.original_create_connection
        return False


class TestOffline(ServerTestCase):
    def setUp(self):
        self.saved_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        self.guard = OfflineGuard()
        self.guard.__enter__()

    def tearDown(self):
        self.guard.__exit__(None, None, None)
        if self.saved_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = self.saved_key

    def test_guard_blocks_non_local_connections(self):
        with self.assertRaises(NonLocalConnectionAttempted):
            socket.create_connection(("api.anthropic.com", 443), timeout=1)
        self.assertEqual(self.guard.attempts, [("api.anthropic.com", 443)])

    def test_full_report_runs_with_no_key_and_no_network(self):
        self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
        self.assertIsInstance(self.server.client, FakeModelClient)
        status, payload = self.get_json("/api/status")
        self.assertTrue(payload["simulated"])

        status, created = self.post_json("/api/reports", dict(GOOD, note=HIDDEN_NOTE, fuel_pct=97.0))
        self.assertEqual(status, 201)
        report = created["report"]
        self.assertEqual(report["verdict"], "no_go")
        self.assertEqual(report["status"], "briefed")
        self.assertTrue(report["needs_review"])
        self.assertIn("hidden_instructions", report["review_reasons"])
        self.assertEqual(created["briefing"]["status"], "pending")
        self.assertEqual(created["briefing"]["text"].splitlines()[0], "VERDICT: NO GO")
        names = [s["name"] for s in created["trace"]]
        for expected in ("limits", "sort", "brief_by", "check_hidden", "check_missing", "check_panic", "draft_1", "review_1", "assemble_briefing"):
            self.assertIn(expected, names)
        self.assertGreater(created["cost_usd"], 0)

        status, approved = self.post_json("/api/briefings/%d/approve" % created["briefing"]["id"], {"approver": "FD Chen"})
        self.assertEqual(status, 200)
        self.assertEqual(approved["briefing"]["status"], "approved")
        self.assertEqual(self.guard.attempts, [])


if __name__ == "__main__":
    unittest.main()
