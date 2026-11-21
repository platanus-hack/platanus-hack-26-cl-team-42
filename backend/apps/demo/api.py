"""Django Ninja API for the eventcore demo — read-only queries.

Write operations (PlaceOrder, ShipOrder, CancelOrder) are now handled by the
generic command API at ``/-/api/commands/``.

Mounted at ``/demo`` on the shared Ninja API (see ``conf/urls.py``), so
full paths are ``/-/api/demo/orders`` etc.
"""

from __future__ import annotations

from typing import Any

from ninja import ModelSchema, Router, Schema
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from eventcore import ModelEvent, registered_commands, registered_events
from eventcore.app.models import LogRecord

from .models import Order

router = Router(tags=["eventcore demo"])

# =============================================================================
# Schemas
# =============================================================================


class OrderOut(ModelSchema):
    # Localized status label (e.g. "Pendiente"), resolved for the request's
    # active language via the dbi18n catalog — see resolve_status_display.
    status_display: str

    class Meta:
        model = Order
        fields = [
            "id",
            "customer_name",
            "item",
            "status",
            "carrier_name",
            "cancel_reason",
            "created_at",
            "shipped_at",
            "cancelled_at",
        ]

    @staticmethod
    def resolve_status_display(obj: Order) -> str:
        # str() evaluates the lazy translation under the active language.
        return str(obj.get_status_display())


class OrderStatusOut(Schema):
    """A status choice with its machine value and localized label."""

    value: str
    label: str


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/orders", response=list[OrderOut])
def list_orders(request):
    """List demo orders, newest first."""
    return Order.objects.all()


@router.get("/order-statuses", response=list[OrderStatusOut])
def list_order_statuses(request):
    """The order statuses with labels localized to the request's language.

    A tiny showcase of database-backed i18n (see lib/dbi18n): the labels come
    from ``gettext`` and are translated per ``Accept-Language`` — try it with
    the language selector on the demo page.
    """
    return [
        OrderStatusOut(value=value, label=str(label)) for value, label in Order.Status.choices
    ]


@router.get("/carriers", response=list[str])
def list_carriers(request):
    """Carriers accepted by the ``ShipOrder`` command."""
    from .commands import SUPPORTED_CARRIERS

    return list(SUPPORTED_CARRIERS)


# =============================================================================
# Eventcore catalog & log — backed by the eventcore registries and the
# ``eventcore.app`` LogRecord model, independent of the Order demo above.
# =============================================================================


class FieldOut(Schema):
    """A single pydantic field of a command or event."""

    name: str
    type: str
    required: bool
    default: Any | None = None


class CommandOut(Schema):
    name: str
    doc: str
    fields: list[FieldOut]
    errors: list[str]


class EventTypeOut(Schema):
    name: str
    doc: str
    target_model: str | None = None
    fields: list[FieldOut]


class LogRecordOut(ModelSchema):
    class Meta:
        model = LogRecord
        fields = ["id", "kind", "name", "correlation_id", "payload", "created_at"]


def _type_name(annotation: Any) -> str:
    """Render a field annotation as a short, human-readable type name."""
    if annotation is None:
        return "None"
    name = getattr(annotation, "__name__", None)
    if name:
        return name
    return str(annotation).replace("typing.", "")


def _field_default(field: FieldInfo) -> Any | None:
    if field.is_required() or field.default is PydanticUndefined:
        return None
    return field.default


def _fields(model_cls: type) -> list[FieldOut]:
    return [
        FieldOut(
            name=name,
            type=_type_name(field.annotation),
            required=field.is_required(),
            default=_field_default(field),
        )
        for name, field in model_cls.model_fields.items()
    ]


def _command_errors(command_cls: type) -> list[str]:
    from eventcore import CommandError

    return sorted(
        attr.__name__
        for attr in vars(command_cls).values()
        if isinstance(attr, type) and issubclass(attr, CommandError)
    )


def _event_target_model(event_cls: type) -> str | None:
    """Best-effort name of the model a ``ModelEvent[M]`` subclass targets."""
    for base in event_cls.__mro__:
        meta = getattr(base, "__pydantic_generic_metadata__", None)
        if meta and meta.get("origin") is ModelEvent and meta.get("args"):
            arg = meta["args"][0]
            return getattr(arg, "__name__", str(arg))
    return None


@router.get("/commands", response=list[CommandOut])
def list_commands(request):
    """Catalog of registered eventcore commands and their payloads."""
    return [
        CommandOut(
            name=command.__name__,
            doc=(command.__doc__ or "").strip(),
            fields=_fields(command),
            errors=_command_errors(command),
        )
        for command in registered_commands()
    ]


@router.get("/event-types", response=list[EventTypeOut])
def list_event_types(request):
    """Catalog of registered eventcore event types and their payloads."""
    return [
        EventTypeOut(
            name=event.__name__,
            doc=(event.__doc__ or "").strip(),
            target_model=_event_target_model(event),
            fields=_fields(event),
        )
        for event in registered_events()
    ]


@router.get("/log", response=list[LogRecordOut])
def list_log(request, kind: str | None = None):
    """Eventcore log records (command invocations + applied events), newest first."""
    qs = LogRecord.objects.all()
    if kind is not None:
        qs = qs.filter(kind=kind)
    return qs


# =============================================================================
# Tracker scenario — fan-out / fan-in with a Celery chord.
#
# A chord must be dispatched inside ``track()`` on the client side: the whole
# canvas is stamped at publish time, and the callback that Celery dispatches
# later (from a worker) carries the propagated stamp, joining the same
# tracker. The generic ``POST /tracker/celery-tasks/{name}/run`` endpoint can
# only dispatch a single task, hence this dedicated endpoint.
# =============================================================================


class RebuildIndexOut(Schema):
    tracker_id: str


@router.post("/scenarios/rebuild-index", response=RebuildIndexOut)
def run_rebuild_index_scenario(request, sections: int = 4):
    """Dispatch a chord of index_section tasks with a merge_indexes callback,
    all tracked as one job."""
    from celery import chord
    from tracker import track

    from .tasks import index_section, merge_indexes

    with track("Rebuild search index") as t:
        chord(
            [index_section.s(section_id) for section_id in range(sections)],
            merge_indexes.s(),
        ).delay()

    return RebuildIndexOut(tracker_id=t.tracker_id)
