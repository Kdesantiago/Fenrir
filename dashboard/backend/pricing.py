"""Token → USD cost. A configurable, derived estimate (Claude Code logs tokens, not dollars).

Cost model (what's counted):
  - fresh input_tokens           × input rate
  - output_tokens                × output rate   (extended-thinking tokens are billed as
                                                   output — there is no separate field — so
                                                   thinking is already included here)
  - cache_read_input_tokens      × read rate     (0.1× input)
  - cache writes, split by TTL from usage.cache_creation:
        ephemeral_5m_input_tokens × 5m-write rate (1.25× input)
        ephemeral_1h_input_tokens × 1h-write rate (2.0×  input)
    (fallback: a flat cache_creation_input_tokens is charged at the 5m rate)

NOT modeled (documented gaps): web-search `server_tool_use` requests, batch/priority
`service_tier` discounts, and the `[1m]` long-context premium (the suffix is stripped).
Prices are public list-price ballparks — adjust `PRICES` to your contract.
"""
from __future__ import annotations

# Base (input, output) USD per 1M tokens, by model-id substring (Anthropic list price,
# 2026-06). Keys are matched in INSERTION ORDER, first substring hit wins — so put the
# version-specific keys BEFORE the generic family key. Cache rates are DERIVED from the
# input rate via CACHE below; the official table's cache columns all equal 1.25×/2×/0.1×
# input, so a contract change is one number per model.
PRICES: dict[str, tuple[float, float]] = {
    "opus-4-1": (15.0, 75.0),  # Opus 4.1 (obsolete) — older, pricier tier
    "opus": (5.0, 25.0),       # Opus 4.5–4.8 (current) + generic opus fallback
    "fable": (10.0, 50.0),     # Fable 5
    "mythos": (10.0, 50.0),    # Mythos 5 (limited availability)
    "sonnet": (3.0, 15.0),     # Sonnet 4–4.6
    "haiku-3": (0.80, 4.0),    # Haiku 3.5 (retired)
    "haiku": (1.0, 5.0),       # Haiku 4.5
}
# NOTE: the retired original Opus 4 ("claude-opus-4-2025…", $15/$75) is not separately keyed
# and resolves to the current opus rate; price it explicitly if old transcripts need it.
DEFAULT = PRICES["sonnet"]  # conservative fallback for unknown models

# Cache multipliers relative to the base INPUT rate (so a contract change is one number).
CACHE = {"w5m": 1.25, "w1h": 2.0, "read": 0.10}


def rates_for(model: str) -> dict[str, float]:
    """Resolve per-1M rates for a model; cache rates derived from its input rate."""
    # Strip a context-tier suffix like "claude-opus-4-8[1m]" before family matching.
    m = (model or "").lower().split("[", 1)[0]
    inp, out = next((v for fam, v in PRICES.items() if fam in m), DEFAULT)
    return {"input": inp, "output": out,
            "w5m": inp * CACHE["w5m"], "w1h": inp * CACHE["w1h"], "read": inp * CACHE["read"]}


def cost_of(usage: dict, model: str) -> float:
    """USD for one usage block. Missing keys treated as 0. Splits cache writes by TTL."""
    r = rates_for(model)
    fresh = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    read = int(usage.get("cache_read_input_tokens", 0) or 0)
    cc = usage.get("cache_creation")
    if isinstance(cc, dict):
        w5 = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
        w1 = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
    else:  # fallback (synthetic / older logs): no TTL split → charge the 5m rate
        w5 = int(usage.get("cache_creation_input_tokens", 0) or 0)
        w1 = 0
    return (fresh * r["input"] + out * r["output"] + read * r["read"]
            + w5 * r["w5m"] + w1 * r["w1h"]) / 1_000_000.0
