"""Delete redundant Translation rows and stale SourceStrings."""

from django.core.management.base import BaseCommand

from dbi18n.pofiles import prune


class Command(BaseCommand):
    help = (
        "Delete Translation rows whose value equals the committed .po/.mo value "
        "(redundant overrides) and SourceStrings marked stale. Typically run on a "
        "live environment after translations have been exported and committed."
    )

    def handle(self, **options):
        prune(stdout=self.stdout)
