"""Commands: validated, named intentions to change the system.

A :class:`Command` is the imperative counterpart to an event. It carries a
typed payload (it is a pydantic model), validates and authorizes the
request, performs the work — typically by applying one or more events to
aggregates — and may fail with a domain-specific :class:`CommandError`.

::

    class SubmitArtifactForReview(Command):
        checkpoint_id: int
        artifact_channel_name: str

        class CheckpointNotFound(CommandError): ...

        def perform(self) -> ArtifactReview:
            try:
                checkpoint = Checkpoint.objects.get(pk=self.checkpoint_id)
            except Checkpoint.DoesNotExist:
                raise self.CheckpointNotFound(
                    "Checkpoint %s not found", self.checkpoint_id
                )
            return apply_event(checkpoint.study, ArtifactReviewCreated(...))

    review = invoke(SubmitArtifactForReview(checkpoint_id=1, ...))

A command is a plain (validated) description of intent: subclasses declare
their payload as pydantic fields and implement :meth:`perform`. Running one is
a library concern handled by the :func:`invoke` free function, which runs
``perform`` inside ``transaction.atomic()`` (so every event applied within
commits atomically) and — once the work commits — emits the command through
the shared registry, so observers registered with ``on(Command, ...)`` (audit
logs, metrics, …) react without the command knowing.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import transaction
from pydantic import BaseModel, ConfigDict, PrivateAttr

from .events import EventMeta, current_meta, meta_context
from .registry import emit

#: Every defined :class:`Command` subclass, in definition order. Populated by
#: :meth:`Command.__init_subclass__`; read via :func:`registered_commands`.
_command_registry: list[type[Command]] = []


def registered_commands() -> list[type[Command]]:
    """Return all defined :class:`Command` subclasses, sorted by name.

    A class appears here once its module has been imported (Django imports
    each app's command modules at startup), making this a live catalog of
    the commands the running process knows about.
    """
    return sorted(_command_registry, key=lambda c: c.__name__)


class CommandError(Exception):
    """Base class for expected, domain-level command failures.

    Subclass it inside a command to model the ways that command can fail.
    A printf-style ``message`` plus arguments are accepted and formatted
    lazily, matching Python's logging conventions::

        raise self.CheckpointNotFound("Checkpoint %s not found", checkpoint_id)
    """

    def __init__(self, message: str = "", *args: Any) -> None:
        self.template = message
        self.context = args
        super().__init__(message % args if args else message)


class NestedCommandError(RuntimeError):
    """Raised when a command is invoked from within another command's ``perform``.

    Commands must not call other commands directly — chaining them hides the
    transition and couples the two. Bridge through a *policy* instead: react to
    the first command's event with an ``on(...)`` subscriber that invokes the
    second command (which runs after the first has committed).
    """


class Command(BaseModel):
    """Base class for commands.

    Subclasses declare their payload as pydantic fields and implement
    :meth:`perform`. A command only *describes* an intention — running it is
    the job of the :func:`invoke` free function. ``perform`` should not be
    called directly; go through :func:`invoke` so the work is wrapped in a
    transaction and announced to ``on(Command, ...)`` subscribers.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    #: Convenient base for nested error classes: ``class NotFound(Command.Error)``.
    Error: ClassVar[type[CommandError]] = CommandError

    #: Correlation id tying this command to the events it applies. Stamped by
    #: :func:`invoke`; shared with each event's ``meta.correlation_id``.
    _correlation_id: str | None = PrivateAttr(default=None)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _command_registry.append(cls)

    @property
    def correlation_id(self) -> str | None:
        """The correlation id assigned when this command was invoked."""
        return self._correlation_id

    def perform(self) -> Any:
        """Perform the command's work. Must be overridden by subclasses."""
        raise NotImplementedError(f"{type(self).__name__} must implement perform()")


def invoke(command: Command) -> Any:
    """Run an already-constructed ``command`` and announce it. Returns the result.

    Establishes the occurrence metadata (a fresh ``correlation_id``,
    ``occurred_at`` now, ``actor`` unset for now) and makes it the active
    :func:`~eventcore.events.meta_context` while :meth:`Command.perform` runs
    inside ``transaction.atomic()`` — so every event applied within shares that
    envelope (and correlation id), and the whole transition commits atomically.
    The command is stamped with the same ``correlation_id`` and then emitted
    through the shared registry, so ``on(Command, ...)`` subscribers react only
    to work that became durable; handler failures are isolated by the registry.

    Typical use::

        order = invoke(PlaceOrder(customer_name="Ada", item="Keyboard"))

    A command may **not** be invoked from within another command's ``perform``
    (raises :class:`NestedCommandError`); route command-to-command flows through
    a policy instead.
    """
    if current_meta() is not None:
        raise NestedCommandError(
            f"{type(command).__name__} was invoked from within another command's "
            "perform(); commands must not invoke commands directly — bridge through "
            "a policy (an on(...) subscriber) instead."
        )
    meta = EventMeta()
    command._correlation_id = meta.correlation_id
    with meta_context(meta), transaction.atomic():
        result = command.perform()
    emit(command)
    return result
