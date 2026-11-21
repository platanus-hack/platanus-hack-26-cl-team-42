"""Unit tests for the eventcore library.

The subscriber registry's dispatch/matching logic is tested directly against a
local :class:`~eventcore.Registry` via :meth:`Registry.run` — synchronous and
DB-free. The ``apply_event`` / ``invoke`` paths emit through
``transaction.on_commit``, so those are exercised with ``@pytest.mark.django_db``
and pytest-django's ``django_capture_on_commit_callbacks``.
"""

from __future__ import annotations

import contextvars

import pytest
from django.db import transaction

import eventcore
from eventcore import Command, CommandError, Event, EventMeta, ModelEvent


# --------------------------------------------------------------------------- #
# Test fixtures: a tiny aggregate and its events
# --------------------------------------------------------------------------- #
class Counter:
    def __init__(self) -> None:
        self.value = 0
        self.stamped_at = None


CounterEvent = ModelEvent[Counter]


class Incremented(CounterEvent):
    by: int = 1

    def apply(self, model: Counter) -> None:
        model.value += self.by


class Stamped(CounterEvent):
    def apply(self, model: Counter) -> None:
        model.stamped_at = self.meta.occurred_at


@pytest.fixture(autouse=True)
def _reset_eventcore():
    """Isolate the global registry between tests."""
    eventcore.clear()
    yield
    eventcore.clear()


@pytest.fixture
def command_context():
    """Simulate running inside a command: ``apply_event`` requires an active
    meta context, which :func:`eventcore.invoke` normally establishes."""
    with eventcore.meta_context(EventMeta()):
        yield


# --------------------------------------------------------------------------- #
# Registry dispatch/matching (synchronous, DB-free)
# --------------------------------------------------------------------------- #
def test_registry_notifies_handler():
    registry = eventcore.Registry()
    received: list[Event] = []
    registry.on(Incremented, received.append)

    event = Incremented(by=5)
    registry.run(event)

    assert received == [event]


def test_registry_handler_registered_via_decorator():
    registry = eventcore.Registry()
    received: list[Event] = []

    @registry.on(Incremented)
    def handler(event: Incremented) -> None:
        received.append(event)

    registry.run(Incremented())

    assert len(received) == 1


def test_registry_handler_on_base_type_receives_subclasses():
    registry = eventcore.Registry()
    seen: list[str] = []
    registry.on(ModelEvent, lambda e: seen.append(type(e).__name__))

    registry.run(Incremented())
    registry.run(Stamped())

    assert seen == ["Incremented", "Stamped"]


def test_registry_isolates_failing_handler():
    registry = eventcore.Registry()
    received: list[Event] = []

    def boom(event: Event) -> None:
        raise RuntimeError("kaboom")

    registry.on(Incremented, boom)
    registry.on(Incremented, received.append)

    registry.run(Incremented())

    assert len(received) == 1


def test_registry_clear_removes_handlers():
    registry = eventcore.Registry()
    received: list[Event] = []
    registry.on(Incremented, received.append)
    registry.clear()

    registry.run(Incremented())

    assert received == []


def test_registry_event_dispatched_without_apply_has_no_model():
    registry = eventcore.Registry()
    received: list[Event] = []
    registry.on(Incremented, received.append)

    registry.run(Incremented(by=9))

    assert received and received[0].model is None


# --------------------------------------------------------------------------- #
# Events / apply_event
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_apply_event_mutates_model_and_returns_event(command_context):
    counter = Counter()
    event = eventcore.apply_event(counter, Incremented(by=3))

    assert counter.value == 3
    assert isinstance(event, Incremented)
    assert event.model is counter


@pytest.mark.django_db
def test_apply_event_binds_metadata(command_context):
    counter = Counter()
    event = eventcore.apply_event(counter, Incremented())

    assert event.meta.occurred_at is not None
    assert event.model is counter


@pytest.mark.django_db
def test_apply_reads_meta_via_self(command_context):
    counter = Counter()
    event = eventcore.apply_event(counter, Stamped())

    assert counter.stamped_at is not None
    assert counter.stamped_at == event.meta.occurred_at


def test_model_event_requires_apply_override(command_context):
    # Raises inside apply() before dispatch, so no transaction is needed.
    class NoApply(CounterEvent):
        pass

    with pytest.raises(NotImplementedError):
        eventcore.apply_event(Counter(), NoApply())


def test_apply_event_outside_command_context_raises():
    # Run in a fresh contextvars.Context (no active meta) to simulate calling
    # apply_event outside a command invocation.
    ctx = contextvars.Context()
    with pytest.raises(RuntimeError):
        ctx.run(eventcore.apply_event, Counter(), Incremented())


@pytest.mark.django_db
def test_apply_event_dispatches_to_subscriber_after_commit(
    command_context, django_capture_on_commit_callbacks
):
    received: list[Event] = []
    eventcore.on(Incremented, received.append)

    with django_capture_on_commit_callbacks(execute=True):
        eventcore.apply_event(Counter(), Incremented(by=5))
        assert received == []  # deferred until commit

    assert len(received) == 1
    assert received[0].model.value == 5


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
class Add(Command):
    a: int
    b: int

    def perform(self) -> int:
        return self.a + self.b


@pytest.mark.django_db
def test_command_invoke_runs_perform():
    assert eventcore.invoke(Add(a=4, b=5)) == 9


def test_command_validates_payload():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Add(a="not-an-int", b=1)


@pytest.mark.django_db
def test_command_error_formats_lazily():
    class Failing(Command):
        class NotFound(CommandError): ...

        def perform(self):
            raise self.NotFound("Item %s not found", 42)

    assert issubclass(Failing.NotFound, CommandError)
    with pytest.raises(Failing.NotFound) as exc_info:
        eventcore.invoke(Failing())
    assert "Item 42 not found" in str(exc_info.value)


@pytest.mark.django_db
def test_base_perform_raises_not_implemented():
    class Bare(Command): ...

    with pytest.raises(NotImplementedError):
        eventcore.invoke(Bare())


@pytest.mark.django_db
def test_invoke_wraps_perform_in_a_transaction():
    captured: dict[str, bool] = {}

    class Touch(Command):
        def perform(self) -> None:
            captured["in_atomic"] = transaction.get_connection().in_atomic_block

    eventcore.invoke(Touch())

    assert captured["in_atomic"] is True


@pytest.mark.django_db
def test_command_cannot_invoke_another_command_from_perform():
    class Inner(Command):
        def perform(self) -> str:
            return "inner"

    class Outer(Command):
        def perform(self):
            return eventcore.invoke(Inner())

    with pytest.raises(eventcore.NestedCommandError):
        eventcore.invoke(Outer())


@pytest.mark.django_db
def test_invoke_notifies_command_subscribers_after_commit(django_capture_on_commit_callbacks):
    received: list[Command] = []
    eventcore.on(Command, received.append)

    with django_capture_on_commit_callbacks(execute=True):
        assert eventcore.invoke(Add(a=1, b=2)) == 3
        assert received == []  # deferred until commit

    assert len(received) == 1
    assert isinstance(received[0], Add)


@pytest.mark.django_db
def test_invoke_shares_correlation_id_between_command_and_events(
    django_capture_on_commit_callbacks,
):
    seen: list[object] = []
    eventcore.on(Command, seen.append)
    eventcore.on(Event, seen.append)

    class Bump(Command):
        def perform(self) -> None:
            eventcore.apply_event(Counter(), Incremented())
            return self

    with django_capture_on_commit_callbacks(execute=True):
        command = eventcore.invoke(Bump())

    correlation_ids = {
        command.correlation_id,
        *(m.meta.correlation_id for m in seen if isinstance(m, Event)),
    }
    assert command.correlation_id is not None
    assert len(correlation_ids) == 1  # command and its event share one id


# --------------------------------------------------------------------------- #
# Registries / introspection
# --------------------------------------------------------------------------- #
def test_registered_commands_lists_subclasses():
    names = {c.__name__ for c in eventcore.registered_commands()}
    assert "Add" in names


def test_registered_events_lists_concrete_events_only():
    names = {e.__name__ for e in eventcore.registered_events()}
    assert {"Incremented", "Stamped"} <= names
    assert "Event" not in names  # framework bases excluded
    assert "ModelEvent" not in names
