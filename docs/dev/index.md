# Development Guide

Documentation for contributors: how the project is structured, how to run it
locally, and how the major pieces fit together.

## Overview

- [**Architecture**](./architecture.md) — Layout, local runtime, data model, and background tasks.
- [**Development bundle**](./bundle.md) — Committing proprietary development configuration and tooling in encrypted form.

## Deep dives

- [**Frontend**](./frontend-deepdive.md) — React 19, Vite, TanStack Router/Query, auth, and data fetching.
- [**Backend**](./backend-deepdive.md) — Django + Ninja API, Allauth headless auth, Celery, and storage.
- [**Docs**](./docs-deepdive.md) — How this VitePress site is built, configured, and run.

## Libraries

Vendored packages under `backend/lib/`, documented from their READMEs.

- [**dbi18n**](./lib/dbi18n.md) — Translation management over standard gettext with a live DB overlay.
- [**eventcore**](./lib/eventcore.md) — Formal Commands and Events for Django apps.
- [**tracker**](./lib/tracker.md) — Progress tracking for Celery workloads.
- [**uncouple**](./lib/uncouple.md) — Typed configuration from environment variables.
