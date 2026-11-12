"""SQLite storage for reports, trace steps and briefings.

One file holds everything. Each call opens its own connection so the
threading HTTP server can use the store from any thread.
"""
import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    station TEXT NOT NULL,
    wind_knots REAL NOT NULL,
    temp_c REAL NOT NULL,
    fuel_pct REAL NOT NULL,
    note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'filed',
    verdict TEXT,
    violations_json TEXT NOT NULL DEFAULT '[]',
    subsystem TEXT,
    severity TEXT,
    effective_severity TEXT,
    brief_by_minutes INTEGER,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons_json TEXT NOT NULL DEFAULT '[]',
    checks_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS trace_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    seq INTEGER NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id),
    status TEXT NOT NULL DEFAULT 'pending',
    summary TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    text TEXT NOT NULL,
    rounds_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    approved_by TEXT,
    approved_at TEXT
);
"""

REPORT_FIELDS = (
    "status", "verdict", "violations_json", "subsystem", "severity",
    "effective_severity", "brief_by_minutes", "needs_review",
    "review_reasons_json", "checks_json",
)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_report(row):
    report = dict(row)
    report["violations"] = json.loads(report.pop("violations_json") or "[]")
    report["review_reasons"] = json.loads(report.pop("review_reasons_json") or "[]")
    report["checks"] = json.loads(report.pop("checks_json") or "{}")
    report["needs_review"] = bool(report["needs_review"])
    return report


def _row_to_step(row):
    step = dict(row)
    step["detail"] = json.loads(step.pop("detail_json") or "{}")
    return step


def _row_to_briefing(row):
    briefing = dict(row)
    briefing["rounds"] = json.loads(briefing.pop("rounds_json") or "[]")
    return briefing


class Store(object):
    def __init__(self, db_path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ----- reports -------------------------------------------------------
    def save_report(self, clean):
        """Save the raw report as filed and return its id."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO reports (created_at, name, station, wind_knots, temp_c, fuel_pct, note)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now_iso(), clean["name"], clean["station"], clean["wind_knots"],
                 clean["temp_c"], clean["fuel_pct"], clean["note"]),
            )
            return cursor.lastrowid

    def update_report(self, report_id, **fields):
        """Update pipeline fields. Lists and dicts are stored as JSON."""
        columns = []
        values = []
        for key, value in fields.items():
            if key in ("violations", "review_reasons", "checks"):
                key = key + "_json"
                value = json.dumps(value)
            if key == "needs_review":
                value = 1 if value else 0
            if key not in REPORT_FIELDS:
                raise ValueError("unknown report field: %s" % key)
            columns.append("%s = ?" % key)
            values.append(value)
        if not columns:
            return
        values.append(report_id)
        with self._connect() as conn:
            conn.execute("UPDATE reports SET %s WHERE id = ?" % ", ".join(columns), values)

    def get_report(self, report_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        return _row_to_report(row) if row else None

    def list_reports(self):
        """Newest first, each with its briefing status and total cost."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.*, b.status AS briefing_status, b.id AS briefing_id,"
                " (SELECT COALESCE(SUM(cost_usd), 0) FROM trace_steps t WHERE t.report_id = r.id) AS cost_usd"
                " FROM reports r"
                " LEFT JOIN briefings b ON b.report_id = r.id"
                " ORDER BY r.id DESC"
            ).fetchall()
        return [_row_to_report(row) for row in rows]

    # ----- trace ---------------------------------------------------------
    def save_trace_step(self, report_id, step):
        with self._connect() as conn:
            seq = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM trace_steps WHERE report_id = ?", (report_id,)
            ).fetchone()[0]
            cursor = conn.execute(
                "INSERT INTO trace_steps (report_id, seq, name, kind, model, input_tokens, output_tokens,"
                " cost_usd, status, detail_json, duration_ms, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (report_id, seq, step["name"], step["kind"], step.get("model"),
                 int(step.get("input_tokens", 0)), int(step.get("output_tokens", 0)),
                 float(step.get("cost_usd", 0.0)), step["status"],
                 json.dumps(step.get("detail", {})), int(step.get("duration_ms", 0)), now_iso()),
            )
            return cursor.lastrowid

    def list_trace(self, report_id):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM trace_steps WHERE report_id = ? ORDER BY seq", (report_id,)
            ).fetchall()
        return [_row_to_step(row) for row in rows]

    # ----- briefings -----------------------------------------------------
    def save_briefing(self, report_id, summary, recommended_action, text, rounds):
        """Save a briefing. It is always pending; only approve_briefing changes that."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO briefings (report_id, status, summary, recommended_action, text, rounds_json, created_at)"
                " VALUES (?, 'pending', ?, ?, ?, ?, ?)",
                (report_id, summary, recommended_action, text, json.dumps(rounds), now_iso()),
            )
            return cursor.lastrowid

    def get_briefing(self, briefing_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM briefings WHERE id = ?", (briefing_id,)).fetchone()
        return _row_to_briefing(row) if row else None

    def get_briefing_for_report(self, report_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM briefings WHERE report_id = ? ORDER BY id DESC LIMIT 1", (report_id,)
            ).fetchone()
        return _row_to_briefing(row) if row else None

    # ----- detail --------------------------------------------------------
    def report_detail(self, report_id):
        report = self.get_report(report_id)
        if report is None:
            return None
        trace = self.list_trace(report_id)
        return {
            "report": report,
            "briefing": self.get_briefing_for_report(report_id),
            "trace": trace,
            "cost_usd": round(sum(step["cost_usd"] for step in trace), 6),
        }
