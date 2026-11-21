# Docs deepdive

This documentation site is built with [VitePress](https://vitepress.dev/), a
static-site generator that turns the Markdown in `docs/` into a small SPA.

## Layout

```txt
docs/
  index.md              home page (VitePress "home" layout)
  dev/                  Development Guide
    index.md
    architecture.md
    frontend-deepdive.md
    backend-deepdive.md
    docs-deepdive.md    this page
    lib/                library pages that @include vendored READMEs
  user/                 User Manual
    index.md
  .vitepress/config.ts  site config (title, nav, sidebar, base)
  docker/Dockerfile     dev server + static build
  package.json          VitePress dependency and scripts
```

## Configuration

Site config lives in `docs/.vitepress/config.ts` — page metadata, the top
`nav`, and the `sidebar`. When you add a page, add it to the `sidebar` there so
it appears in the navigation.

The `base` is set to `/-docs/` because the site is served under that path
behind the local Traefik ingress (see [Architecture](./architecture.md) and
`local/docker-compose.yml`); VitePress prefixes asset and link URLs with it.

## Library docs (single source of truth)

The pages under `docs/dev/lib/` document the vendored backend libraries
(`backend/lib/eventcore`, `backend/lib/tracker`, `backend/lib/uncouple`). Rather than duplicating their
READMEs, each page pulls the README in verbatim with VitePress's build-time
[Markdown include](https://vitepress.dev/guide/markdown#markdown-file-inclusion):

```md
<!--@include: ../../../backend/lib/tracker/README.md-->
```

The README next to the code stays the single source of truth; the docs build
simply embeds it (so the content is still statically rendered, searchable, and
syntax-highlighted). Because the READMEs live outside `docs/`, they are made
reachable in two places:

- **Dev server** (`docs` service in `local/docker-compose.yml`): `backend/lib`
  is bind-mounted read-only at `/backend/lib`, the path the includes resolve to.
- **Static build** (`build` stage in `docker/Dockerfile`): the READMEs are
  copied in from a `libs` named build context, supplied via
  `build.additional_contexts` in compose (or `--build-context libs=...`).

To add another library page, drop a stub in `docs/dev/lib/`, add an `@include`
pointing at its README, and register it in the `sidebar`. If it lives outside
`backend/lib`, also extend the mount and the Dockerfile `COPY --from=libs`
lines. Note that edits to an included README may not hot-reload the dev server;
refresh the page to pick them up.

## Running

In the local stack the docs run as the `docs` service with hot reload, served
at `/-docs/` (`just local up` prints the URL).

To run the site on its own, from the `docs/` directory:

```sh
pnpm install
pnpm dev      # dev server with hot reload
pnpm build    # static build into .vitepress/dist
pnpm preview  # serve the built site
```

## Learn more

See the [VitePress documentation](https://vitepress.dev/) for layouts,
theming, the config reference, and Markdown extensions.
