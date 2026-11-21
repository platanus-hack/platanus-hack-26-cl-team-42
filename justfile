# Project shortcuts — run from the repo root.
#
# Each layer's justfile is mounted as a submodule, so its recipes run from
# the layer directory. For example:
#
#   just local up          # bring up the docker-compose stack
#   just backend test      # run backend tests
#   just frontend e2e      # run Playwright e2e
#   just deploy check       # terraform init + validate

mod backend
mod frontend
mod local
mod deploy
mod tmpl
mod bundle

# List available recipes, including each layer's
default:
    @just --list --list-submodules

# One-time developer setup: install bundle tooling and git pre-commit hooks
setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v age-keygen >/dev/null 2>&1; then
        if command -v brew >/dev/null 2>&1; then
            brew install age
        elif command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update
            sudo apt-get install -y age
        else
            echo "error: age not found — install from https://github.com/FiloSottile/age" >&2
            exit 1
        fi
    fi
    if command -v pre-commit >/dev/null 2>&1; then
        pre-commit install
    else
        uvx pre-commit install
    fi
