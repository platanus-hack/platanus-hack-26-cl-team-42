"""Opt-in live documentation for eventcore commands, events, and policies.

Project-agnostic: discovers whatever the running process has registered.
Enable in any template project with:

1. ``INSTALLED_APPS += ["eventcore.contrib.docs"]``
2. Mount the Ninja router::

       from eventcore.contrib.docs import router as eventcore_docs_router
       api.add_router("/eventcore", eventcore_docs_router)

3. Mount the UI::

       path("eventcore-docs/", include("eventcore.contrib.docs.urls")),

Then open ``/{URL_PREFIX}/eventcore-docs/``.
"""

from .api import router

__all__ = ["router"]
