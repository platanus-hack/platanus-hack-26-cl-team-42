# Frontend e2e tests (Playwright)

End-to-end tests for the frontend running against a real stack (frontend +
backend + postgres). They live alongside other layers' e2e suites under
`<layer>/tests/e2e/` and run from the project root with `just frontend e2e`
(the local stack must be up).

## Run locally

```bash
# from the project root, with the local stack up (`just local up`)
just frontend e2e
```

`just frontend e2e` installs the Playwright Chromium browser and runs the
suite. To run the steps by hand from `frontend/`:

```bash
pnpm install
pnpm exec playwright install --with-deps chromium
pnpm e2e
```

## Configuration

- `playwright.config.ts` — minimal config, `testDir: '.'`, picks up `*.spec.ts`.
- Base URL defaults to `http://localhost:3000`; override with `E2E_BASE_URL`.
- HTML report is written to `playwright-report/` when running under `CI=1`.

## Adding tests

Place new specs in this directory using the `*.spec.ts` suffix. Treat them as
true integration tests: rely on the real backend (`/-/_health/`, allauth
endpoints, etc.) rather than mocking. Mocks belong in `src/**/*.test.tsx`
(Vitest).
