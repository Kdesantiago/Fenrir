# Spec — `challenge-me` violent interrogation mode

Status: Draft (ground truth for the usability-refonte build phase)
Owner requirement: the user wants `/fenrir:challenge-me` to **grill them hard** — an adversarial, multi-round, multi-aspect interrogation that digs progressively deeper until the intent is genuinely clear and complete, *before* any planning or development.

## Problem with today's `challenge-me`
`commands/challenge-me.md` does a single adversarial pass (assumptions / real-problem / smallest-valuable-slice), then writes a spec and immediately drives the creation + delivery skills. It is too shallow and too eager: it does not systematically cover the aspects needed for a complete spec, does not loop until clarity, and moves to building while real unknowns remain.

## Target behaviour
A **gate**, not a formality. It must not emit a spec or advance to `plan`/`deliver` until a completeness bar is met.

### 1. Multi-round, progressive depth
- Run in **rounds**, not one shot. Each round opens with structured questions (use `AskUserQuestion`, ≤4 per call, with a recommended option where one exists), reads the answers, and goes **deeper** on whatever is vague, hand-wavy, or contradictory.
- Do **not** advance an aspect to "settled" until the answer is concrete and falsifiable. Re-ask, narrower, when an answer is mush.
- Hard cap to avoid infinite loops: stop questioning an aspect after 3 dig-downs and record it as an explicit **open risk** instead of stalling.

### 2. Aspect checklist (must be covered, each marked settled / open)
Group the interrogation around these; skip an aspect only by *explicitly* declaring it out of scope with the user:
- **Real problem & owner** — who actually has this pain, how do they solve it today, what does it cost them.
- **Why now** — the trigger; what changes if it is *not* built.
- **Success metric** — the single measurable signal that proves it worked. Refuse "it works" as an answer.
- **Smallest valuable slice** — the thinnest thing shippable that a real user would use. Attack scope creep.
- **Users / personas & primary flow** — who touches it and the one path that must not break.
- **Constraints** — stack, time, budget, team, existing systems it must fit.
- **Non-goals** — what it deliberately will *not* do (forces scope discipline).
- **Data & interfaces** — the data it owns, the contracts/APIs in and out.
- **Failure modes & edge cases** — what breaks, what happens then.
- **Security / privacy / compliance** — sensitive data, authz, blast radius.
- **Scale & ops** — expected load, where it runs, who operates it.
- **Alternatives considered** — buy vs build, simpler option, do-nothing — and why rejected.
- **Definition of done** — the concrete acceptance bar.

### 3. Challenge — guide — suggest — dig
On every round, do all four:
- **Challenge**: name the weakest assumption out loud and pressure-test it (red-team-destroyer energy on the *idea*, not the person). Surface contradictions between answers.
- **Guide**: when the user is stuck, narrow the question and explain *why it matters for the build*.
- **Suggest**: offer 2–3 concrete options (with a recommendation) rather than leaving a blank.
- **Dig**: each answer spawns the next, sharper question until the aspect is concrete.

### 4. Completeness bar before exit
- Maintain a visible scorecard: each aspect = `settled` / `open` / `out-of-scope`.
- **Exit only when** every aspect is `settled` or explicitly `out-of-scope`, OR the user overrides with an explicit "ship it as-is" — in which case the spec lists the `open` aspects as accepted risks at the top.
- The emitted spec must include: the scorecard, the decided answers per aspect, the open risks, and the smallest-valuable-slice as the first deliverable.

### 5. Token discipline (consistency with the refonte)
- The interrogation rounds run in the **main thread** (they are interactive with the user — cannot be a subagent), but keep main-thread prose lean: structured `AskUserQuestion` calls, not long essays.
- Any *research* needed to challenge an answer (e.g. "does this library exist / is this approach standard") is delegated to a subagent so its churn stays out of main context.
- Use the shared terse-mode preamble (the de-duplicated snippet introduced by the token-efficiency work-stream) — do not inline a private copy.

## Acceptance (verify phase)
- A dry-run on a deliberately vague idea ("build a dashboard") must produce ≥3 rounds, cover every checklist aspect, refuse to emit a spec while ≥1 aspect is `open` and unacknowledged, and end with a scorecard + open-risks section in the spec.
- The command must not call `plan`/`deliver` until the completeness bar (or explicit override) is met.
