# Frontend Development Guidelines

- Run `pnpm lint` before committing changes
- Run `pnpm build` to verify TypeScript compilation
- Run `pnpm test` (watch mode) or `pnpm test:run` (single run); from repo root: `just frontend test`
- Use `@radix-ui/themes` components, not raw HTML elements
- Use `@tanstack/react-query` for data fetching
- Use `@tanstack/react-router` for routing
