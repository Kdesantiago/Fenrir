---
description: Turn a raw IDEA into a challenged, scoped, and built project. Use at the very start, when what to build is still fuzzy — it adversarially interrogates assumptions/real-problem/smallest-valuable-slice, writes a reviewed spec, then drives the creation + delivery skills (repo-bootstrap → generators → architect → /fenrir:deliver → /fenrir:ship). Triggers: "/fenrir:challenge-me", "challenge my idea", "is this worth building", "help me scope X". NOT for an already-decided change (use `architect` for design, `/fenrir:deliver` to build). Usage: /fenrir:challenge-me <what you want to build>.
---

# /fenrir:challenge-me <context>

`$ARGUMENTS` = the raw idea. Two gears: **(1) cook it** — challenge and extract what's really worth building; **(2) build it** — route through the existing creation + delivery skills. Do NOT skip gear 1 and start scaffolding; the whole point is to attack the idea before spending effort on it.

## Stance
Adversarial but constructive. Default to the **smallest slice that delivers real value** and make the user defend any scope beyond it. Be willing to conclude **"don't build this"** or **"buy/reuse instead"** — that's a successful outcome, not a failure. No rubber-stamping.

If `$ARGUMENTS` is empty, ask what they want to build before anything else.

## Gear 1 — Challenge & extract (the cooking)
1. **Steelman in one line.** Restate the idea as the strongest version you can, and confirm: "Is this what you mean?" Surfaces misunderstanding cheaply.
2. **Attack the framing** (red-team lens on the IDEA, not code):
   - What's the **real problem** vs the proposed solution? Is the solution the right shape for it?
   - Who is the **user**, and what's the **success metric**? If neither is crisp, that's the first thing to fix.
   - What **kills this**? Hardest constraint (technical, org, time, data, compliance)? What's the riskiest assumption?
   - What's explicitly **out of scope** for v1?
3. **Force the decisive forks** with `AskUserQuestion` (≤4 per round, recommended option first). Typical forks — adapt to the idea:
   - **MVP cut**: the thinnest vertical slice that proves value vs the full thing.
   - **Users / access**: who uses it, internal vs external, SSO/OAuth needs.
   - **Platform**: maps to `org-profile.yaml` `platform` (aks | webapp | k8s | serverless | vm | ecs) and `framework`.
   - **Data & persistence**: stateful? what store? migrations? PII/compliance?
   - **Scale & SLA**: traffic, latency, availability — drives async/observability/IaC.
   - **Integrations / enterprise wrappers**: third-party APIs; does the company wrap Azure (→ `stack-interface.yaml`)?
   - **Build vs buy**: is there an off-the-shelf answer that makes building wasteful?
4. **Converge fast — hard cap 2 rounds of `AskUserQuestion`.** After at most 2 rounds, decide: build (proceed to Gear 2), defer (write down what's blocking), or reject (recommend the smaller/none/buy path). No third round — if it's still unclear after 2, that itself is the finding: the idea isn't ready, say so and stop.

## Gear 2 — Spec & decision record
1. Write the spec to `docs/specs/<slug>.md` (the artifact `/fenrir:deliver` consumes): problem, users, **acceptance criteria**, scope / out-of-scope, chosen stack, the **v1 cut**, risks + riskiest assumption.
2. Record the key decisions and any **deferred scope** to delivery-memory via `memory-keeper` (so the cut is remembered, not silently re-expanded).
3. **Spec red-team (recommended; do it unless the change is trivial):** run `red-team-destroyer` on the spec. If you run it, honor its `VERDICT:` — `REDESIGN` → back to Gear 1; `FIX-FIRST` → fold findings into the spec; `SHIP` → proceed. (The Gear-3 build still has its own gates regardless.) **Dedup:** if this spec red-team already covered the design decision, the `adr-redteam` pass inside `/fenrir:deliver` can be skipped — don't red-team the same decision twice; the final `diff-redteam` on the actual change always runs.

## Gear 3 — Build via the existing skills (deterministic routing)
Route by what the spec actually needs — do not run everything blindly. **Announce + delegate:** before each step, print `→ delegating to <agent> because <reason>` and run substantive work (decompose, design, build, validate) as a **subagent via the Task tool**, so the routing is visible and the main thread stays lean (it orchestrates + reports; the subagent's churn stays in its own context).
1. **Stack**: write/confirm `org-profile.yaml` from the answers (platform, framework, auth_provider, obs_backend, llm_provider, front). If the company uses Azure wrappers, set up `stack-interface.yaml` (+ `stack-adapter`).
2. **Gate first**: `repo-bootstrap` → installs couche-0 (pre-commit + in-session hooks + CI + branch-protection + delivery-memory). No project starts without the gate.
3. **Plan on the board**: `/fenrir:plan` — decompose the spec's v1 cut into a **Feature + atomic US** on the board (one Feature per branch/PR) before any code, so the work is tracked from the start. If a plan already exists for this work, reuse it. (`/fenrir:deliver` checks for this too and creates it if missing.)
4. **Generators, by need**:
   - HTTP API → `api-first` (contract-first).
   - Deploy target → `iac-gen` (aks/webapp/…).
   - Auth → `auth-gen`. Logs/metrics → `observability-gen`. UI → `frontend-gen`. LLM → `llm-gen`. Scheduled work → `cronjob`.
5. **Design**: the **pertinent specialist** writes the ADR for the load-bearing decisions (`azure-architect` for Azure, `dat-architect` for a full architecture doc, `api-first`/`data-model`/`iac-gen`… by topic; generic `architect` only as fallback — see `/fenrir:deliver` §2b). The spec links it.
6. **Deliver the first slice**: `/fenrir:deliver` on the v1 cut, building the US one at a time. It routes to the relevant specialist and ends every route with the **mandatory qa-tester + red-team-destroyer validation gate** before `/fenrir:ship`.

## Stop conditions
- Idea rejected or deferred in Gear 1 → stop with the recommendation; do not build.
- Spec `VERDICT: REDESIGN` → loop, do not proceed to Gear 3.
- Never skip `repo-bootstrap` — a project without the gate is not "standardized delivery", just code.

## Output
- The spec path + the decisions recorded to delivery-memory.
- `org-profile.yaml` (chosen stack) and the ordered build plan.
- What actually ran in Gear 3, and the first PR opened by `/fenrir:ship` (or why it stopped).
