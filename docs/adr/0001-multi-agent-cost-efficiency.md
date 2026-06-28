# ADR 0001 — Multi-agent cost / speed / quality efficiency

Status: accepted · Date: 2026-06-28

## Context

The dashboard showed ~$540 for one day of work; cache-read was ~80% of it. The instinct was
"the cache is wasting money — optimize it." Measurement says the opposite.

- Cache-read is billed at **0.1× input**. The 551M cache-read tokens cost ~$276; **uncached**
  they would be 551M × $5 = **~$2,755**. Caching already saves ~$2,500 (≈10×).
- The cost is high because the **work is context-heavy**: large contexts re-read across 4,513
  Opus calls. The driver is **context volume × model tier**, not the cache discount.

So "optimize the cache" is the wrong frame. The levers that actually move the bill are about
how Fenrir's own multi-agent workflows are *constructed* — what Fenrir controls. (Fenrir cannot
change how Claude Code bills context; it can change what it sends.)

## Decision

Treat this as **context/cost efficiency for multi-agent workflows**, ranked by real impact:

1. **Model tiering (biggest $).** Every call was Opus ($5/$25). Route mechanical stages
   (structured extraction, verify, fix, lint-style) to Sonnet ($3/$15) or Haiku ($1/$5).
   Cache-read scales with the input rate too — Haiku read $0.10 vs Opus $0.50 (5× cheaper).
2. **Prompt budget.** Stop inlining large blobs (full specs / inventory / conventions) into
   *every* agent prompt — pass a file reference the agent reads, or only the needed slice.
3. **Right-sized fan-out.** Cap agent count; batch items; don't spawn 100+ agents when 10 do.
4. **Prefix-stable prompts.** Put the stable context first so N agents share one cache write +
   cheap reads, varying only the tail.
5. **Shorter sessions / compaction.** Main-thread cache-read grows because one long session
   re-reads its swelling context every turn.

Caching itself stays as-is — it is the efficient path, not the problem.

## Scope of this PR

- **Make waste visible (us-51):** a dashboard **cache-efficiency** view — per model/source the
  cache-hit ratio, actual vs **uncached-equivalent** cost, and the savings caching already
  yields. Turns the measurement into a target list.
- **Codify the discipline (us-52):** a `workflow-efficiency` skill — the tiering rubric, prompt
  budget, fan-out caps, prefix-stable prompts — so workflow authors (and `/deliver`) apply
  levers 1–4 by default.

## Deferred (follow-up)

- Apply the tiering defaults inside the orchestration commands + any shipped workflow templates.
- A cost-efficiency lint that flags workflows inlining large blobs.
- Wire budget thresholds via the existing `llm-cost-monitor`.

## Consequences

- The dashboard answers "where is context wasted, and what would it cost uncached?".
- Workflow authors have a single rubric for cheap-but-good multi-agent runs.
- No change to correctness or the cache layer; this is an efficiency + visibility change.
