---
description: Tech-lead view of THIS repo — a single honest markdown report (gate armed?, open/self-granted/lapsed exceptions, onboarding "how we deliver here"). Verified facts or labeled declared/unverified; no DORA proxies. Runs a deterministic helper, then interprets.
---

# /fenrir:status

A read/govern surface for a tech lead. Produces one markdown **Tech Lead Report** for the
current repo and then interprets it into next actions. The numbers come from a
deterministic helper (git + on-disk files + one live branch-protection API call), not an
LLM guess — so the report is reproducible.

## What it answers
- **Is this repo actually gated?** pre-commit installed, CI workflow present, and
  branch-protection **ARMED/NOT-ARMED (verified via `gh api`)** — not just file presence.
- **What needs a lead's attention?** open gate-exceptions, with **self-granted** (claimed
  approver, unverified) and **lapsed** ones flagged.
- **How does a newcomer ship here?** declared stack + the gate + the golden path.

It deliberately shows **no DORA metrics**: locally, tags ≠ deploys and `fix:`-ratio ≠
change-failure, so any such number would be confidently wrong. Facts only.

## Run it
```sh
# Inspects $CLAUDE_PROJECT_DIR by default; --offline skips the live gh api call.
python3 "$CLAUDE_PLUGIN_ROOT/scripts/techlead_report.py"
# Specific repo / branch:  python3 "$CLAUDE_PLUGIN_ROOT/scripts/techlead_report.py" --root . --branch main
```
If `$CLAUDE_PLUGIN_ROOT` is unset (rare), resolve the plugin root from where this command
lives. The helper never crashes on a partial repo — sections degrade to "not configured".

## Then interpret (your value on top of the raw report)
1. Print the report verbatim first.
2. Call out the lead-relevant signals, in priority order:
   - **NOT-ARMED branch-protection** → the repo is not gated for real; recommend
     `terraform apply` on `branch-protection.tf` (or the Azure branch policy).
   - **Self-granted exceptions** → name them; a waiver should have an `approved_by` distinct
     from `granted_by` (see the `memory-keeper` skill). Recommend a real approver.
   - **Lapsed-but-open exceptions** → recommend `memory-keeper` `expire`.
   - **template_version DRIFT** → the repo targets a different plugin major/0.x-minor; bump
     `org-profile.yaml` or pin a matching plugin (`delivery-gates` enforces this).
3. Keep it terse and advisory — this command reports and recommends; it does not change
   anything. The real gate is CI required-checks + branch-protection (infra).
