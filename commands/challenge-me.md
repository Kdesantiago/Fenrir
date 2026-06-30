---
description: Turn a raw IDEA into a challenged, scoped, and built project. Use at the very start, when what to build is still fuzzy — it runs a VIOLENT multi-round adversarial interrogation (progressive-depth, 13-aspect checklist, visible scorecard) that refuses to emit a spec or advance to plan/deliver until every aspect is settled or explicitly out-of-scope, then drives the creation + delivery skills (repo-bootstrap → generators → architect → /fenrir:deliver → /fenrir:ship). Triggers: "/fenrir:challenge-me", "challenge my idea", "is this worth building", "help me scope X". NOT for an already-decided change (use `architect` for design, `/fenrir:deliver` to build). Usage: /fenrir:challenge-me <what you want to build>.
---

# /fenrir:challenge-me <context>

`$ARGUMENTS` = the raw idea. Two gears: **(1) interrogate it** — a violent, multi-round, multi-aspect grilling that digs progressively deeper until the intent is genuinely clear and complete; **(2) build it** — route through the existing creation + delivery skills. Do NOT skip gear 1 and start scaffolding. **This is a GATE, not a formality:** you do not emit a spec or touch `plan`/`deliver` until the completeness bar (§Gear 1.5) is met or the user explicitly overrides.

If `$ARGUMENTS` is empty, ask what they want to build before anything else.

## Stance
Adversarial but constructive — red-team-destroyer energy on the **idea**, never on the person. Default to the **smallest slice that delivers real value** and make the user defend any scope beyond it. Surface contradictions between answers out loud. Be willing to conclude **"don't build this"** or **"buy/reuse instead"** — that's a successful outcome, not a failure. No rubber-stamping, no advancing on mush.

## Token discipline (applies to the whole command)
- The interrogation rounds are **interactive — they run in the main thread** (they cannot be a subagent). Keep main-thread prose lean: ask via structured `AskUserQuestion`, not essays. Fragments over paragraphs.
- Any **research** needed to challenge an answer (does this library exist? is this approach standard? is that API real?) is **delegated to a subagent** via the Task tool, so its churn stays out of main context. Announce it: `→ delegating research to <agent> because <reason>`.
- **Prepend the one-line terse preamble to every subagent prompt** (the shared snippet used across `/fenrir:deliver` and `/fenrir:plan`): *"⚡ Respond in caveman/terse mode: drop articles/filler/pleasantries/hedging; fragments OK; keep ALL technical substance, exact `file:line`, code, and your VERDICT. Minimise output tokens."* Do not inline a longer private copy.

## Gear 1 — Violent interrogation (multi-round, progressive depth)

### The 13-aspect checklist (must all be covered)
Group the interrogation around these. Skip an aspect only by **explicitly** declaring it out-of-scope with the user:
1. **Real problem & owner** — who actually has this pain, how they solve it today, what it costs them.
2. **Why now** — the trigger; what changes if it is *not* built.
3. **Success metric** — the single measurable signal that proves it worked. **Refuse "it works"** as an answer.
4. **Smallest valuable slice** — the thinnest shippable thing a real user would use. Attack scope creep.
5. **Users / personas & primary flow** — who touches it and the one path that must not break.
6. **Constraints** — stack, time, budget, team, existing systems it must fit.
7. **Non-goals** — what it deliberately will *not* do (forces scope discipline).
8. **Data & interfaces** — the data it owns, the contracts/APIs in and out.
9. **Failure modes & edge cases** — what breaks, what happens then.
10. **Security / privacy / compliance** — sensitive data, authz, blast radius.
11. **Scale & ops** — expected load, where it runs, who operates it.
12. **Alternatives considered** — buy vs build, simpler option, do-nothing — and why rejected.
13. **Definition of done** — the concrete acceptance bar.

### The scorecard (keep it visible)
Maintain and **re-print a scorecard every round** so progress is legible. Each aspect carries one status:

| # | Aspect | Status | Decided answer (1 line) |
|---|--------|--------|-------------------------|
| 1 | Real problem & owner | `open` / `settled` / `out-of-scope` | … |
| … | … | … | … |

- `settled` — answer is **concrete and falsifiable**. Do not mark settled on mush.
- `open` — not yet concrete, or not yet asked.
- `out-of-scope` — user explicitly declared it irrelevant to this build.

Start every aspect at `open`.

### Each round — do all four
Steelman the idea in one line first (round 1 only): restate the strongest version and confirm "Is this what you mean?". Then, **every round**, do all four:
- **Challenge** — name the **weakest assumption** out loud and pressure-test it (red-team-destroyer energy on the idea). Surface contradictions between earlier answers.
- **Guide** — when the user is stuck, **narrow** the question and explain *why it matters for the build*.
- **Suggest** — offer **2–3 concrete options with a recommendation** rather than leaving a blank.
- **Dig** — each answer **spawns the next, sharper question** until the aspect is concrete.

### The round loop (this is multi-round, NOT one pass)
Repeat until the completeness bar (§Gear 1.5) is met:
1. Pick the most load-bearing `open` aspects (those that unblock the most downstream decisions first).
2. Ask via **`AskUserQuestion`** — **≤4 questions per call**, each with a **recommended option** where one exists.
3. Read the answers. For each: is it **concrete and falsifiable**? If yes → mark the aspect `settled` and record the one-line decided answer. If it's vague, hand-wavy, or contradicts an earlier answer → **dig down**: re-ask narrower next round, and Challenge/Guide/Suggest on it.
4. If research is needed to challenge an answer → **delegate to a subagent** (see Token discipline), fold the finding back in.
5. **Re-print the scorecard.**
6. **Dig-down cap:** stop questioning any single aspect after **3 dig-downs**. Do not stall — record it as an explicit **OPEN RISK** and move on (status stays `open`, flagged as capped).

There is **no fixed round count** — a vague idea ("build a dashboard") should take **≥3 rounds**. Keep going while aspects are `open` and not capped.

### Gear 1.5 — Completeness bar (the GATE)
You may proceed to Gear 2 **only when**:
- **every aspect is `settled` or explicitly `out-of-scope`**, OR
- the user **explicitly overrides** with a "ship it as-is" instruction.

If aspects are still `open` (including dig-down-capped open risks) and the user has **not** overridden → **do not emit the spec, do not call `plan`/`deliver`.** Keep interrogating, or tell the user exactly which aspects block exit and ask them to either answer, declare out-of-scope, or override.

On an **override**, the emitted spec must list the still-`open` aspects as **accepted risks at the very top**.

## Gear 2 — Spec & decision record (only after the gate)
1. Write the spec to `docs/specs/<slug>.md` (the artifact `/fenrir:deliver` consumes). It **must include**:
   - **Accepted risks** (only if exited via override) — the open aspects, at the top.
   - **The scorecard** — every aspect with its final `settled` / `open` / `out-of-scope` status.
   - **Decided answers per aspect** — the concrete answer recorded for each settled aspect.
   - **Open risks** — the dig-down-capped / acknowledged unknowns.
   - **The smallest-valuable-slice as the first deliverable.**
   - Plus the usual: problem, users, acceptance criteria, scope / out-of-scope, chosen stack, riskiest assumption.
2. Record the key decisions and any **deferred scope** to delivery-memory via `memory-keeper` (so the cut is remembered, not silently re-expanded).
3. **Spec red-team (recommended; do it unless the change is trivial):** run `red-team-destroyer` on the spec. Honor its `VERDICT:` — `REDESIGN` → back to Gear 1 (reopen the relevant aspects); `FIX-FIRST` → fold findings into the spec; `SHIP` → proceed. **Dedup:** if this spec red-team already covered the design decision, the `adr-redteam` pass inside `/fenrir:deliver` can be skipped — don't red-team the same decision twice; the final `diff-redteam` on the actual change always runs.

## Gear 3 — Build via the existing skills (deterministic routing)
**Only reachable after the completeness bar is met and the spec is written.** Route by what the spec actually needs — do not run everything blindly. **Announce + delegate:** before each step, print `→ delegating to <agent> because <reason>` and run substantive work (decompose, design, build, validate) as a **subagent via the Task tool**, so routing is visible and the main thread stays lean. **Prepend the terse-mode line (above) to every subagent prompt.**
1. **Stack**: write/confirm `org-profile.yaml` from the answers (platform, framework, auth_provider, obs_backend, llm_provider, front). If the company uses Azure wrappers, set up `stack-interface.yaml` (+ `stack-adapter`).
2. **Gate first**: `repo-bootstrap` → installs couche-0 (pre-commit + in-session hooks + CI + branch-protection + delivery-memory). No project starts without the gate.
3. **Plan on the board**: `/fenrir:plan` — decompose the spec's v1 cut into a **Feature + atomic US** on the board (one Feature per branch/PR) before any code. If a plan already exists for this work, reuse it. (`/fenrir:deliver` checks for this too and creates it if missing.)
4. **Generators, by need**:
   - HTTP API → `api-first` (contract-first).
   - Deploy target → `iac-gen` (aks/webapp/…).
   - Auth → `auth-gen`. Logs/metrics → `observability-gen`. UI → `frontend-gen`. LLM → `llm-gen`. Scheduled work → `cronjob`.
5. **Design**: the **pertinent specialist** writes the ADR for the load-bearing decisions (`azure-architect` for Azure, `dat-architect` for a full architecture doc, `api-first`/`data-model`/`iac-gen`… by topic; generic `architect` only as fallback — see `/fenrir:deliver` §2b). The spec links it.
6. **Deliver the first slice**: `/fenrir:deliver` on the smallest-valuable-slice, building the US one at a time. It routes to the relevant specialist and ends every route with the **mandatory qa-tester + red-team-destroyer validation gate** before `/fenrir:ship`.

## Stop conditions
- Completeness bar not met and no override → **do not emit the spec, do not call `plan`/`deliver`**; keep interrogating or report the blocking aspects.
- Idea rejected or deferred in Gear 1 → stop with the recommendation; do not build.
- Spec `VERDICT: REDESIGN` → loop back to Gear 1, do not proceed to Gear 3.
- Never skip `repo-bootstrap` — a project without the gate is not "standardized delivery", just code.

## Output
- The spec path (with scorecard + decided answers + open risks + smallest-valuable-slice) and the decisions recorded to delivery-memory.
- `org-profile.yaml` (chosen stack) and the ordered build plan.
- What actually ran in Gear 3, and the first PR opened by `/fenrir:ship` (or why it stopped).
