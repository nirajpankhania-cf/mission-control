"""Validation of a filed report.

Only input that cannot be a reading at all is rejected: missing values,
text where a number belongs, NaN or infinity, and physically absurd numbers.
Out-of-limit readings such as fuel at 100.4 percent are valid input; the
launch limits decide the verdict, not validation.
"""
import math

FIELDS = ("name", "station", "wind_knots", "temp_c", "fuel_pct", "note")

TEXT_LIMITS = {
    "name": (1, 100, "Name"),
    "station": (1, 100, "Station"),
    "note": (1, 4000, "Note"),
}

# Bounds for what can physically be a reading, not the launch limits.
READING_BOUNDS = {
    "wind_knots": (0.0, 500.0, "Wind", "knots"),
    "temp_c": (-150.0, 150.0, "Temperature", "C"),
    "fuel_pct": (0.0, 150.0, "Fuel", "percent"),
}


def _fmt(number):
    return "%g" % number


def message_required(label):
    return "%s is required" % label


def message_too_long(label, limit):
    return "%s must be %d characters or fewer" % (label, limit)


def message_not_number(label):
    return "%s must be a number" % label


def message_out_of_range(label, low, high, unit):
    return "%s must be between %s and %s %s" % (label, _fmt(low), _fmt(high), unit)


def _clean_text(field, value, errors):
    low, high, label = TEXT_LIMITS[field]
    if value is None or isinstance(value, bool) or not isinstance(value, str):
        if value is None or isinstance(value, bool) or isinstance(value, (list, dict)):
            errors[field] = message_required(label)
            return None
        value = str(value)
    value = value.strip()
    if len(value) < low:
        errors[field] = message_required(label)
        return None
    if len(value) > high:
        errors[field] = message_too_long(label, high)
        return None
    return value


def _clean_reading(field, value, errors):
    low, high, label, unit = READING_BOUNDS[field]
    if value is None or (isinstance(value, str) and not value.strip()):
        errors[field] = message_required(label)
        return None
    if isinstance(value, bool):
        errors[field] = message_not_number(label)
        return None
    try:
        if isinstance(value, str):
            number = float(value.strip())
        elif isinstance(value, (int, float)):
            number = float(value)
        else:
            raise ValueError("not a number")
    except (TypeError, ValueError):
        errors[field] = message_not_number(label)
        return None
    if math.isnan(number) or math.isinf(number):
        errors[field] = message_not_number(label)
        return None
    if number < low or number > high:
        errors[field] = message_out_of_range(label, low, high, unit)
        return None
    return number


def validate_report(payload):
    """Return ``(clean, errors)``.

    ``clean`` holds the six fields with text stripped and readings as floats;
    ``errors`` maps a field name to one plain message. When ``errors`` is not
    empty the report must be rejected.
    """
    errors = {}
    clean = {}
    if not isinstance(payload, dict):
        return {}, {"body": "Report must be a JSON object"}
    for field in ("name", "station", "note"):
        value = _clean_text(field, payload.get(field), errors)
        if value is not None:
            clean[field] = value
    for field in ("wind_knots", "temp_c", "fuel_pct"):
        value = _clean_reading(field, payload.get(field), errors)
        if value is not None:
            clean[field] = value
    if errors:
        return {}, errors
    return clean, {}


def all_messages():
    """Every message the server can return, so the form can mirror them."""
    messages = []
    for low, high, label in TEXT_LIMITS.values():
        messages.append(message_required(label))
        messages.append(message_too_long(label, high))
    for low, high, label, unit in READING_BOUNDS.values():
        messages.append(message_required(label))
        messages.append(message_not_number(label))
        messages.append(message_out_of_range(label, low, high, unit))
    return messages
