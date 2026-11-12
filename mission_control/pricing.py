"""Cost arithmetic in code.

Prices are US dollars per million tokens, checked in the Anthropic
documentation on config.PRICES_CHECKED_ON. An unknown model id is priced at
the highest known rate so the console never under-reports.
"""
from mission_control.config import PRICES_CHECKED_ON  # noqa: F401  (re-exported for the README and status)

MTOK = 1000000.0

# Haiku 5.5 charges a higher rate for prompts over 100K tokens.
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50,
                         "long_threshold": 100000, "long_input": 0.50, "long_output": 2.50},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00},
    "claude-fable-5-2": {"input": 8.00, "output": 40.00},
}


def highest_rates():
    """The most expensive input and output rates in the table."""
    best_input = 0.0
    best_output = 0.0
    for entry in PRICES.values():
        best_input = max(best_input, entry["input"], entry.get("long_input", 0.0))
        best_output = max(best_output, entry["output"], entry.get("long_output", 0.0))
    return best_input, best_output


def price_for(model, input_tokens=0):
    """Return ``(input_rate, output_rate)`` per million tokens for a call."""
    entry = PRICES.get(model)
    if entry is None:
        return highest_rates()
    if "long_threshold" in entry and input_tokens > entry["long_threshold"]:
        return entry["long_input"], entry["long_output"]
    return entry["input"], entry["output"]


def step_cost(model, input_tokens, output_tokens):
    """Cost in dollars of one step. Code steps have no model and cost nothing."""
    if model is None:
        return 0.0
    input_rate, output_rate = price_for(model, input_tokens)
    return (input_tokens * input_rate + output_tokens * output_rate) / MTOK


def report_cost(steps):
    """Sum the cost of a report's trace steps."""
    return round(sum(float(step.get("cost_usd", 0.0)) for step in steps), 8)
