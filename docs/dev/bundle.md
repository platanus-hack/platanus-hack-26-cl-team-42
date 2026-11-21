# Development Bundle

`just bundle` manages `bundle.encrypted`: an age-encrypted archive, committed
to the repo, that carries files used during development and maintenance whose
plaintext must never enter git.

Its purpose is to let **proprietary configuration and tooling travel with the
repository**. Some files are essential to how the team develops and maintains
the project — internal tooling configuration, agent instructions, template
answers, credentials for development-time services — but don't belong in the
open, either because they are secret or because they are the organization's
own tooling and shouldn't ship to third parties who receive the repo. The
bundle keeps those files versioned and shared between developers while only
ever committing them in encrypted form.

## What belongs in the bundle

Files that meet **both** criteria:

- They are used during **development or maintenance** of the project — they are
  not read by the application at build time or runtime, in any environment.
- They are **proprietary or sensitive**: internal tooling, org-specific
  configuration, or credentials for development-time services.

Typical examples: copier template answers, agent/superpowers tooling, internal
maintenance scripts, tokens for services used only by maintainers.

What does **not** belong:

- **Application secrets** (database passwords, API keys read by the app) —
  those live in 1Password and each environment's secret store, and reach the
  app through its environment.
- **Environment configuration** — that belongs in `deploy/` or the compose
  files, where it is reviewable.
- Anything a fresh contributor needs just to run the stack — the project must
  work without opening the bundle.

## Moving parts

| File | Committed? | Role |
|---|---|---|
| `bundle.encrypted` | yes | The age-encrypted tarball of every bundled path. |
| `.age-recipients` | yes | Public keys allowed to decrypt the bundle. |
| `bundle.manifest` | no (bundled) | Plaintext list of bundled paths. It is inside the bundle itself, so it round-trips with `open`/`update`. |
| `bundle.lock` | yes | Content fingerprint of the bundled files, used by the pre-commit hook to detect changes. |
| age identity | never | Your private key, at `$AGE_IDENTITY` (default `~/.config/age/keys.txt`). Shared out of band (1Password), never committed. |

Every path listed in the manifest is mirrored into a managed block of
`.gitignore`, so the decrypted plaintext stays untracked. `just bundle update`
refuses to encrypt any path that git does not ignore — a file whose plaintext
could be committed never makes it into the bundle.

## Commands

```sh
just bundle open        # decrypt the bundle into your working tree
just bundle update      # re-encrypt the bundle from your local files
just bundle add <path>  # add a file or directory to the bundle, then re-encrypt
just bundle keygen      # create an age identity and register its public key
```

## First time in a fresh clone

1. `just setup` — installs the pre-commit hook (and `age` if missing).
2. `just bundle keygen` — creates your identity if you don't have one, appends
   your public key to `.age-recipients`, and prints the private key **once**;
   store it in the team's 1Password vault.
3. Commit `.age-recipients` and ask a teammate who can already open the bundle
   to run `just bundle update` — the bundle is re-encrypted to include your key.
4. `just bundle open` — the bundled files appear in your working tree.

If you already have an identity (e.g. restored from 1Password to
`~/.config/age/keys.txt`, or pointed at by `AGE_IDENTITY`) and your key is in
`.age-recipients`, step 4 is all you need.

## Day-to-day

You rarely run `update` by hand. A pre-commit hook (configured in
`.pre-commit-config.yaml`, installed by `just setup`) fingerprints the bundled
files on every commit; when any of them changed, it re-encrypts the bundle and
stages `bundle.encrypted`, `bundle.lock`, and `.gitignore` automatically. Edit
a bundled file, commit as usual, and the encrypted archive stays in sync.

To bundle a new file:

```sh
just bundle add path/to/file
```

This appends the path to `bundle.manifest`, adds it to the managed
`.gitignore` block, and re-encrypts. Commit the resulting `bundle.encrypted`,
`bundle.lock`, and `.gitignore`.

To remove a path, delete its line from `bundle.manifest`, run
`just bundle update`, and decide what to do with the plaintext file — removing
it from the manifest stops bundling it but does not delete it from your tree.
