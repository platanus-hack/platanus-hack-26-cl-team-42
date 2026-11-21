"""Export active Translation rows to a ``messages.tar.gz``."""

from pathlib import Path

from django.core.management.base import BaseCommand

from dbi18n.pofiles import export_to_tarball


class Command(BaseCommand):
    help = (
        "Pack active Translation rows into messages.tar.gz "
        "(locale/<lang>/LC_MESSAGES/django.po per language). "
        "Transfer the tarball to a developer who runs i18n_import to merge "
        "the translations into the committed .po files."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            default="messages.tar.gz",
            help="Output path for the tarball (default: messages.tar.gz)",
        )

    def handle(self, output, **options):
        export_to_tarball(Path(output), stdout=self.stdout)
