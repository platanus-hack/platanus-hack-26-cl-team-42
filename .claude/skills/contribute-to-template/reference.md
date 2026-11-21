# Contribute-to-Template Reference

## Exclusion list

Diff exclusions are maintained as gitignore-style patterns in **[`tmpl/exclude-patterns`](../../../tmpl/exclude-patterns)**,
which `candidate-diff.sh` reads directly via `rsync --exclude-from`. Edit that file to
add or remove exclusions — the scripts pick them up automatically.

In addition to the file-pattern exclusions, always discard candidates that:
- Only substitute project-specific values (names, slugs, domains) without adding new logic — that is instantiation noise, not a contribution.
- Contain real credentials, API keys, or tokens — never contribute these regardless of pattern matches.

### The contribution process is contributable

The `contribute-to-template` skill, its agents, and the `tmpl/` tooling are
**not** excluded — improvements to the contribution process itself should flow
back to the template. Contributable paths include:

- `superpowers/skills/contribute-to-template/` (skill + reference)
- `superpowers/agents/tmpl-*.md` (candidate-analyzer, contribution-stager)
- Symlinks in `.cursor/{skills,agents}/` and `.claude/{skills,agents}/` pointing at
  `superpowers/` (for Cursor and Claude Code discovery)
- `tmpl/bin/`, `tmpl/.justfile`, `tmpl/exclude-patterns`

Two things stay project-local even when contributing the process:

- `tmpl/tmp/` — the gitignored working area (rendered pristine, triage, analysis,
  contrib clones). Excluded via `tmpl/exclude-patterns`.
- `tmpl/contributions.md` — its `last_reviewed_commit` is this project's state
  (triage base pointer only; no review log or upstream PR references). Ship it
  upstream only as a **fresh stub**: empty `last_reviewed_commit`.

---

## Worthiness criteria

**Check upstream first — before any other analysis.** Run `just tmpl diff <files...>`.
If the diff is empty or shows only project-specific value substitutions with no structural
difference, the change is already in the pristine template. Mark it **not worthy**
immediately (reason: "already upstream") and skip further analysis.

A candidate is **worthy** if ALL of the following hold:

1. **Not already upstream** — `just tmpl diff <files>` shows a real structural delta
   from the pristine template baseline (checked first, before anything else).
2. **Generic** — the change is not tied to the project's domain concepts, business
   logic, or application-specific models/APIs. Ask: *would any project generated from
   this template benefit from this change?*
3. **High quality** — the code is clean, well-tested where appropriate, and follows
   the conventions established in the template.
4. **Contributable** — the change can be re-templatized cleanly (all concrete values
   can be replaced with Jinja2 variables from the copier answers).

A candidate is **not worthy** if ANY of the following hold:

- Already present in the pristine template (check this first with `just tmpl diff`)
- Uses project-specific models, services, URLs, or API concepts
- Is too small to justify a PR (a one-line typo fix, whitespace-only)
- Cannot be re-templatized without distorting the intent of the change

---

## Re-templatization

Run `just tmpl map` to get the full substitution table derived from `.copier-answers.yml`.
The table always reflects the actual values of this project.

**General Jinja2 substitution patterns:**

```
{{ project_slug }}         project kebab-case identifier
{{ project_name }}         human-readable project name
{{ org }}                  organization slug
{{ domain_name }}          project domain
{{ github_repository_url}} VCS remote URL
{{ one_password_vault_name }} 1Password vault
{{ aws_account_id }}       AWS account number
{{ aws_region }}           AWS region
{{ tfcloud_organization }} Terraform Cloud org
{% if frontend_framework == 'vue' %}...{% endif %}  framework-conditional blocks
{{ frontend_framework }}   framework string value
```

**Before committing to the template clone:**
```bash
# Run for each concrete value from 'just tmpl map'
grep -r '{{ project_slug }}' . --include='*.py' --include='*.ts' --include='*.yml'
```

---

## Cleanup change types

When the analysis subagent writes a cleanup plan, changes fall into these categories:

| Type | Examples |
|---|---|
| Re-templatization | Replace `<project_slug>` → `{{ project_slug }}`, wrap Vue-specific blocks |
| Tests | Make test fixtures generic, remove project-specific assertions |
| Demo resources | Replace real domain/org names in example data |
| Documentation | Neutralize project-specific wording, remove domain references |
| Naming | Rename files or identifiers that reflect the project name |
| Dependencies | Remove project-specific packages not needed by the template |
| Configuration | Generalize hardcoded values in config files |

Keep cleanup plans **small and targeted**. The goal is to make the change clean,
not to refactor it into something different from what it is.

---

## PR description template

Use this when opening PRs against the upstream template repo. The `_src_path` and
contributing project name come from `.copier-answers.yml` (`project_name`).

```markdown
> Contributed from **{{ project_name }}** (`{{ github_repository_url }}`)

## Summary

<!-- One paragraph: what this change does and why it belongs in the template -->

## Why it generalizes

<!-- Why is this improvement useful for any project generated from this template?
     Mention if and how concrete values were re-templatized. -->

## Files touched

<!-- List the files modified/added/removed in this changeset -->

## New copier variables introduced (if any)

<!-- If this changeset adds a new copier question or default, document it here:
     - Variable name
     - Question text
     - Default value
     - Type (str, bool, etc.) -->

## Testing

<!-- How was this tested locally? Edge cases to watch for? -->
```

---

## Candidate file format

```markdown
---
theme: <short-name>
commits:
  - <sha> <message>
files:
  - path/to/file
rationale: One sentence on why this might generalize.
---

# Candidate NN: <theme>

<Description>
```

## Analysis file format

```markdown
---
candidate: NN
theme: <theme>
verdict: worthy | not-worthy
confidence: high | medium | low
---

# Analysis: Candidate NN — <theme>

## Verdict

<Justification paragraph>

## Cleanup plan

<Itemized list of changes, or "No cleanup required.">

## Files involved

<list>

## Relevant commits

<list>

## Re-templatization notes

<Which values need substituting; any gaps in the map>
```
