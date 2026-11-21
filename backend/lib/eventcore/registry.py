"""Subscriber registry and dispatch.

Side effects are decoupled from what triggers them. Two kinds of *message*
flow through the same registry:

* **events** — facts applied to a model (see :func:`eventcore.apply_event`), and
* **commands** — intentions that were invoked (see :func:`eventcore.invoke`).

Subscribers registered with :func:`on` react to either — launching a Celery
task, sending a notification, writing an audit record, cascading another
command, etc. Matching is by the message's MRO, so a handler registered for a
base type also receives every subclass: ``on(Event, ...)`` observes all
events, ``on(Command, ...)`` observes all command invocations, and
``on(OrderShipped, ...)`` observes just one.

Dispatch is **transaction-aware**: handlers run only once the surrounding
database transaction commits (via ``transaction.on_commit``), so side effects
never fire for work that gets rolled back. In autocommit (no active
transaction) they run immediately. Tests exercise the deferred dispatch with
Django's on-commit capture (pytest-django's
``django_capture_on_commit_callbacks``); the dispatch-matching logic can be
tested directly via :meth:`Registry.run`, which is synchronous.
"""

from __future__ import annotations

import logging
import typing
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from django.db import transaction

logger = logging.getLogger(__name__)

Handler = Callable[[Any], None]


class Registry:
    """Maps message types to handlers and dispatches messages to them.

    A handler registered for a type also receives every subclass of that
    type (matching is by the message's MRO), so ``on(Event, ...)`` observes
    all events, ``on(Command, ...)`` all command invocations, and
    ``on(OrderShipped, ...)`` just one.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def on[T](
        self,
        message_type: type[T],
        handler: Callable[[T], None] | None = None,
    ) -> Callable[[T], None] | Callable[[Callable[[T], None]], Callable[[T], None]]:
        """Register ``handler`` for ``message_type``.

        Usable directly or as a decorator::

            on(InputAdded, parse_document)


            @on(InputAdded)
            def parse_document(event: InputAdded) -> None: ...
        """
        key = _normalize_type(message_type)

        if handler is None:

            def decorator(fn: Callable[[T], None]) -> Callable[[T], None]:
                self._handlers[key].append(fn)  # type: ignore[arg-type]
                return fn

            return decorator

        self._handlers[key].append(handler)  # type: ignore[arg-type]
        return handler

    def handlers_for(self, message: object) -> list[Handler]:
        """Return handlers registered for the message's type and its bases."""
        matched: list[Handler] = []
        for klass in type(message).__mro__:
            matched.extend(self._handlers.get(klass, ()))
        return matched

    def run(self, message: object) -> None:
        """Synchronously invoke every matching handler, isolating failures."""
        for handler in self.handlers_for(message):
            try:
                handler(message)
            except Exception:
                logger.exception(
                    "eventcore subscriber %r failed handling %r",
                    handler,
                    type(message).__name__,
                )

    def emit(self, message: object) -> None:
        """Dispatch a message to its handlers after the surrounding transaction
        commits (immediately if there is no active transaction)."""
        transaction.on_commit(lambda: self.run(message))

    def clear(self) -> None:
        """Remove all registered handlers (primarily for tests)."""
        self._handlers.clear()

    def subscriptions(self) -> list[tuple[type, Handler]]:
        """Return ``(message_type, handler)`` pairs for documentation / introspection."""
        pairs: list[tuple[type, Handler]] = []
        for message_type, handlers in self._handlers.items():
            for handler in handlers:
                pairs.append((message_type, handler))
        return pairs


def _normalize_type(message_type: type) -> type:
    """Resolve a possible typing alias to the class used for MRO matching."""
    origin = typing.get_origin(message_type)
    return origin if origin is not None else message_type


# Process-wide default registry.
_registry = Registry()


def on[T](
    message_type: type[T],
    handler: Callable[[T], None] | None = None,
) -> Callable[[T], None] | Callable[[Callable[[T], None]], Callable[[T], None]]:
    """Register a subscriber on the default registry. See :meth:`Registry.on`."""
    return _registry.on(message_type, handler)


def emit[T](message: T) -> T:
    """Dispatch ``message`` to subscribers on the default registry.

    Returns the message so callers may chain or inspect it.
    """
    _registry.emit(message)
    return message


def clear() -> None:
    """Clear the default registry's handlers (primarily for tests)."""
    _registry.clear()


def registered_subscriptions() -> list[tuple[type, Handler]]:
    """Return every ``(message_type, handler)`` pair on the default registry.

    Used by the live documentation graph (:mod:`eventcore.introspection`);
    not required for normal command/event dispatch.
    """
    return _registry.subscriptions()
