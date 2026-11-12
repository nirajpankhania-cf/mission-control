"""Draft a briefing body with a model and have a second call review it.

Up to three rounds. The loop stops on the first real pass (``approved`` is
the boolean True) or after the third round. The reviewer's feedback is
inserted into the next draft prompt. The verdict, violations and brief-by
lines are not drafted here; code writes them around the model's summary.
"""
from mission_control.prompts import build_draft_request, build_review_request

MAX_ROUNDS = 3

FALLBACK_SUMMARY = "The model draft was unavailable; read the engineer's note in the report."
FALLBACK_ACTION = "Review the raw report and the readings before deciding."


class DraftOutcome(object):
    def __init__(self):
        self.rounds = []
        self.steps = []          # (name, reply_or_None, detail, status, error)
        self.draft = None
        self.approved = False
        self.review_reasons = []


def validate_draft_reply(data):
    """Return ``(draft, valid)``; an unusable reply gives a code fallback."""
    if isinstance(data, dict) and isinstance(data.get("summary"), str) and data["summary"].strip() \
            and isinstance(data.get("recommended_action"), str) and data["recommended_action"].strip():
        return {"summary": data["summary"].strip(), "recommended_action": data["recommended_action"].strip()}, True
    return {"summary": FALLBACK_SUMMARY, "recommended_action": FALLBACK_ACTION}, False


def is_pass(data):
    """Only the JSON boolean true is a pass; "yes", 1 or "true" are not."""
    return isinstance(data, dict) and data.get("approved") is True


def review_feedback(data):
    if isinstance(data, dict) and isinstance(data.get("feedback"), str):
        return data["feedback"].strip()
    return ""


def draft_and_review(client, model, context, max_rounds=MAX_ROUNDS):
    outcome = DraftOutcome()
    feedback = None
    previous = None
    for round_number in range(1, max_rounds + 1):
        # Draft
        try:
            reply = client.complete(build_draft_request(model, context, round_number, previous, feedback))
        except Exception as error:
            outcome.steps.append(("draft_%d" % round_number, None, {}, "error", error))
            outcome.review_reasons.append("draft_failed")
            if outcome.draft is None:
                outcome.draft, _ = validate_draft_reply(None)
            outcome.rounds.append({"round": round_number, "draft": outcome.draft, "draft_status": "error",
                                   "approved": False, "feedback": "", "review_status": "skipped"})
            break
        draft, valid = validate_draft_reply(reply.data)
        if not valid:
            outcome.review_reasons.append("invalid_draft_reply")
        outcome.draft = draft
        outcome.steps.append(("draft_%d" % round_number, reply,
                              {"round": round_number, "summary": draft["summary"],
                               "recommended_action": draft["recommended_action"], "feedback_in": feedback or ""},
                              "ok" if valid else "fallback", None))
        entry = {"round": round_number, "draft": draft, "draft_status": "ok" if valid else "fallback"}

        # Review
        try:
            review = client.complete(build_review_request(model, context, draft, round_number))
        except Exception as error:
            outcome.steps.append(("review_%d" % round_number, None, {}, "error", error))
            outcome.review_reasons.append("review_failed")
            entry.update({"approved": False, "feedback": "", "review_status": "error"})
            outcome.rounds.append(entry)
            break
        approved = is_pass(review.data)
        feedback = review_feedback(review.data)
        outcome.steps.append(("review_%d" % round_number, review,
                              {"round": round_number, "approved": approved, "feedback": feedback,
                               "raw": review.data}, "ok", None))
        entry.update({"approved": approved, "feedback": feedback, "review_status": "ok"})
        outcome.rounds.append(entry)
        if approved:
            outcome.approved = True
            break
        previous = draft
    if outcome.draft is not None and not outcome.approved and "draft_failed" not in outcome.review_reasons \
            and "review_failed" not in outcome.review_reasons:
        outcome.review_reasons.append("reviewer_not_satisfied")
    return outcome


def assemble_briefing(report, context, draft):
    """Write the briefing text. Verdict, violations and brief-by lines come from code."""
    lines = []
    lines.append("VERDICT: %s" % ("GO" if context["verdict"] == "go" else "NO GO"))
    violations = context.get("violations") or []
    if violations:
        lines.append("VIOLATIONS: " + "; ".join(
            "%s = %g (limit %s)" % (v["reading"], float(v["value"]), v["limit"]) for v in violations))
    else:
        lines.append("VIOLATIONS: none")
    minutes = context.get("brief_by_minutes")
    severity_note = "severity %s" % context.get("effective_severity")
    if violations and context.get("severity") != "high":
        severity_note += " (limit violation counts as high)"
    lines.append("BRIEF BY: within %s minutes (%s)" % (minutes, severity_note))
    lines.append("SUBSYSTEM: %s" % context.get("subsystem"))
    reasons = context.get("review_reasons") or []
    lines.append("NEEDS REVIEW: %s" % (", ".join(reasons) if reasons else "no"))
    lines.append("")
    lines.append("SUMMARY: %s" % draft["summary"])
    lines.append("RECOMMENDED ACTION: %s" % draft["recommended_action"])
    lines.append("")
    lines.append("Filed by %s (%s) at %s." % (report["name"], report["station"], report["created_at"]))
    return "\n".join(lines)
