---
layout: home

hero:
  name: "multiplayer-medico"
  text: "Documentation"
  tagline: User documentation and development guides.
  actions:
    - theme: brand
      text: User Manual
      link: /user/
    - theme: alt
      text: Development Guide
      link: /dev/
---

## User Manual

End-user documentation for the application.

- [**Introduction**](/user/) — Getting started and using the product.

## Development Guide

Architecture, deep dives, and vendored backend libraries for contributors.

### Overview

- [**Architecture**](/dev/architecture) — Layout, local runtime, data model, and background tasks.

### Deep dives

- [**Frontend**](/dev/frontend-deepdive) — React 19, Vite, TanStack Router/Query, auth, and data fetching.
- [**Backend**](/dev/backend-deepdive) — Django + Ninja API, Allauth headless auth, Celery, and storage.
- [**Docs**](/dev/docs-deepdive) — How this VitePress site is built, configured, and run.

### Libraries

Vendored packages under `backend/lib/`, documented from their READMEs.

- [**dbi18n**](/dev/lib/dbi18n) — Translation management over standard gettext — committed .po catalogs plus a live DB overlay editable from the admin.
- [**eventcore**](/dev/lib/eventcore) — Formal Commands and Events for Django apps — validated intentions, typed events, and subscriber hooks.
- [**tracker**](/dev/lib/tracker) — Progress tracking for Celery workloads — stamped task groups and a Django Ninja API.
- [**uncouple**](/dev/lib/uncouple) — Typed configuration from environment variables with nesting, prefixes, and secure defaults.
