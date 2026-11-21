# tmpl — template contribution tooling
# Recipes run from the tmpl/ directory (just module convention).

# Quick intro and current status
default:
    @echo "tmpl — template contribution workflow"
    @echo ""
    @echo "Contribute local improvements back to the copier template defined in"
    @echo ".copier-answers.yml (_src_path). Workflow:"
    @echo ""
    @echo "  1. just tmpl render       Render a pristine template baseline (cached)"
    @echo "  2. just tmpl triage       Gather commits since last review → tmp/triage-input.md"
    @echo "     (agent reads triage-input.md and writes tmp/triage/candidate-NN-<theme>.md)"
    @echo "  3. (analysis subagents)   One per candidate → tmp/analysis/candidate-NN-<theme>.md"
    @echo "  4. (review loop)          Agent presents each verdict; you skip / approve / request cleanup"
    @echo "  5. (contribution)         Agent opens a PR per approved candidate (base: next)"
    @echo "  6. (finalize)             Agent updates contributions.md and commits"
    @echo ""
    @echo "Utilities:"
    @echo "  just tmpl map             Print re-templatization substitution table"
    @echo "  just tmpl diff <paths>    Diff specific paths: pristine vs local"
    @echo "  just tmpl status          Show last-reviewed commit and pending files"
    @echo "  just tmpl reset           Wipe tmp/* working area (keeps .gitkeep)"
    @echo ""
    @echo "Current status:"
    @echo "  Last reviewed commit: $(grep 'last_reviewed_commit:' contributions.md | sed 's/last_reviewed_commit:[[:space:]]*//' | tr -d '\"' | sed 's/^$/  (none — first run)/g')"
    @echo "  Candidates:  $(ls tmp/triage/candidate-*.md 2>/dev/null | wc -l | tr -d ' ') file(s) in tmp/triage/"
    @echo "  Analyses:    $(ls tmp/analysis/candidate-*.md 2>/dev/null | wc -l | tr -d ' ') file(s) in tmp/analysis/"

# Show status: last reviewed commit and pending triage files
status:
    @echo "=== Template contribution status ==="
    @grep 'last_reviewed_commit:' contributions.md || echo "(contributions.md not found)"
    @echo ""
    @echo "Triage candidates:"
    @ls tmp/triage/candidate-*.md 2>/dev/null || echo "  (none — run 'just tmpl triage')"
    @echo "Analysis files:"
    @ls tmp/analysis/candidate-*.md 2>/dev/null || echo "  (none)"

# Render a pristine template into tmp/pristine/ (cached; pass --force to re-render)
render *args:
    bash bin/render-template.sh {{args}}

# Gather commits since last review into tmp/triage-input.md
# Override base commit: BASE=<ref> just tmpl triage
triage:
    bash bin/triage.sh

# Diff specific paths between the pristine template and local project
# Usage: just tmpl diff backend/docker/Dockerfile docs/
diff *paths:
    bash bin/candidate-diff.sh {{paths}}

# Print the re-templatization substitution map from .copier-answers.yml
map *args:
    bash bin/answers-map.sh {{args}}

# Remove all generated working files in tmp/ (pristine, triage, analysis, contrib)
# Does NOT touch contributions.md
reset:
    @echo "Removing tmp/* (keeping .gitkeep) ..."
    find tmp -mindepth 1 -not -name '.gitkeep' -delete
    @echo "Done."
