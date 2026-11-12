import re
import unittest

from mission_control import config
from mission_control.pricing import PRICES, highest_rates, price_for, report_cost, step_cost


class TestStepCost(unittest.TestCase):
    def test_haiku_step_is_tokens_times_rate(self):
        # 1000 input tokens at $0.10/MTok + 200 output tokens at $0.50/MTok
        expected = (1000 * 0.10 + 200 * 0.50) / 1e6
        self.assertAlmostEqual(step_cost("claude-haiku-5-5", 1000, 200), expected, places=12)

    def test_opus_step_is_tokens_times_rate(self):
        expected = (2500 * 4.00 + 600 * 20.00) / 1e6
        self.assertAlmostEqual(step_cost("claude-opus-5-5", 2500, 600), expected, places=12)

    def test_haiku_long_prompt_uses_the_higher_tier(self):
        self.assertEqual(price_for("claude-haiku-5-5", 100000), (0.10, 0.50))
        self.assertEqual(price_for("claude-haiku-5-5", 100001), (0.50, 2.50))
        expected = (100001 * 0.50 + 10 * 2.50) / 1e6
        self.assertAlmostEqual(step_cost("claude-haiku-5-5", 100001, 10), expected, places=12)

    def test_unknown_model_is_priced_at_the_highest_rate(self):
        self.assertEqual(price_for("claude-mystery-9"), highest_rates())
        self.assertEqual(highest_rates(), (8.00, 40.00))
        self.assertAlmostEqual(step_cost("claude-mystery-9", 1000, 1000), (1000 * 8.0 + 1000 * 40.0) / 1e6)
        self.assertGreaterEqual(step_cost("claude-mystery-9", 1000, 1000), step_cost("claude-opus-5-5", 1000, 1000))

    def test_code_steps_cost_zero(self):
        self.assertEqual(step_cost(None, 0, 0), 0.0)
        self.assertEqual(step_cost(None, 500, 500), 0.0)

    def test_zero_tokens_cost_zero(self):
        self.assertEqual(step_cost("claude-opus-5-5", 0, 0), 0.0)


class TestReportCost(unittest.TestCase):
    def test_report_cost_sums_steps(self):
        steps = [
            {"name": "limits", "cost_usd": 0.0},
            {"name": "sort", "cost_usd": step_cost("claude-haiku-5-5", 400, 50)},
            {"name": "draft", "cost_usd": step_cost("claude-opus-5-5", 900, 300)},
        ]
        expected = (400 * 0.10 + 50 * 0.50 + 900 * 4.0 + 300 * 20.0) / 1e6
        self.assertAlmostEqual(report_cost(steps), expected, places=8)

    def test_empty_report_costs_nothing(self):
        self.assertEqual(report_cost([]), 0.0)


class TestPriceTable(unittest.TestCase):
    def test_configured_models_are_priced(self):
        self.assertIn(config.DEFAULT_FAST_MODEL, PRICES)
        self.assertIn(config.DEFAULT_STRONG_MODEL, PRICES)

    def test_prices_have_a_check_date(self):
        self.assertIsNotNone(re.match(r"^\d{4}-\d{2}-\d{2}$", config.PRICES_CHECKED_ON))


if __name__ == "__main__":
    unittest.main()
