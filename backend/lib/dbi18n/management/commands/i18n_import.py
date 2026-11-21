"""Import a ``messages.tar.gz`` into the first ``LOCALE_PATHS`` entry."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dbi18n.pofiles import import_from_tarball


class Command(BaseCommand):
    help = (
        "Merge a messages.tar.gz (produced by i18n_export) into the first "
        "LOCALE_PATHS entry. Existing entries are clobbered. Run "
        "compilemessages afterwards to compile the updated .po files."
    )

    def add_arguments(self, parser):
        parser.add_argument("tarball", help="Path to messages.tar.gz")

    def handle(self, tarball, **options):
        path = Path(tarball)
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        import_from_tarball(path, stdout=self.stdout)
        self.stdout.write(
            "Done. Run 'just backend compilemessages' (or "
            "'manage.py compilemessages') to compile the updated .po files.\n"
        )
