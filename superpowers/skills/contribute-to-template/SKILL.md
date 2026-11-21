---
name: contribute-to-template
description: >
  Detects local features worth contributing back to the project's copier template
  and opens upstream PRs for approved changesets. Auto-invokes when a significant
  feature or task finalizes — before or after wrapping up notable work — to surface
  improvements worth generalizing back to the template. All template references are
  resolved generically from .copier-answers.yml (_src_path); nothing is hardcoded.
---

# Contribute-to-Template Skill

Stateful, subagent-driven workflow that reviews commits since the last contribution
review, triages them into candidate changesets, analyzes each with a dedicated
subagent, then guides the user through approving and opening upstream PRs.

State is stored in `tmpl/contributions.md` (committed). Working files live in
`tmpl/tmp/` (gitignored). All tooling is in `tmpl/bin/` and `tmpl/.justfile`.

## Quick reference

```
just tmpl render          # render pristine template into tmpl/tmp/pristine/ (cached)
just tmpl triage          # gather commits → tmpl/tmp/triage-input.md
just tmpl diff <paths>    # diff specific paths: pristine vs local
just tmpl map             # print re-templatization substitution map
just tmpl status          # show last-reviewed commit and pending files
just tmpl reset           # wipe tmpl/tmp/* (keep .gitkeep)
```

---

## Workflow

### Phase 1 — Render + gather

1. Run `just tmpl render` to produce the pristine template baseline.
   Cached — re-running is a no-op unless `--force` is passed.
2. Run `just tmpl triage` to gather commits since `last_reviewed_commit`
   (from `tmpl/contributions.md`) into `tmpl/tmp/triage-input.md`.
   Override base: `BASE=<ref> just tmpl triage`.

### Phase 2 — Triage (you, the agent, author the candidates)

Read `tmpl/tmp/triage-input.md`. For each coherent theme you identify in the
commit log (especially merge commits — they represent completed PRs/features),
write a candidate file:

**`tmpl/tmp/triage/candidate-NN-<theme>.md`**

```markdown
---
theme: <short name, e.g. "docker-bake-hcl">
commits:
  - <sha> <oneline message>
files:
  - path/to/file1
  - path/to/dir/
rationale: >
  One sentence: what the change does and why it might generalize.
---

# Candidate NN: <theme>

<2–3 sentence description of the work and why it's potentially reusable.>
```

Rules for candidates:
- One candidate per coherent theme/feature. Prefer merge-commit boundaries.
- Only include files that are plausibly template-level (not project-specific data).
- The contribution process itself **is** contributable: the
  `contribute-to-template` skill (`superpowers/skills/contribute-to-template/`),
  its agents (`superpowers/agents/tmpl-*.md`), and the `tmpl/` tooling
  (`tmpl/bin/`, `tmpl/.justfile`, `tmpl/exclude-patterns`) are all fair game.
  Cursor and Claude discover them via symlinks in `.cursor/` and `.claude/`.
  When proposing such a candidate, exclude the working area (`tmpl/tmp/`) and
  treat `tmpl/contributions.md` as a fresh stub (only `last_reviewed_commit` is
  project-local state).
- Exclude: `docs/prd/`, `frontend/public/ingested/`, migrations, lockfiles,
  secrets, and the `tmpl/tmp/` working area (see `reference.md` for the full
  exclusion list).
- Candidates are cheap to write; err on the side of more rather than fewer —
  the analysis subagents apply the worthiness filter.

### Phase 3 — Per-candidate analysis (parallel subagents)

For each `tmpl/tmp/triage/candidate-NN-*.md`, launch the **`tmpl-candidate-analyzer`**
subagent (`superpowers/agents/tmpl-candidate-analyzer.md`), passing it the candidate
file path. Send all Task calls in a single message so they run in parallel.

The agent encapsulates the full procedure (upstream check → `git log -p` →
`just tmpl map` → worthiness criteria) and writes
`tmpl/tmp/analysis/candidate-NN-<theme>.md` in the format defined in `reference.md`.
You only need to orchestrate: one analyzer per candidate, then collect verdicts.

### Phase 4 — User review loop

Work through candidates **one at a time**. For each candidate:

**Step 4a — Render the full analysis as a chat message** before asking anything.
Format it like this (use markdown, not a code block):

---
**Candidate NN — `<theme>`** (`worthy` / `not-worthy`, confidence: `high/medium/low`)

**What it is:** _one sentence describing the change_

**Verdict:** _one paragraph justification — why it is or isn't worthy_

**Cleanup needed:**
- item 1
- item 2
_(or "None")_

**Files:** `path/a`, `path/b`, ...
**Commits:** `abc1234 message`, ...
**Re-templatization:** _which concrete values need replacing_

---

**Step 4b — Ask a single AskQuestion** with options that depend on whether cleanup is needed:

If cleanup is needed (cleanup plan is non-empty):
- **Cleanup and contribute** _(recommended — first option)_
- **Skip**

If no cleanup is needed:
- **Contribute** _(recommended — first option)_
- **Skip**

Do NOT offer an "approve as-is" option when cleanup is listed — the cleanup plan
exists precisely because it is needed before contributing.
Do NOT batch multiple candidates into one AskQuestion call.
Do NOT ask for a decision before the full analysis is visible.
Only move to the next candidate after the user responds.

For **Cleanup and contribute**: launch the **`tmpl-contribution-stager`** subagent
(`superpowers/agents/tmpl-contribution-stager.md`), passing it the candidate and
analysis file paths.
It clones the template (`_src_path` from `.copier-answers.yml`) into
`tmpl/tmp/contrib/candidate-NN/`, branches `contrib/<theme>`, applies the cleanup
plan + re-templatization, greps to verify no concrete values remain, and reports
back for user confirmation. It stops before committing — the PR is opened in Phase 5.

For **Contribute** (no cleanup) or after cleanup confirmation: open the PR.

### Phase 5 — Open PR

In the template clone at `tmpl/tmp/contrib/<candidate>/`:

```bash
# Parse template repo from .copier-answers.yml
TEMPLATE_URL=$(sed -n 's/^_src_path:[[:space:]]*//p' .copier-answers.yml | tr -d "'\"")
# Derive owner/repo for gh (strip ssh/https prefix)
REPO=$(echo "$TEMPLATE_URL" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')

git add -A
git commit -m "feat: <short description of the contribution>"
git push origin contrib/<theme>
gh pr create \
  --repo "$REPO" \
  --title "feat: <short description>" \
  --body "$(cat)" <<'EOF'
<use PR template from reference.md>
EOF
```

### Phase 6 — Finalize

After all candidates are processed (skip/contribute/PR):

1. Update `last_reviewed_commit` in `tmpl/contributions.md` to current `HEAD`.
   Do not append a review log, PR links, or upstream references — this file is
   project-local bookkeeping; only the commit pointer matters.
2. Commit: `git add tmpl/contributions.md && git commit -m "chore(tmpl): mark contribution review through <sha>"`
3. Run `just tmpl reset` to wipe the `tmpl/tmp/` working area so the next review starts clean.

---

## Notes

- `just tmpl render` takes ~45s (copier clones the template); the pristine is cached
  for the session — only re-render with `--force` if the template has new commits.
- If `copier update` prompts for new questions (template has new variables), run it
  manually in the worktree and answer interactively.
- For large triage windows, prioritize merge commits — they represent completed,
  reviewable features and make the best contribution candidates.

## Additional resources

- Exclusion list, worthiness criteria, and PR template: see [reference.md](reference.md)
