"""Three model checks that run at the same time.

One looks for hidden instructions in the note, one for missing details and
one for panic in the tone. Each reply is validated in code; a check that
errors or returns something unusable counts as flagged. The checks never
touch the verdict: they only add review reasons.
"""
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

from mission_control.prompts import build_check_request

CHECK_KINDS = ("hidden", "missing", "panic")

REVIEW_REASONS = {
    "hidden": "hidden_instructions",
    "missing": "missing_details",
    "panic": "panic_tone",
}

CheckResult = namedtuple("CheckResult", ["kind", "flagged", "reason", "status", "reply", "error"])


def validate_check_reply(data):
    """Return ``(flagged, reason, valid)``. Anything unusable is flagged."""
    if not isinstance(data, dict) or not isinstance(data.get("flagged"), bool):
        return True, "unusable reply from the model", False
    reason = data.get("reason")
    if not isinstance(reason, str):
        reason = ""
    return data["flagged"], reason, True


def run_one_check(client, model, kind, report):
    try:
        reply = client.complete(build_check_request(model, kind, report))
    except Exception as error:  # an erroring check counts as flagged
        return CheckResult(kind, True, "check failed: %s" % error, "error", None, error)
    flagged, reason, valid = validate_check_reply(reply.data)
    return CheckResult(kind, flagged, reason, "ok" if valid else "fallback", reply, None)


def run_checks(client, model, report):
    """Run the three checks concurrently and return their results in order."""
    with ThreadPoolExecutor(max_workers=len(CHECK_KINDS)) as pool:
        futures = [pool.submit(run_one_check, client, model, kind, report) for kind in CHECK_KINDS]
        return [future.result() for future in futures]


def review_reasons_for(results):
    reasons = []
    for result in results:
        if result.status == "error":
            reasons.append("check_%s_failed" % result.kind)
        elif result.flagged:
            reasons.append(REVIEW_REASONS[result.kind])
    return reasons
