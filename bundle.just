# Development bundle — encrypt/decrypt shared development files committed to git.
#
# `bundle.encrypted` is the committed, age-encrypted archive. `bundle.manifest`
# lists the paths it contains; it lives only in the decrypted working tree (it is
# bundled too, so it round-trips). `.age-recipients` holds the public keys allowed
# to open it. The age identity (private key) is never committed.
#
#   just bundle open            # decrypt the bundle into the working tree
#   just bundle update          # re-encrypt the bundle from local files
#   just bundle add <path>      # add a path to the bundle, then re-encrypt
#   just bundle keygen          # create an age identity, register its public key, print the private key once
#
# The pre-commit hook that keeps the bundle in sync is configured in
# `.pre-commit-config.yaml` and installed by `just setup`.

bundle     := "bundle.encrypted"
manifest   := "bundle.manifest"
recipients := ".age-recipients"
lock       := "bundle.lock"

# Decrypt the bundle into the working tree
open:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f "{{bundle}}" ] || { echo "bundle: nothing to open ({{bundle}} not found)" >&2; exit 1; }
    identity="${AGE_IDENTITY:-$HOME/.config/age/keys.txt}"
    [ -f "$identity" ] || { echo "bundle: no age identity at '$identity' — set AGE_IDENTITY or run 'just bundle keygen'" >&2; exit 1; }
    age -d -i "$identity" "{{bundle}}" | tar -xzf -
    just bundle _gitignore-sync
    just bundle _hash > "{{lock}}"
    echo "bundle: opened into working tree"

# Re-encrypt the bundle from the files listed in the manifest
update:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f "{{manifest}}" ] || { echo "bundle: no {{manifest}} — run 'just bundle add <path>' or 'just bundle open'" >&2; exit 1; }
    [ -f "{{recipients}}" ] || { echo "bundle: missing {{recipients}}" >&2; exit 1; }
    grep -qvE '^[[:space:]]*(#|$)' "{{recipients}}" || { echo "bundle: {{recipients}} has no keys — run 'just bundle keygen'" >&2; exit 1; }
    paths=()
    while IFS= read -r line; do
        paths+=("$line")
    done < <(grep -vE '^[[:space:]]*(#|$)' "{{manifest}}")
    [ "${#paths[@]}" -gt 0 ] || { echo "bundle: {{manifest}} is empty" >&2; exit 1; }
    for p in "${paths[@]}"; do
        [ -e "$p" ] || { echo "bundle: path '$p' from {{manifest}} is missing" >&2; exit 1; }
        git check-ignore -q "$p" || { echo "bundle: refusing — '$p' is not gitignored (its plaintext could be committed)" >&2; exit 1; }
    done
    just bundle _gitignore-sync
    tar -czf - "{{manifest}}" "${paths[@]}" | age -R "{{recipients}}" -o "{{bundle}}"
    just bundle _hash > "{{lock}}"
    echo "bundle: updated {{bundle}} ($(wc -c < "{{bundle}}" | tr -d ' ') bytes, ${#paths[@]} path(s))"

# Add a path to the bundle, then re-encrypt
add path:
    #!/usr/bin/env bash
    set -euo pipefail
    raw="{{path}}"
    p="${raw#./}"; p="${p%/}"
    [ -e "$p" ] || { echo "bundle: '$p' does not exist" >&2; exit 1; }
    touch "{{manifest}}"
    if grep -qxF "$p" "{{manifest}}"; then
        echo "bundle: '$p' is already in {{manifest}}"
    else
        printf '%s\n' "$p" >> "{{manifest}}"
        echo "bundle: added '$p' to {{manifest}}"
    fi
    just bundle _gitignore-sync
    just bundle update

# Create an age identity (if missing), register its public key, and print the private key once
keygen:
    #!/usr/bin/env bash
    set -euo pipefail
    identity="${AGE_IDENTITY:-$HOME/.config/age/keys.txt}"
    created=false
    if [ -f "$identity" ]; then
        echo "bundle: identity already exists at $identity"
    else
        mkdir -p "$(dirname "$identity")"
        age-keygen -o "$identity" >/dev/null 2>&1
        created=true
        echo "bundle: created identity at $identity"
    fi
    public_key="$(age-keygen -y "$identity")"
    touch "{{recipients}}"
    if grep -vE '^[[:space:]]*(#|$)' "{{recipients}}" | grep -qxF "$public_key"; then
        echo "bundle: public key already in {{recipients}}"
    else
        printf '%s\n' "$public_key" >> "{{recipients}}"
        echo "bundle: added public key to {{recipients}} — commit this file"
    fi
    if [ "$created" = true ]; then
        echo ""
        echo "Private key — save the block below in 1Password (never commit it):"
        echo "  Suggested item title: \"age bundle identity ($(whoami))\""
        echo "  Store in your team's 1Password vault."
        echo ""
        cat "$identity"
        echo ""
        echo "Keep a copy at $identity for local use, or set AGE_IDENTITY to another path."
    fi

# pre-commit entrypoint: refresh the bundle when any bundled file changed
_precommit:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -f "{{manifest}}" ] || exit 0
    [ -f "{{recipients}}" ] || exit 0
    grep -qvE '^[[:space:]]*(#|$)' "{{recipients}}" || exit 0
    current="$(just bundle _hash)"
    previous=""
    [ -f "{{lock}}" ] && previous="$(cat "{{lock}}")"
    if [ "$current" != "$previous" ]; then
        echo "bundle: bundled files changed — refreshing {{bundle}}"
        just bundle update >/dev/null
        git add "{{bundle}}" "{{lock}}" .gitignore
    fi

# Content fingerprint of the manifest + every file it lists (for change detection)
_hash:
    #!/usr/bin/env bash
    set -euo pipefail
    {
        sha256sum "{{manifest}}"
        grep -vE '^[[:space:]]*(#|$)' "{{manifest}}" | LC_ALL=C sort | while IFS= read -r p; do
            if [ -d "$p" ]; then
                find "$p" -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do
                    sha256sum "$f"
                done
            elif [ -f "$p" ]; then
                sha256sum "$p"
            else
                echo "MISSING:$p"
            fi
        done
    } | sha256sum | cut -d' ' -f1

# Mirror the manifest into a managed block of .gitignore so plaintext stays untracked
_gitignore-sync:
    #!/usr/bin/env bash
    set -euo pipefail
    gi=".gitignore"
    touch "$gi"
    begin="# >>> bundle (managed — do not edit by hand) >>>"
    end="# <<< bundle (managed) <<<"
    tmp="$(mktemp)"
    awk -v b="$begin" -v e="$end" 'BEGIN{skip=0} $0==b{skip=1; next} skip&&$0==e{skip=0; next} !skip{print}' "$gi" > "$tmp"
    {
        echo "$begin"
        echo "{{manifest}}"
        [ -f "{{manifest}}" ] && grep -vE '^[[:space:]]*(#|$)' "{{manifest}}" | sed 's#/*$##'
        echo "$end"
    } >> "$tmp"
    mv "$tmp" "$gi"
