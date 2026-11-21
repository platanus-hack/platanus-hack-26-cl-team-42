#!/usr/bin/env bash
# answers-map.sh — emit the re-templatization substitution map derived from .copier-answers.yml.
#
# Reads all non-private (non-underscore) keys from the copier answers file and
# prints a markdown table: concrete project value -> Jinja2 template variable.
# Use this output when applying a candidate changeset to the template repo to
# identify every literal value that must be replaced with a Jinja2 expression.
#
# Usage:
#   tmpl/bin/answers-map.sh
#   tmpl/bin/answers-map.sh --raw    # emit KEY=VALUE pairs instead of a table
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
ANSWERS_FILE="$REPO_ROOT/.copier-answers.yml"
RAW_MODE=false

for arg in "$@"; do
  [[ "$arg" == "--raw" ]] && RAW_MODE=true
done

if [[ ! -f "$ANSWERS_FILE" ]]; then
  echo "ERROR: .copier-answers.yml not found at $REPO_ROOT" >&2
  exit 1
fi

# Parse all non-private (non-_-prefixed) key: value pairs.
# Handles both bare values and quoted strings.
declare -a KEYS=()
declare -a VALUES=()

while IFS= read -r line; do
  # Skip private keys (_commit, _src_path, etc.) and comments/blank lines
  [[ "$line" =~ ^_  ]] && continue
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${line// }" ]] && continue

  if [[ "$line" =~ ^([a-zA-Z][a-zA-Z0-9_]*):[[:space:]]*(.*) ]]; then
    key="${BASH_REMATCH[1]}"
    raw_value="${BASH_REMATCH[2]}"
    # Strip surrounding quotes
    value="${raw_value#\'}"
    value="${value%\'}"
    value="${value#\"}"
    value="${value%\"}"
    # Skip empty values — nothing to substitute
    [[ -z "$value" ]] && continue
    KEYS+=("$key")
    VALUES+=("$value")
  fi
done < "$ANSWERS_FILE"

if [[ "$RAW_MODE" == true ]]; then
  for i in "${!KEYS[@]}"; do
    echo "${KEYS[$i]}=${VALUES[$i]}"
  done
  exit 0
fi

# Markdown table
cat <<'EOF'
## Re-templatization map

When contributing a changeset back to the template, replace every occurrence of
the concrete project values below with the corresponding Jinja2 expression.

| Concrete value (this project) | Jinja2 template variable |
|---|---|
EOF

for i in "${!KEYS[@]}"; do
  echo "| \`${VALUES[$i]}\` | \`{{ ${KEYS[$i]} }}\` |"
done

cat <<'EOF'

**Boolean / conditional example:** if a code block is Vue-specific, wrap it:
`{% if frontend_framework == 'vue' %}...{% endif %}`

**Grep before committing:** run `grep -r '<value>' .` in the template clone
for each row above to catch any missed occurrences before opening the PR.
EOF
