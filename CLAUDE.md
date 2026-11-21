# Claude Code

Follow @AGENTS.md for development guidelines, layer layout, and common commands.

## Template contributions

Review local changes worth contributing back to the copier template (`_src_path` in
`.copier-answers.yml`):

- **Skill:** `/contribute-to-template` (`superpowers/skills/contribute-to-template/SKILL.md`)
- **Subagents:** `tmpl-candidate-analyzer`, `tmpl-contribution-stager` (`superpowers/agents/`)
- **State:** `tmpl/contributions.md` (`last_reviewed_commit` only)
- **Commands:** `just tmpl render`, `just tmpl triage`, `just tmpl diff`, `just tmpl map`, `just tmpl reset`

Cursor and Claude Code discover the same files via symlinks in `.cursor/` and `.claude/`.
