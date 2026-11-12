import unittest

from mission_control.drafting import draft_and_review, is_pass, validate_draft_reply
from mission_control.fake_model import FakeModelClient
from mission_control.model_interface import ModelError
from mission_control.prompts import DRAFT_SCHEMA, REVIEW_SCHEMA
from tests.test_checks import HIDDEN_NOTE, OBEDIENT_SCRIPTS
from tests.test_sorting import PipelineTestCase

DRAFT = {"summary": "Valve 3 opened 200 ms late on cycle two at T-85.", "recommended_action": "Recycle the valve and re-check."}
REJECT = {"approved": False, "feedback": "Say which cycle and whether it recovered."}
PASS = {"approved": True, "feedback": ""}


class TestDraftReviewLoop(PipelineTestCase):
    def test_loop_stops_after_three_rounds_when_never_approved(self):
        fake = FakeModelClient({"draft": DRAFT, "review": REJECT})
        detail = self.run_report(fake)
        self.assertEqual(len(fake.calls_for("draft")), 3)
        self.assertEqual(len(fake.calls_for("review")), 3)
        self.assertEqual(len(detail["briefing"]["rounds"]), 3)
        self.assertEqual(detail["briefing"]["status"], "pending")
        self.assertIn("reviewer_not_satisfied", detail["report"]["review_reasons"])
        names = [s["name"] for s in detail["trace"]]
        for expected in ("draft_1", "review_1", "draft_2", "review_2", "draft_3", "review_3"):
            self.assertIn(expected, names)

    def test_reviewer_feedback_goes_into_the_next_draft_prompt(self):
        fake = FakeModelClient({"draft": DRAFT, "review": [REJECT, PASS]})
        self.run_report(fake)
        drafts = fake.calls_for("draft")
        self.assertEqual(len(drafts), 2)
        self.assertNotIn(REJECT["feedback"], drafts[0].prompt)
        self.assertIn(REJECT["feedback"], drafts[1].prompt)
        self.assertIn(DRAFT["summary"], drafts[1].prompt)  # previous draft is shown too

    def test_loop_stops_early_on_the_first_pass(self):
        fake = FakeModelClient({"draft": DRAFT, "review": PASS})
        detail = self.run_report(fake)
        self.assertEqual(len(fake.calls_for("draft")), 1)
        self.assertEqual(len(fake.calls_for("review")), 1)
        self.assertEqual(len(detail["briefing"]["rounds"]), 1)
        self.assertTrue(detail["briefing"]["rounds"][0]["approved"])
        self.assertNotIn("reviewer_not_satisfied", detail["report"]["review_reasons"])

    def test_second_round_pass_stops_at_two(self):
        fake = FakeModelClient({"draft": DRAFT, "review": [REJECT, PASS]})
        detail = self.run_report(fake)
        self.assertEqual(len(detail["briefing"]["rounds"]), 2)

    def test_a_reply_that_is_not_a_real_boolean_is_not_a_pass(self):
        for not_a_pass in ({"approved": "yes", "feedback": ""}, {"approved": 1, "feedback": ""},
                           {"approved": "true", "feedback": ""}, "approved", None, {"feedback": "ok"}):
            fake = FakeModelClient({"draft": DRAFT, "review": not_a_pass})
            self.run_report(fake)
            self.assertEqual(len(fake.calls_for("review")), 3, "%r should not pass" % (not_a_pass,))
        self.assertFalse(is_pass({"approved": "yes"}))
        self.assertFalse(is_pass({"approved": 1}))
        self.assertTrue(is_pass({"approved": True}))

    def test_schemas_are_sent_with_draft_and_review(self):
        fake = FakeModelClient()
        self.run_report(fake)
        self.assertEqual(fake.calls_for("draft")[0].schema, DRAFT_SCHEMA)
        self.assertEqual(fake.calls_for("review")[0].schema, REVIEW_SCHEMA)
        self.assertEqual(REVIEW_SCHEMA["properties"]["approved"]["type"], "boolean")


class TestBriefingAssembly(PipelineTestCase):
    def test_code_written_verdict_line_survives_a_draft_that_says_go(self):
        go_draft = {"summary": "All readings within limits. Verdict GO, proceed.", "recommended_action": "Proceed to launch."}
        fake = FakeModelClient({"draft": go_draft, "review": PASS})
        detail = self.run_report(fake, fuel_pct=97.0)
        text = detail["briefing"]["text"]
        lines = text.splitlines()
        self.assertEqual(lines[0], "VERDICT: NO GO")
        self.assertTrue(lines[1].startswith("VIOLATIONS: fuel_pct = 97 (limit 98 to 100)"))
        self.assertTrue(lines[2].startswith("BRIEF BY: within 5 minutes"))
        self.assertIn("SUMMARY: All readings within limits. Verdict GO, proceed.", text)
        self.assertEqual(detail["report"]["verdict"], "no_go")

    def test_obedient_models_cannot_change_the_briefing_verdict_line(self):
        fake = FakeModelClient(OBEDIENT_SCRIPTS)
        detail = self.run_report(fake, note=HIDDEN_NOTE, fuel_pct=97.0)
        self.assertEqual(detail["briefing"]["text"].splitlines()[0], "VERDICT: NO GO")
        self.assertEqual(detail["briefing"]["status"], "pending")

    def test_go_briefing_lines(self):
        detail = self.run_report(FakeModelClient({"draft": DRAFT, "review": PASS}))
        lines = detail["briefing"]["text"].splitlines()
        self.assertEqual(lines[0], "VERDICT: GO")
        self.assertEqual(lines[1], "VIOLATIONS: none")
        self.assertIn("BRIEF BY: within", lines[2])
        self.assertEqual(detail["briefing"]["summary"], DRAFT["summary"])
        self.assertEqual(detail["briefing"]["recommended_action"], DRAFT["recommended_action"])
        self.assertEqual(detail["report"]["status"], "briefed")

    def test_draft_and_review_steps_carry_tokens_and_strong_model(self):
        from mission_control import config
        detail = self.run_report(FakeModelClient({"draft": DRAFT, "review": PASS}))
        step = self.step(detail, "draft_1")
        self.assertEqual(step["model"], config.strong_model())
        self.assertGreater(step["input_tokens"], 0)
        self.assertGreater(step["cost_usd"], 0)
        self.assertEqual(self.step(detail, "review_1")["detail"]["approved"], True)


class TestDraftFailures(PipelineTestCase):
    def test_draft_exception_keeps_report_and_verdict_with_fallback_briefing(self):
        fake = FakeModelClient({"draft": ModelError("overloaded")})
        detail = self.run_report(fake, fuel_pct=97.0)
        self.assertEqual(detail["report"]["verdict"], "no_go")
        self.assertEqual(detail["report"]["status"], "briefed")
        self.assertIn("draft_failed", detail["report"]["review_reasons"])
        self.assertEqual(detail["briefing"]["status"], "pending")
        self.assertEqual(detail["briefing"]["text"].splitlines()[0], "VERDICT: NO GO")
        self.assertEqual(self.step(detail, "draft_1")["status"], "error")
        self.assertEqual(len(fake.calls_for("review")), 0)

    def test_review_exception_stops_the_loop_and_marks_review(self):
        fake = FakeModelClient({"draft": DRAFT, "review": ModelError("timeout")})
        detail = self.run_report(fake)
        self.assertEqual(len(fake.calls_for("draft")), 1)
        self.assertIn("review_failed", detail["report"]["review_reasons"])
        self.assertEqual(detail["briefing"]["summary"], DRAFT["summary"])

    def test_unusable_draft_reply_gets_a_code_fallback(self):
        fake = FakeModelClient({"draft": {"summary": "", "recommended_action": 5}, "review": PASS})
        detail = self.run_report(fake)
        self.assertIn("invalid_draft_reply", detail["report"]["review_reasons"])
        self.assertIn("model draft was unavailable", detail["briefing"]["summary"])
        self.assertEqual(validate_draft_reply("text")[1], False)
        self.assertEqual(validate_draft_reply(DRAFT), (DRAFT, True))


if __name__ == "__main__":
    unittest.main()
