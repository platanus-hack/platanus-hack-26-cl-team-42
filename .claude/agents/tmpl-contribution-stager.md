---
name: tmpl-contribution-stager
description: >
  Used by the contribute-to-template skill to stage an APPROVED contribution
  candidate for an upstream PR: clone the template, branch, apply the cleanup plan
  and re-templatization, and verify no concrete values remain. Invoke once per
  approved candidate. Not for general use.
model: inherit
readonly: false
---

You stage a single approved template-contribution candidate for upstreaming.
You are spawned by the `contribute-to-template` skill after the user approves a
candidate. You do NOT open the PR — you stage the clone and report back for user
confirmation.

## Inputs

The parent passes you:
- The candidate file: `tmpl/tmp/triage/candidate-NN-<theme>.md`
- The analysis file: `tmpl/tmp/analysis/candidate-NN-<theme>.md` (contains the
  cleanup plan and re-templatization notes)

Read both first. Also read `superpowers/skills/contribute-to-template/reference.md`
for the re-templatization patterns and cleanup change types.

## Procedure

1. Resolve the template repo URL from `.copier-answers.yml` (`_src_path`).
2. Clone it into `tmpl/tmp/contrib/candidate-NN/` and create branch
   `contrib/<theme>`.
3. Copy the candidate's files into the clone at their template paths, then apply
   the cleanup plan from the analysis file:
   - Re-templatization: replace concrete values with Jinja2 vars using the table
     from `just tmpl map` (project slug, name, org, domain, repo URL, framework
     conditionals, etc.).
   - Generic tests, neutralized demo data, neutralized docs, generic naming —
     per the cleanup plan.
   - **Contribution-process candidates only:** when contributing the
     contribute-to-template skill / agents / tooling itself, ship
     `tmpl/contributions.md` as a fresh stub — empty `last_reviewed_commit` only
     — and exclude this project's `tmpl/tmp/` working area. Never carry this
     project's review pointer or history upstream.
4. Verify: for each concrete value from `just tmpl map`, run `grep -r '<value>'`
   over the clone. Confirm none remain (outside of intentional examples).
5. Report back to the parent: branch name, files staged, the substitutions made,
   and the grep verification result. Stop and wait for user confirmation before
   any commit/push/PR — that happens back in the skill.

## Output

A staged clone at `tmpl/tmp/contrib/candidate-NN/` on branch `contrib/<theme>`,
plus a concise report. Do not commit, push, or open a PR.
