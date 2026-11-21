# Deploy e2e tests

This layer's "e2e" is a Terraform sanity check (`terraform init && terraform
validate`) run against the configuration. It runs from the project root with
`just deploy e2e` (see `deploy/.justfile`).

The tricky bit is that the AWS configuration uses a Terraform Cloud
backend, which `terraform init` would normally try to authenticate against.
We avoid needing TFC credentials in CI by dropping `local_state_override.tf`
into `deploy/terraform/` for the duration of the run — Terraform automatically
merges any `*_override.tf` file into the configuration and our override block
swaps the backend to a local file. The override is removed during teardown.

## Local validate vs real deploys

- The override file lives under `deploy/tests/e2e/` so the validate check can
  run locally and in CI without Terraform Cloud credentials.
- Real deploys still go through `just deploy check` (or `terraform plan/apply`
  from `deploy/terraform/`), which uses the real backend.

## When the layer has no terraform yet

`just deploy e2e` early-returns with a message when `deploy/terraform/`
contains no `*.tf` files (currently the case for the Azure preview).
