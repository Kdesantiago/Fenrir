# Delivery Skillset — Org-portable delivery standard (v2)

> v2 = v1 corrected after red-team. 5 kill shots addressed. Read `## Kill shots → fixes` first.

## Core principle (fix #1, the most important one)

**A skill CANNOT enforce.** It is advisory text that the model *chooses* to follow. The real gate lives in deterministic INFRA: git hooks + CI required-checks + branch-protection-as-code. Skills = **fast local feedback**, not the barrier.

So the delivery standard = **3 distinct products**, not 1 skillset:

| Module | What | Primitive | Owner |
|---|---|---|---|
| **A. INFRA (couche 0)** | repo-template + hooks + CI + branch-protection. **The real gate.** | Deterministic files, not a model | Platform team |
| **B. GENERATORS** | profile-driven scaffolding (iac/auth/obs/front/llm) | Skills reading `org-profile.yaml` | Platform team |
| **C. ORCHESTRATION** | subagents + `/fenrir:deliver` + `/fenrir:ship` | Subagents + commands | DevEx |

All shipped as **1 versioned (semver) Claude Code plugin**, no per-repo `~/.claude` copy (= guaranteed drift).

---

## Couche 0 — INFRA (the real standard, definitely NOT skills)

This is where "standardize delivery" has teeth. Deterministic, outside the model's discretion.

| Component | Mechanism | Enforces what |
|---|---|---|
| `pre-commit` / `pre-push` hooks | git hooks (installed by `repo-bootstrap`) | lint, type, secret-scan, format — local, before push |
| CI required status checks | pipeline (Azure/GH Actions) | test, coverage, SAST, build — blocks merge |
| branch-protection-as-code | REST API via `set_branch_protection.py` (no gh/terraform); Terraform/Azure policy optional | PR required, required checks, CODEOWNERS review |
| versioned repo-template | template repo / cookiecutter | org structure, version assertion |

**Protocol**: `repo-bootstrap` generates these files + applies branch-protection via IaC. The skill installs; the INFRA enforces.

---

## org-profile.yaml (fix #2 — without it, generators spit out off-stack code)

Generators are NOT portable naked (OIDC≠SAML, k8s≠serverless, React≠Streamlit). They read a profile and **refuse on mismatch**.

```yaml
# org-profile.yaml — repo root
platform: aks          # aks | webapp | k8s | serverless | vm | ecs
framework: fastapi     # fastapi | express | spring | streamlit
auth_provider: entra   # entra | okta | keycloak | auth0
obs_backend: grafana   # grafana | datadog | cloudwatch | honeycomb | langfuse
llm_provider: anthropic # anthropic | openai | azure | bedrock | vertex
front: streamlit       # react | vue | svelte | streamlit | html | none
```

Generator with no matching profile → **hard stop, clear message**. No guessed scaffold.

---

## Couche 1 — SKILLS (`~/.claude/skills/<name>/SKILL.md` via plugin)

Trimmed vs v1: overlaps killed, secret-scan removed (→ hook), ADR removed from doc (→ architect).

| Skill | Job | Trigger (front-loaded description) | Fix note |
|---|---|---|---|
| `repo-bootstrap` | Init a NEW repo: structure, hooks, CI skeleton, branch-protection IaC, renovate, CODEOWNERS. **Idempotent, skip if exists.** | "initialize a NEW repo tooling — NOT for running checks" | Sole owner of the CI skeleton (collision fix §1) |
| `delivery-gates` | Runs lint+type+test+coverage **locally** = fast feedback. **Advisory.** Real gate = couche 0. | "run existing checks on a diff for fast local feedback" | Does not enforce; says so explicitly (fix #1) |
| `security-review` | Wraps native `/security-review`: SAST + SBOM + threat-check on a diff. **No secret-scan** (→ hook). | "SAST/SBOM/threat on a diff" | Secret-scan = single location (fix §1) |
| `doc-generator` | Aggregates/formats existing docs: README, API docs, changelog. **No ADR.** | "aggregate & format existing docs" | ADR belongs to `architect` (fix §1) |
| `iac-gen` | Profile-driven generator: Helm/ArgoCD if `platform=k8s`, otherwise refuse | "generate IaC for the declared platform" | Reads profile, refuses mismatch (fix #2) |
| `auth-gen` | Generator: OIDC/OAuth2 per `auth_provider`. **Never unreviewed auto-auth.** | "generate auth glue for declared provider" | Refuses without profile; auth = mandatory human review (fix #2, security) |
| `observability-gen` | OTel SDK init + semantic conventions; backend via env, never hardcoded | "generate vendor-neutral OTel init" | Backend = config (fix #2) |
| `frontend-gen` | Generator OR convention-checker per `front`; framework-aware a11y rules | "scaffold/check front for declared framework" | Refuses if framework unknown (fix #2) |
| `llm-gen` | Typed wrapper for `llm_provider`; golden-set eval, cost tracking | "generate LLM wrapper for declared provider" | 1 provider/profile; SDK to be verified against docs (fix #2) |

---

## Couche 2 — SUBAGENTS (`~/.claude/agents/<name>.md`)

Trimmed vs v1 (fix §7 — native overlap).

| Subagent | Verdict | Job |
|---|---|---|
| `architect` | **KEEP** — distinct, read+plan, restricted tools | Design, **ADR (decides+writes)**, trade-offs |
| `qa-tester` | **KEEP** — distinct tool-profile | Writes NEW tests + reproduces bugs (≠ gates, which run existing ones) |
| `reviewer` | **WRAP native** — no custom persona | Calls native `/code-review` + org-specific PR-hygiene rules only |
| `coder` | **KILL** unless a restricted toolset is needed | Otherwise = main thread's default behavior |

---

## Couche 3 — ORCHESTRATION (the "Project Manager", fix §4)

| Command | Job | Fixes applied |
|---|---|---|
| `/fenrir:deliver` | Pipeline: architect→coder→qa→reviewer→gates→PR | (a) **on-disk spec-artifact** = source of truth that each subagent re-reads (anti context-loss). (b) **deterministic routing by script** (LOC, risk files via globs), not LLM judgment. (c) **git checkpoint per stage** + resume. (d) real gates = CI, not the command. |
| `/fenrir:ship` | Opens PR + shows CI status | **Does NOT claim to enforce** — branch-protection (infra) blocks the merge, not `/fenrir:ship` (fix #1) |

**Adaptive resolved**: `light` is the **default** (inline edit or one specialist subagent); the **full** multi-agent pipeline is opt-in via `--full` or auto-triggered only for risky/large diffs (auth/iac/migrations/security path hits, or over the file/LOC threshold) — computed deterministically by script. Routing changes only design/review overhead; the qa-tester + red-team validation gate runs on **both** routes.

---

## Distribution (fix #4 — anti-drift)

- **1 Claude Code plugin, semver, 1 repo of record, changelog, owning team.**
- Repos consume a **pinned version**. Update = bump the pin. `~/.claude` copy forbidden.
- `delivery-gates` **asserts the repo-template version**, fails loud on mismatch.

---

## Added primitives (fix §6 — were missing)

Ordered by priority:

1. **Enforcement infra** (hooks + CI required-checks + branch-protection-as-code) — *already couche 0*
2. **Release mgmt**: semver, tags, auto changelog, release notes
3. **Supply-chain**: SLSA/provenance, artifact signing, pinned deps, license-policy enforce
4. **Secrets mgmt** (vault/SOPS) — ≠ secret *scanning*
5. **Env promotion + rollback + data-migrations** — delivery does not stop at the PR
6. **Dependency policy**: Renovate merge/pin rules, not just the file
7. **ADR-required CI check** on architectural diffs (≠ generating an ADR)

---

## Kill shots → fixes (summary)

| # | Kill shot v1 | Fix v2 |
|---|---|---|
| 1 | A skill cannot enforce the gate | Gate → couche 0 INFRA (hooks+CI+branch-protection). Skill = advisory |
| 2 | 5 non-portable scaffolds | `org-profile.yaml` + generators that refuse on mismatch |
| 3 | `/fenrir:deliver` multi-agent fragile | on-disk spec-artifact + deterministic routing script + checkpoints |
| 4 | Distribution = drift | 1 pinned semver plugin, owning team |
| 5 | 3 products in 1 | Split A(infra)/B(generators)/C(orchestration). **Ship A first** |

---

## Setup order (recommended)

1. **Couche 0 INFRA** + `repo-bootstrap` — without it, nothing enforces. This is the real mandate.
2. `org-profile.yaml` + 1 pilot generator (`iac-gen` on the current k8s stack)
3. `delivery-gates` + `security-review` (native wrap)
4. Subagents `architect` + `qa-tester`
5. `/fenrir:deliver` + `/fenrir:ship`
6. Release + supply-chain + secrets (added primitives)
