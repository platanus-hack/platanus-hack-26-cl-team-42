"""Applying events to models.

:func:`apply_event` is the single entry point that turns an event into a
state transition plus its side effects:

1. bind the active occurrence metadata and the subject onto the event,
2. invoke ``event.apply(model)`` to mutate the model in place, and
3. emit it so registered subscribers react (after commit by default).

Models stay plain Django models — there is no base class or mixin to add.
Events may only be applied **inside a command invocation** (see
:func:`eventcore.invoke`): ``apply_event`` reads the occurrence metadata that
``invoke`` establishes, so calling it outside a command raises. Note that, like
the events themselves, this does **not** persist the model — the calling
command decides when to ``save()``.
"""

from __future__ import annotations

from .events import ModelEvent, current_meta
from .registry import emit


def apply_event(model: object, event: ModelEvent) -> ModelEvent:
    """Apply ``event`` to ``model`` and emit it. Returns the event.

    Binds the occurrence metadata established by :func:`eventcore.invoke` onto
    the event (so ``self.meta`` is available in ``apply`` and to subscribers),
    mutates the model, and emits it. Must run inside a command invocation;
    raises :class:`RuntimeError` otherwise.

    ::

        eventcore.apply_event(study, ArtifactReviewCreated(checkpoint_id=42))
    """
    meta = current_meta()
    if meta is None:
        raise RuntimeError(
            "apply_event() must run inside eventcore.invoke(): no active command "
            "context. Route the state change through a Command."
        )
    event.bind(model=model, meta=meta)
    event.apply(model)
    emit(event)
    return event
