"""Deterministic fake model for tests and for running without an API key.

Replies are scripted per task. A script can be:

* a dict: returned for every call of that task;
* a list: items are consumed in order, the last one repeats; an item that is
  an Exception is raised, any other value is returned as the reply data;
* a callable: called with the ModelRequest, its return value is the reply
  data (or it may raise);
* an Exception instance: raised on every call.

Without a script the fake builds a plausible reply from the request's
context, so the app looks real with no key. Token counts come from text
length so cost cards are never zero. Every call is recorded in ``calls``.
"""
import json
import re
import threading

from mission_control.model_interface import ModelClient, ModelError, ModelReply

SUBSYSTEM_KEYWORDS = [
    ("propulsion", ("valve", "fuel", "pump", "engine", "thrust", "tank", "pressure", "oxidizer")),
    ("telemetry", ("telemetry", "downlink", "uplink", "link", "signal", "packet", "data drop")),
    ("avionics", ("avionics", "computer", "sensor", "gyro", "imu", "flight software", "reboot")),
    ("electrical", ("battery", "power", "voltage", "bus", "current")),
    ("structures", ("structure", "strut", "crack", "fairing", "umbilical", "vibration")),
    ("weather", ("wind", "gust", "cloud", "lightning", "storm", "temperature", "ice")),
    ("ground_systems", ("ground", "pad", "crane", "tower", "water deluge", "range")),
]

HIDDEN_PATTERNS = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions|rules|guidance)",
    r"disregard (the |your |all )?(instructions|limits|rules|readings)",
    r"system prompt",
    r"\b(set|mark|make|report|change|override)\b.{0,40}\b(verdict|go)\b",
    r"you are now",
    r"new instructions?:",
    r"\bassistant\b.{0,20}\bmust\b",
    r"approve (this|the) briefing",
    r"\bseverity\b.{0,20}\b(low|medium)\b.{0,40}\b(regardless|anyway|no matter)\b",
]

SEVERITY_HIGH = ("leak", "fire", "smoke", "loss", "lost", "failed", "failure", "dropped", "rupture", "explod", "abort", "stuck")
SEVERITY_MEDIUM = ("late", "odd", "intermittent", "drift", "slow", "unexpected", "noisy", "degraded", "warning")
PANIC_WORDS = ("panic", "help!", "oh no", "emergency", "we're going to", "disaster", "catastroph", "!!!")


def count_tokens(text):
    """Rough token estimate used only by the fake."""
    return max(1, len(text or "") // 4)


def detect_hidden_instructions(note):
    lowered = (note or "").lower()
    for pattern in HIDDEN_PATTERNS:
        if re.search(pattern, lowered):
            return True
    return False


def default_reply(request):
    """A plausible deterministic reply for each task, from the context."""
    context = request.context
    note = context.get("note", "")
    lowered = note.lower()
    task = request.task
    if task == "sort":
        subsystem = "unknown"
        for name, words in SUBSYSTEM_KEYWORDS:
            if any(word in lowered for word in words):
                subsystem = name
                break
        severity = "low"
        if any(word in lowered for word in SEVERITY_MEDIUM):
            severity = "medium"
        if any(word in lowered for word in SEVERITY_HIGH):
            severity = "high"
        return {"subsystem": subsystem, "severity": severity,
                "reason": "Keyword match on the note (simulated)."}
    if task == "check_hidden":
        flagged = detect_hidden_instructions(note)
        return {"flagged": flagged,
                "reason": "The note contains text addressed to the system." if flagged
                else "No instructions to the system found."}
    if task == "check_missing":
        has_number = bool(re.search(r"\d", note))
        flagged = len(note) < 40 or not has_number
        return {"flagged": flagged,
                "reason": "The note gives no timing or measured value." if flagged
                else "Timing and values are present."}
    if task == "check_panic":
        letters = [c for c in note if c.isalpha()]
        upper_ratio = (sum(1 for c in letters if c.isupper()) / float(len(letters))) if letters else 0.0
        flagged = any(word in lowered for word in PANIC_WORDS) or (len(letters) > 20 and upper_ratio > 0.6)
        return {"flagged": flagged,
                "reason": "The tone is alarmed rather than factual." if flagged else "The tone is factual."}
    if task == "draft":
        feedback = context.get("feedback") or ""
        station = context.get("station", "a station")
        subsystem = context.get("subsystem", "unknown")
        summary = "%s reports a %s anomaly: %s" % (station, subsystem.replace("_", " "), _first_sentence(note))
        if feedback:
            summary = summary + " Reviewer note addressed: %s" % feedback
        action = "Hold for Flight Director review and have %s confirm the readings." % station
        if context.get("verdict") == "no_go":
            action = "Hold the count until the out-of-limit reading is resolved and re-checked."
        return {"summary": summary, "recommended_action": action}
    if task == "review":
        round_number = int(context.get("round", 1))
        if round_number == 1:
            return {"approved": False,
                    "feedback": "Name the station in the summary and keep it to one sentence."}
        return {"approved": True, "feedback": ""}
    raise ModelError("fake has no default reply for task %r" % task)


def _first_sentence(note):
    note = (note or "").strip()
    match = re.match(r"(.+?[.!?])(\s|$)", note)
    sentence = match.group(1) if match else note
    if len(sentence) > 160:
        sentence = sentence[:157].rstrip() + "..."
    return sentence or "(no detail given)"


class FakeModelClient(ModelClient):
    name = "fake"

    def __init__(self, scripts=None):
        self.scripts = dict(scripts or {})
        self.calls = []
        self._lock = threading.Lock()
        self._positions = {}

    def script(self, task, script):
        """Set or replace the script for one task."""
        self.scripts[task] = script

    def calls_for(self, task):
        return [call for call in self.calls if call.task == task]

    def _next_from_script(self, request):
        script = self.scripts[request.task]
        if isinstance(script, BaseException):
            raise script
        if isinstance(script, list):
            with self._lock:
                index = self._positions.get(request.task, 0)
                item = script[min(index, len(script) - 1)]
                self._positions[request.task] = index + 1
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                return item(request)
            return item
        if callable(script):
            return script(request)
        return script

    def complete(self, request):
        with self._lock:
            self.calls.append(request)
        if request.task in self.scripts:
            data = self._next_from_script(request)
        else:
            data = default_reply(request)
        try:
            text = json.dumps(data)
        except (TypeError, ValueError):
            text = str(data)
        return ModelReply(
            data=data,
            text=text,
            input_tokens=count_tokens(request.system) + count_tokens(request.prompt),
            output_tokens=count_tokens(text),
            model=request.model,
        )
