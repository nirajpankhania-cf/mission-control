"""Brief-by time derived from severity in plain code.

High severity is briefed in 5 minutes, medium in 15 and low in 30. Any
launch-limit violation counts as high regardless of the sorted severity.
"""

SEVERITY_MINUTES = {"high": 5, "medium": 15, "low": 30}
SEVERITIES = ("low", "medium", "high")


def effective_severity(severity, has_violation):
    """Severity used for briefing: high when any limit is violated."""
    if has_violation:
        return "high"
    if severity not in SEVERITY_MINUTES:
        return "high"
    return severity


def brief_by_minutes(severity, has_violation):
    """Minutes until the Flight Director must be briefed."""
    return SEVERITY_MINUTES[effective_severity(severity, has_violation)]
