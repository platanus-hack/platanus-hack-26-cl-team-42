"""Events: facts describing something that has happened.

An :class:`Event` is an immutable-ish record of a domain fact. A
:class:`ModelEvent` additionally knows how to *apply* itself to a Django
model instance, mutating that instance (and any related rows) so the
event becomes the single, named place where a particular state
transition is expressed.

This is deliberately **not** event sourcing: events are not persisted to
an append-only log and the current state is not derived by replaying
them. Instead, events are a formal vocabulary for state transitions and
the hook points for side effects (see :mod:`eventcore.registry`).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

if TYPE_CHECKING:
    from collections.abc import Iterator

#: Every defined :class:`Event` subclass, in definition order. Populated by
#: :meth:`Event.__init_subclass__`; read via :func:`registered_events`.
_event_registry: list[type[Event]] = []


def registered_events() -> list[type[Event]]:
    """Return all defined :class:`Event` subclasses, sorted by name.

    The framework bases defined in this module (``ModelEvent``) are excluded,
    so the result is the catalog of concrete event types the running process
    knows about (their modules having been imported at startup).
    """
    return sorted(
        (e for e in _event_registry if e.__module__ != __name__),
        key=lambda e: e.__name__,
    )


class EventMeta(BaseModel):
    """Occurrence metadata shared by a command and the events it applies.

    Describes *the occurrence* — when it happened, who triggered it, and the
    correlation id tying a command to its events — rather than the domain
    payload. It is established once per command run by :func:`eventcore.invoke`
    and made available to each event's ``apply()`` via ``self.meta``.

    ``correlation_id`` is always present (a fresh UUID by default), so consumers
    never have to guard against a missing value; ``actor`` may be unset.
    """

    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str | None = None
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))


# Active occurrence metadata for the current execution context. Set by
# :func:`eventcore.invoke` (via :func:`meta_context`) around a command's
# ``perform()`` and read by :func:`eventcore.apply_event`.
_current_meta: ContextVar[EventMeta | None] = ContextVar("eventcore_meta", default=None)


@contextmanager
def meta_context(meta: EventMeta) -> Iterator[EventMeta]:
    """Bind ``meta`` as the active occurrence context for the current context.

    :func:`eventcore.invoke` enters this around a command's ``perform()`` so
    every :func:`eventcore.apply_event` call within picks up the same envelope.
    Nesting is supported: the previous value is restored on exit.
    """
    token = _current_meta.set(meta)
    try:
        yield meta
    finally:
        _current_meta.reset(token)


def current_meta() -> EventMeta | None:
    """The active :class:`EventMeta`, or ``None`` outside a command invocation."""
    return _current_meta.get()


class Event(BaseModel):
    """Base class for all events.

    Concrete events declare their payload as ordinary pydantic fields::

        class ChangesetApprovalRequested(Event):
            requester: str

    After an event has been applied or emitted, two runtime attributes
    are available:

    * ``meta`` — the :class:`EventMeta` envelope (timestamp, actor, ...).
    * ``model`` — the subject the event was applied to, if any. This is
      what lets subscribers registered via :func:`eventcore.on` reach the
      affected aggregate, e.g. ``on(Foo, lambda e: e.model.do_thing())``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _meta: EventMeta | None = PrivateAttr(default=None)
    _model: Any = PrivateAttr(default=None)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _event_registry.append(cls)

    @property
    def meta(self) -> EventMeta:
        """The metadata envelope, lazily defaulted if not yet bound."""
        if self._meta is None:
            self._meta = EventMeta()
        return self._meta

    @property
    def model(self) -> Any:
        """The subject this event was applied to, or ``None``."""
        return self._model

    def bind(self, *, model: Any = None, meta: EventMeta | None = None) -> Event:
        """Attach runtime envelope/subject to the event. Returns ``self``."""
        if meta is not None:
            self._meta = meta
        if model is not None:
            self._model = model
        return self


class ModelEvent[M](Event):
    """An event that mutates a Django model instance of type ``M``.

    Parameterize with the aggregate it targets to get a typed base for a
    family of events::

        StudyEvent = ModelEvent[Study]


        class ArtifactReviewCreated(StudyEvent):
            checkpoint_id: int

            def apply(self, model: Study) -> None:
                model.reviews.create(checkpoint_id=self.checkpoint_id)

    ``apply`` receives only the model; read ``self.meta`` (occurred_at, actor,
    correlation_id) inside it when the occurrence envelope is needed.
    """

    def apply(self, model: M) -> None:
        """Mutate ``model`` to reflect this event. Must be overridden."""
        raise NotImplementedError(f"{type(self).__name__} must implement apply(self, model)")
