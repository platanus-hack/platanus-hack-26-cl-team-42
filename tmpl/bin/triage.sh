#!/usr/bin/env bash
# triage.sh — gather commit history since the last reviewed commit into tmpl/tmp/triage-input.md.
#
# The base commit is read from tmpl/contributions.md frontmatter (last_reviewed_commit).
# If empty (first run) it falls back to the repository's initial commit, with a warning.
# Override with: BASE=<ref> tmpl/bin/triage.sh
#
# Output: tmpl/tmp/triage-input.md — a structured markdown document for the triage
# subagent to read and author candidate-NN-*.md files from.
#
# Usage:
#   tmpl/bin/triage.sh
#   BASE=abc1234 tmpl/bin/triage.sh
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
CONTRIBUTIONS="$REPO_ROOT/tmpl/contributions.md"
TRIAGE_DIR="$REPO_ROOT/tmpl/tmp/triage"
OUT="$REPO_ROOT/tmpl/tmp/triage-input.md"

# ---------------------------------------------------------------------------
# Resolve base commit
# ---------------------------------------------------------------------------

if [[ -n "${BASE:-}" ]]; then
  BASE_COMMIT="$(git -C "$REPO_ROOT" rev-parse "$BASE")"
  BASE_SOURCE="override (BASE env)"
elif [[ -f "$CONTRIBUTIONS" ]]; then
  RAW="$(sed -n 's/^last_reviewed_commit:[[:space:]]*//p' "$CONTRIBUTIONS" | tr -d "'\"")"
  if [[ -n "$RAW" && "$RAW" != '""' && "$RAW" != "''" ]]; then
    BASE_COMMIT="$(git -C "$REPO_ROOT" rev-parse "$RAW")"
    BASE_SOURCE="tmpl/contributions.md"
  else
    echo "WARNING: last_reviewed_commit is empty in contributions.md — using initial commit as base." >&2
    BASE_COMMIT="$(git -C "$REPO_ROOT" rev-list --max-parents=0 HEAD)"
    BASE_SOURCE="initial commit (first run)"
  fi
else
  echo "ERROR: tmpl/contributions.md not found." >&2
  exit 1
fi

HEAD_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"

if [[ "$BASE_COMMIT" == "$HEAD_COMMIT" ]]; then
  echo "INFO: No new commits since last review ($BASE_COMMIT). Nothing to triage." >&2
  exit 0
fi

RANGE="${BASE_COMMIT}..${HEAD_COMMIT}"
COMMIT_COUNT="$(git -C "$REPO_ROOT" rev-list --count "$RANGE")"

echo "==> Triage range: $RANGE ($COMMIT_COUNT commits, base from: $BASE_SOURCE)"

# ---------------------------------------------------------------------------
# Gather data
# ---------------------------------------------------------------------------

mkdir -p "$TRIAGE_DIR"

{
  cat <<EOF
---
base_commit: $BASE_COMMIT
head_commit: $HEAD_COMMIT
base_source: $BASE_SOURCE
commit_count: $COMMIT_COUNT
---

# Triage Input

This file is the raw material for the triage agent. Read it and author
\`tmpl/tmp/triage/candidate-NN-<theme>.md\` files — one per proposed contribution
candidate — using the format described in the skill.

---

## Commit log (oneline)

\`\`\`
EOF
  git -C "$REPO_ROOT" log --oneline "$RANGE"
  cat <<'EOF'
```

---

## Merge commits (PRs — typically coherent feature changesets)

```
EOF
  git -C "$REPO_ROOT" log --oneline --merges "$RANGE" || echo "(none)"
  cat <<'EOF'
```

---

## Files changed per commit (git log --stat)

```
EOF
  git -C "$REPO_ROOT" log --stat --format="--- %H %s" "$RANGE"
  cat <<'EOF'
```

---

## Aggregate file-change summary (git diff --stat)

```
EOF
  git -C "$REPO_ROOT" diff --stat "$BASE_COMMIT" "$HEAD_COMMIT"
  echo '```'
} > "$OUT"

echo "==> Triage input written to tmpl/tmp/triage-input.md ($COMMIT_COUNT commits)"
echo "    Next: read that file (and the skill instructions) to author candidate files"
echo "    in tmpl/tmp/triage/candidate-NN-<theme>.md"
