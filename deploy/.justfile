[working-directory: 'terraform']
check:
    #!/bin/bash
    set -e
    if [ ! -d .terraform ]; then
        echo "Initializing Terraform..."
        terraform init -no-color || (rm -rf .terraform && exit 1)
    fi
    echo "Validating Terraform..."
    terraform validate -no-color

# End-to-end check: terraform init + validate against the configuration.
#
# Runs `terraform init && terraform validate` against the rendered
# configuration with a local-state backend override so it works in CI without
# Terraform Cloud credentials. The override file is shipped under
# `deploy/tests/e2e/local_state_override.tf` and copied in/removed for the
# duration of the run. No-op (with a warning) when the layer has no `*.tf`
# files (e.g. providers that aren't fleshed out yet).
e2e:
    #!/bin/bash
    set -euo pipefail
    cd terraform
    if ! ls *.tf >/dev/null 2>&1; then
        echo ">> deploy/e2e: no .tf files in $(pwd), skipping"
        exit 0
    fi
    override_src="../tests/e2e/local_state_override.tf"
    override_dst="local_state_override.tf"
    if [ ! -f "$override_src" ]; then
        echo "deploy/e2e: missing override file at $override_src" >&2
        exit 1
    fi
    cleanup() {
        rm -f "$override_dst"
        rm -rf .terraform .terraform.lock.hcl terraform.tfstate terraform.tfstate.backup
    }
    trap cleanup EXIT
    cp "$override_src" "$override_dst"
    echo "deploy/e2e: terraform init"
    terraform init -no-color -input=false
    echo "deploy/e2e: terraform validate"
    terraform validate -no-color
