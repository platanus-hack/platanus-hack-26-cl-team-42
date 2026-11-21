from typing import ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CharField, EmailField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.clinical_templates.models import ClinicalTemplate

from .managers import UserManager


class User(AbstractUser):
    """
    Custom user model with email as the primary identifier.
    If adding fields that need to be filled at user signup,
    check forms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    # Tipo de profesional de la cuenta: decide la plantilla clínica de sus dictados.
    profession = CharField(
        _("Professional type"),
        max_length=32,
        choices=ClinicalTemplate.Profession.choices,
        blank=True,
    )
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})


class Shift(models.Model):
    """Turno de trabajo de un profesional: mientras dura, está de turno y puede participar."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shifts"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self) -> str:
        return f"Turno de {self.user_id}: {self.starts_at:%d-%m %H:%M} a {self.ends_at:%d-%m %H:%M}"
