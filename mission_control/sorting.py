"""Sorting a report by subsystem and severity with a model, checked in code."""
from collections import namedtuple

from mission_control.prompts import SEVERITIES, SUBSYSTEMS, build_sort_request

SortResult = namedtuple("SortResult", ["subsystem", "severity", "review_reasons", "reply", "reason"])

FALLBACK_SUBSYSTEM = "unknown"
FALLBACK_SEVERITY = "high"  # brief soonest when the reply cannot be trusted


def validate_sort_reply(data):
    """Return ``(subsystem, severity, review_reasons, reason)`` from a raw reply.

    Anything that is not a dict with a known subsystem and severity falls
    back: severity to high and subsystem to unknown, each with a review reason.
    """
    review_reasons = []
    if not isinstance(data, dict):
        return FALLBACK_SUBSYSTEM, FALLBACK_SEVERITY, ["invalid_sort_reply"], ""
    subsystem = data.get("subsystem")
    severity = data.get("severity")
    reason = data.get("reason")
    if not isinstance(subsystem, str) or subsystem not in SUBSYSTEMS:
        subsystem = FALLBACK_SUBSYSTEM
        review_reasons.append("invalid_subsystem")
    if not isinstance(severity, str) or severity not in SEVERITIES:
        severity = FALLBACK_SEVERITY
        review_reasons.append("invalid_severity")
    if not isinstance(reason, str):
        reason = ""
    return subsystem, severity, review_reasons, reason


def sort_report(client, model, report):
    """Call the model once and validate its reply in code. May raise."""
    reply = client.complete(build_sort_request(model, report))
    subsystem, severity, review_reasons, reason = validate_sort_reply(reply.data)
    return SortResult(subsystem, severity, review_reasons, reply, reason)
