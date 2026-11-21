# General Development Guidelines

This is a monorepo. Each top-level directory is a "layer" with its own tooling and (where relevant) its own `AGENTS.md`.

## Layers
- `frontend/` — React + Vite + TanStack (see `frontend/AGENTS.md`)
- `backend/`  — Django + Ninja (see `backend/AGENTS.md`)
- `local/`    — `docker-compose` dev environment (`just local up`, `just local test-unit`, `just local manage`)
- `deploy/`   — Terraform infra for  (`just deploy check`)

## Prerequisites

- `just`, `pnpm`, `uv`, `docker`
- `age` (only if you work with the development bundle — see below)
- `terraform` (only if you touch `deploy/`)

## Common commands (from repo root)

Each layer's justfile is mounted as a submodule, so commands run as
`just <layer> <recipe>`. Run `just` to list every recipe across all layers.

- `just local up`         — bring up the docker-compose stack
- `just local down`       — stop the stack
- `just local test-unit`  — backend unit tests (pytest, in the container)
- `just local test-e2e`   — backend e2e tests (stack must be up)
- `just frontend test`    — frontend unit tests (Vitest)
- `just frontend e2e`     — Playwright e2e against the running stack
- `just backend check`    — Django system checks (host, via uv)
- `just deploy check`     — `terraform init` + `validate` against `deploy/terraform/`

Each layer ships its end-to-end suite under `<layer>/tests/e2e/`. Place new
e2e tests in the layer they exercise; reserve `<layer>/tests/` (no `e2e`
subfolder) for true unit tests that don't need a running stack.

## Development bundle

`just bundle …` manages an encrypted archive (`bundle.encrypted`) that is
committed to the repo. It holds secrets used during the development process that
do **not** pertain to the application or any of its environments. The files it
contains are shared between developers but are committed **only** in encrypted
form — their plaintext never enters git.

- `just bundle open`       — decrypt the bundle into your working tree
- `just bundle update`     — re-encrypt the bundle from your local files
- `just bundle add <path>` — add a path to the bundle, then re-encrypt
- `just bundle keygen`     — create your `age` identity, register its public key in `.age-recipients`, and print the private key once (save it in 1Password)

Decryption uses an `age` identity at `$AGE_IDENTITY` (default
`~/.config/age/keys.txt`); it is never committed. Public keys live in
`.age-recipients` (committed). The manifest of bundled paths is mirrored into
`.gitignore` so plaintext stays untracked.

A pre-commit hook (configured in `.pre-commit-config.yaml`, installed by
`just setup`) re-encrypts the bundle automatically whenever a bundled file
changes.

First time in a fresh clone: run `just setup`, then `just bundle keygen` (save the
printed private key in the `multiplayer-medico` 1Password vault and
commit `.age-recipients`), then `just bundle open`.

## Code style

- Declare code top-down, in order of appearance: main entrypoints and public exports at the top of a file, auxiliary helpers and classes below in order of first use. Avoid forward references and forward declarations.

## Before opening a PR

- `just frontend test` and `just local test-unit` pass
- `pnpm lint` passes in `frontend/` (unused imports, TS errors, etc. fail CI)
- New backend code has tests; new frontend components follow existing patterns
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `chore:`…) — `semantic-release` consumes them

## Do not touch

- Lockfiles (`pnpm-lock.yaml`, `uv.lock`) — let the package manager update them
- `deploy/terraform/webapp/` modules — provided upstream; `copier update` overwrites them
- `.copier-answers*.yml` — managed by `copier update`
- Django migrations — flag the need; a human will create them

## Workflow

- Linear tasks: use the branch name suggested by Linear
- When running in a worktree, name the agent tab `[ISSUE-ID] Issue title`
