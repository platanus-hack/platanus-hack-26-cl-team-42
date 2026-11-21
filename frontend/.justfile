# Run unit tests (Vitest)
test:
    pnpm test:run

# Run end-to-end tests (Playwright). Assumes the local stack is up
# (`cd ../local && just up`) so the frontend is reachable on :3000.
e2e:
    pnpm exec playwright install --with-deps chromium
    pnpm e2e
