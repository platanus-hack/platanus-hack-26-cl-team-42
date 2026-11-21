"""Listeners that turn commands and events into :class:`LogRecord` rows.

``register()`` (called once from :meth:`EventcoreAppConfig.ready`) subscribes
both via the shared eventcore registry, relying on MRO matching against the
base types so *every* command/event is observed:

* every applied event -> ``log_event`` (``on(Event, ...)``), and
* every command invocation -> ``log_command`` (``on(Command, ...)``).

Both writes are defensive: a logging failure is recorded but never propagated
back to the command/event flow.
"""

from __future__ import annotations

import logging

import eventcore
from eventcore import Command, Event

from .models import LogRecord

logger = logging.getLogger(__name__)


def log_event(event: Event) -> None:
    """Record an applied event as an ``EVENT`` log row."""
    try:
        LogRecord.objects.create(
            kind=LogRecord.Kind.EVENT,
            name=type(event).__name__,
            correlation_id=event.meta.correlation_id,
            payload=event.model_dump(mode="json"),
        )
    except Exception:
        logger.exception("eventcore.app failed to log event %r", type(event).__name__)


def log_command(command: Command) -> None:
    """Record a command invocation as a ``COMMAND`` log row."""
    try:
        LogRecord.objects.create(
            kind=LogRecord.Kind.COMMAND,
            name=type(command).__name__,
            correlation_id=command.correlation_id,
            payload=command.model_dump(mode="json"),
        )
    except Exception:
        logger.exception("eventcore.app failed to log command %r", type(command).__name__)


def register() -> None:
    """Subscribe both logging listeners. Re-runnable after a registry clear."""
    eventcore.on(Event, log_event)
    eventcore.on(Command, log_command)
