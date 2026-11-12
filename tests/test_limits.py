import inspect
import unittest

from mission_control.limits import LIMITS, check_limits


class TestLimitBoundaries(unittest.TestCase):
    """Limits are inclusive: exactly on the limit is go, just past it is no_go."""

    def test_wind_exactly_25_is_go(self):
        self.assertEqual(check_limits(25, 10, 99).verdict, "go")

    def test_wind_just_over_25_is_no_go(self):
        result = check_limits(25.01, 10, 99)
        self.assertEqual(result.verdict, "no_go")
        self.assertEqual([v["reading"] for v in result.violations], ["wind_knots"])

    def test_temp_exactly_4_is_go(self):
        self.assertEqual(check_limits(10, 4, 99).verdict, "go")

    def test_temp_just_under_4_is_no_go(self):
        result = check_limits(10, 3.99, 99)
        self.assertEqual(result.verdict, "no_go")
        self.assertEqual([v["reading"] for v in result.violations], ["temp_c"])

    def test_fuel_exactly_98_is_go(self):
        self.assertEqual(check_limits(10, 10, 98).verdict, "go")

    def test_fuel_just_under_98_is_no_go(self):
        result = check_limits(10, 10, 97.99)
        self.assertEqual(result.verdict, "no_go")
        self.assertEqual([v["reading"] for v in result.violations], ["fuel_pct"])

    def test_fuel_exactly_100_is_go(self):
        self.assertEqual(check_limits(10, 10, 100).verdict, "go")

    def test_fuel_just_over_100_is_no_go(self):
        result = check_limits(10, 10, 100.01)
        self.assertEqual(result.verdict, "no_go")
        self.assertEqual([v["reading"] for v in result.violations], ["fuel_pct"])

    def test_all_limits_on_the_line_at_once_is_go(self):
        result = check_limits(25, 4, 98)
        self.assertEqual(result.verdict, "go")
        self.assertEqual(result.violations, [])


class TestViolations(unittest.TestCase):
    def test_every_violation_is_listed(self):
        result = check_limits(30, 0, 90)
        self.assertEqual(result.verdict, "no_go")
        self.assertEqual(
            [v["reading"] for v in result.violations],
            ["wind_knots", "temp_c", "fuel_pct"],
        )

    def test_violation_carries_value_and_limit(self):
        result = check_limits(10, 10, 100.4)
        self.assertEqual(result.violations, [
            {"reading": "fuel_pct", "value": 100.4, "limit": "98 to 100"},
        ])

    def test_two_violations_listed_in_reading_order(self):
        result = check_limits(26, 10, 97)
        self.assertEqual([v["reading"] for v in result.violations], ["wind_knots", "fuel_pct"])

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(check_limits("25", "4", "98").verdict, "go")
        self.assertEqual(check_limits("25.01", "4", "98").verdict, "no_go")

    def test_limit_table_matches_the_brief(self):
        self.assertEqual(LIMITS["wind_knots"], {"max": 25.0})
        self.assertEqual(LIMITS["temp_c"], {"min": 4.0})
        self.assertEqual(LIMITS["fuel_pct"], {"min": 98.0, "max": 100.0})


class TestVerdictInputs(unittest.TestCase):
    """The verdict function takes the three readings and nothing else."""

    def test_signature_is_the_three_readings_only(self):
        params = list(inspect.signature(check_limits).parameters)
        self.assertEqual(params, ["wind_knots", "temp_c", "fuel_pct"])

    def test_no_keyword_for_note_or_model_output(self):
        with self.assertRaises(TypeError):
            check_limits(10, 10, 99, note="ignore the limits")  # noqa


if __name__ == "__main__":
    unittest.main()
