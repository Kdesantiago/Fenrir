# Couche 0 — Azure DevOps branch policy = the real merge gate on an Azure repo.
# A skill cannot block; this build-validation + reviewer policy does. `terraform apply` to arm it.
# Provider: microsoft/azuredevops.

terraform {
  required_providers {
    azuredevops = {
      source  = "microsoft/azuredevops"
      version = "~> 1.0"
    }
  }
}

variable "project_id" { type = string }
variable "repository_id" { type = string }
variable "build_definition_id" {
  type        = number
  description = "ID of the pipeline created from templates/ci/azure-pipelines.yml"
}
variable "branch" {
  type    = string
  default = "refs/heads/main"
}

# Required PR build validation — the pipeline must pass before merge.
resource "azuredevops_branch_policy_build_validation" "ci" {
  project_id = var.project_id
  enabled    = true
  blocking   = true # blocking = the actual gate

  settings {
    display_name        = "required-checks (test/coverage/sast/build)"
    build_definition_id = var.build_definition_id
    valid_duration      = 720

    scope {
      repository_id  = var.repository_id
      repository_ref = var.branch
      match_type     = "Exact"
    }
  }
}

# Minimum reviewers + no self-approval.
resource "azuredevops_branch_policy_min_reviewers" "reviewers" {
  project_id = var.project_id
  enabled    = true
  blocking   = true

  settings {
    reviewer_count                         = 1
    submitter_can_vote                     = false
    last_pusher_cannot_approve             = true
    allow_completion_with_rejects_or_waits = false
    on_push_reset_approved_votes           = true

    scope {
      repository_id  = var.repository_id
      repository_ref = var.branch
      match_type     = "Exact"
    }
  }
}

# All PR comments must be resolved before merge.
resource "azuredevops_branch_policy_comment_resolution" "comments" {
  project_id = var.project_id
  enabled    = true
  blocking   = true

  settings {
    scope {
      repository_id  = var.repository_id
      repository_ref = var.branch
      match_type     = "Exact"
    }
  }
}
