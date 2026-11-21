"""Event policies for the demo app.

A *policy* is a rule that reacts to a domain event: when an event is applied,
the policy runs to trigger follow-up actions or side effects — without the
command that applied the event knowing it exists, and (by default) only after
the surrounding transaction commits.

The single policy here logs each order lifecycle event — a stand-in for a real
side effect such as a notification or webhook. It deliberately does *not*
persist an audit trail: durable logging of every command and event is provided
by the optional ``eventcore.app`` (its ``LogRecord`` model), so the demo does
not reimplement it.

Policies are wired to their events in ``apps.py`` ``ready()``.
"""

from __future__ import annotations

import logging

from .events import OrderEvent

logger = logging.getLogger(__name__)


def announce_order_event(event: OrderEvent) -> None:
    """Policy: log a line for any event applied to an order."""
    order = event.model
    logger.info(
        "Order #%s: %s [correlation=%s]",
        order.pk,
        type(event).__name__,
        event.meta.correlation_id,
    )
