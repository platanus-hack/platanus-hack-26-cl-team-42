# Backend Development Guidelines

> See `AGENTS.md` in the project root for general development guidelines.

- Django management command is run in a virtualenv using `just local/manage`
- Tests are run using `just local/test`. Use `-k <pattern>` to filter tests (e.g., `just local/test -k filtering`)
- API queries should access the Django ORM directly, leverage FilterSchemas and paginate() decorator using ninja_extra to allow combining these features
- Business logic that is not a query (mutations, business rules, etc) belongs in a service layer inside the relevant app under ./apps (e.g. `apps/<app>/services.py`), not in views or models
- Ninja schemas should be derived from Django Models or service DTOs
- DTOs are pydantic models
- Use `uv` inside ./backend for adding dependencies or running python
- Do not create Django migrations, we will manually create migrations as needed
- Suffix URL-bearing identifiers with `_url` and filesystem/route path-bearing identifiers with `_path` — `_dir` is also fine as a suffix for directory paths (e.g. `callback_url`, `media_path`, `apps_dir`). Using bare `url` and `path` identifiers is fine as well.
