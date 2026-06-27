"""Token → USD cost. Prices are per 1M tokens, resolved by model family.

These are configurable defaults (public list-price ballparks at time of writing) — adjust
to your contract. Cost is DERIVED (Claude Code logs tokens, not dollars); treat it as an
estimate, not an invoice.
"""
from __future__ import annotations

# (input, output, cache_write_5m, cache_read) USD per 1M tokens, by family substring.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "opus": (15.0, 75.0, 18.75, 1.50),
    "sonnet": (3.0, 15.0, 3.75, 0.30),
    "haiku": (1.0, 5.0, 1.25, 0.10),
    "fable": (15.0, 75.0, 18.75, 1.50),  # treat as a top-tier model until priced
}
DEFAULT = PRICES["sonnet"]  # conservative fallback for unknown models


def rates_for(model: str) -> tuple[float, float, float, float]:
    # Strip a context-tier suffix like "claude-opus-4-8[1m]" before family matching.
    # NOTE: the long-context (e.g. 1M) premium is NOT modeled — this is a base-tier estimate.
    m = (model or "").lower().split("[", 1)[0]
    for family, rates in PRICES.items():
        if family in m:
            return rates
    return DEFAULT


def cost_of(usage: dict, model: str) -> float:
    """USD for one usage block: {input_tokens, output_tokens, cache_creation_input_tokens,
    cache_read_input_tokens}. Missing keys treated as 0."""
    rin, rout, rcw, rcr = rates_for(model)
    fresh_in = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    cw = int(usage.get("cache_creation_input_tokens", 0) or 0)
    cr = int(usage.get("cache_read_input_tokens", 0) or 0)
    return (fresh_in * rin + out * rout + cw * rcw + cr * rcr) / 1_000_000.0
