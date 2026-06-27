"""Tests for backend.pricing — family resolution + per-block cost math.

Self-contained: stdlib + pytest only. No conftest, no __init__. Pure functions only,
so no filesystem / ~/.claude access is needed here.
"""
from __future__ import annotations

import pytest

from backend import pricing

# --- rates_for: family resolution -----------------------------------------------------


@pytest.mark.parametrize(
    "model, expected_family",
    [
        ("claude-opus-4-20250514", "opus"),
        ("claude-3-5-sonnet-20241022", "sonnet"),
        ("claude-3-5-haiku-20241022", "haiku"),
        ("fable-experimental", "fable"),
        # case-insensitive: rates_for lowercases the model string
        ("CLAUDE-OPUS-4", "opus"),
        ("Claude-Sonnet", "sonnet"),
    ],
)
def test_rates_for_known_families(model, expected_family):
    assert pricing.rates_for(model) == pricing.PRICES[expected_family]


def test_rates_for_opus_exact_tuple():
    assert pricing.rates_for("claude-opus-4") == (15.0, 75.0, 18.75, 1.50)


def test_rates_for_fable_matches_opus_pricing():
    # fable is priced identically to opus (top-tier until priced)
    assert pricing.rates_for("fable") == pricing.rates_for("opus")


def test_rates_for_unknown_returns_default():
    assert pricing.rates_for("gpt-4o") == pricing.DEFAULT
    assert pricing.rates_for("some-mystery-model") == pricing.DEFAULT


def test_default_is_sonnet():
    assert pricing.DEFAULT == pricing.PRICES["sonnet"]


def test_rates_for_empty_string_returns_default():
    assert pricing.rates_for("") == pricing.DEFAULT


def test_rates_for_none_returns_default():
    # rates_for guards with `(model or "")`, so None must not raise
    assert pricing.rates_for(None) == pricing.DEFAULT  # type: ignore[arg-type]


def test_rates_for_resolution_order_first_match_wins():
    # PRICES iterates insertion order (opus, sonnet, haiku, fable); a string
    # containing two family names resolves to whichever appears first in PRICES.
    # "opus" precedes "sonnet" in the dict, so an opus+sonnet string -> opus.
    assert pricing.rates_for("opus-sonnet-hybrid") == pricing.PRICES["opus"]


# --- cost_of: token math --------------------------------------------------------------


def test_cost_of_full_block_opus():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    # opus rates: 15 + 75 + 18.75 + 1.50 per 1M each
    expected = 15.0 + 75.0 + 18.75 + 1.50
    assert pricing.cost_of(usage, "claude-opus-4") == pytest.approx(expected)


def test_cost_of_sonnet_input_only():
    usage = {"input_tokens": 2_000_000}
    # sonnet input rate 3.0 per 1M -> 2M = 6.0
    assert pricing.cost_of(usage, "claude-3-5-sonnet") == pytest.approx(6.0)


def test_cost_of_cache_creation_and_read_counted_separately():
    usage = {
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    # sonnet: cache_write 3.75 + cache_read 0.30
    assert pricing.cost_of(usage, "sonnet") == pytest.approx(3.75 + 0.30)


def test_cost_of_haiku_mixed_block():
    usage = {
        "input_tokens": 500_000,
        "output_tokens": 100_000,
        "cache_creation_input_tokens": 200_000,
        "cache_read_input_tokens": 4_000_000,
    }
    # haiku rates: in 1.0, out 5.0, cw 1.25, cr 0.10 (per 1M)
    expected = (
        500_000 * 1.0
        + 100_000 * 5.0
        + 200_000 * 1.25
        + 4_000_000 * 0.10
    ) / 1_000_000.0
    assert pricing.cost_of(usage, "claude-3-5-haiku") == pytest.approx(expected)


def test_cost_of_unknown_model_uses_default_sonnet_rates():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    expected = 3.0 + 15.0  # sonnet in + out
    assert pricing.cost_of(usage, "gpt-4o") == pytest.approx(expected)


# --- cost_of: zero / missing / None keys ----------------------------------------------


def test_cost_of_empty_usage_is_zero():
    assert pricing.cost_of({}, "claude-opus-4") == 0.0


def test_cost_of_all_zero_is_zero():
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    assert pricing.cost_of(usage, "sonnet") == 0.0


def test_cost_of_missing_keys_treated_as_zero():
    # only output present; missing input/cache keys must not raise
    usage = {"output_tokens": 1_000_000}
    assert pricing.cost_of(usage, "sonnet") == pytest.approx(15.0)


def test_cost_of_none_valued_keys_treated_as_zero():
    # the `or 0` guard in cost_of must coerce explicit None to 0
    usage = {
        "input_tokens": None,
        "output_tokens": None,
        "cache_creation_input_tokens": None,
        "cache_read_input_tokens": None,
    }
    assert pricing.cost_of(usage, "opus") == 0.0


def test_cost_of_string_token_values_coerced_to_int():
    # cost_of wraps values in int(...); numeric strings are accepted
    usage = {"input_tokens": "1000000"}
    assert pricing.cost_of(usage, "sonnet") == pytest.approx(3.0)


def test_cost_of_returns_float():
    assert isinstance(pricing.cost_of({"input_tokens": 1}, "sonnet"), float)
