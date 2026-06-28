---
name: explain
description: Use when existing code must be EXPLAINED pedagogically — mental model, then the WHY, then line-by-line — at tunable depth (overview/walkthrough/line-by-line) and audience (junior/senior/non-engineer). Read-only: teaches, never edits, grounds claims in `file:line`. Triggers — "explain this code", "how does this work", "walk me through this", "onboard me to this file". NOT for durable README/API docs (doc-generator), NOT for a DESIGN decision/ADR (architect), NOT for correctness/security (/code-review), NOT for restructuring (fenrir:refactor). No org-profile key.
---

# Explain — teach the code, don't touch it

Pedagogical explanation of code that already exists: the **mental model first, then the WHY, then line-by-line** — at a depth and for an audience you choose. This skill *teaches*; it is strictly read-only and changes nothing. It also cannot make code correct or well-structured — it only explains what is there honestly, grounds every claim in `file:line`, and flags what it cannot determine rather than inventing behavior.

## When to use
- "explain this function/module/file", "how does this work", "walk me through this", "onboard me to this code"
- A newcomer needs the mental model + the WHY behind a non-obvious implementation
- You want a tunable-depth / tunable-audience explanation in the moment, not a durable doc on disk

## When NOT to use
- You want a durable README / API reference written to disk → `doc-generator` (it aggregates + formats existing docs; explain produces no artifact)
- You want a DESIGN decision explained or recorded → `architect` (it writes the ADR; explain teaches existing code, it does not decide or record)
- You want correctness or security findings on the code → `/code-review` or `fenrir:security-review` (explain describes behavior, it does not judge or hunt bugs)
- You want the code restructured for clarity → `fenrir:refactor` (explain teaches; refactor changes — it pins a green baseline and transforms)

## Inputs
- The target code — file / function / module — to explain. **Read it fully first**; ground every claim in `file:line`.
- **Depth knob**: `overview | walkthrough | line-by-line` (default `walkthrough`).
- **Audience knob**: `junior | senior | non-engineer` (default `senior`) — sets vocabulary and assumed background.
- `org-profile.yaml` (OPTIONAL, context only) → `framework`/`platform` to use the right stack vocabulary. **Not required and never refused on** — explain works on any code in any stack.

## Steps
1. **Read before you explain.** Open the target code in full (and the symbols it calls into, as needed). Never explain code you have not read — every statement must trace to a concrete `file:line`. If the scope is a whole module, map the public surface first.
2. **Resolve and state the knobs.** Pick depth + audience from the request (defaults `walkthrough` / `senior`). State them up front (e.g. `Depth: walkthrough · Audience: senior`) so the reader knows the register before the explanation starts.
3. **Mental model FIRST.** In a few sentences: what problem this code solves, its overall shape, and the data flow through it. Give the frame before any detail — the reader should grasp the *what* and *where it sits* before the *how*.
4. **The WHY.** Call out the non-obvious choices — why this structure, this guard, this ordering, this data type — and any trade-offs the code encodes (performance vs clarity, a defensive check, an edge case being handled). Cite `file:line` for each. This is the load-bearing part: anyone can read syntax; the value is the reasoning.
5. **Depth-appropriate detail.** `overview` → stop at the mental model + WHY. `walkthrough` → explain block by block (each function / branch / loop). `line-by-line` → annotate each meaningful line. Match vocabulary to the audience: `junior` defines idioms, `senior` assumes them, `non-engineer` uses analogies and avoids jargon.
6. **Flag, do not guess.** Where behavior is genuinely unclear or depends on external state (env, config, a callee you cannot see, runtime data), say so explicitly — never fabricate. Offer the handoff: `doc-generator` if they want this captured as a durable doc, `architect` if a decision should be recorded, `/code-review` if they actually want bugs found.

## Output / validation
- A spoken/written explanation in chat (no files written): stated depth + audience, the mental model, the WHY, then depth-appropriate detail, each claim carrying a `file:line`.
- Validate it yourself before sending: every behavioral claim traces to a line you actually read; the mental model + WHY come *before* the line-level detail (pedagogy order, not a raw line dump); the requested depth + audience are honored; anything uncertain is flagged, not invented.
- This skill is advisory teaching only — it produces no enforceable artifact and changes no code. For a durable doc the gate is `doc-generator`; for a recorded decision it is `architect`; for correctness it is `/code-review` / `fenrir:security-review`.

## Refuses when
- Asked to **edit, refactor, or "fix" the code** while explaining — this skill is read-only; route to `fenrir:refactor` (restructure) or `/fenrir:deliver` (behavior change).
- Asked to **explain code that cannot be read** (path missing, file unreadable) — it will not fabricate an explanation from a name alone; it asks for the real source.
- Asked to **assert behavior it cannot verify** from the source (depends on unseen external state) — it flags the gap instead of guessing.
- Asked to produce a **durable doc, an ADR, or a bug/security verdict** — those belong to `doc-generator`, `architect`, and `/code-review` / `fenrir:security-review` respectively.
