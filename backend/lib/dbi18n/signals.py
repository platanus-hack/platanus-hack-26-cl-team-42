"""Invalidate the in-process catalog the moment a Translation row changes.

This gives the editing process instant feedback; other processes catch up via
the time-based reload in :func:`dbi18n.catalog.refresh_if_stale`.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save

from . import catalog
from .models import Translation


def connect() -> None:
    post_save.connect(_invalidate, sender=Translation, dispatch_uid="dbi18n_invalidate_save")
    post_delete.connect(_invalidate, sender=Translation, dispatch_uid="dbi18n_invalidate_delete")


def _invalidate(**_kwargs: Any) -> None:
    catalog.reset()
