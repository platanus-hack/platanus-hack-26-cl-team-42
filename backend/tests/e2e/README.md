# Backend e2e tests

End-to-end tests for the backend running against the `local/` docker-compose
stack (postgres + django). They live alongside other layers' e2e suites under
`<layer>/tests/e2e/` and run from the project root with `just local test-e2e`.

Unit tests live in `backend/tests/` (siblings of this folder) and are
collected separately so they run without postgres.

## Run locally

```bash
# from the project root, with the local stack up
just local up
just local test-e2e   # runs `pytest tests/e2e` inside the backend container
```

## Configuration

Tests read `BACKEND_E2E_BASE_URL` from the environment. When unset:
- `http://backend:8000` is used inside the compose network (default for the
  container-side run wired up in `local/.justfile`).
- `http://localhost:8000` is used when running on the host.

## Adding tests

Place new `test_*.py` files in this directory. Treat them as integration tests
that exercise the real wsgi/asgi stack via HTTP. Mocks belong in
`backend/tests/` (true unit tests).
