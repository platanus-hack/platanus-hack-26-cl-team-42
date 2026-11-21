// Test-only override that swaps the configured backend (e.g. Terraform Cloud)
// for a local file backend so `terraform init && terraform validate` can run
// in CI without cloud credentials.
//
// Terraform merges any file ending in `_override.tf` over the rest of the
// configuration (https://developer.hashicorp.com/terraform/language/files/override).
// The redeclared `terraform {}` block here keeps `required_providers` intact
// while replacing the original `cloud {}` block with `backend "local" {}`.
//
// This file is copied into `deploy/terraform/` by `just e2e` (deploy/.justfile)
// for the duration of the validate run and removed in the cleanup trap. It is
// .gitignored so accidental commits inside generated projects are caught.

terraform {
  backend "local" {}
}
