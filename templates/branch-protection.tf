# Couche 0 — the ONLY thing that truly blocks a non-conforming merge.
# A skill cannot block; this branch-protection rule does. `terraform apply` to arm it.
# GitHub variant shown. For Azure DevOps, use the azuredevops_branch_policy_* resources instead.

terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

variable "repository" { type = string }
variable "branch" {
  type    = string
  default = "main"
}

# Required status checks MUST match the job `name:` values in templates/ci/required-checks.yml.
# `test` includes the coverage gate (pytest --cov --cov-fail-under), so there is no separate coverage check.
variable "required_checks" {
  type    = list(string)
  default = ["test", "sast", "build"]
}

resource "github_branch_protection" "main" {
  repository_id = var.repository
  pattern       = var.branch

  required_status_checks {
    strict   = true
    contexts = var.required_checks
  }

  required_pull_request_reviews {
    required_approving_review_count = 1
    require_code_owner_reviews      = true
    dismiss_stale_reviews           = true
  }

  enforce_admins                  = true
  require_conversation_resolution = true
  required_linear_history         = true
  allows_force_pushes             = false
  allows_deletions                = false
}
