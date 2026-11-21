"""Request middleware that keeps each process's catalog fresh.

Install it *after* ``django.middleware.locale.LocaleMiddleware`` so the active
language is already set when the (cheap, time-gated) staleness check runs.
"""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from . import catalog


class DbTranslationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        catalog.refresh_if_stale()
        return self.get_response(request)
