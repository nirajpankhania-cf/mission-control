"""The report pipeline.

Order: save the raw report, limits in code, sort with a model, brief-by
time in code. Every step appends a trace row. The verdict is set by
``check_limits`` from the three readings before the first model call and
no later step reads a model reply for it. Nothing here approves anything.
"""
import time
import traceback

from mission_control import config
from mission_control.brief_time import brief_by_minutes, effective_severity
from mission_control.limits import check_limits
from mission_control.pricing import step_cost
from mission_control.sorting import FALLBACK_SEVERITY, FALLBACK_SUBSYSTEM, sort_report


class Trace(object):
    """Records trace steps for one report with timing and cost."""

    def __init__(self, store, report_id):
        self.store = store
        self.report_id = report_id

    def code_step(self, name, detail, started):
        self.store.save_trace_step(self.report_id, {
            "name": name, "kind": "code", "model": None, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "status": "ok", "detail": detail, "duration_ms": _elapsed_ms(started),
        })

    def model_step(self, name, model, reply, detail, started, status="ok"):
        input_tokens = reply.input_tokens if reply else 0
        output_tokens = reply.output_tokens if reply else 0
        used_model = reply.model if reply and reply.model else model
        self.store.save_trace_step(self.report_id, {
            "name": name, "kind": "model", "model": used_model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": step_cost(used_model, input_tokens, output_tokens),
            "status": status, "detail": detail, "duration_ms": _elapsed_ms(started),
        })

    def error_step(self, name, kind, model, error, started):
        self.store.save_trace_step(self.report_id, {
            "name": name, "kind": kind, "model": model, "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "status": "error",
            "detail": {"error": "%s: %s" % (type(error).__name__, error)},
            "duration_ms": _elapsed_ms(started),
        })


def _elapsed_ms(started):
    return int((time.monotonic() - started) * 1000)


def file_report(store, client, clean):
    """Save the raw report, then run the pipeline on it. Returns the report id."""
    report_id = store.save_report(clean)
    run_pipeline(store, client, report_id)
    return report_id


def run_pipeline(store, client, report_id):
    report = store.get_report(report_id)
    trace = Trace(store, report_id)
    review_reasons = []

    # 1. Launch limits, in code, from the three readings and nothing else.
    started = time.monotonic()
    limits = check_limits(report["wind_knots"], report["temp_c"], report["fuel_pct"])
    store.update_report(report_id, verdict=limits.verdict, violations=limits.violations)
    trace.code_step("limits", {"verdict": limits.verdict, "violations": limits.violations}, started)

    try:
        # 2. Sort with the fast model; the reply is validated in code.
        started = time.monotonic()
        try:
            sorted_result = sort_report(client, config.fast_model(), report)
            subsystem, severity = sorted_result.subsystem, sorted_result.severity
            review_reasons.extend(sorted_result.review_reasons)
            trace.model_step("sort", config.fast_model(), sorted_result.reply, {
                "subsystem": subsystem, "severity": severity, "reason": sorted_result.reason,
                "raw": sorted_result.reply.data, "review_reasons": sorted_result.review_reasons,
            }, started, status="ok" if not sorted_result.review_reasons else "fallback")
        except Exception as error:  # a model failure must not lose the report
            subsystem, severity = FALLBACK_SUBSYSTEM, FALLBACK_SEVERITY
            review_reasons.append("sort_failed")
            trace.error_step("sort", "model", config.fast_model(), error, started)

        # 3. Brief-by time, in code; any violation counts as high.
        started = time.monotonic()
        has_violation = bool(limits.violations)
        final_severity = effective_severity(severity, has_violation)
        minutes = brief_by_minutes(severity, has_violation)
        store.update_report(
            report_id, subsystem=subsystem, severity=severity, effective_severity=final_severity,
            brief_by_minutes=minutes, status="sorted",
        )
        trace.code_step("brief_by", {
            "severity": severity, "effective_severity": final_severity,
            "has_violation": has_violation, "brief_by_minutes": minutes,
        }, started)
    except Exception as error:  # pragma: no cover - defensive: keep the verdict and report
        trace.error_step("pipeline", "code", None, error, time.monotonic())
        store.update_report(report_id, status="error")
        traceback.print_exc()
    finally:
        store.update_report(
            report_id, needs_review=bool(review_reasons), review_reasons=review_reasons,
        )
