#!/usr/bin/env bash
# candidate-diff.sh — diff specific paths between the pristine template and the local project.
#
# Requires tmpl/tmp/pristine/ to exist (run render-template.sh first).
# Outputs a unified diff to stdout so callers can redirect or pipe as needed.
#
# Usage:
#   tmpl/bin/candidate-diff.sh <path> [<path> ...]
#
# Examples:
#   tmpl/bin/candidate-diff.sh backend/docker/Dockerfile backend/pyproject.toml
#   tmpl/bin/candidate-diff.sh docs/ justfile
#
# Exit codes: 0 = no differences, 1 = differences found, 2 = error
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
PRISTINE_DIR="$REPO_ROOT/tmpl/tmp/pristine"
STAGE_DIR="$(mktemp -d)"

cleanup() { rm -rf "$STAGE_DIR"; }
trap cleanup EXIT

if [[ $# -eq 0 ]]; then
  echo "Usage: candidate-diff.sh <path> [<path> ...]" >&2
  exit 2
fi

if [[ ! -d "$PRISTINE_DIR" ]]; then
  echo "ERROR: tmpl/tmp/pristine/ not found. Run 'just tmpl render' first." >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# Noise exclusions (macOS git diff --no-index lacks --exclude; use rsync first)
# Patterns are read from tmpl/exclude-patterns (gitignore-style, one per line).
# ---------------------------------------------------------------------------
EXCLUDE_FILE="$REPO_ROOT/tmpl/exclude-patterns"
if [[ ! -f "$EXCLUDE_FILE" ]]; then
  echo "ERROR: tmpl/exclude-patterns not found at $REPO_ROOT" >&2
  exit 2
fi
RSYNC_EXCLUDES=(--exclude-from="$EXCLUDE_FILE")

mkdir -p "$STAGE_DIR/pristine" "$STAGE_DIR/local"

for rel_path in "$@"; do
  pristine_src="$PRISTINE_DIR/$rel_path"
  local_src="$REPO_ROOT/$rel_path"

  # Copy pristine side (may not exist if path is entirely local-only)
  if [[ -e "$pristine_src" ]]; then
    if [[ -d "$pristine_src" ]]; then
      rsync -a "${RSYNC_EXCLUDES[@]}" "$pristine_src/" "$STAGE_DIR/pristine/$rel_path/"
    else
      mkdir -p "$(dirname "$STAGE_DIR/pristine/$rel_path")"
      rsync -a "${RSYNC_EXCLUDES[@]}" "$pristine_src" "$STAGE_DIR/pristine/$rel_path"
    fi
  fi

  # Copy local side (may not exist if path was removed locally)
  if [[ -e "$local_src" ]]; then
    if [[ -d "$local_src" ]]; then
      rsync -a "${RSYNC_EXCLUDES[@]}" "$local_src/" "$STAGE_DIR/local/$rel_path/"
    else
      mkdir -p "$(dirname "$STAGE_DIR/local/$rel_path")"
      rsync -a "${RSYNC_EXCLUDES[@]}" "$local_src" "$STAGE_DIR/local/$rel_path"
    fi
  fi
done

# git diff --no-index exits 1 when differences exist (expected).
set +e
(
  cd "$STAGE_DIR"
  git diff --no-index --stat --patch pristine local
)
DIFF_EXIT=$?
set -e

if [[ $DIFF_EXIT -gt 1 ]]; then
  echo "ERROR: git diff --no-index failed unexpectedly (exit $DIFF_EXIT)" >&2
  exit 2
fi

exit $DIFF_EXIT
