#!/usr/bin/env bash
# render-template.sh — render a pristine copy of the copier template into tmpl/tmp/pristine/.
#
# The rendered tree is cached: re-running is a no-op unless --force is passed.
# Template URL and VCS ref are always read from .copier-answers.yml (_src_path, _commit).
#
# Usage:
#   tmpl/bin/render-template.sh           # use cached render if present
#   tmpl/bin/render-template.sh --force   # re-render even if cache exists
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ANSWERS_FILE="$REPO_ROOT/.copier-answers.yml"
PRISTINE_DIR="$REPO_ROOT/tmpl/tmp/pristine"
FORCE=false

for arg in "$@"; do
  [[ "$arg" == "--force" ]] && FORCE=true
done

if [[ ! -f "$ANSWERS_FILE" ]]; then
  echo "ERROR: .copier-answers.yml not found at $REPO_ROOT" >&2
  exit 1
fi

TEMPLATE_URL="$(sed -n 's/^_src_path:[[:space:]]*//p' "$ANSWERS_FILE" | tr -d "'\"")"
if [[ -z "$TEMPLATE_URL" ]]; then
  echo "ERROR: _src_path not found in $ANSWERS_FILE" >&2
  exit 1
fi

if [[ -d "$PRISTINE_DIR" && "$FORCE" == false ]]; then
  echo "==> Pristine template already rendered at tmpl/tmp/pristine/ (use --force to re-render)"
  exit 0
fi

echo "==> Rendering pristine template from $TEMPLATE_URL ..."
rm -rf "$PRISTINE_DIR"
mkdir -p "$PRISTINE_DIR"

cp "$ANSWERS_FILE" "$PRISTINE_DIR/.copier-answers.yml"

cd "$PRISTINE_DIR"
if ! uvx copier copy \
       --overwrite \
       --trust \
       --defaults \
       --answers-file .copier-answers.yml \
       --vcs-ref=HEAD \
       "$TEMPLATE_URL" \
       . \
       2>&1; then
  echo "ERROR: copier copy failed." >&2
  exit 1
fi
cd "$REPO_ROOT"

echo "==> Done. Pristine template is at tmpl/tmp/pristine/"
