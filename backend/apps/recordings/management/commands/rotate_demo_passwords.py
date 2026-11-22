"""Reemplaza la clave de todas las cuentas de demo por una aleatoria y la imprime una sola vez.

    manage.py rotate_demo_passwords

Las cuentas de demo (``@localhost``) tienen claves conocidas («test»). Antes de exponer la app
fuera de la máquina (túnel público) hay que rotarlas. Las claves nuevas no se guardan en ningún
lado: solo se muestran aquí.
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

DEMO_DOMAIN = "@localhost"


class Command(BaseCommand):
    help = "Pone una clave aleatoria a cada cuenta @localhost y la imprime una sola vez."

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(email__iendswith=DEMO_DOMAIN).order_by("id")
        for user in users:
            password = secrets.token_urlsafe(12)
            user.set_password(password)
            user.save(update_fields=["password"])
            self.stdout.write(f"  {user.email}  {password}")
        self.stdout.write(self.style.SUCCESS(f"{users.count()} cuentas rotadas."))
