# Couche 0 — the ONLY thing that truly blocks a non-conforming merge to `main`.
# A skill cannot block; this branch-protection rule does. Fenrir DOGFOODS it on its own repo.
# Arm it: `terraform init && terraform apply` (needs a GitHub token with repo admin), OR the
# equivalent `gh api` call in PUBLISHING.md ("Arming branch-protection"). Available only once
# the repo is public or on GitHub Pro/Team.
#
# Solo-maintainer tuned: PRs are required (no direct push to main) and CI must be green, but
# 0 approvals are needed (a lone maintainer can't self-approve) and code-owner review is OFF.
# A team should raise required_approving_review_count to >=1 and turn code-owner reviews on.

terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

variable "repository" {
  type    = string
  default = "Fenrir"
}

variable "branch" {
  type    = string
  default = "main"
}

# MUST match the job `name:` (status context) values in .github/workflows/*.yml.
variable "required_checks" {
  type = list(string)
  default = [
    "dashboard (lint + type + test)",
    "lint + type + test hooks",
    "validate manifests",
    "delivery-trace",
  ]
}

resource "github_branch_protection" "main" {
  repository_id = var.repository
  pattern       = var.branch

  required_status_checks {
    strict   = true
    contexts = var.required_checks
  }

  required_pull_request_reviews {
    required_approving_review_count = 0     # solo maintainer; raise to >=1 for a team
    require_code_owner_reviews      = false # no CODEOWNERS at root yet; enable when added
    dismiss_stale_reviews           = true
  }

  enforce_admins                  = true
  require_conversation_resolution = true
  required_linear_history         = true
  allows_force_pushes             = false
  allows_deletions                = false
}

# Auto-delete the head branch on merge, so merged branches don't pile up on the remote.
# Set as a repo setting (the `github_branch_protection` resource above can't carry it, and
# managing a full `github_repository` resource here would over-claim ownership of the repo).
# This setting lives OUTSIDE terraform state (imperative), so `terraform plan` won't reconcile
# it — treat it as known out-of-state config:
#
#   gh api -X PATCH repos/<owner>/<repo> -f delete_branch_on_merge=true
#
# `repo-bootstrap` runs this when arming the gate. NOTE: it deletes the REMOTE branch only (and
# GitHub skips a branch that another open PR still targets), so `/fenrir:ship` also deletes the
# LOCAL branch after merge (a squash-merge isn't detected by `git branch --merged`). Sweep stale
# locals (anchored to the REAL default branch, whole-name match, safe `-d` only):
#   DEF=$(git symbolic-ref --short refs/remotes/origin/HEAD | cut -d/ -f2)
#   git fetch --prune && git branch --merged "$DEF" | grep -vE "^[* ]+($DEF|HEAD)$" | xargs -r git branch -d
