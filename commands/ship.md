---
description: Open a conventional-commit PR linking the ADR + spec artifact, run delivery-gates for fast local feedback, then surface CI required-check status — does NOT enforce; branch-protection (infra) decides the merge.
---

# /fenrir:ship

Open the PR and surface CI status. This command **prepares and reports — it does not gate**. The merge is blocked or allowed by **branch-protection-as-code + CI required status checks** (couche 0 infra), not by `/fenrir:ship`. Anything below is local feedback and PR plumbing; the authoritative decision happens in infra after the PR exists.

## 1. Preconditions
- Clean-ish working tree on a feature branch (not the default branch). If on default branch, STOP.
- Confirm `org-profile.yaml` at root. Locate the artifacts to link: the spec at `docs/specs/<slug>.md` and the ADR at `docs/adr/NNNN-*.md` (passed in by `/fenrir:deliver`, or discovered from the branch's diff). If an architectural / risk-path diff has no ADR, WARN loudly — branch-protection's ADR-required check will likely reject it.

## 2. Local fast feedback (advisory, before pushing)
- Run `delivery-gates` (lint + type + test + coverage on the diff) for quick pass/fail. This is FAST FEEDBACK, not a gate. If it fails, surface the failures and ask before proceeding — but note the real block is CI, not this step.

## 3. Sync docs (doc-keeper)
Delegate to the `doc-keeper` agent: update `CHANGELOG.md` + the affected README(s)/API-docs to match the diff so docs are never left stale. `doc-keeper` checks for an existing `[Unreleased]` entry and skips it, so if `/fenrir:deliver` already synced this diff this is a genuine no-op (no duplicate entries). This is what makes the reviewer's "changelog entry present" check pass and keeps docs always-up-to-date on every ship (light or full path).

## 4. Automated pre-PR review (the review automator — /fenrir:ship-driven)
This is the automatic LLM review before any PR exists. Runs in the main thread (which can invoke slash commands; a subagent cannot).
- Run `/code-review` on the working diff → capture its correctness/security findings as text.
- Delegate to the `reviewer` subagent, passing those findings + the diff → it adds org PR-hygiene (conventional title, ADR link for risk-path diffs, changelog entry, no secrets, profile respected) and returns a verdict block. Parse its `Verdict:` line (`READY | BLOCK`).
- **If verdict = BLOCK** (any unresolved critical/high): STOP — do NOT open the PR. Report findings and ask. The review is advisory, but `/fenrir:ship` chooses not to publish a known-bad PR.
- Record any recurring/confirmed finding to delivery-memory `lessons.md` (via `memory-keeper`) so the same class is caught earlier next time.

## 5. Build the conventional-commit PR
- Derive a **conventional-commit title**: `type(scope): subject` (feat|fix|chore|docs|refactor|test|perf|build|ci), inferred from the diff's intent.

### 5a. No-CLI path (FIRST-class — no `gh`, no `az` required)
This is the default, zero-cloud-dependency way to open a PR. It needs only `git`.
1. Push and set upstream: `git push -u origin <branch>`.
2. Derive the PR-create URL from the remote so you can open it in the browser:
   - Get the remote: `git remote get-url origin`.
   - GitHub: an `ssh` remote `git@github.com:ORG/REPO.git` or `https` remote `https://github.com/ORG/REPO.git` → open `https://github.com/ORG/REPO/compare/<default>...<branch>?expand=1`. (After the first `git push -u`, GitHub also prints this "Create a pull request" URL directly in the push output — use that line if present.)
   - Azure DevOps: remote `https://dev.azure.com/ORG/PROJECT/_git/REPO` → open `https://dev.azure.com/ORG/PROJECT/_git/REPO/pullrequestcreate?sourceRef=<branch>&targetRef=<default>`.
3. In the browser "Compare & pull request" page, paste the conventional-commit **title** and the **body** (artifacts + US ids, per below). Submit to open the PR.
4. **Arming branch-protection without terraform:** the merge gate is normally armed by `terraform apply` on `templates/branch-protection.tf` (see the `repo-bootstrap` skill). To arm it without terraform and without `gh`/`az`, call the platform REST API with a token directly — GitHub: `PUT /repos/{owner}/{repo}/branches/{branch}/protection` with the CI required-check names (an `Authorization: Bearer $GITHUB_TOKEN` curl); Azure DevOps: the branch-policy REST API. The required-check names MUST equal the CI job names. This is how the gate gets armed on a fresh clone with only a token.

### 5b. CLI accelerators (OPTIONAL — only if `gh`/`az` are installed and authed)
If you have the platform CLI it's faster, but it is **not required** — 5a is the supported path.
- Push the branch.
- Open the PR with the platform CLI:
  - GitHub: `gh pr create --title "<conventional title>" --body "<body>"`
  - Azure DevOps: `az repos pr create --title "<conventional title>" --description "<body>"`

- **PR body must link the artifacts** (both paths): the spec (`docs/specs/<slug>.md`), the ADR (`docs/adr/NNNN-*.md`) when present, a changelog reference, the **US ids this PR delivers** (`us-N` — required so the `delivery-trace` check passes), and a short summary of the deterministic route taken. These let reviewers and the ADR-/delivery-trace CI checks resolve their inputs.
- **Move the delivered US to `review`** now the PR is open: `python -m backend.cli move --kind story --id <us> --status review` (from `dashboard/`).

## 6. Surface CI required-check status
- **No-CLI path (FIRST-class):** CI status is visible **in the browser** — open the PR page (the URL from step 5a) and read the checks panel / "Checks" tab; the merge button reflects the branch-protection state. No `gh`/`az` needed to *see* status; the merge decision is enforced by branch-protection regardless of how you view it.
- **CLI accelerators (optional):** if `gh`/`az` are installed, poll the required checks from the terminal and report their status, do not interpret them as your own gate:
  - GitHub: `gh pr checks <pr>` (and `gh pr view <pr> --json mergeStateStatus,reviewDecision`)
  - Azure: `az repos pr show --id <pr>` / pipeline status
- Report each required check (name → pending/pass/fail) and the branch-protection merge state.
- **After the PR merges, close its US:** move every US the PR delivered to `done` (`python -m backend.cli move --kind story --id <us> --status done`). A merged PR that leaves its US in `review`/`in_progress` is stale board state — don't.
- **After the PR merges, delete the branch — remote AND local, SAFELY.**
  - **Stacked PRs first:** if other open PRs target this branch (`gh pr list --base <branch> --state open`), retarget them to the default branch (`gh pr edit <child> --base <default>`) BEFORE deleting — `gh ... --delete-branch` *closes* dependent PRs rather than retargeting them ([cli#1168](https://github.com/cli/cli/issues/1168)).
  - **Merge + remote delete:** `gh pr merge <pr> --squash --delete-branch` (the repo's `delete_branch_on_merge` setting is the backstop for the remote).
  - **Local delete, guarded:** `git switch <default> && git pull --ff-only`, then `git branch -d <branch>`. A squash-merge isn't recognized by `git branch --merged`, so `-d` will refuse; only then force — but FIRST confirm there's no unpushed work: `git log @{u}.. --oneline` (or `git cherry`) must be empty before `git branch -D <branch>`. **Never blind force-delete** — `-D` discards unmerged local commits. Sweep stragglers: `git fetch --prune`.

## 7. Output — state the boundary explicitly
Report:
- PR URL + conventional title.
- Linked artifacts (spec, ADR, changelog).
- Local `delivery-gates` result (advisory).
- Pre-PR review verdict (`READY | BLOCK`) + any blocking findings.
- CI required-check status + merge state.

End with the explicit statement: **the merge is gated by branch-protection + CI required-checks (infra), not by `/fenrir:ship`.** This command surfaces status; infra enforces it.
