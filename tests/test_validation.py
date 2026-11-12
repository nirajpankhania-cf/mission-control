import unittest

from mission_control.validation import all_messages, validate_report

GOOD = {
    "name": "Ada Lovelace",
    "station": "Propulsion",
    "wind_knots": 12,
    "temp_c": 18.5,
    "fuel_pct": 99.1,
    "note": "Valve 3 opened 200 ms late on the second cycle.",
}


def with_changes(**changes):
    payload = dict(GOOD)
    payload.update(changes)
    return payload


class TestValidReports(unittest.TestCase):
    def test_good_report_is_clean(self):
        clean, errors = validate_report(GOOD)
        self.assertEqual(errors, {})
        self.assertEqual(clean["name"], "Ada Lovelace")
        self.assertEqual(clean["wind_knots"], 12.0)
        self.assertEqual(clean["fuel_pct"], 99.1)

    def test_out_of_limit_readings_are_valid_input(self):
        clean, errors = validate_report(with_changes(fuel_pct=100.4, wind_knots=40, temp_c=-10))
        self.assertEqual(errors, {})
        self.assertEqual(clean["fuel_pct"], 100.4)

    def test_numeric_strings_are_accepted(self):
        clean, errors = validate_report(with_changes(wind_knots="25", temp_c=" 4 ", fuel_pct="98.0"))
        self.assertEqual(errors, {})
        self.assertEqual((clean["wind_knots"], clean["temp_c"], clean["fuel_pct"]), (25.0, 4.0, 98.0))

    def test_text_is_stripped(self):
        clean, errors = validate_report(with_changes(name="  Ada  ", note="  late valve  "))
        self.assertEqual(errors, {})
        self.assertEqual(clean["name"], "Ada")
        self.assertEqual(clean["note"], "late valve")

    def test_zero_readings_are_valid(self):
        clean, errors = validate_report(with_changes(wind_knots=0, temp_c=0, fuel_pct=0))
        self.assertEqual(errors, {})


class TestRejectedReports(unittest.TestCase):
    def test_missing_fields_each_get_a_message(self):
        clean, errors = validate_report({})
        self.assertEqual(clean, {})
        self.assertEqual(set(errors), {"name", "station", "wind_knots", "temp_c", "fuel_pct", "note"})
        self.assertEqual(errors["name"], "Name is required")
        self.assertEqual(errors["wind_knots"], "Wind is required")

    def test_text_reading_is_rejected(self):
        clean, errors = validate_report(with_changes(wind_knots="breezy"))
        self.assertEqual(errors, {"wind_knots": "Wind must be a number"})

    def test_blank_reading_is_rejected(self):
        clean, errors = validate_report(with_changes(temp_c=""))
        self.assertEqual(errors, {"temp_c": "Temperature is required"})

    def test_nan_and_infinity_are_rejected(self):
        clean, errors = validate_report(with_changes(fuel_pct="nan"))
        self.assertEqual(errors, {"fuel_pct": "Fuel must be a number"})
        clean, errors = validate_report(with_changes(fuel_pct=float("inf")))
        self.assertEqual(errors, {"fuel_pct": "Fuel must be a number"})

    def test_boolean_is_not_a_reading(self):
        clean, errors = validate_report(with_changes(wind_knots=True))
        self.assertEqual(errors, {"wind_knots": "Wind must be a number"})

    def test_absurd_readings_are_rejected(self):
        clean, errors = validate_report(with_changes(wind_knots=900))
        self.assertEqual(errors, {"wind_knots": "Wind must be between 0 and 500 knots"})
        clean, errors = validate_report(with_changes(temp_c=-300))
        self.assertEqual(errors, {"temp_c": "Temperature must be between -150 and 150 C"})
        clean, errors = validate_report(with_changes(fuel_pct=250))
        self.assertEqual(errors, {"fuel_pct": "Fuel must be between 0 and 150 percent"})

    def test_blank_text_is_rejected(self):
        clean, errors = validate_report(with_changes(name="   ", note=""))
        self.assertEqual(errors, {"name": "Name is required", "note": "Note is required"})

    def test_too_long_text_is_rejected(self):
        clean, errors = validate_report(with_changes(station="x" * 101, note="y" * 4001))
        self.assertEqual(errors, {
            "station": "Station must be 100 characters or fewer",
            "note": "Note must be 4000 characters or fewer",
        })

    def test_non_object_body_is_rejected(self):
        clean, errors = validate_report(["not", "a", "dict"])
        self.assertEqual(errors, {"body": "Report must be a JSON object"})

    def test_all_messages_lists_every_message(self):
        messages = all_messages()
        self.assertIn("Wind must be between 0 and 500 knots", messages)
        self.assertIn("Note must be 4000 characters or fewer", messages)
        self.assertEqual(len(messages), len(set(messages)))


if __name__ == "__main__":
    unittest.main()
