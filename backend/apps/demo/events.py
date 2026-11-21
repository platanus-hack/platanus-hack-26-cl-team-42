"""Domain events for the demo ``Order`` aggregate.

Each event is the single, named place where a state transition is
expressed. Events mutate the order in ``apply()`` but never persist it —
the calling command decides when to ``save()``.
"""

from __future__ import annotations

from eventcore import ModelEvent

from .models import Order

OrderEvent = ModelEvent[Order]


class OrderPlaced(OrderEvent):
    customer_name: str
    item: str

    def apply(self, model: Order) -> None:
        model.customer_name = self.customer_name
        model.item = self.item
        model.status = Order.Status.PENDING


class OrderShipped(OrderEvent):
    carrier_name: str

    # Read self.meta for occurrence info (occurred_at, actor, correlation_id).
    def apply(self, model: Order) -> None:
        model.status = Order.Status.SHIPPED
        model.carrier_name = self.carrier_name
        model.shipped_at = self.meta.occurred_at


class OrderCancelled(OrderEvent):
    reason: str

    def apply(self, model: Order) -> None:
        model.status = Order.Status.CANCELLED
        model.cancel_reason = self.reason
        model.cancelled_at = self.meta.occurred_at
