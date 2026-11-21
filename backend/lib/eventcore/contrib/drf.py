# ruff: noqa: E402
"""Django REST Framework integration for eventcore commands.

Provides a registry-driven router that exposes one POST endpoint per
registered Command, with request bodies validated via drf-pydantic
serializers generated from each command's pydantic fields.

Intended usage in ``conf/urls.py``::

    from eventcore.contrib.drf import command_urlpatterns

    urlpatterns += [
        path("api/commands/", include((command_urlpatterns(), "commands"))),
    ]

Import-order note
-----------------
``CsrfExemptSessionAuthentication`` must be defined *before* any import
that touches ``rest_framework.views`` or ``rest_framework.schemas``.
Those modules access ``api_settings.DEFAULT_AUTHENTICATION_CLASSES`` at
import time, which causes Django to import this very class by dotted path.
Defining the class first ensures the partially-initialised module already
has the attribute when Django's ``cached_import`` looks it up.
"""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session auth without CSRF enforcement.

    The project disables Django's CSRF middleware globally; DRF's default
    ``SessionAuthentication`` would still call ``enforce_csrf`` on every
    POST, rejecting them. This subclass skips that check so the command API
    (and the browsable-API form POST) work with session cookies.
    """

    def enforce_csrf(self, request) -> None:
        return


# ---------------------------------------------------------------------------
# Remaining imports — safe now that CsrfExemptSessionAuthentication exists
# ---------------------------------------------------------------------------

from typing import Any

import drf_pydantic
from django.db.models import Model
from django.urls import path
from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, ValidationError, create_model
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.views import APIView

from eventcore.commands import CommandError, registered_commands

# ---------------------------------------------------------------------------
# Serializer factory
# ---------------------------------------------------------------------------


def command_serializer(command_cls: type) -> type[Serializer]:
    """Return a drf-pydantic serializer class for *command_cls*.

    We cannot subclass the command itself (that would re-fire
    ``Command.__init_subclass__`` and pollute ``registered_commands()``),
    so we build a fresh ``drf_pydantic.BaseModel`` mirroring the command's
    ``model_fields``, then return its ``.drf_serializer``.

    Each field's ``FieldInfo`` (annotation, default, constraints) is
    forwarded verbatim, so the generated DRF fields stay in sync with the
    real command validation.
    """
    payload_cls = create_model(
        f"{command_cls.__name__}Payload",
        __base__=drf_pydantic.BaseModel,
        __config__=ConfigDict(arbitrary_types_allowed=True),
        **{name: (field.annotation, field) for name, field in command_cls.model_fields.items()},
    )
    return payload_cls.drf_serializer


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def _serialize_result(value: Any) -> Any:
    """Best-effort JSON-safe representation of ``invoke``'s return value."""
    if value is None:
        return None
    if isinstance(value, Model):
        from django.forms.models import model_to_dict

        return model_to_dict(value)
    if isinstance(value, PydanticBaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        return [_serialize_result(item) for item in value]
    return value


# ---------------------------------------------------------------------------
# Introspection helpers (mirrors demo api.py _fields / _command_errors)
# ---------------------------------------------------------------------------


def _field_info(command_cls: type) -> list[dict]:
    from pydantic_core import PydanticUndefined

    result = []
    for name, field in command_cls.model_fields.items():
        annotation = field.annotation
        type_name = (
            getattr(annotation, "__name__", None) or str(annotation).replace("typing.", "")
        )
        required = field.is_required()
        default = None if required or field.default is PydanticUndefined else field.default
        result.append({"name": name, "type": type_name, "required": required, "default": default})
    return result


def _error_names(command_cls: type) -> list[str]:
    return sorted(
        attr.__name__
        for attr in vars(command_cls).values()
        if isinstance(attr, type) and issubclass(attr, CommandError)
    )


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class CommandIndexView(APIView):
    """List every registered command with its fields and possible errors."""

    def get(self, request: Request) -> Response:
        return Response(
            [
                {
                    "name": cmd.__name__,
                    "doc": (cmd.__doc__ or "").strip(),
                    "url": request.build_absolute_uri(cmd.__name__),
                    "fields": _field_info(cmd),
                    "errors": _error_names(cmd),
                }
                for cmd in registered_commands()
            ]
        )


class CommandView(APIView):
    """Submit a specific command.

    ``command_cls`` is bound by ``as_view(command_cls=…)``.

    GET  — describe the command (for the browsable API form).
    POST — validate body, invoke the command, return a result envelope.
    """

    command_cls: type = None  # overridden via as_view(command_cls=SomeCommand)

    def _serializer_class(self) -> type[Serializer]:
        # Cache per command class to avoid regenerating on every request.
        cache_attr = f"_drf_serializer_{self.command_cls.__name__}"
        cached = getattr(CommandView, cache_attr, None)
        if cached is None:
            cached = command_serializer(self.command_cls)
            setattr(CommandView, cache_attr, cached)
        return cached

    def get(self, request: Request) -> Response:
        return Response(
            {
                "name": self.command_cls.__name__,
                "doc": (self.command_cls.__doc__ or "").strip(),
                "fields": _field_info(self.command_cls),
                "errors": _error_names(self.command_cls),
            }
        )

    def post(self, request: Request) -> Response:
        from eventcore.commands import invoke

        serializer = self._serializer_class()(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        try:
            command = self.command_cls(**serializer.validated_data)
        except ValidationError as exc:
            return Response({"detail": exc.errors()}, status=400)

        try:
            result = invoke(command)
        except CommandError as exc:
            error_name = type(exc).__name__
            http_status = 404 if error_name.endswith(("NotFound", "DoesNotExist")) else 409
            return Response({"error": error_name, "detail": str(exc)}, status=http_status)

        return Response(
            {
                "command": self.command_cls.__name__,
                "correlation_id": command.correlation_id,
                "result": _serialize_result(result),
            }
        )


# ---------------------------------------------------------------------------
# URL patterns
# ---------------------------------------------------------------------------


def command_urlpatterns() -> list:
    """Return one URL pattern per registered command, plus an index.

    Call this inside ``include()``::

        path("api/commands/", include((command_urlpatterns(), "commands"))),
    """
    patterns = [
        path("", CommandIndexView.as_view(), name="index"),
    ]
    for cmd in registered_commands():
        patterns.append(
            path(
                cmd.__name__,
                CommandView.as_view(command_cls=cmd),
                name=cmd.__name__,
            )
        )
    return patterns
