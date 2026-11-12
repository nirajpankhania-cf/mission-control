"""Launch limits checked in plain code.

The verdict is decided here from the three readings and nothing else: no
model reply, no note text and no other report field is an input. Limits
are inclusive, so a value exactly on a limit is go.
"""
from collections import namedtuple

# Inclusive limits. A reading is go when it satisfies every bound listed.
LIMITS = {
    "wind_knots": {"max": 25.0},
    "temp_c": {"min": 4.0},
    "fuel_pct": {"min": 98.0, "max": 100.0},
}

GO = "go"
NO_GO = "no_go"

LimitResult = namedtuple("LimitResult", ["verdict", "violations"])


def _describe(reading, bounds):
    if "min" in bounds and "max" in bounds:
        return "%s to %s" % (_fmt(bounds["min"]), _fmt(bounds["max"]))
    if "max" in bounds:
        return "%s or less" % _fmt(bounds["max"])
    return "%s or more" % _fmt(bounds["min"])


def _fmt(number):
    return ("%g" % number)


def check_limits(wind_knots, temp_c, fuel_pct):
    """Return a LimitResult for the three readings.

    ``violations`` is a list of ``{"reading", "value", "limit"}`` dicts, one per
    reading outside its limit, in the order wind, temperature, fuel. The
    verdict is ``no_go`` when the list is not empty, otherwise ``go``.
    """
    readings = [
        ("wind_knots", float(wind_knots)),
        ("temp_c", float(temp_c)),
        ("fuel_pct", float(fuel_pct)),
    ]
    violations = []
    for name, value in readings:
        bounds = LIMITS[name]
        outside = False
        if "max" in bounds and value > bounds["max"]:
            outside = True
        if "min" in bounds and value < bounds["min"]:
            outside = True
        if value != value:  # NaN cannot be a reading inside any limit
            outside = True
        if outside:
            violations.append({
                "reading": name,
                "value": value,
                "limit": _describe(name, bounds),
            })
    verdict = NO_GO if violations else GO
    return LimitResult(verdict, violations)
