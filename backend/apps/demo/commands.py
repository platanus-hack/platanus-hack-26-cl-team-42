"""Commands driving the demo ``Order`` aggregate.

Commands are the only write path for orders: they validate business rules
(failing with domain-specific ``CommandError`` subclasses), apply events,
and persist. Running one through ``eventcore.invoke()`` wraps it in
``transaction.atomic()``, so subscriber side effects dispatch only after the
transition commits.
"""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from eventcore import Command, CommandError, apply_event

from .events import OrderCancelled, OrderPlaced, OrderShipped
from .models import Order

#: Carriers the demo "store" can ship with — a stand-in for real
#: per-tenant configuration.
SUPPORTED_CARRIERS = ("ups", "fedex", "dhl")


class PlaceOrder(Command):
    customer_name: str
    item: str

    def perform(self) -> Order:
        order = Order()
        apply_event(order, OrderPlaced(customer_name=self.customer_name, item=self.item))
        order.save()
        return order


class ShipOrder(Command):
    order_id: int
    carrier_name: str

    class OrderNotFound(CommandError): ...

    class CarrierNotSupported(CommandError): ...

    class NotPending(CommandError): ...

    def perform(self) -> Order:
        try:
            order = Order.objects.get(pk=self.order_id)
        except Order.DoesNotExist:
            raise self.OrderNotFound(
                # Pre-format with a named placeholder so the (lazy) message stays
                # translatable per request and translators can reorder it.
                _("Order %(order_id)s not found") % {"order_id": self.order_id}
            ) from None

        if self.carrier_name not in SUPPORTED_CARRIERS:
            raise self.CarrierNotSupported(
                _("Carrier %(carrier)s is not supported") % {"carrier": self.carrier_name}
            )

        if order.status != Order.Status.PENDING:
            raise self.NotPending(
                _("Order %(order_id)s is %(status)s; only pending orders can be shipped")
                % {"order_id": self.order_id, "status": order.get_status_display()}
            )

        apply_event(order, OrderShipped(carrier_name=self.carrier_name))
        order.save()
        return order


class CancelOrder(Command):
    order_id: int
    reason: str = ""

    class OrderNotFound(CommandError): ...

    class NotPending(CommandError): ...

    def perform(self) -> Order:
        try:
            order = Order.objects.get(pk=self.order_id)
        except Order.DoesNotExist:
            raise self.OrderNotFound(
                _("Order %(order_id)s not found") % {"order_id": self.order_id}
            ) from None

        if order.status != Order.Status.PENDING:
            raise self.NotPending(
                _("Order %(order_id)s is %(status)s; only pending orders can be cancelled")
                % {"order_id": self.order_id, "status": order.get_status_display()}
            )

        apply_event(order, OrderCancelled(reason=self.reason))
        order.save()
        return order
