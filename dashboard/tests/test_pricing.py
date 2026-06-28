"""Tests for backend.pricing — family resolution + per-block cost math.

Self-contained: stdlib + pytest only. No conftest, no __init__. Pure functions only,
so no filesystem / ~/.claude access is needed here.
"""
from __future__ import annotations

import pytest

from backend import pricing

# --- rates_for: family resolution -----------------------------------------------------


def _expected(fam):
    """The derived rate dict for a base PRICES family (cache rates from input)."""
    inp, out = pricing.PRICES[fam]
    c = pricing.CACHE
    return {"input": inp, "output": out, "w5m": inp * c["w5m"], "w1h": inp * c["w1h"],
            "read": inp * c["read"]}


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
    assert pricing.rates_for(model) == _expected(expected_family)


def test_rates_for_opus_48_current_rates():
    # Opus 4.5–4.8 (current): base (5, 25) + derived cache 5m=6.25, 1h=10, read=0.50
    assert pricing.rates_for("claude-opus-4-8") == {
        "input": 5.0, "output": 25.0, "w5m": 6.25, "w1h": 10.0, "read": 0.50}


def test_rates_for_opus_41_is_the_pricier_legacy_tier():
    # Opus 4.1 (obsolete): base (15, 75) — version key wins over the generic "opus"
    assert pricing.rates_for("claude-opus-4-1") == {
        "input": 15.0, "output": 75.0, "w5m": 18.75, "w1h": 30.0, "read": 1.5}


def test_rates_for_fable_is_its_own_tier():
    # Fable 5 is $10/$50, NOT the opus rate
    assert pricing.rates_for("claude-fable-5") == {
        "input": 10.0, "output": 50.0, "w5m": 12.5, "w1h": 20.0, "read": 1.0}


def test_rates_for_haiku_35_is_cheaper_than_haiku_45():
    assert pricing.rates_for("claude-haiku-3-5") == _expected("haiku-3")
    assert pricing.rates_for("claude-haiku-4-5") == _expected("haiku")


def test_rates_for_unknown_returns_default():
    assert pricing.rates_for("gpt-4o") == _expected("sonnet")
    assert pricing.rates_for("some-mystery-model") == _expected("sonnet")


def test_default_is_sonnet():
    assert pricing.DEFAULT == pricing.PRICES["sonnet"]


def test_rates_for_empty_string_returns_default():
    assert pricing.rates_for("") == _expected("sonnet")


def test_rates_for_none_returns_default():
    # rates_for guards with `(model or "")`, so None must not raise
    assert pricing.rates_for(None) == _expected("sonnet")  # type: ignore[arg-type]


def test_rates_for_resolution_order_first_match_wins():
    # PRICES iterates insertion order (opus, sonnet, haiku, fable); a string
    # containing two family names resolves to whichever appears first in PRICES.
    # "opus" precedes "sonnet" in the dict, so an opus+sonnet string -> opus.
    assert pricing.rates_for("opus-sonnet-hybrid") == _expected("opus")


# --- cost_of: token math --------------------------------------------------------------


def test_cost_of_full_block_opus():
    usage = {
        "input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    # current Opus (4.5–4.8) rates: 5 + 25 + 6.25 (5m write) + 0.50 (read) per 1M each
    expected = 5.0 + 25.0 + 6.25 + 0.50
    assert pricing.cost_of(usage, "claude-opus-4-8") == pytest.approx(expected)


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
