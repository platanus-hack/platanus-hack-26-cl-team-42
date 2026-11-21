# Frontend deepdive

The frontend is a React app in `frontend/`. It uses Vite and TanStack Router.

## Entry point

```txt
frontend/src/main.tsx
```

`main.tsx` creates the TanStack Router from `routeTree.gen.ts`, which gets generated upon running the app, so don't worry if you see typescript errors everywhere after installing dependencies.

The route tree is generated from files under:

```txt
frontend/src/routes/
```

## App shell

The root route is:

```txt
frontend/src/routes/__root.tsx
```

It installs app-wide providers:

- `Theme` from `@radix-ui/themes`
- `QueryClientProvider` from TanStack React Query
- `AllAuthProvider`

It then renders the active route through `Outlet`.

## Routes

You will find the following preexisting routes:

```txt
frontend/src/routes/__root.tsx
frontend/src/routes/_authenticated.tsx
frontend/src/routes/_authenticated/index.tsx
frontend/src/routes/_authenticated/profile/index.tsx
frontend/src/routes/_authenticated/tracker.tsx
frontend/src/routes/login.tsx
frontend/src/routes/login-callback.tsx
```

Main routes:

| Route | Purpose |
| --- | --- |
| `/` | authenticated home page |
| `/tracker` | Celery task tracker (run tasks, watch live progress) |
| `/profile` | authenticated profile page |
| `/login` | login page |
| `/login-callback` | auth callback page |

## Authenticated layout

Authenticated pages use:

```txt
frontend/src/routes/_authenticated.tsx
```

That layout checks the auth session from `useAuth()`.

If auth has not finished loading, it renders a loading state. If the user is anonymous, it redirects to `/login`. If the user is authenticated, it renders the sidebar and the active child route.

## Authentication

Frontend auth is handled in:

```txt
frontend/src/services/auth/AllAuthProvider.tsx
```

The provider talks to Django Allauth headless endpoints under (`AUTH_URL`):

```txt
/-/.auth/headless
```

It uses these endpoints:

```txt
/browser/v1/config
/browser/v1/auth/session
/browser/v1/auth/login
/browser/v1/auth/provider/redirect
```

At startup it:

1. fetches auth config from the backend
2. checks the current session
3. exposes auth state through `useAuth()`

The login page chooses between provider login and email/password login based on the backend config.

## Backend calls

All backend routes live under the `/-/` prefix. When the Vite dev server runs
standalone (`just frontend` / `pnpm dev`) it proxies that prefix to the backend.
The proxy is configured in:

```txt
frontend/vite.config.ts
```

Proxy rule:

```txt
/-/* -> VITE_PROXY_BACKEND_URL
```

Frontend code should use relative URLs under the prefix, such as `/-/api/...`
and `/-/.auth/...`, instead of hard-coded backend hosts. Through the local
Traefik ingress the same `/-/*` paths reach the backend directly (no Vite proxy
involved).

## Data fetching

Use TanStack React Query for server state.

The app creates its `QueryClient` in `__root.tsx`. Query defaults are configured there, including stale time, retry behavior, and refetch-on-window-focus behavior, these can be overriden in useQuery invocations if need should arise.

For a complete, copyable pattern of a typed API client plus React Query hooks,
see `src/services/tracker.ts` (fetchers, `useQuery` hooks, polling) together
with its UI in `src/components/tracker/`, wired up in the `/tracker` route.
The `src/services/` directory is the home for API clients; `src/services/auth/`
holds the auth provider.

## UI

Use `@radix-ui/themes` components and theme styles. Global styles are imported in `main.tsx`:

```ts
import "@radix-ui/themes/styles.css";
import "./styles.css";
```
