"""Demo models showcasing the eventcore command/event flow.

``Order`` is the evented aggregate: its state transitions happen through
events applied by commands (see ``events.py`` / ``commands.py``), mirroring
the example in ``lib/eventcore/README.md``.

The audit trail of every command and event is provided by the optional
``eventcore.app`` (its ``LogRecord`` model), so the demo does not define its
own — see the policy in ``policies.py`` for how a side effect attaches to
events without coupling.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Order(models.Model):
    """A demo purchase order, mutated exclusively through eventcore events."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SHIPPED = "shipped", _("Shipped")
        CANCELLED = "cancelled", _("Cancelled")

    customer_name = models.CharField(max_length=255)
    item = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    carrier_name = models.CharField(max_length=50, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Order #{self.pk}: {self.item} for {self.customer_name} ({self.status})"
