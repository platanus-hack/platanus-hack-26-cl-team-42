"""Persistence for the eventcore audit trail.

A single :class:`LogRecord` model captures both halves of the eventcore
flow: ``COMMAND`` rows for command invocations and ``EVENT`` rows for applied
events. Rows are written by :mod:`eventcore.app.subscribers`; nothing else
should create them.
"""

from django.db import models


class LogRecord(models.Model):
    """One recorded command invocation or applied event."""

    class Kind(models.TextChoices):
        COMMAND = "command", "Command"
        EVENT = "event", "Event"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    #: The Command/Event subclass name, e.g. ``"PlaceOrder"`` / ``"OrderShipped"``.
    name = models.CharField(max_length=200)
    #: Correlation id shared by a command and the events it applied.
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    #: The pydantic payload, ``model_dump(mode="json")`` of the command/event.
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind}:{self.name}"
