"""eventcore — formal Commands and Events for Django apps.

A lightweight framework that models two domain concepts explicitly:

* **Commands** (:class:`Command`) — validated, named intentions to change
  the system. They authorize and orchestrate work, failing with
  :class:`CommandError` when a business rule is violated.
* **Events** (:class:`Event` / :class:`ModelEvent`) — facts describing
  what happened. A ``ModelEvent`` knows how to apply itself to a Django
  model, and applying it notifies subscribers registered with :func:`on`.

This is intentionally *not* event sourcing. Models remain the source of
truth and are mutated in place; events are a shared vocabulary for state
transitions and the seam where side effects (Celery tasks, notifications,
cascading commands) attach.

Typical wiring lives in an app's ``apps.py``::

    import eventcore
    from myapp.events import InputAdded


    class MyAppConfig(AppConfig):
        def ready(self):
            from myapp.tasks import ParseSourceTask

            eventcore.on(InputAdded, lambda e: ParseSourceTask.delay(e.model.id))
"""

from __future__ import annotations

from .apply import apply_event
from .commands import Command, CommandError, NestedCommandError, invoke, registered_commands
from .events import Event, EventMeta, ModelEvent, current_meta, meta_context, registered_events
from .registry import Registry, clear, emit, on, registered_subscriptions

__all__ = [
    "Command",
    "CommandError",
    "Event",
    "EventMeta",
    "ModelEvent",
    "NestedCommandError",
    "Registry",
    "apply_event",
    "clear",
    "current_meta",
    "emit",
    "invoke",
    "meta_context",
    "on",
    "registered_commands",
    "registered_events",
    "registered_subscriptions",
]
