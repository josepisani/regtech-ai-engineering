"""Smoke tests that run without any API keys or network — safe in CI."""
from src import config
from src.hello_claude import estimate_cost


def test_estimate_cost_is_positive():
    assert estimate_cost(1000, 500) > 0


def test_config_has_defaults():
    # Defaults apply even when nothing is set in the environment.
    assert config.CLAUDE_MODEL
    assert config.MAX_TOKENS > 0
