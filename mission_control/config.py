"""Model ids and prices.

Model ids and per-token prices were checked in the Anthropic documentation
on PRICES_CHECKED_ON. Both ids can be overridden with environment variables.
"""
import os

PRICES_CHECKED_ON = "2026-11-12"

DEFAULT_FAST_MODEL = "claude-haiku-5-5"
DEFAULT_STRONG_MODEL = "claude-opus-5-5"


def fast_model():
    """Small fast model for sorting and the three checks."""
    return os.environ.get("MC_FAST_MODEL", DEFAULT_FAST_MODEL)


def strong_model():
    """Stronger model for the draft and the review."""
    return os.environ.get("MC_STRONG_MODEL", DEFAULT_STRONG_MODEL)


def api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip() or None


def is_simulated():
    """True when there is no API key and the fake model is used."""
    return api_key() is None
