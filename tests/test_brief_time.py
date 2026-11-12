import unittest

from mission_control.brief_time import SEVERITY_MINUTES, brief_by_minutes, effective_severity


class TestBriefByTime(unittest.TestCase):
    def test_high_is_5_minutes(self):
        self.assertEqual(brief_by_minutes("high", False), 5)

    def test_medium_is_15_minutes(self):
        self.assertEqual(brief_by_minutes("medium", False), 15)

    def test_low_is_30_minutes(self):
        self.assertEqual(brief_by_minutes("low", False), 30)

    def test_violation_forces_5_minutes_for_low_severity(self):
        self.assertEqual(brief_by_minutes("low", True), 5)

    def test_violation_forces_5_minutes_for_medium_severity(self):
        self.assertEqual(brief_by_minutes("medium", True), 5)

    def test_violation_with_high_severity_is_still_5(self):
        self.assertEqual(brief_by_minutes("high", True), 5)

    def test_unknown_severity_briefs_soonest(self):
        self.assertEqual(brief_by_minutes("urgent", False), 5)
        self.assertEqual(brief_by_minutes(None, False), 5)

    def test_table_matches_the_brief(self):
        self.assertEqual(SEVERITY_MINUTES, {"high": 5, "medium": 15, "low": 30})


class TestEffectiveSeverity(unittest.TestCase):
    def test_violation_counts_as_high(self):
        self.assertEqual(effective_severity("low", True), "high")
        self.assertEqual(effective_severity("medium", True), "high")

    def test_no_violation_keeps_sorted_severity(self):
        self.assertEqual(effective_severity("low", False), "low")
        self.assertEqual(effective_severity("medium", False), "medium")
        self.assertEqual(effective_severity("high", False), "high")


if __name__ == "__main__":
    unittest.main()
